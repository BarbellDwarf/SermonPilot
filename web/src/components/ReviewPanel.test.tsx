import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { ReviewPanel } from "./ReviewPanel";
import type { EditPlan } from "../mock/data";

function renderPanel(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function plan(overrides: Partial<EditPlan> = {}): EditPlan {
  return {
    sermonId: "s-1",
    status: "pending_review",
    revision: 2,
    revisionsTotal: 3,
    confidence: 87,
    qa: "Pass",
    evidence: "Silence gate at both ends.",
    startSec: 8.5,
    endSec: 2512.3,
    offsetSec: 0.4,
    detectionStatus: "ok",
    reasoning: "Teaching starts after the welcome; Q&A begins after the closing prayer.",
    notes: "",
    ...overrides,
  };
}

const noop = () => {};

describe("ReviewPanel refine controls", () => {
  it("shows detection status, reasoning, and each prior note with its revision", () => {
    renderPanel(
      <ReviewPanel
        plan={plan()}
        history={[
          plan({ revision: 1, status: "superseded", notes: "Keep only the second class" }),
          plan({ revision: 2, notes: "Trim the announcements" }),
        ]}
        sermonId="s-1"
        sermonTitle="Teaching"
        onToast={noop}
      />,
    );

    expect(screen.getByText(/Detection: ok/)).toBeTruthy();
    expect(screen.getByText(/Teaching starts after the welcome/)).toBeTruthy();
    expect(screen.getByText("revision 1")).toBeTruthy();
    expect(screen.getByText(/Keep only the second class/)).toBeTruthy();
    expect(screen.getByText("revision 2")).toBeTruthy();
    expect(screen.getByText(/Trim the announcements/)).toBeTruthy();
  });

  it("hides the note history when no revision carries a note", () => {
    renderPanel(
      <ReviewPanel plan={plan()} history={[plan()]} sermonId="s-1" sermonTitle="T" onToast={noop} />,
    );
    expect(screen.queryByText("Rejection notes")).toBeNull();
  });

  it("runs a refine from notes and shows the new revision and note", async () => {
    const user = userEvent.setup();
    const toasts: string[] = [];
    renderPanel(
      <ReviewPanel
        plan={plan()}
        history={[plan({ revision: 1, status: "superseded", notes: "first note" })]}
        sermonId="s-1"
        sermonTitle="Teaching"
        onToast={(m) => toasts.push(m)}
      />,
    );

    const box = screen.getByLabelText("Reject with notes") as HTMLTextAreaElement;
    expect((screen.getByRole("button", { name: /Re-run with notes/ }) as HTMLButtonElement).disabled).toBe(true);
    await user.type(box, "only the second class");
    await user.click(screen.getByRole("button", { name: /Re-run with notes/ }));

    await waitFor(() => {
      expect(screen.getByText("revision 3")).toBeTruthy();
    });
    expect(screen.getAllByText(/only the second class/).length).toBeGreaterThan(0);
    expect(screen.getByText(/revision 3 of 3/)).toBeTruthy();
    expect(toasts.join(" ")).toContain("Previous revision superseded");
  });

  it("re-detects from scratch without adding a rejection note", async () => {
    const user = userEvent.setup();
    const toasts: string[] = [];
    renderPanel(
      <ReviewPanel
        plan={plan()}
        history={[plan({ revision: 1, status: "superseded", notes: "first note" })]}
        sermonId="s-1"
        sermonTitle="Teaching"
        onToast={(m) => toasts.push(m)}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Re-detect from scratch" }));

    await waitFor(() => {
      expect(screen.getByText(/revision 3 of 3/)).toBeTruthy();
    });
    expect(screen.queryByText("revision 2")).toBeNull();
    expect(screen.getByText("revision 1")).toBeTruthy();
    expect(toasts.join(" ")).toContain("from scratch");
  });

  it("keeps the refine controls available when detection failed", () => {
    renderPanel(
      <ReviewPanel
        plan={plan({ detectionStatus: "unavailable", confidence: 0 })}
        sermonId="s-1"
        sermonTitle="Teaching"
        onToast={noop}
      />,
    );

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Detection: unavailable/)).toBeTruthy();
    expect(screen.getByLabelText("Reject with notes")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Re-detect from scratch" })).toBeTruthy();
    expect(screen.queryByText("Proposed cuts")).toBeNull();
  });
});
