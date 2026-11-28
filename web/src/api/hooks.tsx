import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  activeJobs,
  completedJobs,
  editPlans,
  failedJobs,
  getActivityJobs,
  jobActivityState,
  librarySermons,
  sermonCounts,
  services,
  type ActivityJobState,
  type EditPlan,
  type Job,
  type JobState,
  type LibrarySermon,
  type PlanStatus,
  type ServiceStatus,
} from "../mock/data";
import { Button, Card, useBriefLoading } from "../components/ui";
import { formatDate, formatDateTime } from "../utils/format";
import {
  deriveLifecycleState,
  lifecycleCounts,
  type LifecycleCounts,
  type LifecycleState,
} from "../utils/lifecycle";
import { api, filesApi, isLive, mediaApi, type ApiEditPlan, type ApiJob, type ApiMediaItem, type ApiSermonListItem } from "./client";

export type LibrarySort = "date" | "title" | "duration";

export function describeLoadError(
  error: unknown,
  subject: string,
  notFound = `${subject} could not be found (404).`,
): string | null {
  if (!error) return null;
  const candidate = error as { status?: unknown };
  const status =
    typeof error === "object" && error !== null && typeof candidate.status === "number"
      ? candidate.status
      : null;
  if (status !== null) {
    if (status === 404) return notFound;
    if (status >= 500) return `Server error (${status}). Try again in a moment.`;
    const reason = error instanceof Error && error.message ? `: ${error.message}` : "";
    return `${subject} could not be loaded (${status}${reason}).`;
  }
  const reason = error instanceof Error && error.message ? ` (${error.message})` : "";
  return `${subject} could not be loaded. Check the API bridge and try again.${reason}`;
}

export function QueryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card>
      <p className="text-sm font-semibold">Could not load data</p>
      <p className="mt-1 text-sm text-muted">{message}</p>
      <div className="mt-3">
        <Button onClick={onRetry}>Retry</Button>
      </div>
    </Card>
  );
}

function toSeconds(d: string): number {
  const parts = d.split(":").map(Number);
  if (parts.some((n) => !Number.isFinite(n))) return 0;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

const KNOWN_PLAN_STATUSES: PlanStatus[] = [
  "draft",
  "pending_review",
  "applied_local",
  "processed",
  "superseded",
];

export function toEditPlan(p: ApiEditPlan): EditPlan {
  return {
    sermonId: p.sermon_id,
    status: KNOWN_PLAN_STATUSES.includes(p.status as PlanStatus)
      ? (p.status as PlanStatus)
      : "pending_review",
    revision: p.revision,
    revisionsTotal: p.revisions_total,
    confidence: p.confidence,
    qa: p.qa_judgment || "—",
    evidence: p.evidence,
    startSec: p.start_sec ?? 0,
    endSec: p.end_sec ?? 0,
    removeSegments: (p.remove_segments ?? []).map((segment) => ({
      startSec: Number(segment.start_sec),
      endSec: Number(segment.end_sec),
    })),
    offsetSec: p.offset_sec,
    detectionStatus: p.detection_status === "unavailable" ? "unavailable" : "ok",
    reasoning: p.reasoning ?? "",
    notes: p.notes ?? "",
  };
}

export function toLibrarySermon(s: ApiSermonListItem): LibrarySermon {
  const status =
    s.status === "draft"
      ? "draft"
      : s.status === "processed"
        ? "processed"
        : s.status === "error"
          ? "failed"
          : "rendered";
  return {
    id: s.id,
    title: s.title || "(untitled)",
    speaker: s.speaker || "Unknown speaker",
    date: s.date,
    duration: s.duration,
    series: s.series,
    status,
    edit_status: s.edit_status ?? null,
    upload_status: s.upload_status ?? null,
    plan_status: s.plan_status ?? null,
  };
}

export function lifecycleOfSermon(sermon: LibrarySermon): LifecycleState {
  return deriveLifecycleState({
    status: sermon.status === "failed" ? "error" : sermon.status,
    edit_status:
      sermon.edit_status ??
      (sermon.status === "rendered" ? "rendered" : sermon.status === "failed" ? "failed" : null),
    upload_status: sermon.upload_status,
    plan_status: sermon.plan_status,
  });
}

function toLifecycleCounts(raw: Record<string, number> | undefined): LifecycleCounts {
  const counts = lifecycleCounts([]);
  if (!raw) return counts;
  for (const state of ["draft", "needs_review", "processing", "ready", "published", "failed"] as const) {
    counts[state] = Number(raw[state]) || 0;
  }
  counts.total = Number(raw.total) || counts.draft + counts.needs_review + counts.processing + counts.ready + counts.published + counts.failed;
  return counts;
}

const JOB_STATE_MAP: Record<string, JobState> = {
  queued: "queued",
  running: "running",
  completed: "done",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
  interrupted: "interrupted",
};

export function toJob(j: ApiJob, logs: string[] = []): Job {
  return {
    id: j.id,
    type: j.type,
    title: j.title,
    kind: j.title || j.type,
    sermon: j.description || j.type,
    description: j.description ?? "",
    state: JOB_STATE_MAP[j.status] ?? "queued",
    created: fmtStamp(j.created_at),
    createdAt: j.created_at ?? "",
    finished: j.completed_at ? fmtStamp(j.completed_at) : null,
    duration: j.duration,
    progress: typeof j.progress === "number" ? j.progress : 0,
    error: j.error ?? null,
    log: logs,
    parameters: null,
  };
}

export function fmtStamp(value: string | null, timeZone?: string): string {
  if (!value || value === "—") return "—";
  const trimmed = value.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return formatDate(trimmed, { timeZone });
  }
  return formatDateTime(trimmed, { timeZone });
}

