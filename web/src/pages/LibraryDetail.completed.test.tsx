import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import type { ApiMediaItem } from "../api/client";
import type { EditPlan, LibrarySermon, PlanStatus } from "../mock/data";
import { api } from "../api/client";
import { LibraryDetail } from "./LibraryDetail";

const mocks = vi.hoisted(() => ({
  detail: vi.fn(),
  media: vi.fn(),
  plan: vi.fn(),
  transcript: vi.fn(),
  segments: vi.fn(),
}));

vi.mock("../api/hooks", () => ({
  useSermonDetail: mocks.detail,
  useSermonMedia: mocks.media,
  useSermonPlan: mocks.plan,
  useSermonTranscript: mocks.transcript,
  useTranscriptSegments: mocks.segments,
}));

vi.mock("../api/client", () => ({
  isLive: true,
  mediaStreamUrl: (id: string, kind: string) => `/api/media/sermons/${id}/${kind}`,
  api: { deleteSermon: vi.fn(), updateSermon: vi.fn() },
  writeApi: {
    uploadNow: vi.fn(),
    uploadOnly: vi.fn(),
    applyPlan: vi.fn(),
    refinePlan: vi.fn(),
    reDetectPlan: vi.fn(),
    regenerateDescription: vi.fn(),
  },
}));

vi.mock("../api/useConfigSection", () => ({
  useConfigSection: () => ({ fields: {}, loaded: true, error: null, save: vi.fn() }),
  fieldValue: (_fields: unknown, _path: string, fallback: unknown) => fallback,
}));

function sermon(status: LibrarySermon["status"]): LibrarySermon {
  return {
    id: "s-1",
    title: "Sample Teaching",
    speaker: "Speaker A",
    date: "2026-09-06",
    duration: "42:10",
    series: "Sample Series",
    status,
  };
}

function plan(status: PlanStatus): EditPlan {
  return {
    sermonId: "s-1",
    status,
    revision: 2,
    revisionsTotal: 3,
    confidence: 87,
    qa: "Pass",
    evidence: "Silence gate at both ends.",
    startSec: 8.5,
    endSec: 2512.3,
    offsetSec: 0.4,
    detectionStatus: "ok",
    reasoning: "Teaching starts after the welcome.",
    notes: "Keep only the second class.",
  };
}

function mediaData() {
  const items: ApiMediaItem[] = [
    { kind: "processed", label: "Rendered output", available: true, content_type: "video/mp4", size: 3145728 },
    { kind: "keeper", label: "Keeper", available: true, content_type: "video/mp4", size: 1048576 },
    { kind: "source", label: "Source media", available: true, content_type: "video/mp4", size: 5242880 },
    { kind: "enhanced", label: "Enhanced audio", available: true, content_type: "audio/wav", size: 2097152 },
    { kind: "snippet_start", label: "Start cut", available: true, content_type: "video/mp4", size: 262144 },
    { kind: "transcript", label: "Transcript", available: true, content_type: "text/plain", size: 4096 },
  ];
  return {
    items,
    byKind: Object.fromEntries(items.map((item) => [item.kind, item])),
    primary: "processed",
    audio: "enhanced",
    isLoading: false,
    error: null,
    retry: () => {},
  };
}

function setSermon(status: LibrarySermon["status"], planStatus: PlanStatus) {
  mocks.detail.mockReturnValue({
    data: {
      sermon: sermon(status),
      description: "A sample description.",
      descriptionNeedsReview: false,
      files: [],
      transcriptAvailable: true,
      transcriptLength: 11,
      sermonaudioId: "12345",
      uploadedAt: "2026-09-07 08:30",
      uploadStatus: "success",
      bibleText: "A placeholder passage.",
      scriptureReference: "Sample 1:1",
    },
    isLoading: false,
    error: null,
    retry: vi.fn(),
  });
  mocks.media.mockReturnValue(mediaData());
  mocks.plan.mockReturnValue({
    plan: plan(planStatus),
    history: [plan(planStatus)],
    isLoading: false,
    error: null,
    retry: vi.fn(),
  });
  mocks.transcript.mockReturnValue({
    data: { id: "s-1", transcript: "hello world", truncated: false, total_length: 11 },
    isLoading: false,
    error: null,
  });
  mocks.segments.mockReturnValue({ segments: [], isLoading: false });
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/library/s-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/library/:id" element={<LibraryDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  (api.updateSermon as unknown as Mock).mockResolvedValue({});
});

