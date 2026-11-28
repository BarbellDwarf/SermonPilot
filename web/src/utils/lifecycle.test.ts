import { describe, expect, it } from "vitest";
import {
  LIFECYCLE_META,
  deriveLifecycleState,
  lifecycleCounts,
  lifecycleTone,
  type LifecycleInput,
  type LifecycleState,
} from "./lifecycle";

describe("deriveLifecycleState", () => {
  const cases: [string, LifecycleInput, LifecycleState][] = [
    ["status error", { status: "error" }, "failed"],
    ["upload failed", { upload_status: "failed" }, "failed"],
    ["edit failed", { edit_status: "failed" }, "failed"],
    ["error outranks rendered", { status: "error", edit_status: "rendered" }, "failed"],
    ["upload failed outranks processed", { status: "processed", upload_status: "failed" }, "failed"],
    ["failed outranks a pending plan", { edit_status: "failed", plan_status: "pending_review" }, "failed"],
    ["applied is processing", { edit_status: "applied" }, "processing"],
    ["applied outranks a pending plan", { edit_status: "applied", plan_status: "pending_review" }, "processing"],
    ["applied outranks processed", { edit_status: "applied", status: "processed" }, "processing"],
    ["upload failed outranks applied", { edit_status: "applied", upload_status: "failed" }, "failed"],
    ["rendered is ready", { edit_status: "rendered" }, "ready"],
    ["rendered outranks processed", { edit_status: "rendered", status: "processed" }, "ready"],
    ["rendered outranks a pending plan", { edit_status: "rendered", plan_status: "pending_review" }, "ready"],
    ["rendered outranks draft", { edit_status: "rendered", status: "draft" }, "ready"],
    ["plan pending review", { plan_status: "pending_review" }, "needs_review"],
    ["edit pending review", { edit_status: "pending_review" }, "needs_review"],
    ["needs review outranks processed", { plan_status: "pending_review", status: "processed" }, "needs_review"],
    ["needs review outranks draft", { plan_status: "pending_review", status: "draft" }, "needs_review"],
    ["non-review plan status does not match", { plan_status: "superseded", status: "draft" }, "draft"],
    ["edit uploaded is published", { edit_status: "uploaded" }, "published"],
    ["processed is published", { status: "processed" }, "published"],
    ["published ignores upload_status complete", { status: "processed", upload_status: "complete" }, "published"],
    ["status draft", { status: "draft" }, "draft"],
    ["edit draft", { edit_status: "draft" }, "draft"],
    ["no fields", {}, "draft"],
    ["all fields missing", { status: null, edit_status: null, upload_status: null, plan_status: null }, "draft"],
    ["unknown status", { status: "mystery" }, "draft"],
    ["pending status has no lifecycle row", { status: "pending" }, "draft"],
  ];

  it.each(cases)("%s", (_name, sermon, expected) => {
    expect(deriveLifecycleState(sermon)).toBe(expected);
  });

  it("normalizes case and whitespace", () => {
    expect(deriveLifecycleState({ edit_status: " Rendered " })).toBe("ready");
    expect(deriveLifecycleState({ upload_status: "FAILED" })).toBe("failed");
  });
});

describe("LIFECYCLE_META", () => {
  it("carries one label, tone and primary per state", () => {
    expect(Object.keys(LIFECYCLE_META)).toEqual([
      "draft",
      "needs_review",
      "processing",
      "ready",
      "published",
      "failed",
    ]);
    expect(LIFECYCLE_META.draft).toEqual({ label: "Draft", tone: "neutral", primary: "Continue" });
    expect(LIFECYCLE_META.needs_review).toEqual({
      label: "Needs review",
      tone: "warn",
      primary: "Review",
    });
    expect(LIFECYCLE_META.processing).toEqual({
      label: "Processing",
      tone: "info",
      primary: "View job",
    });
    expect(LIFECYCLE_META.ready).toEqual({
      label: "Ready to publish",
      tone: "ok",
      primary: "Publish",
    });
    expect(LIFECYCLE_META.failed).toEqual({ label: "Failed", tone: "danger", primary: "Retry" });
  });

  it("gives published no primary action", () => {
    expect(LIFECYCLE_META.published).toEqual({ label: "Published", tone: "ok", primary: null });
  });

  it("maps every state to its chip tone", () => {
    expect(lifecycleTone("draft")).toBe("neutral");
    expect(lifecycleTone("needs_review")).toBe("warn");
    expect(lifecycleTone("processing")).toBe("info");
    expect(lifecycleTone("ready")).toBe("ok");
    expect(lifecycleTone("published")).toBe("ok");
    expect(lifecycleTone("failed")).toBe("danger");
  });
});

describe("lifecycleCounts", () => {
  it("returns zero for every state and total when empty", () => {
    expect(lifecycleCounts([])).toEqual({
      draft: 0,
      needs_review: 0,
      processing: 0,
      ready: 0,
      published: 0,
      failed: 0,
      total: 0,
    });
  });

  it("counts every state plus the total", () => {
    const items: LifecycleInput[] = [
      { status: "draft" },
      {},
      { edit_status: "rendered" },
      { plan_status: "pending_review" },
      { edit_status: "applied" },
      { status: "processed" },
      { upload_status: "failed" },
      { status: "mystery" },
    ];
    expect(lifecycleCounts(items)).toEqual({
      draft: 3,
      needs_review: 1,
      processing: 1,
      ready: 1,
      published: 1,
      failed: 1,
      total: 8,
    });
  });
});