const LIBRARY_PAGE_SIZE = 50;

export function useLibrarySermons(query: string, sort: LibrarySort) {
  const briefLoading = useBriefLoading();
  const [pages, setPages] = useState(1);
  const live = useQuery({
    queryKey: ["sermons", pages],
    queryFn: () => api.sermons({ limit: LIBRARY_PAGE_SIZE * pages }),
    enabled: isLive,
    staleTime: 10_000,
  });
  const loaded = useMemo(
    () => (live.data?.items ?? []).map(toLibrarySermon),
    [live.data],
  );
  const serverTotal = live.data?.total ?? loaded.length;
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = q
      ? loaded.filter((s) =>
          [s.title, s.speaker, s.series].some((f) => f.toLowerCase().includes(q)),
        )
      : [...loaded];
    rows.sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      if (sort === "duration") return toSeconds(b.duration) - toSeconds(a.duration);
      return b.date.localeCompare(a.date);
    });
    return rows;
  }, [loaded, query, sort]);

  const mockItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? librarySermons.filter((s) =>
          [s.title, s.speaker, s.series].some((f) => f.toLowerCase().includes(q)),
        )
      : [...librarySermons];
    filtered.sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      if (sort === "duration") return toSeconds(b.duration) - toSeconds(a.duration);
      return b.date.localeCompare(a.date);
    });
    return filtered;
  }, [query, sort]);

  if (!isLive) {
    return {
      items: mockItems,
      isLoading: briefLoading,
      error: null as string | null,
      retry: () => {},
      total: mockItems.length,
      hasMore: false,
      isLoadingMore: false,
      loadMore: () => {},
      counts: sermonCounts,
    };
  }
  return {
    items: filtered,
    isLoading: live.isPending,
    error: describeLoadError(live.error, "The teachings list"),
    retry: () => void live.refetch(),
    total: serverTotal,
    hasMore: loaded.length < serverTotal,
    isLoadingMore: live.isFetching && !live.isPending,
    loadMore: () => setPages((p) => p + 1),
    counts: live.data?.counts ? toLifecycleCounts(live.data.counts) : lifecycleCounts(loaded),
  };
}

