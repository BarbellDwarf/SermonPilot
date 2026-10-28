import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ToastHost } from "../components/toast";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Job } from "../mock/data";

const mocks = vi.hoisted(() => ({
  jobsData: vi.fn(),
  jobDetail: vi.fn(),
  cancelJob: vi.fn(),
}));

vi.mock("../api/client", () => ({
  isLive: true,
  writeApi: { cancelJob: mocks.cancelJob },
}));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return {
    ...actual,
    useJobsData: () => mocks.jobsData(),
    useJobDetail: (id: string, enabled: boolean) => mocks.jobDetail(id, enabled),
  };
});

import { Jobs } from "./Jobs";

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
    parameters: null,
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
  isLoading: false,
  error: null as string | null,
};

beforeEach(() => {
  mocks.jobsData.mockReturnValue(jobsData());
  mocks.jobDetail.mockReturnValue(DETAIL);
  mocks.cancelJob.mockResolvedValue({ cancelled: true, job_id: "job-1" });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

function renderJobs() {
  return render(
    <MemoryRouter>
      <Jobs />
      <ToastHost />
    </MemoryRouter>,
  );
}

describe("Jobs rows", () => {
  it("renders one scannable row with sermon name, action, and an always-visible timestamp", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));

    renderJobs();

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

    renderJobs();

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

    renderJobs();

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

    renderJobs();
    fireEvent.click(screen.getByRole("tab", { name: /Failed/ }));

    const row = screen.getByTestId("job-row-job-failed");
    expect(within(row).getByText("FAILED")).toBeTruthy();
    expect(within(row).getByText("Gateway timeout while uploading.")).toBeTruthy();
    expect(within(row).queryByText(/Second line detail/)).toBeNull();
  });

  it("marks restart-interrupted jobs with the INTERRUPTED label", () => {
    mocks.jobsData.mockReturnValue(
      jobsData([], [], [
        job({
          id: "job-interrupted",
          state: "failed",
          error: "Job interrupted by app restart: the app restarted while this job was running.",
        }),
      ]),
    );

    renderJobs();
    fireEvent.click(screen.getByRole("tab", { name: /Failed/ }));

    expect(within(screen.getByTestId("job-row-job-interrupted")).getByText("INTERRUPTED")).toBeTruthy();
  });

  it("reveals description, type, context, id, readable parameters, log, and actions on expansion", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running", progress: 42 })]));

    renderJobs();
    expect(screen.queryByText(/Processing "Sunday Teaching"/)).toBeNull();

    fireEvent.click(screen.getByTestId("job-row-job-1"));

    expect(screen.getByTestId("job-row-job-1").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(/Processing "Sunday Teaching"/)).toBeTruthy();
    expect(screen.getByText("Sermon processing")).toBeTruthy();
    expect(screen.getByText("Sample Speaker · 2026-10-25")).toBeTruthy();
    expect(screen.getByText("job-1")).toBeTruthy();
    expect(screen.getByText("Start: 0:40")).toBeTruthy();
    expect(screen.getByText("End: 49:18")).toBeTruthy();
    expect(screen.getByText("Audio offset: +0.9s")).toBeTruthy();
    expect(screen.getByText("Mode: Render only")).toBeTruthy();
    expect(screen.getByText("Whisper model: base")).toBeTruthy();
    expect(screen.getByText("Dry run: No")).toBeTruthy();
    expect(screen.getByText("21:09 enhancement done")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
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

    const { rerender } = renderJobs();
    fireEvent.click(screen.getByTestId("job-row-job-a"));
    expect(screen.getByTestId("job-row-job-a").getAttribute("aria-expanded")).toBe("true");

    mocks.jobsData.mockReturnValue(jobsData([{ ...first }, { ...second }]));
    rerender(
      <MemoryRouter>
        <Jobs />
        <ToastHost />
      </MemoryRouter>,
    );

    const rows = screen.getAllByTestId(/^job-row-/);
    expect(rows.map((row) => row.getAttribute("data-job-id"))).toEqual(["job-a", "job-b"]);
    expect(screen.getByTestId("job-row-job-a").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("job-row-job-b").getAttribute("aria-expanded")).toBe("false");
  });

  it("still cancels a running job through the confirm dialog", async () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));

    renderJobs();
    fireEvent.click(screen.getByTestId("job-row-job-1"));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Cancel this job?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(mocks.cancelJob).toHaveBeenCalledWith("job-1"));
  });

  it("selects the job id and explains the copy shortcut without a clipboard", () => {
    mocks.jobsData.mockReturnValue(jobsData([job({ id: "job-1", state: "running" })]));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });

    renderJobs();
    fireEvent.click(screen.getByTestId("job-row-job-1"));
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(screen.getByText(/Job ID selected; press Ctrl\/Cmd\+C/)).toBeTruthy();
    expect(window.getSelection()?.toString()).toContain("job-1");
  });
});
