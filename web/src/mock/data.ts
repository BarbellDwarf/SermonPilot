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

export type JobState = "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";

export interface Job {
  id: string;
  type: string;
  title: string;
  kind: string;
  sermon: string;
  description: string;
  state: JobState;
  created: string;
  createdAt: string;
  finished: string | null;
  duration: string;
  progress: number;
  error: string | null;
  log: string[];
  parameters?: Record<string, unknown> | null;
}

export const services: ServiceStatus[] = [
  { id: "api", label: "API", detail: "SermonAudio endpoint reachable", state: "ok", level: 92 },
  { id: "db", label: "Database", detail: "142 records indexed", state: "ok", level: 64 },
  { id: "llm", label: "LLM", detail: "Queue depth 3, responses slow", state: "warn", level: 38 },
  { id: "storage", label: "Storage", detail: "61 GB free of 120 GB", state: "ok", level: 51 },
];

function minutesAgo(minutes: number): { iso: string; label: string; time: string } {
  const date = new Date(Date.now() - minutes * 60_000);
  return {
    iso: date.toISOString(),
    label: `${date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })}`,
    time: date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }),
  };
}

const runningStart = minutesAgo(12);
const runningEnhance = minutesAgo(8);
const runningTranscribe = minutesAgo(3);

export const activeJobs: Job[] = [
  {
    id: "job-1042",
    type: "sermon_processing",
    title: "Process + auto-edit · Sunday Teaching · Sample Speaker",
    kind: "Enhance + Transcribe",
    sermon: "Sunday Teaching",
    description:
      'Processing "Sunday Teaching" (Sample Speaker, 2026-10-25) and auto-editing the video.',
    state: "running",
    created: runningStart.label,
    createdAt: runningStart.iso,
    finished: null,
    duration: "running",
    progress: 44.5,
    error: null,
    log: [
      `${runningStart.time} job accepted`,
      `${runningEnhance.time} enhancement pass 1/2`,
      `${runningTranscribe.time} transcription started`,
    ],
    parameters: {
      sermon_id: "s-01",
      form_data: {
        speaker_name: "Sample Speaker",
        recorded_date: "2026-10-25",
        whisper_model: "base",
        skip_audio: false,
        dry_run: false,
      },
      actions: ["enhance", "transcribe"],
    },
  },
  {
    id: "job-1041",
    type: "metadata_update",
    title: "Generate metadata · Midweek Class · Sample Speaker",
    kind: "Metadata",
    sermon: "Midweek Class",
    description:
      'Generating the description and hashtags for "Midweek Class" (Sample Speaker, 2026-10-24).',
    state: "queued",
    created: "Oct 25, 09:38",
    createdAt: "2026-10-25T09:38:00",
    finished: null,
    duration: "waiting",
    progress: 0,
    error: null,
    log: ["09:38 job accepted", "09:38 waiting for worker"],
    parameters: { sermon_id: "s-02", actions: { generate_description: true } },
  },
];

export const recentSermons: Sermon[] = [
  { id: "s-01", title: "Sample Teaching 1", speaker: "Speaker A", duration: "42:10", status: "ready", updated: "Today 09:12" },
  { id: "s-02", title: "Sample Teaching 2", speaker: "Speaker B", duration: "38:44", status: "processing", updated: "Today 08:50" },
  { id: "s-03", title: "Sample Teaching 3", speaker: "Speaker C", duration: "51:02", status: "draft", updated: "Yesterday 17:20" },
  { id: "s-04", title: "Sample Teaching 4", speaker: "Speaker A", duration: "44:37", status: "failed", updated: "Yesterday 15:03" },
];

export type LibrarySermonStatus = "draft" | "rendered" | "processed" | "failed";

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

export type DetectionStatus = "ok" | "unavailable";

export interface RemoveSegment {
  startSec: number;
  endSec: number;
}

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
  removeSegments: RemoveSegment[];
  offsetSec: number;
  detectionStatus: DetectionStatus;
  reasoning: string;
  notes: string;
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
    removeSegments: [],
    offsetSec: 0.4,
    detectionStatus: "ok",
    reasoning: "Teaching starts after the welcome; Q&A begins after the closing prayer.",
    notes: "Keep only the second of the two back-to-back classes.",
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
    removeSegments: [],
    offsetSec: -0.3,
    detectionStatus: "ok",
    reasoning: "Confident opening cut, the ending sits just before the audience question.",
    notes: "",
  },
};

export const completedJobs: Job[] = [
  {
    id: "job-1039",
    type: "sermon_processing",
    title: "Process sermon · Sunday Teaching · Sample Speaker",
    kind: "Full pipeline",
    sermon: "Sunday Teaching",
    description:
      'Running the processing pipeline for "Sunday Teaching" (Sample Speaker, 2026-10-24).',
    state: "done",
    created: "Oct 24, 16:02",
    createdAt: "2026-10-24T16:02:00",
    finished: "Oct 24, 16:41",
    duration: "39m",
    progress: 100,
    error: null,
    log: ["16:02 job accepted", "16:20 enhancement done", "16:33 transcription done", "16:41 upload done"],
    parameters: { sermon_id: "s-01", form_data: { whisper_model: "base", dry_run: false } },
  },
  {
    id: "job-1038",
    type: "transcript_generation",
    title: "Transcribe · Midweek Class · Sample Speaker",
    kind: "Transcribe only",
    sermon: "Midweek Class",
    description: 'Transcribing "Midweek Class" (Sample Speaker, 2026-10-24).',
    state: "done",
    created: "Oct 24, 14:10",
    createdAt: "2026-10-24T14:10:00",
    finished: "Oct 24, 14:26",
    duration: "16m",
    progress: 100,
    error: null,
    log: ["14:10 job accepted", "14:26 transcription done"],
    parameters: { sermon_id: "s-02", form_data: { whisper_model: "small" } },
  },
];

export const failedJobs: Job[] = [
  {
    id: "job-1037",
    type: "sermon_processing",
    title: "Process sermon · Midweek Class · Sample Speaker",
    kind: "Full pipeline",
    sermon: "Midweek Class",
    description:
      'Running the processing pipeline for "Midweek Class" (Sample Speaker, 2026-10-23).',
    state: "failed",
    created: "Oct 23, 15:03",
    createdAt: "2026-10-23T15:03:00",
    finished: "Oct 23, 15:19",
    duration: "16m",
    progress: 68,
    error: "Upload rejected: gateway timeout\nCheck the SermonAudio bridge and retry.",
    log: ["15:03 job accepted", "15:11 enhancement done", "15:19 upload rejected: gateway timeout"],
    parameters: { sermon_id: "s-02", form_data: { whisper_model: "base", dry_run: false } },
  },
];
