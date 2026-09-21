import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Combobox, type ComboboxOption } from "./Combobox";

const options: ComboboxOption[] = [
  { name: "Alice Johnson", count: 3 },
  { name: "Bob Smith", count: 1 },
  { name: "Carol Danvers" },
];

function Harness({ onChange }: { onChange?: (value: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <Combobox
      id="speaker"
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange?.(next);
      }}
      options={options}
      ariaLabel="Speaker"
    />
  );
}

describe("Combobox", () => {
  it("opens the listbox on click", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("combobox", { name: "Speaker" });
    expect(input.getAttribute("aria-expanded")).toBe("false");
    await user.click(input);
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(input.getAttribute("aria-activedescendant")).toBe("speaker-opt-0");
  });

  it("filters options case-insensitively as you type", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("combobox", { name: "Speaker" });
    await user.click(input);
    await user.type(input, "bO");
    const visible = screen.getAllByRole("option");
    expect(visible).toHaveLength(1);
    expect(visible[0].textContent).toContain("Bob Smith");
    expect(screen.queryByRole("option", { name: /Alice/ })).toBeNull();
  });

  it("selects the active option with the keyboard", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const input = screen.getByRole("combobox", { name: "Speaker" }) as HTMLInputElement;
    await user.click(input);
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenLastCalledWith("Bob Smith");
    expect(input.value).toBe("Bob Smith");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("selects an option on click", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("combobox", { name: "Speaker" }) as HTMLInputElement;
    await user.click(input);
    await user.click(screen.getByRole("option", { name: /Carol Danvers/ }));
    expect(input.value).toBe("Carol Danvers");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("closes on Escape and keeps free text", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("combobox", { name: "Speaker" }) as HTMLInputElement;
    await user.click(input);
    await user.type(input, "Unknown Person");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(input.value).toBe("Unknown Person");
  });

  it("keeps free text after blurring", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("combobox", { name: "Speaker" }) as HTMLInputElement;
    await user.click(input);
    await user.type(input, "A Brand New Name");
    await user.tab();
    expect(input.value).toBe("A Brand New Name");
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
