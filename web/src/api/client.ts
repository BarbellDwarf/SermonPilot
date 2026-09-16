export type ApiMode = "mock" | "live";

export const API_MODE: ApiMode =
  import.meta.env.VITE_API_MODE === "live" ? "live" : "mock";

export const isLive = API_MODE === "live";

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export interface ApiSermonListItem {
  id: string;
  title: string;
  speaker: string;
  date: string;
  duration: string;
  series: string;
  status: string;
}

export interface ApiSermonList {
  items: ApiSermonListItem[];
  total: number;
}

export interface ApiSermonFile {
  file_type: string;
  file_path: string;
  file_size: number | null;
}

export interface ApiSermonDetail extends ApiSermonListItem {
  duration_seconds: number | null;
  description: string | null;
  files: ApiSermonFile[];
  transcript_available: boolean;
  transcript_length: number;
}

export interface ApiEditPlan {
  sermon_id: string;
  status: string;
  revision: number;
  revisions_total: number;
  confidence: number;
  qa_judgment: string;
  evidence: string;
  start_sec: number | null;
  end_sec: number | null;
  offset_sec: number;
}

export interface ApiSermonPlan {
  plan: ApiEditPlan | null;
  history: ApiEditPlan[];
}

export interface ApiJob {
  id: string;
  type: string;
  title: string;
  description: string | null;
  status: string;
  created_at: string | null;
  completed_at: string | null;
  duration: string;
  error: string | null;
}

export interface ApiJobList {
  items: ApiJob[];
  total: number;
}

export interface ApiJobDetail extends ApiJob {
  logs: string[];
  parameters: Record<string, unknown>;
  result: Record<string, unknown> | null;
}

export interface ApiServiceState {
  status: string;
  message: string;
  details: string;
  timestamp?: string;
}

export interface ApiStatus {
  status: Record<string, ApiServiceState>;
  checked_at: string;
}

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const qs = params
    ? `?${new URLSearchParams(
        Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)])),
      ).toString()}`
    : "";
  const res = await fetch(`${BASE}${path}${qs}`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new Error(`GET ${path} failed with ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  sermons: (params?: { search?: string; sort?: string }) => get<ApiSermonList>("/api/sermons", params),
  sermon: (id: string) => get<ApiSermonDetail>(`/api/sermons/${encodeURIComponent(id)}`),
  plan: (id: string) => get<ApiSermonPlan>(`/api/sermons/${encodeURIComponent(id)}/plan`),
  jobs: (params?: { status?: string; limit?: number }) => get<ApiJobList>("/api/jobs", params),
  job: (id: string) => get<ApiJobDetail>(`/api/jobs/${encodeURIComponent(id)}`),
  status: () => get<ApiStatus>("/api/status"),
};
