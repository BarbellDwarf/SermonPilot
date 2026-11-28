import { createElement, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fmtStamp, toJob, useActivityJobs, useJobDetail } from "./hooks";
import type { ApiJob } from "./client";

const apiMocks = vi.hoisted(() => ({
  jobs: vi.fn(),
  job: vi.fn(),
}));

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return {
    ...actual,
    isLive: true,
    api: {
      ...actual.api,
      jobs: apiMocks.jobs,
      job: apiMocks.job,
    },
  };
});

const base: ApiJob = {
  id: "job-1",
  type: "sermon_processing",
  title: "Process sermon · Sample Teaching · Sample Speaker",
  description: 'Running the processing pipeline for "Sample Teaching" (Sample Speaker, 2026-01-01).',
  status: "queued",
  progress: 12.5,
  created_at: "2026-01-01 09:00:00",
  completed_at: null,
  duration: "—",
  error: null,
};

function jsonResponse(body: unknown, status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    clone() {
      return this;
    },
  } as unknown as Response;
}

function queryWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children);
  };
}

beforeEach(() => {
  apiMocks.jobs.mockResolvedValue({ items: [], total: 0 });
  apiMocks.job.mockResolvedValue({
    ...base,
    status: "running",
    logs: [],
    parameters: {},
    result: null,
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
  vi.clearAllMocks();
});

describe("toJob", () => {
  it("uses the human job label as the console headline and detail line", () => {
    const job = toJob(base);
    expect(job.kind).toBe(base.title);
    expect(job.sermon).toBe(base.description);
    expect(job.state).toBe("queued");
    expect(job.progress).toBe(12.5);
    expect(job.createdAt).toBe(base.created_at);
    expect(job.created).toContain("Jan 1");
  });

  it("falls back to the job type when a label is missing", () => {
    const job = toJob({ ...base, title: "", description: null });
    expect(job.kind).toBe("sermon_processing");
    expect(job.sermon).toBe("sermon_processing");
  });

  it("keeps interrupted as a distinct state", () => {
    expect(toJob({ ...base, status: "interrupted" }).state).toBe("interrupted");
  });
});

describe("fmtStamp", () => {
  it("treats a naive database timestamp as UTC and shows the browser zone", () => {
    expect(fmtStamp("2026-10-27 23:30:00", "America/New_York")).toBe("Oct 27, 19:30");
    expect(fmtStamp("2026-10-27 23:30:00", "Asia/Tokyo")).toBe("Oct 28, 08:30");
  });

  it("keeps an explicit offset as the instant it names", () => {
    expect(fmtStamp("2026-10-27T23:30:00Z", "America/New_York")).toBe("Oct 27, 19:30");
    expect(fmtStamp("2026-10-28T08:30:00+09:00", "America/New_York")).toBe("Oct 27, 19:30");
  });

  it("does not shift a date-only recorded date", () => {
    expect(fmtStamp("2026-10-27", "America/New_York")).toBe("Oct 27, 2026");
    expect(fmtStamp("2026-10-27", "Asia/Tokyo")).toBe("Oct 27, 2026");
  });

  it("crosses a DST boundary without showing the wrong day", () => {
    expect(fmtStamp("2026-03-08 06:30:00", "America/New_York")).toBe("Mar 8, 01:30");
    expect(fmtStamp("2026-03-08 07:30:00", "America/New_York")).toBe("Mar 8, 03:30");
    expect(fmtStamp("2026-11-01 03:30:00", "America/New_York")).toBe("Oct 31, 23:30");
  });
});

describe("jobs API contract", () => {
  it("posts one retry request and returns the new job id", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ job_id: "job-2", status: "queued" }, 202),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_MODE", "live");
    vi.resetModules();
    const { writeApi } = await vi.importActual<typeof import("./client")>("./client");

    await expect(writeApi.retryJob("job-1")).resolves.toEqual({
      job_id: "job-2",
      status: "queued",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/jobs/job-1/retry");
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("POST");
  });

  it("sends status, limit, and offset to the jobs list", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ items: [], total: 125 }, 200),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_MODE", "live");
    vi.resetModules();
    const { api } = await vi.importActual<typeof import("./client")>("./client");

    await expect(api.jobs({ status: "failed", limit: 50, offset: 100 })).resolves.toEqual({
      items: [],
      total: 125,
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/jobs?status=failed&limit=50&offset=100");
  });
});

