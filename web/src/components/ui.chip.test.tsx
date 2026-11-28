import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Chip } from "./ui";

describe("Chip tones", () => {
  it("renders danger with the danger token", () => {
    render(<Chip tone="danger">Failed</Chip>);
    const chip = screen.getByText("Failed");
    expect(chip.className).toContain("text-danger");
    expect(chip.className).toContain("border-danger");
  });

  it("keeps error as the same visual tone", () => {
    render(<Chip tone="error">Failed</Chip>);
    const chip = screen.getByText("Failed");
    expect(chip.className).toContain("text-danger");
    expect(chip.className).toContain("border-danger");
  });
});
