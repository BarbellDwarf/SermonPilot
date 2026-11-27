import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TeachingRow, type TeachingRowProps } from "./TeachingRow";
import type { LibrarySermon } from "../mock/data";

const sermon: LibrarySermon = {
  id: "s-1",
  title: "Sample Teaching 1",
  speaker: "Speaker A",
  date: "2026-09-06",
  duration: "42:10",
  series: "Sample Series",
  status: "rendered",
  edit_status: "pending_review",
};

function renderRow(overrides: Partial<TeachingRowProps> = {}) {
  const props: TeachingRowProps = {
    sermon,
    state: "needs_review",
    action: { label: "Review", onClick: vi.fn(), primary: true, testId: "row-action" },
    menu: [{ label: "Open teaching", onSelect: vi.fn() }],
    ...overrides,
  };
  return render(
    <MemoryRouter>
      <ol>
        <TeachingRow {...props} />
      </ol>
    </MemoryRouter>,
  );
}

function setMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    }),
  });
}

afterEach(() => {
  delete (window as { matchMedia?: unknown }).matchMedia;
});

describe("TeachingRow", () => {
  it("keeps one row action, one menu and a title link", () => {
    renderRow();
    const row = screen.getByTestId("teaching-row-s-1");

    expect(within(row).getByTestId("row-action").textContent).toBe("Review");
    expect(within(row).getByTestId("teaching-actions-s-1")).toBeTruthy();
    expect(within(row).getByRole("link", { name: /^Sample Teaching 1/ })).toBeTruthy();
    expect(row.querySelectorAll("button")).toHaveLength(2);
  });

  it("uses the accent fill only for the primary action", () => {
    const { unmount } = renderRow();
    expect(screen.getByTestId("row-action").className).toContain("bg-accent");
    unmount();

    renderRow({ action: { label: "Review", onClick: vi.fn(), testId: "row-action" } });
    expect(screen.getByTestId("row-action").className).not.toContain("bg-accent");
  });

  it("demotes the primary action to secondary on mobile", () => {
    setMatchMedia(false);
    renderRow();
    expect(screen.getByTestId("row-action").className).not.toContain("bg-accent");
    expect(screen.getByTestId("row-action").className).toContain("bg-raised");
  });

  it("meets the 44px hit target and row height slots", () => {
    renderRow();
    const row = screen.getByTestId("teaching-row-s-1");
    expect(row.className).toContain("min-h-[112px]");
    expect(row.className).toContain("md:min-h-[64px]");
    expect(screen.getByTestId("row-action").className).toContain("min-h-[44px]");
    expect(screen.getByTestId("teaching-actions-s-1").className).toContain("min-h-[44px]");
    expect(screen.getByTestId("teaching-actions-s-1").className).toContain("min-w-[44px]");
  });

  it("never covers the row with an absolute full-row link", () => {
    const { container } = renderRow();
    expect(container.querySelector(".absolute")).toBeNull();
  });

  it("clamps a long title and keeps the full value in title", () => {
    const title = "A long teaching title that keeps going well past a hundred characters so the row has to clamp it cleanly without growing";
    renderRow({ sermon: { ...sermon, title } });
    expect(screen.getByTitle(title)).toBeTruthy();
    expect(screen.getByTitle(title).className).toContain("truncate");
  });

  it("shows the duration as evidence unless another value is supplied", () => {
    const { unmount } = renderRow();
    expect(screen.getByText("42m 10s")).toBeTruthy();
    unmount();

    renderRow({ evidence: "87%" });
    expect(screen.getByText("87%")).toBeTruthy();
    expect(screen.queryByText("42m 10s")).toBeNull();
  });

  it("renders the state chip label from the lifecycle state", () => {
    renderRow({ state: "failed" });
    expect(screen.getByText("Failed")).toBeTruthy();
  });
});