describe("LibraryDetail completed sermons", () => {
  it("renders the finished view for a published record and hides every editing control", () => {
    setSermon("processed", "pending_review");
    renderDetail();

    expect(screen.getByTestId("sermon-completed")).toBeTruthy();
    expect(screen.getByTestId("completed-player")).toBeTruthy();
    expect(document.querySelector("video")).toBeTruthy();
    for (const id of [
      "detail-title",
      "detail-speaker",
      "detail-series",
      "detail-date",
      "detail-description",
    ]) {
      expect(screen.getByTestId(id)).toBeTruthy();
    }
    expect(screen.getByTestId("detail-scripture").textContent).toContain("Sample 1:1");
    expect(screen.getByTestId("detail-scripture").textContent).toContain("A placeholder passage.");
    expect(screen.getByTestId("completed-publication")).toBeTruthy();
    expect(screen.getByTestId("completed-transcript")).toBeTruthy();
    const files = screen.getByTestId("completed-files");
    expect(within(files).getAllByTestId("completed-file-row").length).toBe(5);
    for (const label of [
      "Rendered output",
      "Keeper",
      "Source media",
      "Enhanced audio",
      "Start cut",
    ]) {
      expect(within(files).getByText(label)).toBeTruthy();
    }
    expect(within(files).queryByText("Transcript")).toBeNull();
    expect(screen.getByTestId("edit-sermon")).toBeTruthy();

    expect(screen.queryByTestId("sermon-review")).toBeNull();
    expect(screen.queryByTestId("timeline-region-keep")).toBeNull();
    expect(screen.queryByTestId("timeline-handle-start")).toBeNull();
    expect(document.querySelector("#cut-start")).toBeNull();
    expect(document.querySelector("#cut-end")).toBeNull();
    expect(document.querySelector("#cut-offset")).toBeNull();
    expect(screen.queryByRole("button", { name: /Re-render/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Approve/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject with notes" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Re-detect" })).toBeNull();
  });

  it("keeps the editing view for a draft awaiting review", () => {
    setSermon("draft", "pending_review");
    renderDetail();

    expect(screen.getByTestId("sermon-review")).toBeTruthy();
    expect(screen.getByTestId("timeline-region-keep")).toBeTruthy();
    expect(document.querySelector("#cut-start")).toBeTruthy();
    expect(document.querySelector("#cut-end")).toBeTruthy();
    expect(document.querySelector("#cut-offset")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Approve · Render-only/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reject with notes" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Re-detect" })).toBeTruthy();

    expect(screen.queryByTestId("sermon-completed")).toBeNull();
    expect(screen.queryByTestId("edit-sermon")).toBeNull();
  });

  it("treats a processed plan as completed even when the record status lags", () => {
    setSermon("rendered", "processed");
    renderDetail();

    expect(screen.getByTestId("sermon-completed")).toBeTruthy();
    expect(screen.queryByTestId("sermon-review")).toBeNull();
  });

  it("switches a published record into editing mode and back again", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();

    await user.click(screen.getByTestId("edit-sermon"));
    expect(screen.getByTestId("sermon-review")).toBeTruthy();
    expect(screen.getByTestId("timeline-region-keep")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Re-render · Render-only/ })).toBeTruthy();
    expect(screen.getByTestId("show-completed-view")).toBeTruthy();

    await user.click(screen.getByTestId("show-completed-view"));
    expect(screen.getByTestId("sermon-completed")).toBeTruthy();
    expect(screen.queryByTestId("sermon-review")).toBeNull();
  });
});

describe("LibraryDetail completed details editing", () => {
  it("issues the same metadata update call from the finished view", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();

    await user.click(screen.getByTestId("edit-details"));
    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Renamed Teaching");
    await user.click(screen.getByRole("button", { name: /Save details/ }));

    await waitFor(() =>
      expect(api.updateSermon).toHaveBeenCalledWith(
        "s-1",
        expect.objectContaining({ title: "Renamed Teaching", series_title: "Sample Series" }),
      ),
    );
    await waitFor(() => {
      expect(screen.getByTestId("details-save-state").textContent).toContain("Saved");
    });
    expect(screen.queryByTestId("sermon-review")).toBeNull();
  });

  it("opens the transcript from the finished view with copy and download affordances", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();

    const section = screen.getByTestId("completed-transcript");
    await user.click(within(section).getByRole("button", { name: "Show transcript" }));

    expect(screen.getByText("hello world")).toBeTruthy();
    expect(within(section).getByRole("button", { name: "Copy" })).toBeTruthy();
    expect(within(section).getByRole("link", { name: "Download" })).toBeTruthy();
  });
});
