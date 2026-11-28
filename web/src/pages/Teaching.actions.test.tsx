import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ToastHost } from "../components/toast";
import { api, writeApi } from "../api/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiMediaItem } from "../api/client";
import type { EditPlan, LibrarySermon } from "../mock/data";
import { Teaching } from "./Teaching";

const mocks = vi.hoisted(() => ({
  detail: vi.fn(),
  media: vi.fn(),
  plan: vi.fn(),
  transcript: vi.fn(),
  jobs: vi.fn(),
}));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return {
    ...actual,
    useSermonDetail: mocks.detail,
    useSermonMedia: mocks.media,
    useSermonPlan: mocks.plan,
    useSermonTranscript: mocks.transcript,
    useJobsData: mocks.jobs,
  };
});

vi.mock("../api/client", () => {
  class ApiError extends Error {
    status: number;
    code?: string;
    constructor(message: string, status = 500, detail?: { code?: string }) {
      super(message);
      this.status = status;
      this.code = detail?.code;
    }
  }
  return {
    isLive: true,
    mediaApi: { waveform: async () => ({ peaks: [], duration: 0 }) },
    ApiError,
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
    edit_status: status === "processed" ? "uploaded" : status === "rendered" ? "pending_review" : status,
    plan_status: status === "draft" ? null : "pending_review",
  };
}

function plan(): EditPlan {
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
    removeSegments: [],
    offsetSec: 0.4,
    detectionStatus: "ok",
    reasoning: "Teaching starts after the welcome.",
    notes: "",
  };
}

function mediaData(hasRender: boolean) {
  const items: ApiMediaItem[] = hasRender
    ? [{ kind: "processed", label: "Rendered output", available: true, content_type: "video/mp4", size: 3145728 }]
    : [];
  const byKind = Object.fromEntries(items.map((item) => [item.kind, item]));
  return { items, byKind, primary: hasRender ? "processed" : null, audio: null, isLoading: false, error: null, retry: () => {} };
}

function setSermon(status: LibrarySermon["status"], hasRender: boolean, durationSeconds: number | null = null, hasPlan = true, overrides: Partial<LibrarySermon> = {}) {
  mocks.detail.mockReturnValue({
    data: {
      sermon: { ...sermon(status), ...overrides },
      durationSeconds,
      description: "A description.",
      descriptionNeedsReview: false,
      files: [],
      transcriptAvailable: false,
      transcriptLength: 0,
    },
    isLoading: false,
    error: null,
    retry: vi.fn(),
  });
  mocks.media.mockReturnValue(mediaData(hasRender));
  mocks.plan.mockReturnValue({ plan: hasPlan ? plan() : undefined, history: [], isLoading: false, error: null, retry: vi.fn() });
  mocks.transcript.mockReturnValue({ data: null, isLoading: false, error: null });
}

function renderDetail(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/teaching/s-1"]}>
        <Routes><Route path="/teaching/:id" element={<Teaching />} /></Routes>
        <ToastHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
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
  vi.mocked(writeApi.applyPlan).mockResolvedValue({ job_id: "job-approve", status: "queued" });
  vi.mocked(writeApi.uploadNow).mockResolvedValue({ job_id: "job-publish", status: "queued" });
  vi.mocked(writeApi.reDetectPlan).mockResolvedValue({ job_id: "job-detect", status: "queued" });
  mocks.jobs.mockReturnValue({ data: { active: [], completed: [], failed: [] }, isLoading: false, error: null, retry: vi.fn() });
});

describe("Teaching lifecycle actions", () => {
  it("keeps published records primary-free while preserving edit and render actions", async () => {
    const user = userEvent.setup();
    setSermon("processed", true);
    renderDetail();

    expect(screen.getByTestId("sermon-completed")).toBeTruthy();
    expect(pagePrimary()).toBeNull();
    await user.click(screen.getByTestId("more-actions-trigger"));
    await user.click(screen.getByTestId("edit-sermon"));

    expect(screen.getByTestId("sermon-review")).toBeTruthy();
    expect(pagePrimary()).toBeNull();
    await user.click(screen.getByTestId("more-actions-trigger"));
    const menu = screen.getByTestId("more-actions");
    expect(within(menu).getByRole("menuitem", { name: "Render only" })).toBeTruthy();
    expect(within(menu).queryByRole("menuitem", { name: "Push to SermonAudio" })).toBeNull();
    expect(within(menu).getByTestId("show-completed-view")).toBeTruthy();
  });

  it("captures the approve job, invalidates workspace queries, and blocks a second approve", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    setSermon("rendered", false);
    renderDetail(client);
    await user.click(screen.getByTestId("approve-primary"));

    await waitFor(() => expect(writeApi.applyPlan).toHaveBeenCalledTimes(1));
    await expect(screen.findByTestId("queued-state")).resolves.toBeTruthy();
    expect(screen.getByTestId("queued-job-link").getAttribute("href")).toBe("/activity/job-approve");
    expect(pagePrimary()).toBeNull();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["sermon-plan", "s-1"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["jobs"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["sermons"] });
  });

  it("restores workspace actions after the queued job leaves the active list", async () => {
    const user = userEvent.setup();
    setSermon("rendered", false);
    renderDetail();
    await user.click(screen.getByTestId("approve-primary"));
    await expect(screen.findByTestId("queued-state")).resolves.toBeTruthy();
    mocks.jobs.mockReturnValue({
      data: {
        active: [],
        completed: [{ id: "job-approve", state: "done" }],
        failed: [],
      },
      isLoading: false,
      error: null,
      retry: vi.fn(),
    });
    await user.click(screen.getByRole("tab", { name: "Transcript" }));
    await expect(pagePrimary()).toBeVisible();
  });

  it("publishes a ready render through uploadNow", async () => {
    const user = userEvent.setup();
    setSermon("rendered", true, null, true, { edit_status: "rendered", plan_status: "draft" });
    renderDetail();
    await expect(pagePrimary()).toHaveTextContent("Publish");
    await user.click(screen.getByTestId("approve-primary"));
    await waitFor(() => expect(writeApi.uploadNow).toHaveBeenCalledWith("s-1"));
    await expect(screen.findByTestId("queued-state")).resolves.toBeTruthy();
  });

  it("passes the source duration to the desktop timeline", () => {
    setSermon("rendered", false, 3600);
    renderDetail();
    expect(screen.getByTestId("timeline-track").getAttribute("data-span-sec")).toBe("3600");
  });

  it("queues detection for a draft with no plan", async () => {
    const user = userEvent.setup();
    setSermon("draft", false, null, false);
    renderDetail();
    await expect(pagePrimary()).toHaveTextContent("Run cut detection");
    await user.click(screen.getByTestId("approve-primary"));
    await waitFor(() => expect(writeApi.reDetectPlan).toHaveBeenCalledWith("s-1"));
    await expect(screen.findByTestId("queued-state")).resolves.toBeTruthy();
  });

  it("defers deletion so Undo cancels the server call", async () => {
    const user = userEvent.setup();
    setSermon("rendered", false);
    renderDetail();
    await user.click(screen.getByTestId("more-actions-trigger"));
    await user.click(within(screen.getByTestId("more-actions")).getByRole("menuitem", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    expect(screen.getByRole("heading", { name: "Teaching deleted" })).toBeTruthy();
    expect(api.deleteSermon).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.queryByRole("heading", { name: "Teaching deleted" })).toBeNull();
  });
});

function pagePrimary() {
  return screen.queryByTestId("approve-primary");
}
