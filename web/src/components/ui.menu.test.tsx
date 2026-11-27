import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Menu } from "./ui";

const onSelect = vi.fn();

const items = [
  { label: "Open teaching", onSelect, testId: "item-open", disabled: false },
  { label: "Preview", onSelect, testId: "item-preview" },
  { label: "Delete", onSelect, testId: "item-delete", danger: true },
];

const PANEL = { width: 224, height: 200 };

function setViewport(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
}

function setTriggerRect(left: number, top: number, width = 44, height = 44) {
  return vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    x: left,
    y: top,
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    toJSON: () => ({}),
  } as DOMRect);
}

function renderMenu() {
  return render(
    <>
      <Menu label="Actions for Sample Teaching 1" trigger="Actions" triggerTestId="row-actions" items={items} />
      <button type="button">Outside</button>
    </>,
  );
}

const panel = () => screen.getByRole("menu").parentElement as HTMLElement;

beforeEach(() => {
  onSelect.mockClear();
  setViewport(1024, 768);
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get: () => PANEL.width,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get: () => PANEL.height,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Menu", () => {
  it("opens a body portal with menu semantics and the first item focused", async () => {
    const user = userEvent.setup();
    setTriggerRect(600, 100);
    renderMenu();

    const trigger = screen.getByTestId("row-actions");
    expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    await user.click(trigger);

    const menu = screen.getByRole("menu", { name: "Actions for Sample Teaching 1" });
    expect(panel().parentElement).toBe(document.body);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(trigger.getAttribute("aria-controls")).toBe(menu.id);
    expect(panel().className).toContain("fixed");
    expect(panel().className).toContain("max-h-[min(60vh,20rem)]");
    expect(panel().className).toContain("overflow-y-auto");
    expect(document.activeElement).toBe(screen.getByTestId("item-open"));
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    setTriggerRect(600, 100);
    renderMenu();

    const trigger = screen.getByTestId("row-actions");
    await user.click(trigger);
    await user.click(screen.getByTestId("item-preview"));
    await user.click(trigger);
    expect(screen.getByRole("menu")).toBeTruthy();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("moves focus with ArrowDown, ArrowUp, Home, and End", async () => {
    const user = userEvent.setup();
    setTriggerRect(600, 100);
    renderMenu();
    await user.click(screen.getByTestId("row-actions"));

    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(screen.getByTestId("item-preview"));
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(screen.getByTestId("item-delete"));
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(screen.getByTestId("item-open"));
    await user.keyboard("{ArrowUp}");
    expect(document.activeElement).toBe(screen.getByTestId("item-delete"));
    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(screen.getByTestId("item-open"));
    await user.keyboard("{End}");
    expect(document.activeElement).toBe(screen.getByTestId("item-delete"));
  });

  it("closes on an outside pointerdown but keeps open for pointerdown inside the panel", async () => {
    const user = userEvent.setup();
    setTriggerRect(600, 100);
    renderMenu();
    await user.click(screen.getByTestId("row-actions"));

    fireEvent.pointerDown(screen.getByTestId("item-preview"));
    expect(screen.getByRole("menu")).toBeTruthy();

    fireEvent.pointerDown(screen.getByRole("button", { name: "Outside" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("fires the item action before it closes and restores focus", async () => {
    const user = userEvent.setup();
    setTriggerRect(600, 100);
    renderMenu();
    const trigger = screen.getByTestId("row-actions");
    await user.click(trigger);

    const preview = screen.getByTestId("item-preview");
    fireEvent.pointerDown(preview);
    await user.click(preview);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("closes when focus leaves both the trigger and the panel", async () => {
    const user = userEvent.setup();
    setTriggerRect(600, 100);
    renderMenu();
    await user.click(screen.getByTestId("row-actions"));
    expect(screen.getByRole("menu")).toBeTruthy();

    act(() => screen.getByRole("button", { name: "Outside" }).focus());

    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("flips above and clamps inside the viewport when it does not fit below", async () => {
    const user = userEvent.setup();
    setViewport(390, 568);
    setTriggerRect(140, 470);
    renderMenu();

    await user.click(screen.getByTestId("row-actions"));

    expect(panel().style.top).toBe("262px");
    expect(panel().style.left).toBe("8px");
    expect(panel().dataset.side).toBe("top");
  });

  it("places below and inside the viewport when there is room", async () => {
    const user = userEvent.setup();
    setViewport(390, 568);
    setTriggerRect(100, 100, 44, 44);
    renderMenu();

    await user.click(screen.getByTestId("row-actions"));

    expect(panel().style.top).toBe("152px");
    expect(panel().style.left).toBe("8px");
    expect(panel().dataset.side).toBe("bottom");
  });

  it("recomputes the position on scroll and resize while open", async () => {
    const user = userEvent.setup();
    setViewport(390, 568);
    const rect = setTriggerRect(100, 100);
    renderMenu();
    await user.click(screen.getByTestId("row-actions"));
    expect(panel().style.top).toBe("152px");

    rect.mockReturnValue({
      x: 100,
      y: 20,
      left: 100,
      top: 20,
      width: 44,
      height: 44,
      right: 144,
      bottom: 64,
      toJSON: () => ({}),
    } as DOMRect);
    act(() => {
      window.dispatchEvent(new Event("scroll"));
    });
    expect(panel().style.top).toBe("72px");

    rect.mockReturnValue({
      x: 100,
      y: 100,
      left: 100,
      top: 100,
      width: 44,
      height: 44,
      right: 144,
      bottom: 144,
      toJSON: () => ({}),
    } as DOMRect);
    setViewport(390, 300);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(panel().style.top).toBe("92px");
  });
});
