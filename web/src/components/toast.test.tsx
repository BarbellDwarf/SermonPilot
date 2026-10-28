import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastHost, clearToasts, pushToast, useToast } from "./toast";

afterEach(() => {
  clearToasts();
  vi.useRealTimers();
});

describe("toast queue", () => {
  it("keeps at most three visible and drops the oldest", () => {
    render(<ToastHost />);
    act(() => {
      pushToast({ message: "First" });
      pushToast({ message: "Second" });
      pushToast({ message: "Third" });
      pushToast({ message: "Fourth" });
    });

    expect(screen.queryByText("First")).toBeNull();
    expect(screen.getByText("Second")).toBeTruthy();
    expect(screen.getByText("Fourth")).toBeTruthy();
  });

  it("runs an undo action and dismisses that toast", async () => {
    const user = userEvent.setup();
    const onUndo = vi.fn();
    function Harness() {
      const notify = useToast();
      return (
        <>
          <button type="button" onClick={() => notify.undo("Deleted.", onUndo)}>
            Delete
          </button>
          <ToastHost />
        </>
      );
    }
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Undo" }));

    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Deleted.")).toBeNull();
  });

  it("announces errors assertively and pauses dismissal on hover", () => {
    vi.useFakeTimers();
    render(<ToastHost />);
    act(() => {
      pushToast({ message: "Could not save.", variant: "error" });
    });

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Could not save.");

    act(() => {
      fireEvent.mouseEnter(alert);
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.getByRole("alert")).toBeTruthy();

    act(() => {
      fireEvent.mouseLeave(screen.getByRole("alert"));
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
