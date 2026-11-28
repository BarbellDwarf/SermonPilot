import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { clearToasts, ToastHost } from "../components/toast";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { jobActivityState, type Job } from "../mock/data";

const mocks = vi.hoisted(() => ({
  isLive: true,
  jobsData: vi.fn(),
  activityJobs: vi.fn(),
  jobDetail: vi.fn(),
  cancelJob: vi.fn(),
  retryJob: vi.fn(),
}));

vi.mock("../api/client", () => ({
  get isLive() {
    return mocks.isLive;
  },
  mediaApi: { waveform: async () => ({ peaks: [], duration: 0 }) },
  writeApi: { cancelJob: mocks.cancelJob, retryJob: mocks.retryJob },
}));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return {
    ...actual,
    useJobsData: () => mocks.jobsData(),
    useActivityJobs: (state: string) => mocks.activityJobs(state),
    useJobDetail: (id: string, enabled: boolean, poll: boolean) =>
      mocks.jobDetail(id, enabled, poll),
  };
});

import { Activity } from "./Activity";

type ActivityState = "all" | "active" | "completed" | "failed" | "interrupted";

interface ActivityResult {
  jobs: Job[];
  total: number;
  counts: Record<ActivityState, number>;
  isLoading: boolean;
  error: string | null;
  retry: ReturnType<typeof vi.fn>;
  page: number;
  pageCount: number;
  nextPage: ReturnType<typeof vi.fn>;
  previousPage: ReturnType<typeof vi.fn>;
}

function job({ id, state, ...overrides }: Partial<Job> & Pick<Job, "id" | "state">): Job {
  return {
    id,
    kind: "Process + auto-edit · Sunday Teaching · Sample Speaker",
    title: "Process + auto-edit · Sunday Teaching · Sample Speaker",
    type: "sermon_processing",
    sermon: "Sunday Teaching",
    description:
      'Processing "Sunday Teaching" (Sample Speaker, 2026-10-25) and auto-editing the video.',
    state,
    created: "Oct 25, 21:07",
    createdAt: "2026-10-25T21:07:00Z",
    finished: null,
    duration: "running",
    progress: 0,
    error: null,
    log: ["21:07 job accepted"],
    parameters: { sermon_id: "s-1" },
    ...overrides,
  };
}

function jobsData(active: Job[] = [], completed: Job[] = [], failed: Job[] = []) {
  return {
    data: { active, completed, failed },
    isLoading: false,
    error: null as string | null,
    retry: vi.fn(),
  };
}

function activityResult(
  active: Job[] = [],
  completed: Job[] = [],
  failed: Job[] = [],
  overrides: Partial<ActivityResult> = {},
): ActivityResult {
  const jobs = [...active, ...completed, ...failed];
  const interrupted = failed.filter((item) => item.state === "interrupted").length;
  return {
    jobs,
    total: jobs.length,
    counts: {
      all: jobs.length,
      active: active.length,
      completed: completed.length,
      failed: failed.length - interrupted,
      interrupted,
    },
    isLoading: false,
    error: null,
    retry: vi.fn(),
    page: 0,
    pageCount: Math.max(1, Math.ceil(jobs.length / 50)),
    nextPage: vi.fn(),
    previousPage: vi.fn(),
    ...overrides,
  };
}

const DETAIL = {
  logs: ["21:07 job accepted", "21:09 enhancement done"],
  parameters: {
    sermon_id: "s-1",
    start: 40,
    end: 2958,
    audio_offset: 0.9,
    render_only: true,
    form_data: {
      speaker_name: "Sample Speaker",
      recorded_date: "2026-10-25",
      whisper_model: "base",
      dry_run: false,
      api_key: "should-not-render",
    },
    config: { api_key: "should-not-render" },
  },
  status: "running",
  isLoading: false,
  error: null as string | null,
};

function LocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="location">
        {location.pathname}
        {location.search}
      </output>
      <button type="button" onClick={() => navigate(-1)}>
        Go back
      </button>
    </>
  );
}

beforeEach(() => {
  mocks.isLive = true;
  mocks.jobsData.mockReturnValue(jobsData());
  mocks.activityJobs.mockImplementation((state: ActivityState) => {
    const data = mocks.jobsData();
    const all = [...data.data.active, ...data.data.completed, ...data.data.failed];
    const result = activityResult(data.data.active, data.data.completed, data.data.failed);
    return {
      ...result,
      jobs: state === "all" ? all : all.filter((item) => jobActivityState(item) === state),
      total: state === "all" ? all.length : all.filter((item) => jobActivityState(item) === state).length,
    };
  });
  mocks.jobDetail.mockReturnValue(DETAIL);
  mocks.cancelJob.mockResolvedValue({ cancelled: true, job_id: "job-1" });
  mocks.retryJob.mockResolvedValue({ job_id: "job-2000", status: "queued" });
});

afterEach(() => {
  clearToasts();
  vi.useRealTimers();
  vi.clearAllMocks();
});

function renderActivity(initialEntry = "/activity") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/activity" element={<Activity />} />
          <Route path="/activity/:id" element={<Activity />} />
        </Routes>
        <LocationProbe />
        <ToastHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

