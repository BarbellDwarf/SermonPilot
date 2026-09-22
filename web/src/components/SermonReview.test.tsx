import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { SermonReview, type DetailsPatch } from "./SermonReview";
import type { SermonMediaData } from "../api/hooks";
import type { ApiMediaItem } from "../api/client";
import type { EditPlan, LibrarySermon } from "../mock/data";

function renderReview(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function plan(overrides: Partial<EditPlan> = {}): EditPlan {
  return {
    sermonId: "s-1",
    status: "pending_review",
    revision: 2,
    revisionsTotal: 3,
    confidence: 87,
    qa: "Pass",
    evidence: "Silence gate at both ends.",
    startSec: 8.5,
    endSec: 2512.3,
    offsetSec: 0.4,
    detectionStatus: "ok",
    reasoning: "Teaching starts after the welcome; Q&A begins after the closing prayer.",
    notes: "",
    ...overrides,
  };
}

function sermon(overrides: Partial<LibrarySermon> = {}): LibrarySermon {
  return {
    id: "s-1",
    title: "Sample Teaching",
    speaker: "Speaker A",
    date: "2026-09-06",
    duration: "42:10",
    series: "Sample Series",
    status: "rendered",
    ...overrides,
  };
}

function media(): SermonMediaData {
  const items: ApiMediaItem[] = [
    {
      kind: "keeper",
      label: "Keeper",
      available: true,
      content_type: "video/mp4",
      size: 1048576,
      start_sec: 8.5,
      end_sec: 2512.3,
    },
    {
      kind: "source",
      label: "Source media",
      available: true,
      content_type: "video/mp4",
      size: 5242880,
    },
    {
      kind: "processed",
      label: "Rendered output",
      available: true,
      content_type: "video/mp4",
      size: 3145728,
    },
    {
      kind: "snippet_start",
      label: "Start cut",
      available: true,
      content_type: "video/mp4",
      size: 262144,
      start_sec: 0,
      end_sec: 18.5,
    },
    {
      kind: "snippet_end",
      label: "End cut",
      available: true,
      content_type: "video/mp4",
      size: 262144,
      start_sec: 2502.3,
      end_sec: 2522.3,
    },
    {
      kind: "snippet_ending",
      label: "Proposed ending",
      available: true,
      content_type: "video/mp4",
      size: 262144,
      start_sec: 2482.3,
      end_sec: 2512.3,
    },
    {
      kind: "enhanced",
      label: "Enhanced audio",
      available: true,
      content_type: "audio/wav",
      size: 2097152,
    },
    {
      kind: "transcript",
      label: "Transcript",
      available: true,
      content_type: "text/plain",
      size: 4096,
    },
  ];
  const byKind = Object.fromEntries(items.map((item) => [item.kind, item]));
  return {
    items,
    byKind,
    primary: "keeper",
    audio: "enhanced",
    isLoading: false,
    error: null,
    retry: () => {},
  };
}

const noop = () => {};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SermonReview single player and plan", () => {
  it("renders exactly one media element with every artifact present", () => {
    renderReview(
      <SermonReview
        sermon={sermon()}
        description="A sample description."
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    expect(document.querySelectorAll("video").length).toBe(1);
    expect(document.querySelectorAll("video, audio").length).toBe(1);
    expect(document.querySelector("video[data-media-kind='keeper']")).toBeTruthy();
  });

  it("derives the three plan regions from the plan seconds", () => {
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    expect(screen.getByTestId("timeline-region-keep")).toBeTruthy();
    expect(screen.getByTestId("timeline-region-cut-before")).toBeTruthy();
    expect(screen.getByTestId("timeline-region-cut-after")).toBeTruthy();
    expect(screen.getByTestId("timeline-region-ending")).toBeTruthy();

    const keep = screen.getByTestId("timeline-region-keep");
    expect(keep.getAttribute("data-start-sec")).toBe("8.5");
    expect(keep.getAttribute("data-end-sec")).toBe("2512.3");
  });

  it("moves the start marker when the start field changes, with no programmatic scrolling", () => {
    const scrollSpy = vi.spyOn(Element.prototype, "scrollIntoView");
    const scrollBefore = window.scrollY;
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    const keep = screen.getByTestId("timeline-region-keep");
    const before = keep.style.left;
    fireEvent.change(screen.getByLabelText(/^Start \(/), { target: { value: "900" } });

    expect(keep.style.left).not.toBe(before);
    expect(screen.getByTestId("timeline-handle-start").getAttribute("aria-valuenow")).toBe("900");
    expect(scrollSpy).not.toHaveBeenCalled();
    expect(window.scrollY).toBe(scrollBefore);
  });

  it("keeps the focused cut input identical and focused when plan state changes", () => {
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    const input = screen.getByLabelText(/^Start \(/) as HTMLInputElement;
    input.focus();
    expect(document.activeElement).toBe(input);

    fireEvent.change(input, { target: { value: "120" } });

    const after = screen.getByLabelText(/^Start \(/) as HTMLInputElement;
    expect(after).toBe(input);
    expect(document.activeElement).toBe(input);
  });

  it("seeks the single player when a region chip is pressed", async () => {
    const user = userEvent.setup();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    const video = document.querySelector("video") as HTMLVideoElement;
    expect(video.currentTime).toBe(0);

    await user.click(screen.getByTestId("region-chip-snippet_end"));
    expect(video.currentTime).toBe(2502.3);
  });
});

describe("SermonReview artifacts", () => {
  it("shows three primary rows and collapses the rest behind the disclosure", async () => {
    const user = userEvent.setup();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    expect(screen.getAllByTestId("artifact-primary-row").length).toBe(3);

    const disclosure = screen.getByTestId("artifacts-disclosure");
    const other = document.getElementById("all-files");
    expect(disclosure.textContent).toContain("Show all files");
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
    expect(other?.hasAttribute("hidden")).toBe(true);

    await user.click(disclosure);

    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
    expect(other?.hasAttribute("hidden")).toBe(false);
    expect(screen.getAllByTestId("artifact-other-row").length).toBe(5);
  });
});

describe("SermonReview details", () => {
  it("saves edited details inline and reports the result", async () => {
    const user = userEvent.setup();
    const onSaveDetails = vi.fn<(patch: DetailsPatch) => Promise<void>>().mockResolvedValue();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description="Original description."
        plan={plan()}
        media={media()}
        isLive
        onSaveDetails={onSaveDetails}
        onToast={noop}
      />,
    );

    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Renamed Teaching");
    await user.click(screen.getByRole("button", { name: /Save details/ }));

    expect(onSaveDetails).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Renamed Teaching" }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("details-save-state").textContent).toContain("Saved");
    });
  });
});

