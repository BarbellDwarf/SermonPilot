import { describe, expect, it } from "vitest";
import { sermonViewMode, workspacePrimary } from "./sermonActions";
import type { LibrarySermonStatus, PlanStatus } from "../mock/data";

function mode(status: LibrarySermonStatus, planStatus?: PlanStatus) {
  return sermonViewMode({ status, planStatus });
}

describe("workspacePrimary", () => {
  it.each([
    ["needs_review", true, true, "approve", "Approve & upload"],
    ["ready", true, true, "publish", "Publish"],
    ["processing", true, true, "view-job", "View job"],
    ["draft", true, true, "publish-draft", "Publish draft"],
    ["draft", false, false, "detect", "Run cut detection"],
    ["published", true, true, "none", null],
  ] as const)("maps %s to %s", (state, hasPlan, hasRender, kind, label) => {
    expect(workspacePrimary({ state, hasPlan, hasRender })).toEqual({ kind, label });
  });
});

describe("sermonViewMode", () => {
  it("shows the finished view for a published record", () => {
    expect(mode("processed", "pending_review")).toBe("completed");
  });

  it("shows the finished view when the edit plan has been processed", () => {
    expect(mode("rendered", "processed")).toBe("completed");
  });

  it("keeps the editing view for a draft", () => {
    expect(mode("draft", "pending_review")).toBe("editing");
    expect(mode("draft")).toBe("editing");
  });

  it("keeps the editing view while a plan is pending review", () => {
    expect(mode("rendered", "pending_review")).toBe("editing");
  });

  it("keeps the editing view for a locally applied render", () => {
    expect(mode("rendered", "applied_local")).toBe("editing");
  });

  it("keeps the editing view for a failed record", () => {
    expect(mode("failed", "pending_review")).toBe("editing");
  });
});