describe("Activity rows", () => {
  it("renders the Activity heading without a page-header create button", () => {
    renderActivity();

    expect(screen.getByRole("heading", { level: 1, name: "Activity" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "New teaching" })).toBeNull();
  });

  it("renders one scannable row with sermon name, action, and an always-visible timestamp", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));

    renderActivity();

    const row = screen.getByTestId("job-row-job-1");
    expect(within(row).getByText("Sunday Teaching · Process")).toBeTruthy();
    expect(within(row).getByText("Oct 25, 21:07")).toBeTruthy();
    expect(within(row).getByText("RUNNING")).toBeTruthy();
    expect(within(row).queryByText(/Sample Speaker/)).toBeNull();
    expect(within(row).queryByText(/2026-10-25/)).toBeNull();
    expect(row.className).toContain("min-h-[56px]");
    expect(within(row).getByText("Oct 25, 21:07").className).not.toContain("hidden");
  });

  it("derives the short action from the job type and title variant", () => {
    mocks.jobsData.mockReturnValue(
      jobsData([
        job({
          id: "job-edit",
          state: "queued",
          type: "auto_edit_apply",
          title: "Apply edit · Midweek Class · Sample Speaker",
          description: 'Rendering the approved cut for "Midweek Class" (Sample Speaker, 2026-10-24).',
        }),
        job({
          id: "job-upload",
          state: "queued",
          type: "sermon_publish",
          title: "Upload existing render · Sunday Teaching",
          description: 'Uploading the existing render for "Sunday Teaching".',
        }),
        job({
          id: "job-detect",
          state: "queued",
          type: "auto_edit",
          title: "Re-detect cuts · Midweek Class · Sample Speaker",
          description: 'Re-detecting the opening and closing cut for "Midweek Class" (Sample Speaker, 2026-10-24).',
        }),
      ]),
    );

    renderActivity();

    expect(screen.getByText("Midweek Class · Edit")).toBeTruthy();
    expect(screen.getByText("Sunday Teaching · Upload")).toBeTruthy();
    expect(screen.getByText("Midweek Class · Re-detect")).toBeTruthy();
  });

  it("shows percentage and elapsed time on running rows", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-25T21:09:05Z"));
    mocks.jobsData.mockReturnValue(
      jobsData([job({ id: "job-1", state: "running", progress: 42.4 })]),
    );

    renderActivity();

    const bar = screen.getByRole("progressbar", { name: /Progress for Sunday Teaching/i });
    expect(bar.getAttribute("aria-valuenow")).toBe("42");
    expect(screen.getByText(/42%/)).toBeTruthy();
    expect(screen.getByText(/2m 5s/)).toBeTruthy();
  });

  it("shows only the first line of the error on a failed row", () => {
    mocks.jobsData.mockReturnValue(
      jobsData([], [], [
        job({
          id: "job-failed",
          state: "failed",
          error: "Gateway timeout while uploading.\nSecond line detail stays behind expansion.",
        }),
      ]),
    );

    renderActivity();
    fireEvent.click(screen.getByRole("button", { name: /^Failed/ }));

    const row = screen.getByTestId("job-row-job-failed");
    expect(within(row).getByText("FAILED")).toBeTruthy();
    expect(within(row).getByText("Gateway timeout while uploading.")).toBeTruthy();
    expect(within(row).queryByText(/Second line detail/)).toBeNull();
  });

  it("shows the reason on a cancelled row", () => {
    mocks.jobsData.mockReturnValue(
      jobsData([], [], [job({ id: "job-cancelled", state: "cancelled", error: "Job cancelled by user" })]),
    );

    renderActivity();
    fireEvent.click(screen.getByRole("button", { name: /^Failed/ }));

    const row = screen.getByTestId("job-row-job-cancelled");
    expect(within(row).getByText("CANCELLED")).toBeTruthy();
    expect(within(row).getByText("Job cancelled by user")).toBeTruthy();
  });

  it("marks restart-interrupted jobs with the INTERRUPTED label and filter", () => {
    mocks.jobsData.mockReturnValue(
      jobsData([], [], [
        job({
          id: "job-interrupted",
          state: "interrupted",
          error: "Job interrupted by app restart: the app restarted while this job was running.",
        }),
      ]),
    );

    renderActivity();
    fireEvent.click(screen.getByRole("button", { name: /^Interrupted/ }));

    expect(within(screen.getByTestId("job-row-job-interrupted")).getByText("INTERRUPTED")).toBeTruthy();
    expect(screen.getByTestId("location")).toHaveTextContent("/activity?state=interrupted");
  });

  it("reveals description, type, context, id, readable parameters, log, and actions on expansion", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running", progress: 42 })]));

    renderActivity();
    expect(screen.queryByText(/Processing "Sunday Teaching"/)).toBeNull();

    fireEvent.click(screen.getByTestId("job-row-job-1"));

    expect(screen.getByTestId("job-row-job-1").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(/Processing "Sunday Teaching"/)).toBeTruthy();
    expect(screen.getByText("Processing")).toBeTruthy();
    expect(screen.queryByText("Sermon processing")).toBeNull();
    expect(screen.getByText("Sample Speaker · Oct 25, 2026")).toBeTruthy();
    expect(screen.getByText("job-1")).toBeTruthy();
    expect(screen.getByText("Start: 0:40")).toBeTruthy();
    expect(screen.getByText("End: 49:18")).toBeTruthy();
    expect(screen.getByText("Audio offset: +0.9s")).toBeTruthy();
    expect(screen.getByText("Mode: Render only")).toBeTruthy();
    expect(screen.getByText("Whisper model: base")).toBeTruthy();
    expect(screen.getByText("Dry run: No")).toBeTruthy();
    expect(screen.getByText("21:09 enhancement done")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Stop job" })).toBeTruthy();
    expect(screen.queryByText(/should-not-render/)).toBeNull();
  });

  it("keeps order and expansion state when polling returns fresh objects", () => {
    const first = job({ id: "job-a", state: "running", progress: 10 });
    const second = job({
      id: "job-b",
      state: "queued",
      type: "auto_edit_apply",
      title: "Apply edit · Midweek Class · Sample Speaker",
      description: 'Rendering the approved cut for "Midweek Class" (Sample Speaker, 2026-10-24).',
    });
    mocks.jobsData.mockReturnValue(jobsData([first, second]));

    const { rerender, queryClient } = renderActivity();
    fireEvent.click(screen.getByTestId("job-row-job-a"));
    expect(screen.getByTestId("job-row-job-a").getAttribute("aria-expanded")).toBe("true");

    mocks.jobsData.mockReturnValue(jobsData([{ ...first }, { ...second }]));
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/activity"]}>
          <Routes>
            <Route path="/activity" element={<Activity />} />
            <Route path="/activity/:id" element={<Activity />} />
          </Routes>
          <LocationProbe />
          <ToastHost />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const rows = screen.getAllByTestId(/^job-row-/);
    expect(rows.map((row) => row.getAttribute("data-job-id"))).toEqual(["job-a", "job-b"]);
    expect(screen.getByTestId("job-row-job-a").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("job-row-job-b").getAttribute("aria-expanded")).toBe("false");
  });

  it("keeps the log on one scroll axis and wraps long lines", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));

    renderActivity();
    fireEvent.click(screen.getByTestId("job-row-job-1"));

    const log = screen.getByRole("region", { name: "Job log" }).querySelector("div");
    expect(log?.className).toContain("overflow-y-auto");
    expect(log?.className).toContain("overflow-x-hidden");
    expect(log?.querySelector("ol")?.className).toContain("break-words");
  });

  it("selects the job id and explains the copy shortcut without a clipboard", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });

    renderActivity();
    fireEvent.click(screen.getByTestId("job-row-job-1"));
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(screen.getByText(/Job ID selected; press Ctrl\/Cmd\+C/)).toBeTruthy();
    expect(window.getSelection()?.toString()).toContain("job-1");
  });
});