describe("SermonReview refine controls", () => {
  it("shows detection status, reasoning, and each prior note with its revision", async () => {
    const user = userEvent.setup();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        history={[
          plan({ revision: 1, status: "superseded", notes: "Keep only the second class" }),
          plan({ revision: 2, notes: "Trim the announcements" }),
        ]}
        media={media()}
        isLive={false}
        onToast={noop}
      />,
    );

    expect(screen.getByText(/Detection: ok/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "History" }));
    expect(screen.getByText(/Teaching starts after the welcome/)).toBeTruthy();
    expect(screen.getByText("revision 1")).toBeTruthy();
    expect(screen.getByText(/Keep only the second class/)).toBeTruthy();
    expect(screen.getByText("revision 2")).toBeTruthy();
    expect(screen.getByText(/Trim the announcements/)).toBeTruthy();
  });

  it("hides the note history when no revision carries a note", async () => {
    const user = userEvent.setup();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        history={[plan()]}
        media={media()}
        isLive={false}
        onToast={noop}
      />,
    );

    await user.click(screen.getByRole("button", { name: "History" }));
    expect(screen.getByText("No rejection notes yet.")).toBeTruthy();
  });

  it("runs a refine from notes and shows the new revision and note", async () => {
    const user = userEvent.setup();
    const toasts: string[] = [];
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        history={[plan({ revision: 1, status: "superseded", notes: "first note" })]}
        media={media()}
        isLive={false}
        onToast={(m) => toasts.push(m)}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Reject with notes" }));
    const box = screen.getByLabelText("Reject with notes") as HTMLTextAreaElement;
    expect(
      (screen.getByRole("button", { name: /Re-run with notes/ }) as HTMLButtonElement).disabled,
    ).toBe(true);
    await user.type(box, "only the second class");
    await user.click(screen.getByRole("button", { name: /Re-run with notes/ }));

    await waitFor(
      () => {
        expect(screen.getByText(/revision 3 of 3/)).toBeTruthy();
      },
      { timeout: 3000 },
    );
    expect(screen.getAllByText(/only the second class/).length).toBeGreaterThan(0);
    expect(toasts.join(" ")).toContain("Previous revision superseded");
  });

  it("re-detects from scratch without adding a rejection note", async () => {
    const user = userEvent.setup();
    const toasts: string[] = [];
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        history={[plan({ revision: 1, status: "superseded", notes: "first note" })]}
        media={media()}
        isLive={false}
        onToast={(m) => toasts.push(m)}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Re-detect" }));

    await waitFor(
      () => {
        expect(screen.getByText(/revision 3 of 3/)).toBeTruthy();
      },
      { timeout: 3000 },
    );
    expect(screen.queryByText("revision 2")).toBeNull();
    expect(screen.getByText("revision 1")).toBeTruthy();
    expect(toasts.join(" ")).toContain("from scratch");
  });

  it("keeps the refine controls available when detection failed", async () => {
    const user = userEvent.setup();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan({ detectionStatus: "unavailable", confidence: 0 })}
        media={media()}
        isLive={false}
        onToast={noop}
      />,
    );

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Detection: unavailable")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Reject with notes" }));
    expect(screen.getByLabelText("Reject with notes")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Re-detect" })).toBeTruthy();
  });
});
