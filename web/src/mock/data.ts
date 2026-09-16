export type ServiceState = "ok" | "warn" | "error";

export interface ServiceStatus {
  id: string;
  label: string;
  detail: string;
  state: ServiceState;
  level: number;
}

export type SermonStatus = "ready" | "processing" | "draft" | "failed";

export interface Sermon {
  id: string;
  title: string;
  speaker: string;
  duration: string;
  status: SermonStatus;
  updated: string;
}

export type JobState = "queued" | "running" | "done" | "failed";

export interface Job {
  id: string;
  kind: string;
  sermon: string;
  state: JobState;
  created: string;
  finished: string | null;
  duration: string;
  log: string[];
}

export const services: ServiceStatus[] = [
  { id: "api", label: "API", detail: "SermonAudio endpoint reachable", state: "ok", level: 92 },
  { id: "db", label: "Database", detail: "142 records indexed", state: "ok", level: 64 },
  { id: "llm", label: "LLM", detail: "Queue depth 3, responses slow", state: "warn", level: 38 },
  { id: "storage", label: "Storage", detail: "61 GB free of 120 GB", state: "ok", level: 51 },
];

export const activeJobs: Job[] = [
  {
    id: "job-1042",
    kind: "Enhance + Transcribe",
    sermon: "Sample Teaching 1",
    state: "running",
    created: "09:41",
    finished: null,
    duration: "12m so far",
    log: ["09:41 job accepted", "09:42 enhancement pass 1/2", "09:47 transcription started"],
  },
  {
    id: "job-1041",
    kind: "Metadata",
    sermon: "Sample Teaching 2",
    state: "queued",
    created: "09:38",
    finished: null,
    duration: "waiting",
    log: ["09:38 job accepted", "09:38 waiting for worker"],
  },
];

export const recentSermons: Sermon[] = [
  { id: "s-01", title: "Sample Teaching 1", speaker: "Speaker A", duration: "42:10", status: "ready", updated: "Today 09:12" },
  { id: "s-02", title: "Sample Teaching 2", speaker: "Speaker B", duration: "38:44", status: "processing", updated: "Today 08:50" },
  { id: "s-03", title: "Sample Teaching 3", speaker: "Speaker C", duration: "51:02", status: "draft", updated: "Yesterday 17:20" },
  { id: "s-04", title: "Sample Teaching 4", speaker: "Speaker A", duration: "44:37", status: "failed", updated: "Yesterday 15:03" },
];

export type LibrarySermonStatus = "draft" | "rendered" | "processed";

export interface LibrarySermon {
  id: string;
  title: string;
  speaker: string;
  date: string;
  duration: string;
  series: string;
  status: LibrarySermonStatus;
}

export const librarySermons: LibrarySermon[] = [
  { id: "s-01", title: "Sample Teaching 1", speaker: "Speaker A", date: "2026-09-06", duration: "42:10", series: "Sample Series A", status: "rendered" },
  { id: "s-02", title: "Sample Teaching 2", speaker: "Speaker B", date: "2026-09-05", duration: "38:44", series: "Sample Series A", status: "draft" },
  { id: "s-03", title: "Sample Teaching 3", speaker: "Speaker C", date: "2026-09-04", duration: "51:02", series: "Sample Series B", status: "processed" },
  { id: "s-04", title: "Sample Teaching 4", speaker: "Speaker A", date: "2026-09-03", duration: "44:37", series: "Sample Series B", status: "rendered" },
  { id: "s-05", title: "Sample Teaching 5", speaker: "Speaker B", date: "2026-09-02", duration: "39:15", series: "Sample Series C", status: "processed" },
  { id: "s-06", title: "Sample Teaching 6", speaker: "Speaker C", date: "2026-09-01", duration: "47:28", series: "Sample Series C", status: "draft" },
];

export type PlanStatus = "draft" | "pending_review" | "applied_local" | "processed" | "superseded";

export interface EditPlan {
  sermonId: string;
  status: PlanStatus;
  revision: number;
  revisionsTotal: number;
  confidence: number;
  qa: string;
  evidence: string;
  startSec: number;
  endSec: number;
  offsetSec: number;
}

export const editPlans: Record<string, EditPlan> = {
  "s-01": {
    sermonId: "s-01",
    status: "pending_review",
    revision: 2,
    revisionsTotal: 3,
    confidence: 87,
    qa: "Pass",
    evidence: "Silence gate at both ends, loudness within target band.",
    startSec: 8.5,
    endSec: 2512.3,
    offsetSec: 0.4,
  },
  "s-04": {
    sermonId: "s-04",
    status: "pending_review",
    revision: 1,
    revisionsTotal: 2,
    confidence: 72,
    qa: "Review",
    evidence: "Low-confidence ending boundary, verify before render.",
    startSec: 12.0,
    endSec: 2650.0,
    offsetSec: -0.3,
  },
};

export const completedJobs: Job[] = [
  {
    id: "job-1039",
    kind: "Full pipeline",
    sermon: "Sample Teaching 5",
    state: "done",
    created: "Yesterday 16:02",
    finished: "Yesterday 16:41",
    duration: "39m",
    log: ["16:02 job accepted", "16:20 enhancement done", "16:33 transcription done", "16:41 upload done"],
  },
  {
    id: "job-1038",
    kind: "Transcribe only",
    sermon: "Sample Teaching 6",
    state: "done",
    created: "Yesterday 14:10",
    finished: "Yesterday 14:26",
    duration: "16m",
    log: ["14:10 job accepted", "14:26 transcription done"],
  },
];

export const failedJobs: Job[] = [
  {
    id: "job-1037",
    kind: "Full pipeline",
    sermon: "Sample Teaching 4",
    state: "failed",
    created: "Yesterday 15:03",
    finished: "Yesterday 15:19",
    duration: "16m",
    log: ["15:03 job accepted", "15:11 enhancement done", "15:19 upload rejected: gateway timeout"],
  },
];
