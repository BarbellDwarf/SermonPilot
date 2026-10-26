import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Job, Sermon, ServiceStatus } from "../mock/data";

const mocks = vi.hoisted(() => ({ home: vi.fn() }));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return { ...actual, useHomeData: () => mocks.home() };
});

import { Home } from "./Home";

function service(overrides: Partial<ServiceStatus> = {}): ServiceStatus {
  return { id: "api", label: "API", detail: "Reachable", state: "ok", level: 90, ...overrides };
}

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    type: "sermon_processing",
    title: "Process sermon · Sample Teaching · Speaker A",
    kind: "Process sermon",
    sermon: "Sample Teaching",
    description: 'Processing "Sample Teaching" (Speaker A, 2026-10-25).',
    state: "running",
    created: "Oct 25, 21:07",
    createdAt: "2026-10-25T21:07:00Z",
    finished: null,
    duration: "running",
    progress: 42,
    error: null,
    log: [],
    parameters: null,
    ...overrides,
  };
}

function sermon(overrides: Partial<Sermon> = {}): Sermon {
  return {
    id: "s-1",
    title: "Sample Teaching 3",
    speaker: "Speaker C",
    duration: "41:02",
    status: "ready",
    updated: "Oct 24",
    ...overrides,
  };
}

function homeData(overrides: {
  services?: ServiceStatus[];
  activeJobs?: Job[];
  recentSermons?: Sermon[];
} = {}) {
  return {
    data: {
      services: overrides.services ?? [service()],
      activeJobs: overrides.activeJobs ?? [],
      recentSermons: overrides.recentSermons ?? [],
      upNext: [],
    },
    isLoading: false,
    error: null as string | null,
    retry: vi.fn(),
  };
}

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.home.mockReturnValue(homeData());
});

describe("Home", () => {
  it("offers one primary new-teaching action and compact empty states", () => {
    mocks.home.mockReturnValue(homeData({ services: [] }));
    renderHome();

    expect(screen.getAllByRole("link", { name: "New teaching" })).toHaveLength(1);
    expect(screen.getByText("No services reported")).toBeTruthy();
    expect(screen.getByText("No active jobs")).toBeTruthy();
    expect(screen.getByText("No teachings yet")).toBeTruthy();
    expect(screen.queryByText("Up next")).toBeNull();
  });

  it("shows pipeline health, active jobs, and recent teachings without duplicate sections", () => {
    mocks.home.mockReturnValue(
      homeData({
        services: [service(), service({ id: "db", label: "Database", state: "warn", detail: "Slow query" })],
        activeJobs: [
          job(),
          job({ id: "job-2", state: "queued", title: "Apply edit · Sample Teaching 2 · Speaker B" }),
        ],
        recentSermons: [sermon()],
      }),
    );
    renderHome();

    expect(screen.getByRole("heading", { name: "Pipeline health" })).toBeTruthy();
    expect(screen.getAllByText("Database").length).toBeGreaterThan(0);
    expect(screen.getByText("Slow query")).toBeTruthy();
    expect(screen.getByText("Sample Teaching · Process")).toBeTruthy();
    expect(screen.getByText("RUNNING")).toBeTruthy();
    expect(screen.getByText("QUEUED")).toBeTruthy();
    expect(screen.getByText("Recent teachings")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sample Teaching 3 by Speaker C, Processed" })).toBeTruthy();
    expect(screen.queryByText("Up next")).toBeNull();
    expect(screen.getAllByRole("link", { name: "New teaching" })).toHaveLength(1);
  });
});
