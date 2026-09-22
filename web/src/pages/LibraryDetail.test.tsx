import { describe, expect, it } from "vitest";
import { describeDeleteOutcome } from "./LibraryDetail";
import type { ApiTrashRecord } from "../api/client";

function record(overrides: Partial<ApiTrashRecord>): ApiTrashRecord {
  return {
    source: "s",
    destination: "d",
    mode: "local",
    reason: "sermon_deleted",
    deleted_at: "2026-01-01T00:00:00",
    moved: true,
    recoverable: true,
    ...overrides,
  };
}

describe("describeDeleteOutcome", () => {
  it("reports the local trash destination", () => {
    const message = describeDeleteOutcome([
      record({ mode: "local", destination: "/data/_trash/2026-01-01/1-ab/item" }),
    ]);
    expect(message).toContain("/data/_trash/2026-01-01/1-ab/item");
  });

  it("says cloud media stayed recoverable instead of deleted", () => {
    const message = describeDeleteOutcome([
      record({ mode: "remote-kept", moved: false, destination: "remote:gdrive:talks/a.mp3" }),
    ]);
    expect(message).toContain("stayed recoverable");
    expect(message).not.toContain("destroyed");
  });

  it("reports a remote move", () => {
    const message = describeDeleteOutcome([
      record({ mode: "remote", moved: true, destination: "remote:gdrive:_trash/2026-01-01/a.mp3" }),
    ]);
    expect(message).toContain("remote:gdrive:_trash/2026-01-01/a.mp3");
  });

  it("never claims media was destroyed when nothing moved", () => {
    expect(describeDeleteOutcome([])).toContain("No media was destroyed");
  });
});
