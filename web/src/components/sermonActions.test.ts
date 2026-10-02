import { describe, expect, it } from "vitest";
import { sermonActionMatrix, sermonViewMode } from "./sermonActions";
import type { LibrarySermonStatus, PlanStatus } from "../mock/data";

function mode(status: LibrarySermonStatus, planStatus?: PlanStatus) {
  return sermonViewMode({ status, planStatus });
}

describe("sermonViewMode", () => {
  it("shows the finished view for a published record", () => {
    expect(mode("uploaded", "pending_review")).toBe("completed");
  });

  it("shows the finished view when the edit plan has been processed", () => {
    expect(mode("draft", "processed")).toBe("completed");
  });

  it("keeps the editing view for a draft", () => {
    expect(mode("draft", "pending_review")).toBe("editing");
    expect(mode("draft")).toBe("editing");
  });

  it("keeps the editing view while a plan is pending review", () => {
    expect(mode("draft", "pending_review")).toBe("editing");
  });

  it("keeps the editing view for a locally applied render", () => {
    expect(mode("draft", "applied_local")).toBe("editing");
  });

  it("keeps the editing view for a failed record", () => {
    expect(mode("failed", "pending_review")).toBe("editing");
  });
});

/**
 * The visual pass found a queued record and an unrendered draft both offering
 * "Push to SermonAudio" as their primary action, which is a button that can only
 * fail: neither has anything on disk to publish.
 */
describe("sermonActionMatrix", () => {
  function actions(status: LibrarySermonStatus, hasRender = false) {
    return sermonActionMatrix({ status, hasRender });
  }

  it("offers nothing to publish on a queued record with no render", () => {
    const a = actions("queued", false);
    expect(a.canPublishLegacy).toBe(false);
    expect(a.canUploadExisting).toBe(false);
  });

  it("offers nothing to publish on a draft with no render", () => {
    const a = actions("draft", false);
    expect(a.canPublishLegacy).toBe(false);
    expect(a.canUploadExisting).toBe(false);
  });

  it("offers to publish a draft that already has a render on disk", () => {
    expect(actions("draft", true).canPublishLegacy).toBe(true);
    expect(actions("draft", true).canUploadExisting).toBe(true);
  });

  it("offers nothing to publish on an uploaded record", () => {
    const a = actions("uploaded", true);
    expect(a.published).toBe(true);
    expect(a.canPublishLegacy).toBe(false);
    expect(a.canUploadExisting).toBe(false);
  });

  it("still lets a failed record be pushed, since that is the way to retry it", () => {
    expect(actions("failed", false).canPublishLegacy).toBe(true);
  });
});
