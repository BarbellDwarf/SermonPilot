import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LibrarySermon } from "../mock/data";

const mocks = vi.hoisted(() => ({ sermons: vi.fn() }));

vi.mock("../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/hooks")>();
  return { ...actual, useLibrarySermons: () => mocks.sermons() };
});

vi.mock("../api/client", () => ({
  isLive: false,
  api: {},
  filesApi: {},
  mediaApi: {},
  mediaStreamUrl: (id: string, kind: string) => `/api/media/${id}/${kind}`,
}));

import { Library } from "./Library";

const rows: LibrarySermon[] = [
  {
    id: "s-1",
    title: "Sample Teaching 1",
    speaker: "Speaker A",
    date: "2026-09-06",
    duration: "42:10",
    series: "Sample Series",
    status: "processed",
  },
  {
    id: "s-2",
    title: "Sample Teaching 2",
    speaker: "Speaker B",
    date: "2026-09-05",
    duration: "38:44",
    series: "Sample Series",
    status: "draft",
  },
  {
    id: "s-3",
    title: "Sample Teaching 3",
    speaker: "Speaker C",
    date: "2026-09-04",
    duration: "51:02",
    series: "Sample Series",
    status: "rendered",
  },
];

function libraryData(items: LibrarySermon[] = rows) {
  return {
    items,
    isLoading: false,
    error: null as string | null,
    retry: vi.fn(),
    total: items.length,
    hasMore: false,
    isLoadingMore: false,
    loadMore: vi.fn(),
  };
}

function renderLibrary() {
  return render(
    <MemoryRouter initialEntries={["/library"]}>
      <Routes>
        <Route path="/library" element={<Library />} />
        <Route path="/library/:id" element={<p>teaching detail</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.sermons.mockReturnValue(libraryData());
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:sample"),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
});

describe("Library rows", () => {
  it("renders one compact row per teaching with no per-row preview buttons", () => {
    renderLibrary();

    expect(screen.getAllByTestId(/^library-row-/)).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Preview" })).toBeNull();
    expect(screen.getAllByRole("link", { name: /^Open Sample Teaching/ })).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: /^Actions for Sample Teaching/ })).toHaveLength(3);
    expect(screen.getByText("Speaker A · 2026-09-06")).toBeTruthy();
  });

  it("renders only the loaded page, not every matching row, at scale", () => {
    const page = Array.from({ length: 50 }, (_, i) => ({
      ...rows[0],
      id: `s-page-${i}`,
      title: `Teaching ${i}`,
    }));
    mocks.sermons.mockReturnValue({
      ...libraryData(page),
      total: 10000,
      hasMore: true,
    });
    const { container } = renderLibrary();

    expect(screen.getAllByTestId(/^library-row-/)).toHaveLength(50);
    expect(screen.getByText("50 of 50 loaded")).toBeTruthy();
    expect(container.querySelectorAll("*").length).toBeLessThan(2000);
  });

  it("opens the teaching from a row click", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(screen.getByRole("link", { name: /^Open Sample Teaching 1/ }));
    expect(screen.getByText("teaching detail")).toBeTruthy();
  });

  it("renders markup in a title as text, never as DOM", () => {
    const hostile = '<script>window.__pwned = 1</script><img src=x onerror="alert(1)">';
    mocks.sermons.mockReturnValue(
      libraryData([{ ...rows[0], id: "s-hostile", title: hostile }]),
    );
    const { container } = renderLibrary();

    expect(screen.getByText(hostile)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it("keeps open and preview inside the row overflow menu", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(screen.getByTestId("library-actions-s-1"));
    const menu = screen.getByRole("menu", { name: "Actions for Sample Teaching 1" });
    expect(within(menu).getByRole("menuitem", { name: "Open teaching" })).toBeTruthy();

    await user.click(within(menu).getByRole("menuitem", { name: "Preview" }));
    expect(screen.getByText("Preview available in the live console.")).toBeTruthy();

    await user.click(screen.getByTestId("library-actions-s-1"));
    await user.click(screen.getByRole("menuitem", { name: "Hide preview" }));
    expect(screen.queryByText("Preview available in the live console.")).toBeNull();
  });
});

describe("Library toolbar", () => {
  it("keeps search, status, and sort visible while moving export and clear into the overflow", async () => {
    const user = userEvent.setup();
    renderLibrary();

    expect(screen.getByLabelText("Search teachings")).toBeTruthy();
    expect(screen.getByLabelText("Filter by status")).toBeTruthy();
    expect(screen.getByLabelText("Sort teachings")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Export CSV" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Clear" })).toBeNull();

    await user.type(screen.getByLabelText("Search teachings"), "Sample Teaching 1");
    await user.selectOptions(screen.getByLabelText("Filter by status"), "processed");
    await user.click(screen.getByTestId("library-toolbar-menu"));
    const menu = screen.getByRole("menu", { name: "Library actions" });
    expect(within(menu).getByRole("menuitem", { name: "Export CSV" })).toBeTruthy();

    await user.click(within(menu).getByRole("menuitem", { name: "Clear filters" }));
    expect((screen.getByLabelText("Search teachings") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Filter by status") as HTMLSelectElement).value).toBe("all");
  });

  it("exports the visible rows from the toolbar overflow", async () => {
    const user = userEvent.setup();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderLibrary();

    await user.click(screen.getByTestId("library-toolbar-menu"));
    await user.click(screen.getByRole("menuitem", { name: "Export CSV" }));

    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:sample");
    click.mockRestore();
  });
});
