import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SaveBar } from "./ui";

afterEach(() => {
  vi.useRealTimers();
});

describe("SaveBar", () => {
  it("renders no surface for a clean section", () => {
    render(<SaveBar dirty={false} onSave={() => {}} label="Save audio settings" />);

    expect(screen.queryByTestId("settings-save-bar")).toBeNull();
    expect(screen.queryByText("Saved.")).toBeNull();
    expect(screen.queryByText("No unsaved changes.")).toBeNull();
  });

  it("uses a named secondary action while dirty", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<SaveBar dirty onSave={onSave} label="Save audio settings" />);

    const button = screen.getByRole("button", { name: "Save audio settings" });
    expect(button.className).toContain("bg-raised");
    expect(button.className).not.toContain("bg-accent");
    await user.click(button);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("shows Saved briefly after a dirty section becomes clean", () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <SaveBar dirty onSave={() => {}} label="Save audio settings" />,
    );

    rerender(<SaveBar dirty={false} onSave={() => {}} label="Save audio settings" />);
    expect(screen.getByText("Saved.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save audio settings" })).toBeNull();

    act(() => vi.advanceTimersByTime(3000));
    expect(screen.queryByTestId("settings-save-bar")).toBeNull();
  });
});
