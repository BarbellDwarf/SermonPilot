import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LibrarySermon, ServiceStatus } from "../mock/data";
import type { InboxData, InboxSection } from "../api/hooks";
import { lifecycleCounts } from "../utils/lifecycle";

const mocks = vi.hoisted(() => ({ inbox: vi.fn() }));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return { ...actual, useInboxData: () => mocks.inbox() };
});

vi.mock("../api/client", () => ({
  isLive: false,
  api: {},
  filesApi: {},
  mediaApi: {},
  mediaStreamUrl: (id: string, kind: string) => `/api/media/${id}/${kind}`,
}));

import { Inbox } from "./Inbox";

function sermon(id: string, title: string): LibrarySermon {
  return {
    id,
    title,
    speaker: "Speaker A",
    date: "2026-09-06",
    duration: "42:10",
    series: "Sample Series",
    status: "rendered",
  };
}

function section(state: InboxSection["state"], items: LibrarySermon[]): InboxSection {
  return { state, items };
}

const services: ServiceStatus[] = [
  { id: "api", label: "API", detail: "Reachable", state: "ok", level: 90 },
  { id: "db", label: "Database", detail: "Indexed", state: "ok", level: 70 },
  { id: "llm", label: "LLM", detail: "Slow", state: "warn", level: 40 },
  { id: "storage", label: "Storage", detail: "Free", state: "ok", level: 50 },
];

function inboxData(overrides: Partial<InboxData> = {}): InboxData {
  return {
    sections: [],
    counts: lifecycleCounts([]),
    services,
    publishedThisWeek: 2,
    isLoading: false,
    error: null,
    retry: vi.fn(),
    ...overrides,
  };
}

function renderInbox() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Inbox />} />
        <Route path="/library/:id" element={<p>teaching detail</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.inbox.mockReturnValue(inboxData());
});

describe("Inbox", () => {
  it("renders one section per non-empty lifecycle state with a heading, count and rows", () => {
    mocks.inbox.mockReturnValue(
      inboxData({
        sections: [
          section("needs_review", [sermon("s-1", "Needs one"), sermon("s-2", "Needs two")]),
          section("processing", []),
          section("failed", [sermon("s-3", "Broke")]),
        ],
      }),
    );
    renderInbox();

    const headings = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(headings).toEqual(["Needs review", "Failed"]);
    expect(screen.getByTestId("inbox-section-needs_review").textContent).toContain("2");
    expect(screen.getAllByTestId(/^teaching-row-/)).toHaveLength(3);
    expect(screen.queryByTestId("inbox-section-processing")).toBeNull();
  });

  it("uses the lifecycle verb for every state and keeps one accent action", () => {
    mocks.inbox.mockReturnValue(
      inboxData({
        sections: [
          section("needs_review", [sermon("s-1", "Needs review")]),
          section("ready", [sermon("s-2", "Ready")]),
          section("processing", [sermon("s-3", "Running")]),
          section("failed", [sermon("s-4", "Failed")]),
          section("draft", [sermon("s-5", "Draft")]),
        ],
      }),
    );
    renderInbox();

    for (const verb of ["Review", "Publish", "View job", "Retry", "Continue"]) {
      expect(screen.getByRole("button", { name: verb })).toBeTruthy();
    }
    expect(document.querySelectorAll("button.bg-accent")).toHaveLength(1);
    expect(document.querySelector("button.bg-accent")?.textContent).toBe("Review");
  });

  it("opens the teaching from a row verb", async () => {
    const user = userEvent.setup();
    mocks.inbox.mockReturnValue(
      inboxData({ sections: [section("needs_review", [sermon("s-1", "Needs review")])] }),
    );
    renderInbox();

    await user.click(screen.getByRole("button", { name: "Review" }));
    expect(screen.getByText("teaching detail")).toBeTruthy();
  });

  it("shows service health, the week's publishes and the library link in the footer", () => {
    mocks.inbox.mockReturnValue(
      inboxData({ sections: [section("needs_review", [sermon("s-1", "Needs review")])] }),
    );
    renderInbox();

    const footer = screen.getByTestId("inbox-footer");
    expect(footer.textContent).toContain("Services 3/4");
    expect(footer.textContent).toContain("Published this week 2");
    expect(screen.getByRole("link", { name: "Open library" })).toBeTruthy();
  });

  it("renders the empty state with one New teaching action and no page primary", () => {
    renderInbox();

    expect(screen.getByText("Nothing needs you.")).toBeTruthy();
    const newTeaching = screen.getAllByRole("link", { name: "New teaching" });
    expect(newTeaching).toHaveLength(1);
    expect(newTeaching[0].className).toContain("bg-raised");
    expect(document.querySelectorAll(".bg-accent")).toHaveLength(0);
  });

  it("shows section skeletons and no counts while loading", () => {
    mocks.inbox.mockReturnValue(inboxData({ isLoading: true }));
    renderInbox();

    expect(screen.getByTestId("inbox-loading")).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
    expect(screen.queryByTestId("inbox-footer")).toBeNull();
  });

  it("shows the error with a retry and keeps the footer", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    mocks.inbox.mockReturnValue(inboxData({ error: "The inbox could not be loaded.", retry }));
    renderInbox();

    expect(screen.getByText("The inbox could not be loaded.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("inbox-footer")).toBeTruthy();
  });

  it("never renders a New teaching header button", () => {
    mocks.inbox.mockReturnValue(
      inboxData({ sections: [section("needs_review", [sermon("s-1", "Needs review")])] }),
    );
    renderInbox();

    expect(screen.queryByRole("link", { name: "New teaching" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New teaching" })).toBeNull();
  });
});