describe("Activity filters and URLs", () => {
  it("uses pressed filter chips and stores the selected state in the URL", () => {
    mocks.jobsData.mockReturnValue(
      jobsData([job({ id: "job-running", state: "running" })], [], [
        job({ id: "job-failed", state: "failed" }),
      ]),
    );

    renderActivity();

    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByRole("button", { name: /^All/ }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /^Failed/ }));
    expect(screen.getByRole("button", { name: /^Failed/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("location")).toHaveTextContent("/activity?state=failed");
    expect(screen.getByTestId("job-row-job-failed")).toBeTruthy();
    expect(screen.queryByTestId("job-row-job-running")).toBeNull();
  });

  it("removes an invalid state value while preserving the job deep link", async () => {
    mocks.jobsData.mockReturnValue(jobsData([], [], [job({ id: "job-failed", state: "failed" })]));

    renderActivity("/activity/job-failed?state=unknown&job=job-failed");

    expect(mocks.activityJobs).toHaveBeenCalledWith("all");
    expect(screen.getByTestId("job-row-job-failed").getAttribute("aria-expanded")).toBe("true");
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/activity/job-failed?job=job-failed",
      ),
    );
  });

  it("opens a route deep link expanded and preserves the filter on back", () => {
    const failed = job({ id: "job-failed", state: "failed" });
    mocks.activityJobs.mockImplementation((state: ActivityState) =>
      activityResult([], [], state === "all" || state === "failed" ? [failed] : []),
    );

    renderActivity("/activity/job-failed?state=failed");

    expect(screen.getByTestId("job-row-job-failed").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("job-detail-job-failed")).toBeTruthy();

    fireEvent.click(screen.getByTestId("job-row-job-failed"));
    expect(screen.getByTestId("location")).toHaveTextContent("/activity?state=failed");
    fireEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.getByTestId("job-row-job-failed").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("location")).toHaveTextContent("/activity/job-failed?state=failed");
  });

  it("opens the job named by the job query parameter", () => {
    mocks.jobsData.mockReturnValue(jobsData([], [], [job({ id: "job-1037", state: "failed" })]));

    renderActivity("/activity?state=failed&job=job-1037");

    expect(screen.getByTestId("job-row-job-1037").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("job-detail-job-1037")).toBeTruthy();
  });

  it("shows the server total beyond the page size and exposes paging", () => {
    const nextPage = vi.fn();
    mocks.activityJobs.mockReturnValue(
      activityResult([job({ id: "job-1", state: "running" })], [], [], {
        total: 125,
        counts: { all: 125, active: 125, completed: 0, failed: 0, interrupted: 0 },
        pageCount: 3,
        nextPage,
      }),
    );

    renderActivity();

    expect(screen.getByText(/1-50 of 125/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(nextPage).toHaveBeenCalledTimes(1);
  });
});