describe("useActivityJobs", () => {
  it("uses the filtered total and requests the next offset", async () => {
    apiMocks.jobs.mockImplementation(async (params: { status?: string; offset?: number }) => ({
      items: params.status === "failed" && params.offset === 0 ? [base] : [],
      total: params.status === "failed" ? 125 : 0,
    }));

    const { result } = renderHook(() => useActivityJobs("failed"), {
      wrapper: queryWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(apiMocks.jobs).toHaveBeenCalledWith({ status: "failed", limit: 50, offset: 0 });
    expect(result.current.total).toBe(125);
    expect(result.current.counts.failed).toBe(125);
    expect(result.current.pageCount).toBe(3);

    act(() => result.current.nextPage());
    await waitFor(() =>
      expect(apiMocks.jobs).toHaveBeenCalledWith({ status: "failed", limit: 50, offset: 50 }),
    );
    expect(result.current.page).toBe(1);
  });

  it("ranks restart-marked failures with interrupted jobs", async () => {
    const jobs: ApiJob[] = [
      {
        ...base,
        id: "plain-failed",
        status: "failed",
        error: "Gateway timeout",
        created_at: "2026-01-01T12:00:03Z",
      },
      {
        ...base,
        id: "restart-failed",
        status: "failed",
        error: "Job interrupted by app restart: the worker no longer exists.",
        created_at: "2026-01-01T12:00:01Z",
      },
      {
        ...base,
        id: "cancelled",
        status: "cancelled",
        error: "Job cancelled by user",
        created_at: "2026-01-01T12:00:02Z",
      },
    ];
    apiMocks.jobs.mockImplementation(async (params: { status?: string }) => ({
      items: params.status ? [] : jobs,
      total: params.status ? 0 : jobs.length,
    }));

    const { result } = renderHook(() => useActivityJobs("all"), {
      wrapper: queryWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.jobs.map((job) => job.id)).toEqual([
      "restart-failed",
      "plain-failed",
      "cancelled",
    ]);
  });

  it("clamps the page and requests the first page when the total shrinks", async () => {
    let total = 125;
    apiMocks.jobs.mockImplementation(async (params: { status?: string }) => ({
      items: [],
      total: params.status === "failed" ? total : 0,
    }));

    const { result } = renderHook(() => useActivityJobs("failed"), {
      wrapper: queryWrapper(),
    });

    await waitFor(() => expect(result.current.pageCount).toBe(3));
    act(() => result.current.nextPage());
    await waitFor(() => expect(result.current.page).toBe(1));
    act(() => result.current.nextPage());
    await waitFor(() => expect(result.current.page).toBe(2));
    await waitFor(() =>
      expect(apiMocks.jobs).toHaveBeenCalledWith({ status: "failed", limit: 50, offset: 100 }),
    );

    apiMocks.jobs.mockClear();
    total = 10;
    act(() => result.current.retry());

    await waitFor(() => expect(result.current.total).toBe(10));
    await waitFor(() => expect(result.current.page).toBe(0));
    await waitFor(() =>
      expect(apiMocks.jobs).toHaveBeenCalledWith({ status: "failed", limit: 50, offset: 0 }),
    );
    await waitFor(() => expect(result.current.total).toBe(10));
    expect(result.current.pageCount).toBe(1);
  });
});

describe("useJobDetail", () => {
  it("polls every two seconds while open and stops after a terminal response", async () => {
    vi.useFakeTimers();
    apiMocks.job
      .mockResolvedValueOnce({
        ...base,
        status: "running",
        logs: [],
        parameters: {},
        result: null,
      })
      .mockResolvedValueOnce({
        ...base,
        status: "completed",
        logs: ["finished"],
        parameters: {},
        result: null,
      });

    const { result } = renderHook(() => useJobDetail("job-1", true, true), {
      wrapper: queryWrapper(),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe("running");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(apiMocks.job).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("completed");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(apiMocks.job).toHaveBeenCalledTimes(2);
  });
});
