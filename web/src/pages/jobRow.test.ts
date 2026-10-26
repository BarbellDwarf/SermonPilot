import { describe, expect, it } from "vitest";
import type { Job } from "../mock/data";
import {
  elapsedSince,
  jobContext,
  jobParameterLines,
  jobRowTitle,
  jobStatus,
} from "./jobRow";

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    type: "sermon_processing",
    title: "Process sermon · Sunday Teaching · Sample Speaker",
    kind: "Process sermon",
    sermon: "Sunday Teaching",
    description: "",
    state: "queued",
    created: "Oct 25, 21:07",
    createdAt: "2026-10-25T21:07:00Z",
    finished: null,
    duration: "waiting",
    progress: 0,
    error: null,
    log: [],
    ...overrides,
  };
}

describe("jobRowTitle", () => {
  it("keeps the full sermon name and drops the speaker", () => {
    expect(jobRowTitle(job())).toBe("Sunday Teaching · Process");
  });

  it("prefers the quoted title from the description when it contains a separator", () => {
    expect(
      jobRowTitle(
        job({
          description: 'Processing "Midweek Class · Part 2" (Sample Speaker, 2026-10-24).',
          title: "Process sermon · Midweek Class · Part 2 · Sample Speaker",
        }),
      ),
    ).toBe("Midweek Class · Part 2 · Process");
  });

  it("falls back to the title when there is no description", () => {
    expect(
      jobRowTitle(
        job({
          type: "auto_edit_apply",
          title: "Apply edit · Midweek Class · Sample Speaker",
        }),
      ),
    ).toBe("Midweek Class · Edit");
  });

  it("keeps the existing short name for other job types", () => {
    expect(
      jobRowTitle(
        job({ type: "validation", title: "Validate descriptions · Midweek Class · Sample Speaker" }),
      ),
    ).toBe("Midweek Class · Validate descriptions");
    expect(
      jobRowTitle(job({ type: "batch_processing", title: "Batch process · 3 sermons" })),
    ).toBe("3 sermons · Batch process");
    expect(
      jobRowTitle(
        job({ type: "auto_edit", title: "Refine cuts · Midweek Class · Sample Speaker" }),
      ),
    ).toBe("Midweek Class · Refine cuts");
  });
});

describe("jobStatus", () => {
  it("labels restart-interrupted failures as INTERRUPTED", () => {
    expect(
      jobStatus(
        job({ state: "failed", error: "Job interrupted by app restart: the worker is gone." }),
      ),
    ).toBe("INTERRUPTED");
  });
});

describe("jobContext", () => {
  it("reads speaker and date from a per-sermon description", () => {
    expect(
      jobContext(job({ description: 'Processing "Sunday Teaching" (Sample Speaker, 2026-10-25).' })),
    ).toEqual({ speaker: "Sample Speaker", date: "2026-10-25" });
  });

  it("does not mistake a batch scope note for a speaker", () => {
    expect(
      jobContext(
        job({
          description: "Checking the generated descriptions for 2 sermons (recent only).",
        }),
      ),
    ).toEqual({ speaker: null, date: null });
  });
});

describe("jobParameterLines", () => {
  it("formats range, audio, booleans, lists, and paths readably", () => {
    const lines = jobParameterLines({
      start: 40,
      end: 2958,
      audio_offset: 0,
      render_only: false,
      source: "/data/media/nested/episode.mp4",
      sermon_ids: ["a", "b"],
      form_data: { whisper_model: "base", dry_run: true },
      config: { api_key: "secret" },
      api_key: "secret",
    });

    expect(lines).toContain("Start: 0:40");
    expect(lines).toContain("End: 49:18");
    expect(lines).toContain("Audio offset: none");
    expect(lines).toContain("Mode: Render + upload");
    expect(lines).toContain("Source: episode.mp4");
    expect(lines).toContain("Sermon IDs: a, b");
    expect(lines).toContain("Whisper model: base");
    expect(lines).toContain("Dry run: Yes");
    expect(lines.join(" ")).not.toContain("secret");
    expect(lines.join(" ")).not.toContain("{");
  });

  it("shows enabled action names instead of a raw object", () => {
    expect(
      jobParameterLines({ actions: { enhance: true, transcribe: false, metadata: true } }),
    ).toEqual(["Actions: Enhance, Metadata"]);
  });

  it("renders hour-long clocks", () => {
    expect(jobParameterLines({ start: 3661, end: 7322 })).toEqual([
      "Start: 1:01:01",
      "End: 2:02:02",
    ]);
  });
});

describe("elapsedSince", () => {
  it("formats seconds, minutes, and hours", () => {
    const start = "2026-10-25T21:00:00Z";
    const base = Date.parse(start);
    expect(elapsedSince(start, base + 12_000)).toBe("12s");
    expect(elapsedSince(start, base + 125_000)).toBe("2m 5s");
    expect(elapsedSince(start, base + 3_900_000)).toBe("1h 5m");
  });
});
