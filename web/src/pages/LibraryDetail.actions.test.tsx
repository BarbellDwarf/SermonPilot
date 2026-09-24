import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiMediaItem } from "../api/client";
import type { EditPlan, LibrarySermon } from "../mock/data";
import { LibraryDetail } from "./LibraryDetail";

const mocks = vi.hoisted(() => ({
  detail: vi.fn(),
  media: vi.fn(),
  plan: vi.fn(),
  transcript: vi.fn(),
}));

vi.mock("../api/hooks", () => ({
  useSermonDetail: mocks.detail,
  useSermonMedia: mocks.media,
  useSermonPlan: mocks.plan,
  useSermonTranscript: mocks.transcript,
}));

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
    ? [
        {
          kind: "processed",
          label: "Rendered output",
          available: true,
          content_type: "video/mp4",
          size: 3145728,
        },
      ]
    : [];
  const byKind = Object.fromEntries(items.map((item) => [item.kind, item]));
  return { items, byKind, primary: hasRender ? "processed" : null, audio: null, isLoading: false, error: null, retry: () => {} };
}

function setSermon(status: LibrarySermon["status"], hasRender: boolean, durationSeconds: number | null = null) {
  mocks.detail.mockReturnValue({
    data: {
      sermon: sermon(status),
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
  mocks.plan.mockReturnValue({ plan: plan(), history: [], isLoading: false, error: null, retry: vi.fn() });
  mocks.transcript.mockReturnValue({ data: null, isLoading: false, error: null });
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
});

describe("LibraryDetail state-aware header actions", () => {
  it("hides the legacy push and keeps the re-render actions once a published sermon is opened for editing", async () => {
    const user = userEvent.setup();
    setSermon("processed", true);
    renderDetail();

    expect(screen.getByTestId("sermon-completed")).toBeTruthy();
    await user.click(screen.getByTestId("edit-sermon"));

    expect(screen.queryByRole("button", { name: "Push to SermonAudio" })).toBeNull();
    expect(screen.getByRole("button", { name: /Re-render · Render-only/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Re-render · Render\+upload/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });

  it("keeps the legacy push for a locally rendered sermon that is not published", () => {
    setSermon("rendered", true);
    renderDetail();

    expect(screen.getByRole("button", { name: "Push to SermonAudio" })).toBeTruthy();
  });

  it("passes the detail duration to the review timeline", () => {
    setSermon("rendered", false, 3600);
    renderDetail();

    expect(screen.getByTestId("timeline-track").getAttribute("data-span-sec")).toBe("3600");
  });
});