export interface InboxSection {
  state: LifecycleState;
  items: LibrarySermon[];
}

export interface InboxData {
  sections: InboxSection[];
  counts: LifecycleCounts;
  services: ServiceStatus[];
  publishedThisWeek: number;
  isLoading: boolean;
  error: string | null;
  retry: () => void;
}

const INBOX_STATES: LifecycleState[] = [
  "needs_review",
  "ready",
  "processing",
  "failed",
  "draft",
];

function buildInboxSections(items: LibrarySermon[]): InboxSection[] {
  return INBOX_STATES.map((state) => ({
    state,
    items: items.filter((item) => lifecycleOfSermon(item) === state),
  })).filter((section) => section.items.length > 0);
}

function publishedThisWeek(items: LibrarySermon[]): number {
  const now = Date.now();
  return items.filter((item) => {
    if (lifecycleOfSermon(item) !== "published") return false;
    const date = Date.parse(item.date);
    return Number.isFinite(date) && now - date <= 7 * 24 * 60 * 60 * 1000;
  }).length;
}

const SERVICE_LABELS: Record<string, string> = {
  sermonaudio_api: "API",
  database: "Database",
  llm_primary: "LLM",
  local_storage: "Storage",
};

function toServiceStatus(data: { status?: Record<string, { status: string; message: string; details: string }> } | undefined): ServiceStatus[] {
  return Object.entries(data?.status ?? {})
    .filter(([id]) => id in SERVICE_LABELS)
    .map(([id, s]) => ({
      id,
      label: SERVICE_LABELS[id],
      detail: s.message || s.details,
      state: s.status === "ok" ? "ok" : s.status === "warning" ? "warn" : "error",
      level: s.status === "ok" ? 85 : s.status === "warning" ? 40 : 15,
    }));
}

export function useInboxData(): InboxData {
  const briefLoading = useBriefLoading();
  const sermonsQuery = useQuery({
    queryKey: ["sermons", { limit: 50, sort: "date" }],
    queryFn: () => api.sermons({ limit: 50, sort: "date" }),
    enabled: isLive,
    staleTime: 15_000,
  });
  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    enabled: isLive,
    staleTime: 15_000,
  });

  if (!isLive) {
    return {
      sections: buildInboxSections(librarySermons),
      counts: sermonCounts,
      services,
      publishedThisWeek: publishedThisWeek(librarySermons),
      isLoading: briefLoading,
      error: null,
      retry: () => {},
    };
  }

  const items = (sermonsQuery.data?.items ?? []).map(toLibrarySermon);
  return {
    sections: buildInboxSections(items),
    counts: sermonsQuery.data?.counts
      ? toLifecycleCounts(sermonsQuery.data.counts)
      : lifecycleCounts(items),
    services: toServiceStatus(statusQuery.data),
    publishedThisWeek: publishedThisWeek(items),
    isLoading: sermonsQuery.isPending,
    error: describeLoadError(sermonsQuery.error, "The inbox"),
    retry: () => {
      void sermonsQuery.refetch();
      void statusQuery.refetch();
    },
  };
}

export function useInboxCount(): number {
  const sermonsQuery = useQuery({
    queryKey: ["sermons", { limit: 50, sort: "date" }],
    queryFn: () => api.sermons({ limit: 50, sort: "date" }),
    enabled: isLive,
    staleTime: 15_000,
  });

  if (!isLive) return sermonCounts.needs_review;
  const items = (sermonsQuery.data?.items ?? []).map(toLibrarySermon);
  const counts = sermonsQuery.data?.counts
    ? toLifecycleCounts(sermonsQuery.data.counts)
    : lifecycleCounts(items);
  return counts.needs_review;
}

