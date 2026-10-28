import type { Job } from "../mock/data";
import { formatDuration } from "../utils/format";

const SEP = " · ";

const TYPE_ACTIONS: Record<string, string> = {
  sermon_processing: "Process",
  batch_processing: "Batch process",
  sermon_import: "Import",
  validation: "Validate descriptions",
  audio_enhancement: "Enhance audio",
  transcript_generation: "Transcribe",
  metadata_update: "Generate metadata",
  auto_edit: "Auto-edit",
  auto_edit_apply: "Edit",
  sermon_publish: "Upload",
};

const TYPE_LABELS: Record<string, string> = {
  sermon_processing: "Sermon processing",
  batch_processing: "Batch processing",
  sermon_import: "Sermon import",
  validation: "Validation",
  audio_enhancement: "Audio enhancement",
  transcript_generation: "Transcription",
  metadata_update: "Metadata",
  auto_edit: "Auto-edit",
  auto_edit_apply: "Apply edit",
  sermon_publish: "Publish",
};

const TITLE_ACTIONS: [string, string][] = [
  ["Process + auto-edit", "Process"],
  ["Process sermon", "Process"],
  ["Re-process", "Re-process"],
  ["Apply edit", "Edit"],
  ["Upload existing render", "Upload"],
  ["Re-detect cuts", "Re-detect"],
  ["Refine cuts", "Refine cuts"],
  ["Batch process", "Batch process"],
  ["Batch push", "Batch push"],
  ["Batch AI", "Batch AI"],
  ["Re-import", "Re-import"],
  ["Auto-edit", "Auto-edit"],
  ["Generate metadata", "Generate metadata"],
  ["Enhance audio", "Enhance audio"],
  ["Validate descriptions", "Validate descriptions"],
  ["Transcribe", "Transcribe"],
  ["Import", "Import"],
  ["Upload", "Upload"],
];

export type JobDisplayStatus =
  | "RUNNING"
  | "QUEUED"
  | "DONE"
  | "FAILED"
  | "CANCELLED"
  | "INTERRUPTED";

export const STATUS_DOT: Record<JobDisplayStatus, string> = {
  RUNNING: "bg-accent",
  QUEUED: "bg-muted",
  DONE: "bg-ok",
  FAILED: "bg-danger",
  CANCELLED: "bg-muted",
  INTERRUPTED: "bg-warn",
};

export const STATUS_TEXT: Record<JobDisplayStatus, string> = {
  RUNNING: "text-accent",
  QUEUED: "text-muted",
  DONE: "text-ok",
  FAILED: "text-danger",
  CANCELLED: "text-muted",
  INTERRUPTED: "text-warn",
};

function storedTitle(job: Job): string {
  return (job.title || job.kind || "").trim();
}

function stripRetry(value: string): string {
  return value.replace(/^\(Retry\)\s*/i, "");
}

function actionFromTitle(title: string): string | null {
  for (const [prefix, action] of TITLE_ACTIONS) {
    if (title === prefix || title.startsWith(`${prefix}${SEP}`)) return action;
  }
  return null;
}

function humanize(key: string): string {
  const words = key.replace(/[_-]+/g, " ").trim().toLowerCase().split(" ");
  return words
    .map((word, index) => {
      if (word === "id") return "ID";
      if (word === "ids") return "IDs";
      return index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word;
    })
    .join(" ");
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function jobAction(job: Job): string {
  const title = stripRetry(storedTitle(job));
  return (
    actionFromTitle(title) ||
    TYPE_ACTIONS[job.type] ||
    title.split(SEP)[0]?.trim() ||
    humanize(job.type || "job")
  );
}

export function jobSermon(job: Job): string {
  const quoted = /"([^"]+)"/.exec(job.description ?? "");
  if (quoted?.[1]?.trim()) return quoted[1].trim();

  const title = stripRetry(storedTitle(job));
  const action = actionFromTitle(title);
  const remainder = action
    ? title.includes(SEP)
      ? title.slice(title.indexOf(SEP) + SEP.length)
      : ""
    : title;
  const parts = remainder.split(SEP).map((part) => part.trim()).filter(Boolean);
  if (action) return parts[0] || "Untitled job";
  if (parts.length > 1) return parts[1] || parts[0];
  return parts[0] || "Untitled job";
}

export function jobRowTitle(job: Job): string {
  const sermon = jobSermon(job);
  const action = jobAction(job);
  return sermon === action ? sermon : `${sermon}${SEP}${action}`;
}

export function jobStatus(job: Job): JobDisplayStatus {
  if (job.state === "interrupted" || /interrupted by app restart/i.test(job.error ?? "")) {
    return "INTERRUPTED";
  }
  switch (job.state) {
    case "running":
      return "RUNNING";
    case "done":
      return "DONE";
    case "failed":
      return "FAILED";
    case "cancelled":
      return "CANCELLED";
    default:
      return "QUEUED";
  }
}

