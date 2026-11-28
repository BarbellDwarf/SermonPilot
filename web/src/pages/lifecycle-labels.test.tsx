import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { librarySermons, sermonCounts, type LibrarySermon } from "../mock/data";
import type { InboxData } from "../api/hooks";
import { LIFECYCLE_META, lifecycleCounts, type LifecycleState } from "../utils/lifecycle";

const mocks = vi.hoisted(() => ({ library: vi.fn(), inbox: vi.fn() }));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return {
    ...actual,
    useLibrarySermons: () => mocks.library(),
    useInboxData: () => mocks.inbox(),
  };
});

vi.mock("../api/client", () => ({
  isLive: false,
  api: {},
  filesApi: {},
  mediaApi: {},
  mediaStreamUrl: (id: string, kind: string) => `/api/media/${id}/${kind}`,
}));

import { Inbox } from "./Inbox";
import { Library } from "./Library";
import { lifecycleOfSermon } from "../api/hooks";

const fixtures: [LifecycleState, LibrarySermon][] = [
  ["draft", { id: "s-draft", title: "Draft teaching", speaker: "A", date: "2026-09-06", duration: "42:10", series: "", status: "draft" }],
  ["needs_review", { id: "s-needs", title: "Needs teaching", speaker: "A", date: "2026-09-06", duration: "42:10", series: "", status: "rendered", edit_status: "pending_review" }],
  ["processing", { id: "s-processing", title: "Running teaching", speaker: "A", date: "2026-09-06", duration: "42:10", series: "", status: "draft", edit_status: "applied" }],
  ["ready", { id: "s-ready", title: "Ready teaching", speaker: "A", date: "2026-09-06", duration: "42:10", series: "", status: "rendered", edit_status: "rendered" }],
  ["published", { id: "s-published", title: "Published teaching", speaker: "A", date: "2026-09-06", duration: "42:10", series: "", status: "processed" }],
  ["failed", { id: "s-failed", title: "Failed teaching", speaker: "A", date: "2026-09-06", duration: "42:10", series: "", status: "failed", edit_status: "failed" }],
];

function countsOf(items: LibrarySermon[]) {
  const value = lifecycleCounts([]);
  for (const item of items) value[lifecycleOfSermon(item)] += 1;
  value.total = items.length;
  return value;
}

function inboxData(sermon: LibrarySermon, state: LifecycleState): InboxData {
  return {
    sections: [{ state, items: [sermon] }],
    counts: countsOf([sermon]),
    services: [],
    publishedThisWeek: 0,
    isLoading: false,
    error: null,
    retry: vi.fn(),
  };
}

function libraryData(sermon: LibrarySermon) {
  return {
    items: [sermon],
    isLoading: false,
    error: null as string | null,
    retry: vi.fn(),
    total: 1,
    hasMore: false,
    isLoadingMore: false,
    loadMore: vi.fn(),
    counts: countsOf([sermon]),
  };
}

describe("lifecycle label parity", () => {
  it.each(fixtures)("shows the same %s chip label on Inbox and Library", (state, sermon) => {
    const label = LIFECYCLE_META[state].label;

    mocks.inbox.mockReturnValue(inboxData(sermon, state));
    const inbox = render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Inbox />} />
        </Routes>
      </MemoryRouter>,
    );
    const inboxLabel = within(screen.getByTestId(`teaching-row-${sermon.id}`))
      .getByText(label)
      .textContent;
    inbox.unmount();

    mocks.library.mockReturnValue(libraryData(sermon));
    render(
      <MemoryRouter initialEntries={["/library"]}>
        <Routes>
          <Route path="/library" element={<Library />} />
        </Routes>
      </MemoryRouter>,
    );
    const libraryLabel = within(screen.getByTestId(`library-row-${sermon.id}`))
      .getByText(label)
      .textContent;

    expect(libraryLabel).toBe(inboxLabel);
  });

  it("keeps the mock fixtures and counts on the same six lifecycle states", () => {
    const derived = lifecycleCounts([]);
    for (const sermon of librarySermons) derived[lifecycleOfSermon(sermon)] += 1;
    derived.total = librarySermons.length;

    expect(sermonCounts).toEqual(derived);
    expect(Object.entries(derived).filter(([key, value]) => key !== "total" && value > 0)).toHaveLength(6);
  });
});
