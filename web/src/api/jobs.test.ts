import { describe, expect, it } from "vitest";
import { fmtStamp, toJob } from "./hooks";
import type { ApiJob } from "./client";

const base: ApiJob = {
  id: "job-1",
  type: "sermon_processing",
  title: "Process sermon · Sample Teaching · Sample Speaker",
  description: 'Running the processing pipeline for "Sample Teaching" (Sample Speaker, 2026-01-01).',
  status: "queued",
  progress: 12.5,
  created_at: "2026-01-01 09:00:00",
  completed_at: null,
  duration: "—",
  error: null,
};

describe("toJob", () => {
  it("uses the human job label as the console headline and detail line", () => {
    const job = toJob(base);
    expect(job.kind).toBe(base.title);
    expect(job.sermon).toBe(base.description);
    expect(job.state).toBe("queued");
    expect(job.progress).toBe(12.5);
    expect(job.createdAt).toBe(base.created_at);
    expect(job.created).toContain("Jan 1");
  });

  it("falls back to the job type when a label is missing", () => {
    const job = toJob({ ...base, title: "", description: null });
    expect(job.kind).toBe("sermon_processing");
    expect(job.sermon).toBe("sermon_processing");
  });
});

describe("fmtStamp", () => {
  it("treats a naive database timestamp as UTC and shows the browser zone", () => {
    expect(fmtStamp("2026-10-27 23:30:00", "America/New_York")).toBe("Oct 27, 19:30");
    expect(fmtStamp("2026-10-27 23:30:00", "Asia/Tokyo")).toBe("Oct 28, 08:30");
  });

  it("keeps an explicit offset as the instant it names", () => {
    expect(fmtStamp("2026-10-27T23:30:00Z", "America/New_York")).toBe("Oct 27, 19:30");
    expect(fmtStamp("2026-10-28T08:30:00+09:00", "America/New_York")).toBe("Oct 27, 19:30");
  });

  it("does not shift a date-only recorded date", () => {
    expect(fmtStamp("2026-10-27", "America/New_York")).toBe("Oct 27, 2026");
    expect(fmtStamp("2026-10-27", "Asia/Tokyo")).toBe("Oct 27, 2026");
  });

  it("crosses a DST boundary without showing the wrong day", () => {
    expect(fmtStamp("2026-03-08 06:30:00", "America/New_York")).toBe("Mar 8, 01:30");
    expect(fmtStamp("2026-03-08 07:30:00", "America/New_York")).toBe("Mar 8, 03:30");
    expect(fmtStamp("2026-11-01 03:30:00", "America/New_York")).toBe("Oct 31, 23:30");
  });
});
