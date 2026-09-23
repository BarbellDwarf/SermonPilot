import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { SermonReview, type DetailsPatch, type TranscriptState } from "./SermonReview";
import { writeApi, ApiError } from "../api/client";
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

const transcriptState: TranscriptState = {
  open: false,
  onToggle: noop,
  loading: false,
  error: null,
  plainText: "",
  totalLength: 0,
  truncated: false,
  timestampsAvailable: false,
  copied: false,
  onCopy: noop,
};

const originalMatchMedia = window.matchMedia;

function setViewportWidth(width: number) {
  window.matchMedia = ((query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query);
    const min = /min-width:\s*(\d+)px/.exec(query);
    const matches = (!max || width <= Number(max[1])) && (!min || width >= Number(min[1]));
    return {
      matches,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  }) as typeof window.matchMedia;
}

function withUnavailablePreviews(source: SermonMediaData): SermonMediaData {
  const items = source.items.map((item) =>
    item.kind.startsWith("snippet_") ? { ...item, available: false, size: null } : item,
  );
  return {
    ...source,
    items,
    byKind: Object.fromEntries(items.map((item) => [item.kind, item])),
  };
}

function withoutPreviews(source: SermonMediaData): SermonMediaData {
  const items = source.items.filter((item) => !item.kind.startsWith("snippet_"));
  return {
    ...source,
    items,
    byKind: Object.fromEntries(items.map((item) => [item.kind, item])),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  window.matchMedia = originalMatchMedia;
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
  it("groups media rows and reveals preview cards behind the disclosure", async () => {
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
    expect(screen.getByTestId("artifact-group-files-media")).toBeTruthy();
    expect(screen.getByTestId("artifact-group-files-transcripts")).toBeTruthy();

    const disclosure = screen.getByTestId("artifacts-disclosure");
    const hidden = document.getElementById("all-files");
    expect(disclosure.textContent).toContain("Show all files");
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
    expect(hidden?.hasAttribute("hidden")).toBe(true);

    await user.click(disclosure);

    expect(disclosure.textContent).toContain("Hide files");
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
    expect(hidden?.hasAttribute("hidden")).toBe(false);
    expect(screen.getByTestId("artifact-group-files-previews")).toBeTruthy();
    expect(screen.getAllByTestId("artifact-preview-row").length).toBe(3);
  });

  it("omits the files disclosure when nothing is hidden", () => {
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={withoutPreviews(media())}
        isLive
        onToast={noop}
      />,
    );

    expect(screen.queryByTestId("artifacts-disclosure")).toBeNull();
  });

  it("renders no preview card when the previews are unavailable, and explains instead", async () => {
    const user = userEvent.setup();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={withUnavailablePreviews(media())}
        isLive
        onToast={noop}
      />,
    );

    await user.click(screen.getByTestId("artifacts-disclosure"));

    expect(screen.queryAllByTestId("artifact-preview-row").length).toBe(0);
    expect(screen.getByTestId("previews-empty").textContent).toContain("Previews appear after a render");
  });

  it("shows exactly one transcript entry point", () => {
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        transcript={transcriptState}
        onToast={noop}
      />,
    );

    expect(screen.getAllByTestId("transcript-entry").length).toBe(1);
    expect(screen.getAllByRole("button", { name: /transcript/i }).length).toBe(1);
    expect(screen.queryByText("Plain-text transcript of the teaching.")).toBeNull();
  });
});

