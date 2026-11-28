import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import type { ApiMediaItem } from "../api/client";
import type { EditPlan, LibrarySermon, PlanStatus } from "../mock/data";
import { api, writeApi } from "../api/client";
import { Teaching } from "./Teaching";
import { ToastHost } from "../components/toast";

const mocks = vi.hoisted(() => ({
  detail: vi.fn(),
  media: vi.fn(),
  plan: vi.fn(),
  transcript: vi.fn(),
  segments: vi.fn(),
}));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return {
    ...actual,
    useSermonDetail: mocks.detail,
    useSermonMedia: mocks.media,
    useSermonPlan: mocks.plan,
    useSermonTranscript: mocks.transcript,
    useTranscriptSegments: mocks.segments,
    useJobsData: () => ({ data: { active: [], completed: [], failed: [] }, isLoading: false, error: null, retry: vi.fn() }),
  };
});

vi.mock("../api/client", () => {
  class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
  return {
    ApiError,
    mediaApi: { waveform: async () => ({ peaks: [], duration: 0 }) },
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
      pushMetadata: vi.fn(),
      replaceRecording: vi.fn(),
    },
  };
});

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
    edit_status: status === "processed" ? "uploaded" : status === "rendered" ? "rendered" : status,
    plan_status: null,
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
    removeSegments: [],
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