export function jobTypeLabel(job: Job): string {
  return TYPE_LABELS[job.type] || humanize(job.type || "job");
}

export function jobContext(job: Job): { speaker: string | null; date: string | null } {
  const form = isRecord(job.parameters?.form_data) ? job.parameters.form_data : {};
  let speaker =
    text(form.speaker_name) || text(form.speaker) || text(job.parameters?.speaker) || "";
  let date = text(form.recorded_date) || text(job.parameters?.recorded_date) || "";
  const description = job.description ?? "";

  if (!speaker || !date) {
    const pair = /\(([^,()]+),\s*([^()]+)\)/.exec(description);
    if (pair) {
      speaker ||= pair[1].trim();
      date ||= pair[2].trim();
    } else if (!speaker && /"[^"]+"/.test(description)) {
      const solo = /\(([^()]+)\)\s*\.?/.exec(description);
      if (solo) speaker = solo[1].trim();
    }
  }
  return { speaker: speaker || null, date: date || null };
}

export function firstErrorLine(error: string | null | undefined): string {
  return (error ?? "").split(/\r?\n/)[0]?.trim() ?? "";
}

export function elapsedSince(createdAt: string | null | undefined, now: number): string {
  const start = createdAt ? Date.parse(createdAt.replace(" ", "T")) : NaN;
  if (!Number.isFinite(start)) return "";
  const total = Math.max(0, Math.floor((now - start) / 1000));
  return formatDuration(total);
}

function clockValue(value: unknown): string | null {
  const total = Number(value);
  if (!Number.isFinite(total) || total < 0) return null;
  const seconds = Math.round(total);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function offsetValue(value: unknown): string | null {
  const offset = Number(value);
  if (!Number.isFinite(offset)) return null;
  if (Math.abs(offset) < 0.0005) return "none";
  return `${offset > 0 ? "+" : ""}${offset.toFixed(1)}s`;
}

function truthy(value: unknown): boolean {
  return value === true || value === 1 || value === "true";
}

function basename(value: string): string {
  const parts = value.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || value;
}

const SECRET_NAMES = new Set(["password", "passwd", "token", "secret", "auth", "authorization"]);
const SECRET_SUFFIXES = ["_key", "_token", "_secret", "_password", "_passwd"];
const SKIP_KEYS = new Set([
  "config",
  "form_data",
  "user_id",
  "title",
  "speaker",
  "speaker_name",
  "recorded_date",
]);

function isSecretKey(key: string): boolean {
  const lower = key.toLowerCase();
  return SECRET_NAMES.has(lower) || SECRET_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

function displayValue(key: string, value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    const short =
      value.length <= 5 &&
      value.every((item) => ["string", "number", "boolean"].includes(typeof item)) &&
      value.join(", ").length <= 80;
    if (short) {
      return key === "actions"
        ? value.map((item) => humanize(String(item))).join(", ")
        : value.join(", ");
    }
    return `${value.length} items`;
  }
  if (isRecord(value)) {
    if (key === "actions") {
      const enabled = Object.entries(value)
        .filter(([, flag]) => truthy(flag))
        .map(([action]) => humanize(action));
      return enabled.length ? enabled.join(", ") : "none";
    }
    return null;
  }
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/(source|file|path|dir|folder)/i.test(key) && /[\\/]/.test(trimmed)) return basename(trimmed);
  return trimmed.length > 80 ? `${trimmed.slice(0, 77)}…` : trimmed;
}

export function jobParameterLines(
  parameters: Record<string, unknown> | null | undefined,
): string[] {
  if (!isRecord(parameters)) return [];
  const entries: [string, unknown][] = [];
  const seen = new Set<string>();
  const add = (key: string, value: unknown) => {
    if (SKIP_KEYS.has(key) || isSecretKey(key) || seen.has(key)) return;
    seen.add(key);
    entries.push([key, value]);
  };
  for (const [key, value] of Object.entries(parameters)) add(key, value);
  if (isRecord(parameters.form_data)) {
    for (const [key, value] of Object.entries(parameters.form_data)) add(key, value);
  }

  const range: string[] = [];
  const lines: string[] = [];
  for (const [key, value] of entries) {
    if (key === "start" || key === "final_start") {
      const clock = clockValue(value);
      if (clock) range.push(`Start: ${clock}`);
      continue;
    }
    if (key === "end" || key === "final_end") {
      const clock = clockValue(value);
      if (clock) range.push(`End: ${clock}`);
      continue;
    }
    if (key === "audio_offset") {
      const offset = offsetValue(value);
      if (offset) lines.push(`Audio offset: ${offset}`);
      continue;
    }
    if (key === "render_only") {
      lines.push(`Mode: ${truthy(value) ? "Render only" : "Render + upload"}`);
      continue;
    }
    const display = displayValue(key, value);
    if (display !== null) lines.push(`${humanize(key)}: ${display}`);
  }
  return [...range, ...lines];
}