export interface SermonDetailData {
  sermon: LibrarySermon;
  durationSeconds: number | null;
  description: string | null;
  descriptionNeedsReview: boolean;
  files: { file_type: string; file_path: string; file_size: number | null }[];
  transcriptAvailable: boolean;
  transcriptLength: number;
  sermonaudioId: string | null;
  uploadedAt: string | null;
  uploadStatus: string | null;
  bibleText: string | null;
  scriptureReference: string | null;
  hashtags: string | null;
}

export function useSermonDetail(id: string | undefined) {
  const live = useQuery({
    queryKey: ["sermon", id],
    queryFn: () => api.sermon(id ?? ""),
    enabled: isLive && !!id,
    staleTime: 15_000,
  });
  const mockSermon = librarySermons.find((s) => s.id === id);

  if (!isLive) {
    return {
      data: mockSermon
        ? ({
            sermon: mockSermon,
            durationSeconds: null,
            description: null,
            descriptionNeedsReview: false,
            files: [],
            transcriptAvailable: false,
            transcriptLength: 0,
            sermonaudioId: null,
            uploadedAt: null,
            uploadStatus: null,
            bibleText: null,
            scriptureReference: null,
            hashtags: null,
          } as SermonDetailData)
        : null,
      isLoading: false,
      error: null as string | null,
      retry: () => {},
    };
  }
  return {
    data: live.data
      ? ({
          sermon: toLibrarySermon(live.data),
          durationSeconds: live.data.duration_seconds,
          description: live.data.description,
          descriptionNeedsReview: live.data.description_needs_review,
          files: live.data.files,
          transcriptAvailable: live.data.transcript_available,
          transcriptLength: live.data.transcript_length,
          sermonaudioId: live.data.sermonaudio_id,
          uploadedAt: live.data.upload_date,
          uploadStatus: live.data.upload_status,
          bibleText: live.data.bible_text,
          scriptureReference: live.data.scripture_reference,
          hashtags: live.data.hashtags,
        } as SermonDetailData)
      : null,
    isLoading: live.isPending,
    error: describeLoadError(
      live.error,
      "This teaching",
      "This teaching is no longer in the library (it may have been applied or removed).",
    ),
    retry: () => void live.refetch(),
  };
}

export function useSermonTranscript(id: string | undefined, enabled: boolean) {
  const live = useQuery({
    queryKey: ["sermon-transcript", id],
    queryFn: () => api.transcript(id ?? ""),
    enabled: isLive && !!id && enabled,
    staleTime: 60_000,
  });

  if (!isLive) {
    return { data: null, isLoading: false, error: null as string | null };
  }
  return {
    data: live.data ?? null,
    isLoading: live.isPending,
    error: describeLoadError(live.error, "The transcript"),
  };
}

export interface SermonMediaData {
  items: ApiMediaItem[];
  byKind: Record<string, ApiMediaItem>;
  primary: string | null;
  audio: string | null;
  isLoading: boolean;
  error: string | null;
  retry: () => void;
}

