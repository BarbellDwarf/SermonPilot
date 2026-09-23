import { describe, expect, it } from "vitest";
import { toJob } from "./hooks";
import type { ApiJob } from "./client";

const base: ApiJob = {
  id: "job-1",
  type: "sermon_processing",
  title: "Process sermon · Sample Teaching · Sample Speaker",
  description: 'Running the processing pipeline for "Sample Teaching" (Sample Speaker, 2026-01-01).',
  status: "queued",
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
  });

  it("falls back to the job type when a label is missing", () => {
    const job = toJob({ ...base, title: "", description: null });
    expect(job.kind).toBe("sermon_processing");
    expect(job.sermon).toBe("sermon_processing");
  });
});
