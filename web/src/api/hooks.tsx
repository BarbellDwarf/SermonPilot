import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  activeJobs,
  completedJobs,
  editPlans,
  failedJobs,
  librarySermons,
  recentSermons,
  services,
  type EditPlan,
  type Job,
  type JobState,
  type LibrarySermon,
  type PlanStatus,
  type Sermon,
  type SermonStatus,
  type ServiceStatus,
} from "../mock/data";
import { Button, Card, useBriefLoading } from "../components/ui";
import { api, filesApi, isLive, mediaApi, type ApiEditPlan, type ApiJob, type ApiMediaItem, type ApiSermonListItem } from "./client";

export type LibrarySort = "date" | "title" | "duration";

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
  };
}

const JOB_STATE_MAP: Record<string, JobState> = {
  queued: "queued",
  running: "running",
  completed: "done",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
};

export function toJob(j: ApiJob, logs: string[] = []): Job {
  return {
    id: j.id,
    kind: j.title || j.type,
    sermon: j.description || j.type,
    state: JOB_STATE_MAP[j.status] ?? "queued",
    created: fmtStamp(j.created_at),
    finished: j.completed_at ? fmtStamp(j.completed_at) : null,
    duration: j.duration,
    log: logs,
  };
}

function fmtStamp(value: string | null): string {
  if (!value || value === "—") return "—";
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) return value;
  const date = parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  if (/^\d{4}-\d{2}-\d{2}$/.test(value.trim())) return date;
  const time = parsed.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${date}, ${time}`;
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
    };
  }
  return {
    items: filtered,
    isLoading: live.isPending,
    error: live.isError ? "The teachings list could not be loaded. Check the API bridge and try again." : null,
    retry: () => void live.refetch(),
    total: serverTotal,
    hasMore: loaded.length < serverTotal,
    isLoadingMore: live.isFetching && !live.isPending,
    loadMore: () => setPages((p) => p + 1),
  };
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
        } as SermonDetailData)
      : null,
    isLoading: live.isPending,
    error: live.isError ? "This teaching could not be loaded. Check the API bridge and try again." : null,
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
    error: live.isError ? "The transcript could not be loaded." : null,
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
    error: live.isError ? "Media previews could not be loaded." : null,
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
    error: live.isError ? "The auto-edit plan could not be loaded." : null,
    retry: () => void live.refetch(),
  };
}

export interface JobsData {
  active: Job[];
  completed: Job[];
  failed: Job[];
}

export function useJobDetail(id: string, enabled: boolean) {
  const live = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.job(id),
    enabled: isLive && enabled,
    staleTime: 0,
  });

  if (!isLive) {
    return { logs: null as string[] | null, isLoading: false, error: null as string | null };
  }
  return {
    logs: live.data?.logs ?? null,
    isLoading: live.isPending,
    error: live.isError ? "The job log could not be loaded." : null,
  };
}

function partitionJobs(jobs: Job[]): JobsData {
  return {
    active: jobs.filter((j) => j.state === "queued" || j.state === "running"),
    completed: jobs.filter((j) => j.state === "done"),
    failed: jobs.filter((j) => j.state === "failed" || j.state === "cancelled"),
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
    error: live.isError ? "Jobs could not be loaded. Check the API bridge and try again." : null,
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

export interface HomeData {
  services: ServiceStatus[];
  activeJobs: Job[];
  recentSermons: Sermon[];
  upNext: Job[];
}

const SERMON_STATUS_MAP: Record<string, SermonStatus> = {
  processed: "ready",
  draft: "draft",
  pending: "processing",
  error: "failed",
};

function toRecentSermon(s: ApiSermonListItem): Sermon {
  return {
    id: s.id,
    title: s.title || "(untitled)",
    speaker: s.speaker || "Unknown speaker",
    duration: s.duration,
    status: SERMON_STATUS_MAP[s.status] ?? "processing",
    updated: fmtStamp(s.date),
  };
}

const SERVICE_LABELS: Record<string, string> = {
  sermonaudio_api: "API",
  database: "Database",
  llm_primary: "LLM",
  local_storage: "Storage",
};

export function useHomeData() {
  const briefLoading = useBriefLoading();
  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    enabled: isLive,
    staleTime: 15_000,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.jobs({ limit: 100 }),
    enabled: isLive,
    staleTime: 5_000,
    refetchInterval: isLive ? 5_000 : false,
  });
  const sermonsQuery = useQuery({
    queryKey: ["sermons", "", "date"],
    queryFn: () => api.sermons({ sort: "date" }),
    enabled: isLive,
    staleTime: 15_000,
  });
  const mock = useMemo(
    () => ({
      services,
      activeJobs,
      recentSermons,
      upNext: activeJobs.filter((j) => j.state === "queued").slice(0, 3),
    }),
    [],
  );

  if (!isLive) {
    return { data: mock, isLoading: briefLoading, error: null as string | null, retry: () => {} };
  }
  const servicesLive: ServiceStatus[] = Object.entries(statusQuery.data?.status ?? {})
    .filter(([id]) => id in SERVICE_LABELS)
    .map(([id, s]) => ({
      id,
      label: SERVICE_LABELS[id],
      detail: s.message || s.details,
      state: s.status === "ok" ? "ok" : s.status === "warning" ? "warn" : "error",
      level: s.status === "ok" ? 85 : s.status === "warning" ? 40 : 15,
    }));
  const allJobs = (jobsQuery.data?.items ?? []).map((j) => toJob(j));
  const data: HomeData = {
    services: servicesLive,
    activeJobs: allJobs.filter((j) => j.state === "queued" || j.state === "running"),
    recentSermons: (sermonsQuery.data?.items ?? []).slice(0, 4).map(toRecentSermon),
    upNext: allJobs.filter((j) => j.state === "queued").slice(0, 3),
  };
  const isLoading = statusQuery.isPending || jobsQuery.isPending || sermonsQuery.isPending;
  const isError = statusQuery.isError || jobsQuery.isError || sermonsQuery.isError;
  return {
    data,
    isLoading,
    error: isError ? "Home data could not be loaded. Check the API bridge and try again." : null,
    retry: () => {
      void statusQuery.refetch();
      void jobsQuery.refetch();
      void sermonsQuery.refetch();
    },
  };
}
