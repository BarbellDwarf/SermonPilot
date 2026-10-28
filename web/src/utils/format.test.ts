import { describe, expect, it } from "vitest";
import {
  formatBytes,
  formatCount,
  formatDate,
  formatDateTime,
  formatDuration,
  formatDurationValue,
  formatRelativeTime,
  parseDuration,
} from "./format";
import { truncateText } from "./text";

describe("formatDuration", () => {
  it("uses the shortest complete form", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(59)).toBe("59s");
    expect(formatDuration(60 * 60)).toBe("1h");
    expect(formatDuration(3 * 60 * 60)).toBe("3h");
    expect(formatDuration(33 * 60 + 56)).toBe("33m 56s");
    expect(formatDuration(115 * 60)).toBe("1h 55m");
  });

  it("never renders a zero seconds tail after hours", () => {
    expect(formatDuration(3600)).not.toContain("0s");
    expect(formatDuration(7200)).not.toContain("0s");
    expect(formatDuration(1.4)).toBe("1s");
  });

  it("returns a dash for missing or invalid values", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration(Number.NaN)).toBe("—");
    expect(formatDuration(-1)).toBe("—");
    expect(formatDurationValue("--:--")).toBe("—");
    expect(formatDurationValue("running")).toBe("—");
  });

  it("normalizes clocks and server prose", () => {
    expect(parseDuration("42:10")).toBe(2530);
    expect(parseDuration("1:02:03")).toBe(3723);
    expect(parseDuration("39m")).toBe(2340);
    expect(parseDuration("1h 0m")).toBe(3600);
    expect(formatDurationValue("42:10")).toBe("42m 10s");
    expect(formatDurationValue("1h 0m")).toBe("1h");
  });
});

describe("formatBytes", () => {
  it("scales to the largest sensible unit", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1.6 * 1024 ** 3)).toBe("1.6 GB");
    expect(formatBytes(12 * 1024 ** 2)).toBe("12 MB");
    expect(formatBytes(null)).toBe("size unknown");
    expect(formatBytes(-1)).toBe("size unknown");
  });
});

describe("formatCount", () => {
  it("pluralizes and groups", () => {
    expect(formatCount(0, "teaching")).toBe("0 teachings");
    expect(formatCount(1, "teaching")).toBe("1 teaching");
    expect(formatCount(22, "teaching")).toBe("22 teachings");
    expect(formatCount(1200, "job")).toBe("1,200 jobs");
  });
});

describe("date and time formats", () => {
  it("renders absolute dates without ISO", () => {
    expect(formatDate("2026-10-11")).toBe("Oct 11, 2026");
    expect(formatDate("")).toBe("—");
    expect(formatDate(null)).toBe("—");
  });

  it("renders absolute date and time in one form", () => {
    expect(formatDateTime("2026-10-27 23:30:00", { timeZone: "America/New_York" })).toBe(
      "Oct 27, 19:30",
    );
    expect(formatDateTime("2025-01-02 03:04:05", { timeZone: "UTC" })).toBe(
      "Jan 2, 2025, 03:04",
    );
    expect(formatDateTime("2026-10-27")).toBe("Oct 27, 2026");
  });

  it("renders relative time and falls back to a date after a week", () => {
    const now = Date.parse("2026-10-28T12:00:00Z");
    expect(formatRelativeTime("2026-10-28T11:59:40Z", now)).toBe("just now");
    expect(formatRelativeTime("2026-10-28T11:55:00Z", now)).toBe("5m ago");
    expect(formatRelativeTime("2026-10-28T09:00:00Z", now)).toBe("3h ago");
    expect(formatRelativeTime("2026-10-26T12:00:00Z", now)).toBe("2d ago");
    expect(formatRelativeTime("2026-10-01T12:00:00Z", now)).toBe("Oct 1, 2026");
  });
});

describe("truncateText", () => {
  const longTitle =
    "A very long teaching title about patience, perseverance, and the quiet work of hope across many seasons of ministry";

  it("clamps at a word boundary with an ellipsis", () => {
    const result = truncateText(longTitle, 60);
    expect(result.length).toBeLessThanOrEqual(60);
    expect(result.endsWith("…")).toBe(true);
    expect(result.slice(0, -1).endsWith(" ")).toBe(false);
    expect(longTitle.startsWith(result.slice(0, -1))).toBe(true);
  });

  it("handles short values, empty values, and long speaker names", () => {
    expect(truncateText("Short", 40)).toBe("Short");
    expect(truncateText(null, 40)).toBe("");
    expect(truncateText("   ", 40)).toBe("");
    expect(truncateText("A".repeat(40), 20)).toBe(`${"A".repeat(19)}…`);
    expect(truncateText("  Sample   Speaker  ", 40)).toBe("Sample Speaker");
  });

  it("collapses whitespace before clamping", () => {
    expect(truncateText("one\n two\tthree", 40)).toBe("one two three");
  });
});