export function useSermonMedia(id: string | undefined, enabled = true): SermonMediaData {
  const live = useQuery({
    queryKey: ["sermon-media", id],
    queryFn: () => mediaApi.list(id ?? ""),
    enabled: isLive && !!id && enabled,
    staleTime: 15_000,
  });
  const items = live.data?.items ?? [];
  const byKind = useMemo(
    () => Object.fromEntries(items.map((item) => [item.kind, item])),
    [items],
  );
  if (!isLive) {
    return {
      items: [],
      byKind: {},
      primary: null,
      audio: null,
      isLoading: false,
      error: null,
      retry: () => {},
    };
  }
  return {
    items,
    byKind,
    primary: live.data?.primary ?? null,
    audio: live.data?.audio ?? null,
    isLoading: live.isPending,
    error: describeLoadError(live.error, "Media previews"),
    retry: () => void live.refetch(),
  };
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export function useTranscriptSegments(id: string | undefined, enabled: boolean) {
  const live = useQuery({
    queryKey: ["sermon-timestamps", id],
    queryFn: () => mediaApi.fetchJson<TranscriptSegment[]>(id ?? "", "transcript_timestamps"),
    enabled: isLive && !!id && enabled,
    staleTime: 60_000,
    retry: false,
  });
  const segments = useMemo<TranscriptSegment[]>(() => {
    const raw = Array.isArray(live.data) ? live.data : [];
    return raw
      .map((segment) => ({
        start: Number(segment.start) || 0,
        end: Number(segment.end) || 0,
        text: String(segment.text ?? "").trim(),
      }))
      .filter((segment) => segment.text.length > 0);
  }, [live.data]);
  if (!isLive) {
    return { segments: [] as TranscriptSegment[], isLoading: false };
  }
  return { segments, isLoading: live.isPending };
}

export function useSermonPlan(id: string | undefined) {
  const live = useQuery({
    queryKey: ["sermon-plan", id],
    queryFn: () => api.plan(id ?? ""),
    enabled: isLive && !!id,
    staleTime: 15_000,
  });
  const mockPlan = id ? editPlans[id] : undefined;

  if (!isLive) {
    return {
      plan: mockPlan,
      history: mockPlan ? [mockPlan] : ([] as EditPlan[]),
      isLoading: false,
      error: null as string | null,
      retry: () => {},
    };
  }
  return {
    plan: live.data?.plan ? toEditPlan(live.data.plan) : undefined,
    history: (live.data?.history ?? []).map(toEditPlan),
    isLoading: live.isPending,
    error: describeLoadError(live.error, "The auto-edit plan"),
    retry: () => void live.refetch(),
  };
}

export interface JobsData {
  active: Job[];
  completed: Job[];
  failed: Job[];
}

export function useJobDetail(id: string, enabled: boolean, poll = false) {
  const live = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.job(id),
    enabled: isLive && enabled,
    staleTime: 0,
    refetchInterval: poll
      ? (query) => {
          const status = query.state.data?.status;
          return !status || status === "queued" || status === "running" ? 2000 : false;
        }
      : false,
  });

  if (!isLive) {
    return {
      logs: null as string[] | null,
      parameters: null as Record<string, unknown> | null,
      status: null as string | null,
      isLoading: false,
      error: null as string | null,
    };
  }
  return {
    logs: live.data?.logs ?? null,
    parameters: live.data?.parameters ?? null,
    status: live.data?.status ?? null,
    isLoading: live.isPending,
    error: describeLoadError(live.error, "The job log"),
  };
}

function partitionJobs(jobs: Job[]): JobsData {
  return {
    active: jobs.filter((j) => j.state === "queued" || j.state === "running"),
    completed: jobs.filter((j) => j.state === "done"),
    failed: jobs.filter((j) => j.state === "failed" || j.state === "cancelled"),
  };
}

export type ActivityFilter = "all" | ActivityJobState;

const ACTIVITY_FILTERS: ActivityFilter[] = ["all", "active", "completed", "failed", "interrupted"];
const ACTIVITY_PAGE_SIZE = 50;

function activityStateRank(job: Job): number {
  if (job.state === "running") return 0;
  if (job.state === "queued") return 1;
  if (job.state === "failed") return 2;
  if (job.state === "cancelled") return 3;
  if (jobActivityState(job) === "interrupted") return 4;
  return 5;
}

function sortActivityJobs(jobs: Job[]): Job[] {
  return [...jobs].sort((a, b) => {
    const state = activityStateRank(a) - activityStateRank(b);
    if (state !== 0) return state;
    return (Date.parse(b.createdAt) || 0) - (Date.parse(a.createdAt) || 0);
  });
}

