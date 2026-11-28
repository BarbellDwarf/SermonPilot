import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusChip } from "./StatusChip";
import { LIFECYCLE_META, type LifecycleState } from "../utils/lifecycle";

const STATES: LifecycleState[] = [
  "draft",
  "needs_review",
  "processing",
  "ready",
  "published",
  "failed",
];

describe("StatusChip", () => {
  it.each(STATES)("renders the %s label from LIFECYCLE_META", (state) => {
    render(<StatusChip state={state} />);
    expect(screen.getByText(LIFECYCLE_META[state].label)).toBeTruthy();
  });

  it("uses the danger tone for a failed record", () => {
    render(<StatusChip state="failed" />);
    expect(screen.getByText("Failed").className).toContain("border-danger");
    expect(screen.getByText("Failed").className).toContain("text-danger");
  });

  it("uses neutral for a draft and ok for ready and published", () => {
    const { rerender } = render(<StatusChip state="draft" />);
    expect(screen.getByText("Draft").className).toContain("border-line");
    rerender(<StatusChip state="ready" />);
    expect(screen.getByText("Ready to publish").className).toContain("border-ok");
    rerender(<StatusChip state="published" />);
    expect(screen.getByText("Published").className).toContain("border-ok");
  });
});
