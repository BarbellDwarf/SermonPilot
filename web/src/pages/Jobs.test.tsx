import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Jobs } from "./Jobs";
import { withProviders } from "../test/harness";
import type { Job } from "../mock/data";

const mocks = vi.hoisted(() => ({ jobs: vi.fn(), detail: vi.fn() }));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return {
    ...actual,
    useJobsData: mocks.jobs,
    useJobDetail: mocks.detail,
  };
});

vi.mock("../api/client", () => ({
  isLive: true,
  writeApi: { cancelJob: vi.fn(), deleteJob: vi.fn() },
}));

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    kind: "Process teaching · Sample Teaching · Sample Speaker",
    sermon: 'Running the processing pipeline for "Sample Teaching".',
    state: "failed",
    created: "Sep 6, 09:00",
    finished: "Sep 6, 09:04",
    duration: "4m",
    log: [],
    error: null,
    ...overrides,
  };
}

function jobsData(items: Job[], isLoading = false) {
  return {
    data: {
      active: items.filter((j) => j.state === "queued" || j.state === "running"),
      completed: items.filter((j) => j.state === "done"),
      failed: items.filter((j) => j.state === "failed"),
      cancelled: items.filter((j) => j.state === "cancelled"),
    },
    isLoading,
    error: null as string | null,
    retry: () => {},
  };
}

describe("Jobs never offers an action that cannot work", () => {
  async function openFailed() {
    mocks.jobs.mockReturnValue(jobsData([job()]));
    mocks.detail.mockReturnValue({ data: null, logs: [], isLoading: false, error: null });
    const user = userEvent.setup();
    withProviders(<Jobs />);
    await user.click(await screen.findByRole("tab", { name: /Failed/ }));
    await waitFor(() => expect(screen.getAllByText(/Process teaching/).length).toBeGreaterThan(0));
    return user;
  }

  it("has no Retry button for a failed job on the live bridge", async () => {
    await openFailed();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.getByText(/cannot re-run a failed job/)).toBeTruthy();
  });

  it("still offers Cancel and Delete on a failed job, which do work", async () => {
    await openFailed();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });

  it("confirms before it deletes a job record", async () => {
    const user = await openFailed();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Delete this job record?")).toBeTruthy();
  });

  it("does not report zero jobs while the list is still loading", () => {
    mocks.jobs.mockReturnValue(jobsData([], true));
    mocks.detail.mockReturnValue({ data: null, logs: [], isLoading: false, error: null });
    withProviders(<Jobs />);

    expect(screen.getByText("Reading the job list…")).toBeTruthy();
    expect(screen.queryByText(/0 active · 0 completed/)).toBeNull();
  });

  it("says the list is empty only after it has loaded and found nothing", async () => {
    mocks.jobs.mockReturnValue(jobsData([]));
    mocks.detail.mockReturnValue({ data: null, logs: [], isLoading: false, error: null });
    withProviders(<Jobs />);

    expect(await screen.findByText("No active jobs")).toBeTruthy();
  });

  it("does not promise a Retry button the live console does not have", async () => {
    mocks.jobs.mockReturnValue(jobsData([]));
    mocks.detail.mockReturnValue({ data: null, logs: [], isLoading: false, error: null });
    const user = userEvent.setup();
    withProviders(<Jobs />);

    await user.click(await screen.findByRole("tab", { name: /Failed/ }));
    expect(await screen.findByText("No failed jobs")).toBeTruthy();
    expect(screen.getByText(/the reason it stopped/).textContent).not.toMatch(/Retry/i);
  });
});

/**
 * The visual pass found the API's failure reason arriving on every failed and
 * cancelled job and never reaching the screen, so an operator saw "failed" with
 * no idea what broke. These pin the reason to the row that has one.
 */
describe("a job row carries the reason it stopped", () => {
  async function openTab(items: Job[], tab: RegExp) {
    mocks.jobs.mockReturnValue(jobsData(items));
    mocks.detail.mockReturnValue({ data: null, logs: [], isLoading: false, error: null });
    const user = userEvent.setup();
    withProviders(<Jobs />);
    await user.click(await screen.findByRole("tab", { name: tab }));
    return user;
  }

  it("shows the recorded reason on a failed job", async () => {
    await openTab(
      [job({ error: "The remote endpoint rejected the upload: 502 Bad Gateway." })],
      /Failed/,
    );
    expect((await screen.findByTestId("job-error")).textContent).toContain("502 Bad Gateway");
  });

  it("shows the recorded reason on a cancelled job, in its own tab", async () => {
    await openTab(
      [
        job({
          state: "cancelled",
          finished: null,
          error: "Stopped by the operator before the upload started.",
        }),
      ],
      /Cancelled/,
    );
    expect((await screen.findByTestId("job-error")).textContent).toContain("before the upload");
  });

  it("does not count a cancelled run as a failure", async () => {
    await openTab([job({ state: "cancelled", error: null })], /Cancelled/);
    await waitFor(() => expect(screen.getAllByText(/0 failed/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/1 cancelled/).length).toBeGreaterThan(0);
  });
});