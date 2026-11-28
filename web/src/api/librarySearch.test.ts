import { describe, expect, it } from "vitest";
import type { LibrarySermon } from "../mock/data";
import { matchesLibraryQuery } from "./hooks";

const sermon: LibrarySermon = {
  id: "s-1",
  title: "Sample Teaching 2",
  speaker: "Speaker B",
  date: "2026-09-05",
  duration: "38:44",
  series: "Sample Series",
  status: "draft",
};

describe("matchesLibraryQuery", () => {
  it("accepts every token in any order", () => {
    expect(matchesLibraryQuery(sermon, "2 sample")).toBe(true);
    expect(matchesLibraryQuery(sermon, "speaker series")).toBe(true);
  });

  it("requires every token to match a field", () => {
    expect(matchesLibraryQuery(sermon, "sample missing")).toBe(false);
  });

  it("does not match across field boundaries as a phrase", () => {
    expect(matchesLibraryQuery(sermon, "2 speaker")).toBe(true);
    expect(matchesLibraryQuery(sermon, "teaching 2 speaker")).toBe(true);
  });

  it("ignores surrounding whitespace and case", () => {
    expect(matchesLibraryQuery(sermon, "  SAMPLE   ")).toBe(true);
    expect(matchesLibraryQuery(sermon, "")).toBe(true);
  });
});