function setSermon(status: LibrarySermon["status"], planStatus: PlanStatus, overrides: Partial<LibrarySermon> = {}) {
  mocks.detail.mockReturnValue({
    data: {
      sermon: { ...sermon(status), ...overrides },
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
  mocks.plan.mockReturnValue({ plan: plan(planStatus), history: [plan(planStatus)], isLoading: false, error: null, retry: vi.fn() });
  mocks.transcript.mockReturnValue({ data: { id: "s-1", transcript: "hello world", truncated: false, total_length: 11 }, isLoading: false, error: null });
  mocks.segments.mockReturnValue({ segments: [], isLoading: false });
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/teaching/s-1"]}>
        <Routes><Route path="/teaching/:id" element={<Teaching />} /></Routes>
        <ToastHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.matchMedia = ((query: string) => ({
    matches: query.includes("min-width"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  (api.updateSermon as unknown as Mock).mockResolvedValue({});
  (writeApi.pushMetadata as unknown as Mock).mockResolvedValue({ job_id: "job-push", status: "queued", full_push: true });
});

describe("Teaching published body", () => {
  it("uses the shared skeleton with editable details and publication rows", () => {
    setSermon("processed", "pending_review");
    renderDetail();

    expect(screen.getByTestId("teaching-workspace")).toBeTruthy();
    expect(screen.getByTestId("sermon-completed")).toBeTruthy();
    expect(screen.getByTestId("completed-player")).toBeTruthy();
    expect(document.querySelector("video")).toBeTruthy();
    expect(screen.getByLabelText("Title")).toBeVisible();
    expect(screen.getByLabelText("Speaker")).toBeVisible();
    expect(screen.getByTestId("detail-scripture").textContent).toContain("Sample 1:1");
    expect(screen.getByTestId("completed-publication")).toBeTruthy();
    expect(screen.queryByTestId("approve-primary")).toBeNull();
    expect(screen.queryByTestId("timeline")).toBeNull();
  });

  it("keeps media and preview files in the Files tab", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();
    await user.click(screen.getByRole("tab", { name: "Files" }));
    const files = screen.getByTestId("workspace-panel-files");
    expect(within(files).getAllByTestId("artifact-primary-row")).toHaveLength(3);
    expect(within(files).getAllByTestId("artifact-other-row")).toHaveLength(1);
    expect(within(files).getAllByTestId("artifact-preview-row")).toHaveLength(1);
    expect(within(files).queryByText("Transcript")).toBeNull();
  });

  it("keeps the work body for a draft awaiting review", () => {
    setSermon("draft", "pending_review", { edit_status: "pending_review", plan_status: "pending_review" });
    renderDetail();
    expect(screen.getByTestId("sermon-review")).toBeTruthy();
    expect(screen.getByTestId("timeline")).toBeTruthy();
    expect(screen.getByTestId("approve-primary")).toHaveTextContent("Approve & upload");
  });

  it("keeps a rendered record in work mode until its lifecycle is published", () => {
    setSermon("rendered", "processed");
    renderDetail();
    expect(screen.getByTestId("sermon-review")).toBeTruthy();
    expect(screen.queryByTestId("sermon-completed")).toBeNull();
    expect(screen.getByTestId("approve-primary")).toHaveTextContent("Publish");
  });

  it("switches a published record into editing mode and back", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();
    await user.click(screen.getByTestId("more-actions-trigger"));
    await user.click(screen.getByTestId("edit-sermon"));
    expect(screen.getByTestId("sermon-review")).toBeTruthy();
    expect(screen.queryByTestId("approve-primary")).toBeNull();
    await user.click(screen.getByTestId("more-actions-trigger"));
    await user.click(screen.getByTestId("show-completed-view"));
    expect(screen.getByTestId("sermon-completed")).toBeTruthy();
  });
});

describe("Teaching published details and actions", () => {
  it("saves metadata directly from the open Details tab", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();
    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Renamed Teaching");
    await user.click(screen.getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(api.updateSermon).toHaveBeenCalledWith("s-1", expect.objectContaining({ title: "Renamed Teaching", series_title: "Sample Series" })));
    await waitFor(() => expect(screen.getByTestId("details-save-state")).toHaveTextContent("Saved"));
  });

  it("keeps published records primary-free and secondary actions in overflow", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();
    expect(screen.queryByTestId("approve-primary")).toBeNull();
    await user.click(screen.getByTestId("more-actions-trigger"));
    const menu = screen.getByTestId("more-actions");
    for (const name of ["Edit teaching", "Regenerate description", "Push metadata", "Replace recording", "Delete"]) {
      expect(within(menu).getByRole("menuitem", { name })).toBeTruthy();
    }
  });

  it("queues a replacement for the same SermonAudio entry", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    (writeApi.replaceRecording as unknown as Mock).mockResolvedValue({ id: "s-1", job_id: "job-replace", status: "queued", filename: "replacement.mp4" });
    renderDetail();
    await user.click(screen.getByTestId("more-actions-trigger"));
    await user.click(screen.getByTestId("replace-recording"));
    const dialog = screen.getByTestId("replace-recording-dialog");
    const file = new File(["video"], "replacement.mp4", { type: "video/mp4" });
    await user.upload(within(dialog).getByLabelText("New video or audio file"), file);
    await user.click(within(dialog).getByRole("button", { name: "Replace and reprocess" }));
    await waitFor(() => expect(writeApi.replaceRecording).toHaveBeenCalledWith("s-1", file));
    await waitFor(() => expect(screen.getByTestId("queued-state")).toHaveTextContent("job-replace"));
  });

  it("queues a full metadata push from overflow", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();
    await user.click(screen.getByTestId("more-actions-trigger"));
    await user.click(within(screen.getByTestId("more-actions")).getByRole("menuitem", { name: "Push metadata" }));
    await waitFor(() => expect(writeApi.pushMetadata).toHaveBeenCalledWith("s-1", true));
    await waitFor(() => expect(screen.getByTestId("queued-state")).toHaveTextContent("job-push"));
  });

  it("opens the transcript from its tab with copy and download affordances", async () => {
    const user = userEvent.setup();
    setSermon("processed", "pending_review");
    renderDetail();
    await user.click(screen.getByRole("tab", { name: "Transcript" }));
    await user.click(screen.getByRole("button", { name: "Show transcript" }));
    expect(screen.getByText("hello world")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download" })).toBeTruthy();
  });
});