describe("Activity recovery actions", () => {
  it("gives failed and cancelled rows Retry and View teaching without Cancel", () => {
    mocks.activityJobs.mockReturnValue(
      activityResult([], [], [
        job({ id: "job-failed", state: "failed", parameters: { sermon_id: "s-1" } }),
        job({ id: "job-cancelled", state: "cancelled", parameters: { sermon_id: "s-2" } }),
      ]),
    );
    mocks.jobDetail.mockImplementation((id: string) => ({
      ...DETAIL,
      parameters: { ...DETAIL.parameters, sermon_id: id === "job-cancelled" ? "s-2" : "s-1" },
    }));

    renderActivity("/activity?state=failed");

    for (const id of ["job-failed", "job-cancelled"]) {
      const row = screen.getByTestId(`job-row-${id}`);
      const item = row.closest("li") as HTMLLIElement;
      expect(within(item).getByRole("button", { name: "Retry" }).className).toContain("bg-accent");
      expect(within(item).getByRole("link", { name: "View teaching" }).getAttribute("href")).toBe(
        `/teaching/${id === "job-failed" ? "s-1" : "s-2"}`,
      );
      fireEvent.click(row);
      expect(within(item).queryByRole("button", { name: "Cancel" })).toBeNull();
      expect(within(item).queryByRole("button", { name: "Stop job" })).toBeNull();
    }
  });

  it("retries once, invalidates jobs and detail, and expands the new active job", async () => {
    const failed = job({ id: "job-failed", state: "failed", parameters: { sermon_id: "s-1" } });
    const queued = job({
      id: "job-2000",
      state: "queued",
      title: "(Retry) Process + auto-edit · Sunday Teaching · Sample Speaker",
      progress: 0,
      error: null,
    });
    mocks.activityJobs.mockImplementation((state: ActivityState) => {
      if (state === "active") return activityResult([queued]);
      if (state === "failed") return activityResult([], [], [failed]);
      return activityResult([queued], [], [failed]);
    });

    const { queryClient } = renderActivity("/activity?state=failed");
    queryClient.setQueryData(["jobs"], { items: [failed] });
    queryClient.setQueryData(["job", "job-failed"], { status: "failed" });
    queryClient.setQueryData(["job", "job-2000"], { status: "queued" });
    const retry = screen.getByRole("button", { name: "Retry" });
    fireEvent.click(retry);
    fireEvent.click(retry);

    await waitFor(() => expect(mocks.retryJob).toHaveBeenCalledTimes(1));
    expect(mocks.retryJob).toHaveBeenCalledWith("job-failed");
    await waitFor(() =>
      expect(screen.getByTestId("job-row-job-2000").getAttribute("aria-expanded")).toBe("true"),
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/activity/job-2000?state=active");
    expect(screen.getByText(/Retry queued as job job-2000/)).toBeTruthy();
    expect(queryClient.getQueryState(["jobs"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["job", "job-failed"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["job", "job-2000"])?.isInvalidated).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /^Failed/ }));
    expect(screen.getByTestId("job-row-job-failed")).toBeTruthy();
    expect(screen.queryByTestId("job-row-job-2000")).toBeNull();
  });

  it("keeps the failed row and explains a 409 retry rejection", async () => {
    mocks.activityJobs.mockReturnValue(
      activityResult([], [], [job({ id: "job-failed", state: "failed" })]),
    );
    mocks.retryJob.mockRejectedValue(
      Object.assign(new Error("The worker is busy."), { status: 409 }),
    );

    renderActivity("/activity?state=failed");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Job job-failed cannot be retried right now. The worker is busy.",
      ),
    );
    expect(mocks.retryJob).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("location")).toHaveTextContent("/activity?state=failed");
    expect(screen.getByTestId("job-row-job-failed")).toBeTruthy();
  });

  it("stops a running job through matching confirm and toast copy", async () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));

    renderActivity();
    fireEvent.click(screen.getByRole("button", { name: "Stop job" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Stop this job?")).toBeTruthy();
    expect(within(dialog).getByText(/retry the job after it stops/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Stop job" }));

    await waitFor(() => expect(mocks.cancelJob).toHaveBeenCalledWith("job-1"));
    expect(screen.getByText(/Job job-1 stopped.*retry is available/)).toBeTruthy();
  });

  it("retains Delete on completed rows in demo mode", () => {
    mocks.isLive = false;
    mocks.jobsData.mockReturnValue(jobsData([], [job({ id: "job-done", state: "done" })]));

    renderActivity();
    fireEvent.click(screen.getByRole("button", { name: /^Completed/ }));

    const item = screen.getByTestId("job-row-job-done").closest("li") as HTMLLIElement;
    fireEvent.click(within(item).getByRole("button", { name: "Delete" }));
    expect(screen.getByText("Delete this job record?")).toBeTruthy();
  });

  it("places expanded actions above the log", () => {
    mocks.activityJobs.mockReturnValue(
      activityResult([], [], [job({ id: "job-failed", state: "failed" })]),
    );

    renderActivity("/activity/job-failed?state=failed");

    const retry = screen.getByRole("button", { name: "Retry" });
    const log = screen.getByRole("heading", { name: "Log" });
    expect(retry.compareDocumentPosition(log) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("Activity detail polling", () => {
  it("polls an open running job and disables polling when it closes", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));

    renderActivity();
    fireEvent.click(screen.getByTestId("job-row-job-1"));
    expect(mocks.jobDetail).toHaveBeenCalledWith("job-1", true, true);

    fireEvent.click(screen.getByTestId("job-row-job-1"));
    expect(mocks.jobDetail).toHaveBeenLastCalledWith("job-1", false, false);
  });

  it("loads an open terminal job without polling it", () => {
    mocks.activityJobs.mockReturnValue(
      activityResult([], [], [job({ id: "job-failed", state: "failed" })]),
    );

    renderActivity("/activity/job-failed?state=failed");

    expect(mocks.jobDetail).toHaveBeenCalledWith("job-failed", true, false);
  });
});

describe("Activity edge cases and failures", () => {
  it("clamps a 120-character job title and keeps the full text on the tooltip", () => {
    const sermon = "A very long teaching title ".repeat(5).trim();
    mocks.jobsData.mockReturnValue(
      jobsData([
        job({
          id: "job-long",
          state: "running",
          title: `Process sermon · ${sermon} · Sample Speaker`,
          description: `Processing "${sermon}" (Sample Speaker, 2026-10-25).`,
        }),
      ]),
    );
    renderActivity();

    const row = screen.getByTestId("job-row-job-long");
    const title = within(row).getAllByTitle(new RegExp(sermon.slice(0, 20)))[0];
    expect(title.className).toContain("truncate");
    expect(title.getAttribute("title")?.length).toBeGreaterThan(120);
  });

  it("shows server error copy and a working Retry for a failed list", () => {
    const retry = vi.fn();
    mocks.activityJobs.mockReturnValue({
      ...activityResult(),
      error: "Server error (500). Try again in a moment.",
      retry,
    });
    renderActivity();

    expect(screen.getByText("Server error (500). Try again in a moment.")).toBeTruthy();
    expect(screen.queryByText(/API bridge/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
