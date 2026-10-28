import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

function Explodes(): ReactElement {
  throw new Error("boom from a component");
}

describe("ErrorBoundary", () => {
  it("shows a recoverable panel with a Reload action instead of a blank screen", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Explodes />
      </ErrorBoundary>,
    );

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("The console hit an error");
    expect(alert.textContent).toContain("boom from a component");
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    spy.mockRestore();
  });

  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeTruthy();
  });
});
