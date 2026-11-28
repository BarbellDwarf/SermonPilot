import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EditPlan } from "../../mock/data";
import { PlanSummary } from "./PlanSummary";

const plan: EditPlan = {
  sermonId: "s-1",
  status: "pending_review",
  revision: 2,
  revisionsTotal: 3,
  confidence: 87,
  qa: "Pass",
  evidence: "",
  startSec: 10,
  endSec: 1000,
  removeSegments: [
    { startSec: 100, endSec: 130 },
    { startSec: 300, endSec: 300 },
  ],
  offsetSec: 0,
  detectionStatus: "ok",
  reasoning: "",
  notes: "",
};

describe("PlanSummary", () => {
  it("separates boundary trims from enabled interior cuts", () => {
    render(
      <PlanSummary
        plan={plan}
        duration={990}
        keptDuration={920}
        timelineDuration={1100}
        safeStart={10}
        safeEnd={1000}
        enabledRemoveSegments={[{ startSec: 100, endSec: 130 }]}
      />,
    );

    expect(screen.getByTestId("boundary-trim-count")).toHaveTextContent("2");
    expect(screen.getByTestId("interior-cut-count")).toHaveTextContent("1");
    expect(screen.getByTestId("cut-kept-summary")).toHaveTextContent("15m 20s");
    expect(screen.queryByText("Cut 2")).toBeNull();
  });
});