export function useActivityJobs(state: ActivityFilter) {
  const [pages, setPages] = useState<Record<ActivityFilter, number>>({
    all: 0,
    active: 0,
    completed: 0,
    failed: 0,
    interrupted: 0,
  });
  const page = pages[state];
  const queries = useQueries({
    queries: ACTIVITY_FILTERS.map((filter) => {
      const selected = filter === state;
      const limit = selected ? ACTIVITY_PAGE_SIZE : 1;
      const offset = selected ? page * ACTIVITY_PAGE_SIZE : 0;
      return {
        queryKey: ["jobs", "activity", filter, limit, offset],
        queryFn: () =>
          api.jobs({
            ...(filter === "all" ? {} : { status: filter }),
            limit,
            offset,
          }),
        enabled: isLive,
        staleTime: 5_000,
        refetchInterval: 5_000,
      };
    }),
  });
  const selected = queries[ACTIVITY_FILTERS.indexOf(state)];
  const total = selected.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / ACTIVITY_PAGE_SIZE));
  const counts = ACTIVITY_FILTERS.reduce(
    (result, filter, index) => {
      result[filter] = queries[index].data?.total ?? 0;
      return result;
    },
    {} as Record<ActivityFilter, number>,
  );

  if (!isLive) {
    const all = getActivityJobs();
    const mockCounts = ACTIVITY_FILTERS.reduce(
      (result, filter) => {
        result[filter] =
          filter === "all" ? all.length : all.filter((job) => jobActivityState(job) === filter).length;
        return result;
      },
      {} as Record<ActivityFilter, number>,
    );
    const filtered = all.filter((job) => state === "all" || jobActivityState(job) === state);
    const mockTotal = filtered.length;
    const mockPageCount = Math.max(1, Math.ceil(mockTotal / ACTIVITY_PAGE_SIZE));
    return {
      jobs: sortActivityJobs(filtered).slice(
        page * ACTIVITY_PAGE_SIZE,
        (page + 1) * ACTIVITY_PAGE_SIZE,
      ),
      total: mockTotal,
      counts: mockCounts,
      isLoading: false,
      error: null as string | null,
      retry: () => {},
      page,
      pageCount: mockPageCount,
      nextPage: () =>
        setPages((current) => ({
          ...current,
          [state]: Math.min(current[state] + 1, mockPageCount - 1),
        })),
      previousPage: () =>
        setPages((current) => ({ ...current, [state]: Math.max(0, current[state] - 1) })),
    };
  }

  return {
    jobs: sortActivityJobs((selected.data?.items ?? []).map((job) => toJob(job))),
    total,
    counts,
    isLoading: selected.isPending,
    error: describeLoadError(selected.error, "Jobs"),
    retry: () => void selected.refetch(),
    page,
    pageCount,
    nextPage: () =>
      setPages((current) => ({ ...current, [state]: Math.min(current[state] + 1, pageCount - 1) })),
    previousPage: () =>
      setPages((current) => ({ ...current, [state]: Math.max(0, current[state] - 1) })),
  };
}

export function useJobsData() {
  const briefLoading = useBriefLoading();
  const live = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.jobs({ limit: 100 }),
    enabled: isLive,
    staleTime: 5_000,
    refetchInterval: isLive ? 5_000 : false,
  });
  const mock = useMemo(
    () => ({
      active: activeJobs,
      completed: completedJobs,
      failed: failedJobs,
    }),
    [],
  );

  if (!isLive) {
    return { data: mock, isLoading: briefLoading, error: null as string | null, retry: () => {} };
  }
  return {
    data: partitionJobs((live.data?.items ?? []).map((j) => toJob(j))),
    isLoading: live.isPending,
    error: describeLoadError(live.error, "Jobs"),
    retry: () => void live.refetch(),
  };
}

export function useUserFiles(enabled: boolean) {
  const live = useQuery({
    queryKey: ["user-files"],
    queryFn: filesApi.list,
    enabled: isLive && enabled,
    staleTime: 15_000,
  });

  if (!isLive) {
    return { root: null as string | null, items: [] as { name: string }[] };
  }
  return {
    root: live.data?.root ?? null,
    items: live.data?.items ?? [],
  };
}