describe("SermonReview mobile layout", () => {
  it("orders the player before the details and files regions on a narrow viewport", () => {
    setViewportWidth(390);
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

    const player = document.getElementById("player-plan");
    const details = document.getElementById("details");
    const files = document.getElementById("files");
    expect(player).toBeTruthy();
    expect(details).toBeTruthy();
    expect(files).toBeTruthy();
    expect(
      player!.compareDocumentPosition(details!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      player!.compareDocumentPosition(files!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("makes the approval row sticky and collapses files and cut adjusts on a narrow viewport", () => {
    setViewportWidth(390);
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

    expect(screen.getByTestId("approval-bar").className).toContain("sticky");
    expect(document.getElementById("files-body")?.hasAttribute("hidden")).toBe(true);
    expect(document.getElementById("history-body")?.hasAttribute("hidden")).toBe(true);

    const adjust = screen.getByTestId("adjust-cuts-disclosure");
    expect(adjust.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("adjust-cuts-summary").textContent).toContain("Start");
  });

  it("pins a compact one-row bar and keeps the secondary actions behind More actions on a narrow viewport", async () => {
    setViewportWidth(390);
    const user = userEvent.setup();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
        onUpload={noop}
      />,
    );

    const bar = screen.getByTestId("approval-bar");
    expect(bar.className).toContain("sticky");
    expect(within(bar).getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reject with notes" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Re-detect" })).toBeNull();
    expect(screen.queryByRole("button", { name: "History" })).toBeNull();

    await user.click(within(bar).getByRole("button", { name: "More actions" }));
    const menu = screen.getByTestId("more-actions");
    for (const name of ["Reject with notes", "Re-detect", "History", "Upload"]) {
      expect(within(menu).getByRole("menuitem", { name })).toBeTruthy();
    }
    expect(within(bar).queryByRole("button", { name: "History" })).toBeNull();
  });

  it("renders a non-sticky status summary above the player on a narrow viewport", () => {
    setViewportWidth(390);
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

    const summary = screen.getByTestId("approval-summary");
    expect(summary.className).not.toContain("sticky");
    expect(summary.textContent).toContain("Pending review");
    expect(summary.textContent).toContain("QA: Pass");

    const player = document.getElementById("player-plan");
    expect(player).toBeTruthy();
    expect(
      summary.compareDocumentPosition(player!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("matches the content padding to the pinned bar height on a narrow viewport", () => {
    setViewportWidth(390);
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

    const bar = screen.getByTestId("approval-bar");
    const content = screen.getByTestId("approval-content");
    expect(bar.style.height).toBe("64px");
    expect(content.style.paddingTop).toBe(bar.style.height);
  });

  it("keeps the desktop full action row and column layout unchanged", () => {
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

    const bar = screen.getByTestId("approval-bar");
    expect(screen.queryByTestId("approval-summary")).toBeNull();
    expect(screen.queryByTestId("more-actions")).toBeNull();
    for (const name of [
      /Approve · Render-only/,
      /Approve · Render\+upload/,
      "Reject with notes",
      "Re-detect",
      "History",
    ]) {
      expect(within(bar).getByRole("button", { name })).toBeTruthy();
    }
    expect(bar.className).toContain("lg:static");

    const content = screen.getByTestId("approval-content");
    expect(content.style.paddingTop).toBe("");
    expect(content.className).toContain("lg:grid-cols-[minmax(0,1fr)_20rem]");

    const player = document.getElementById("player-plan");
    const details = document.getElementById("details");
    const files = document.getElementById("files");
    expect(
      player!.compareDocumentPosition(details!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      player!.compareDocumentPosition(files!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

describe("SermonReview enhancement choice", () => {
  it("defaults the enhancement control to the app config and sends it", async () => {
    const user = userEvent.setup();
    const apply = vi
      .spyOn(writeApi, "applyPlan")
      .mockResolvedValue({ job_id: "j-1", status: "queued" });
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
        enhanceDefault={false}
      />,
    );

    const toggle = screen.getByTestId("apply-enhance-audio") as HTMLInputElement;
    expect(toggle.checked).toBe(false);

    await user.click(screen.getByRole("button", { name: /Approve · Render-only/ }));
    await waitFor(() => expect(apply).toHaveBeenCalled());
    expect(apply.mock.calls[0][1]).toMatchObject({ enhance_audio: false });
  });

  it("sends enhancement on when the configured default is on", async () => {
    const user = userEvent.setup();
    const apply = vi
      .spyOn(writeApi, "applyPlan")
      .mockResolvedValue({ job_id: "j-2", status: "queued" });
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
        enhanceDefault
      />,
    );

    const toggle = screen.getByTestId("apply-enhance-audio") as HTMLInputElement;
    expect(toggle.checked).toBe(true);

    await user.click(screen.getByRole("button", { name: /Approve · Render-only/ }));
    await waitFor(() => expect(apply).toHaveBeenCalled());
    expect(apply.mock.calls[0][1]).toMatchObject({ enhance_audio: true });
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

describe("SermonReview description review", () => {
  it("shows the failure state and retries the description generation", async () => {
    const user = userEvent.setup();
    const regenerate = vi.fn();
    renderReview(
      <SermonReview
        sermon={sermon()}
        description={null}
        descriptionNeedsReview
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
        onRegenerateDescription={regenerate}
      />,
    );

    expect(screen.getByText(/Description generation failed - retry/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Retry generation" }));
    expect(regenerate).toHaveBeenCalledTimes(1);
  });

  it("does not show the retry state when the description is fine", () => {
    renderReview(
      <SermonReview
        sermon={sermon()}
        description="A good description."
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    expect(screen.queryByText(/Description generation failed - retry/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry generation" })).toBeNull();
  });
});

describe("SermonReview upload existing render", () => {
  it("queues the stored render without touching the plan", async () => {
    const user = userEvent.setup();
    const upload = vi
      .spyOn(writeApi, "uploadOnly")
      .mockResolvedValue({ job_id: "j-up", status: "queued" });
    const onToast = vi.fn();
    renderReview(
      <SermonReview
        sermon={sermon({ status: "rendered" })}
        description="A description."
        plan={plan()}
        media={media()}
        isLive
        onToast={onToast}
      />,
    );

    await user.click(screen.getByTestId("upload-existing-render"));

    await waitFor(() =>
      expect(upload).toHaveBeenCalledWith("s-1", { confirm_missing_description: false }),
    );
    expect(onToast).toHaveBeenCalledWith(expect.stringContaining("existing render"));
  });

  it("refuses an empty description, then uploads after explicit confirmation", async () => {
    const user = userEvent.setup();
    const upload = vi
      .spyOn(writeApi, "uploadOnly")
      .mockRejectedValueOnce(
        new ApiError("The description is empty, so uploading would publish a SermonAudio entry without one. Regenerate the description from the transcript, then upload.", 422, {
          code: "missing_description",
          message:
            "The description is empty, so uploading would publish a SermonAudio entry without one. Regenerate the description from the transcript, then upload.",
          can_regenerate: true,
        }),
      )
      .mockResolvedValueOnce({ job_id: "j-up", status: "queued" });
    renderReview(
      <SermonReview
        sermon={sermon({ status: "rendered" })}
        description=""
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    await user.click(screen.getByTestId("upload-existing-render"));

    const confirm = await screen.findByRole("button", { name: "Upload anyway" });
    const dialog = confirm.closest("dialog");
    await waitFor(() => expect(dialog?.hasAttribute("open")).toBe(true));
    expect(dialog?.textContent).toContain("Regenerate the description");

    await user.click(confirm);
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload.mock.calls[1][1]).toMatchObject({ confirm_missing_description: true });
  });

  it("hides the upload action once the teaching is published", () => {
    renderReview(
      <SermonReview
        sermon={sermon({ status: "processed" })}
        description="A description."
        plan={plan()}
        media={media()}
        isLive
        onToast={noop}
      />,
    );

    expect(screen.queryByTestId("upload-existing-render")).toBeNull();
  });

  it("disables the upload action when no render exists", () => {
    const source = media();
    const withoutProcessed = {
      ...source,
      byKind: { ...source.byKind },
    };
    delete withoutProcessed.byKind.processed;
    renderReview(
      <SermonReview
        sermon={sermon({ status: "rendered" })}
        description="A description."
        plan={plan()}
        media={withoutProcessed}
        isLive
        onToast={noop}
      />,
    );

    expect(
      (screen.getByTestId("upload-existing-render") as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
