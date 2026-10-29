import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  mediaStreamUrl,
  writeApi,
  type ApiMediaItem,
  ApiError,
  type ApiMetadataField,
} from "../api/client";
import type { SermonMediaData } from "../api/hooks";
import type { EditPlan, LibrarySermon, PlanStatus, RemoveSegment } from "../mock/data";
import { formatCut, parseCut } from "../utils/time";
import { formatBytes, formatCount, formatDate, formatDuration } from "../utils/format";
import { MediaPlayer, type PlayWindow } from "./MediaPlayer";
import { Timeline, type TimelineClip, type TimelineRange } from "./Timeline";
import { TranscriptViewer } from "./TranscriptViewer";
import { sermonActionMatrix } from "./sermonActions";
import { Button, Chip, ConfirmDialog, Icon, Menu, PageHeader, Skeleton, Switch, Toggle, buttonClass } from "./ui";

export const planStatusLabel: Record<PlanStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  applied_local: "Applied locally",
  processed: "Processed",
  superseded: "Superseded",
};

const planStatusTone: Record<PlanStatus, string> = {
  draft: "neutral",
  pending_review: "warn",
  applied_local: "info",
  processed: "ok",
  superseded: "neutral",
};

const PRIMARY_KINDS = ["source", "processed", "keeper"] as const;

const PREVIEW_KINDS = ["snippet_start", "snippet_end", "snippet_ending"] as const;

const TRANSCRIPT_KINDS = ["transcript", "transcript_timestamps"] as const;

const chipButtonClass =
  "inline-flex min-h-[44px] items-center rounded-md border border-line bg-raised px-3 text-xs font-semibold text-mist transition-[background-color,border-color,color,filter] duration-150 hover:border-muted hover:brightness-110 active:brightness-95";

function ArtifactGroup({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section data-testid={`artifact-group-${id}`} aria-labelledby={`${id}-group-h`} className="flex flex-col gap-2">
      <h3
        id={`${id}-group-h`}
        className="text-xs font-semibold uppercase tracking-wide text-muted"
      >
        {title}
      </h3>
      {children}
    </section>
  );
}

function ArtifactRow({
  sermonId,
  item,
  testId,
  live,
  onOpen,
}: {
  sermonId: string;
  item: ApiMediaItem;
  testId: string;
  live: boolean;
  onOpen?: (kind: string) => void;
}) {
  const linkClass =
    "inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted";
  return (
    <li
      data-testid={testId}
      className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-ink p-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0">
        <p className="text-sm font-semibold">{item.label || artifactLabel(item.kind)}</p>
        <p className="text-xs text-muted">
          {ARTIFACT_NOTES[item.kind] ?? "Additional processing artifact."} ·{" "}
          {item.available ? formatBytes(item.size) : "not available"}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {item.available && live ? (
          <a href={mediaStreamUrl(sermonId, item.kind)} download className={linkClass}>
            Download
          </a>
        ) : null}
        {item.available && live && onOpen ? (
          <button type="button" onClick={() => onOpen(item.kind)} className={linkClass}>
            Open in player
          </button>
        ) : null}
      </div>
    </li>
  );
}

const ARTIFACT_NOTES: Record<string, string> = {
  source: "The original recording as it was ingested.",
  processed: "The rendered output with the approved cuts applied.",
  keeper: "The retained portion of the teaching, cut ends removed.",
  enhanced: "Noise-reduced audio used for transcription and render.",
  transcript: "Plain-text transcript of the teaching.",
  transcript_timestamps: "Transcript split into timecoded segments.",
  snippet_start: "Preview window around the opening cut.",
  snippet_end: "Preview window around the closing cut.",
  snippet_ending: "Preview window for the proposed ending card.",
};

const MIN_CUT_SECONDS = 0.25;
const JOIN_PREVIEW_SECONDS = 10;

export interface UiCut extends RemoveSegment {
  enabled: boolean;
}

interface CutSnapshot {
  startText: string;
  endText: string;
  cuts: UiCut[];
}

function initialCuts(segments: RemoveSegment[] | undefined): UiCut[] {
  return (segments ?? []).map((segment) => ({ ...segment, enabled: true }));
}

function qaCopy(qa: string): string {
  const value = qa.trim().toLowerCase();
  if (!value || value === "—") return "";
  if (value === "pass") return "No problems found";
  if (value === "review") return "Check the cut points";
  if (value === "fail") return "Automated check flagged this plan";
  return `Automated check: ${qa}`;
}

function normalizeUiRemoveSegments(
  segments: RemoveSegment[],
  startSec: number,
  endSec: number,
): { segments: RemoveSegment[]; errors: string[] } {
  const errors: string[] = [];
  const parsed = segments
    .map((segment, index) => ({ ...segment, index }))
    .sort((left, right) => left.startSec - right.startSec || left.endSec - right.endSec);
  const normalized: RemoveSegment[] = [];
  for (const segment of parsed) {
    if (
      !Number.isFinite(segment.startSec) ||
      !Number.isFinite(segment.endSec) ||
      segment.endSec <= segment.startSec
    ) {
      errors.push(`Cut ${segment.index + 1} must end after it starts.`);
      continue;
    }
    if (segment.endSec - segment.startSec < MIN_CUT_SECONDS) {
      errors.push(`Cut ${segment.index + 1} needs at least 0.25 seconds.`);
      continue;
    }
    if (segment.startSec <= startSec || segment.endSec >= endSec) {
      errors.push(`Cut ${segment.index + 1} must stay inside the keep window.`);
      continue;
    }
    const previous = normalized[normalized.length - 1];
    if (previous && segment.startSec < previous.endSec) {
      errors.push(`Cut ${segment.index + 1} overlaps another cut.`);
      continue;
    }
    if (previous && segment.startSec === previous.endSec) {
      previous.endSec = segment.endSec;
    } else {
      normalized.push({ startSec: segment.startSec, endSec: segment.endSec });
    }
  }
  return { segments: normalized, errors };
}

export interface DetailsPatch {
  title?: string;
  speaker?: string;
  series_title?: string;
  recorded_date?: string;
  description?: string;
  hashtags?: string;
}

export interface TranscriptState {
  open: boolean;
  onToggle: () => void;
  loading: boolean;
  error: string | null;
  plainText: string;
  totalLength: number;
  truncated: boolean;
  timestampsAvailable: boolean;
  copied: boolean;
  onCopy: () => void;
}

export interface SermonReviewProps {
  sermon: LibrarySermon;
  description: string | null;
  descriptionNeedsReview?: boolean;
  hashtags?: string | null;
  plan: EditPlan;
  history?: EditPlan[];
  sourceDurationSec?: number | null;
  media: SermonMediaData;
  isLive: boolean;
  statusChip?: ReactNode;
  onDelete?: () => void;
  deleting?: boolean;
  transcript?: TranscriptState;
  onSaveDetails?: (patch: DetailsPatch) => Promise<void> | void;
  onRegenerateDescription?: () => Promise<void> | void;
  onRefresh?: () => void;
  onToast: (msg: string, variant?: "success" | "error" | "info") => void;
  onUpload?: () => void;
  enhanceDefault?: boolean;
  onShowCompleted?: () => void;
}

export function CollapsibleSection({
  id,
  title,
  summary,
  defaultOpen = false,
  open,
  onToggle,
  testId,
  className = "",
  children,
}: {
  id: string;
  title: string;
  summary?: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onToggle?: (next: boolean) => void;
  testId?: string;
  className?: string;
  children: ReactNode;
}) {
  const [internal, setInternal] = useState(defaultOpen);
  const isOpen = open ?? internal;
  const toggle = () => {
    const next = !isOpen;
    if (onToggle) onToggle(next);
    else setInternal(next);
  };
  return (
    <section
      id={id}
      data-testid={testId}
      aria-labelledby={`${id}-h`}
      className={`rounded-lg border border-line bg-surface ${className}`}
    >
      <div className="flex items-center justify-between gap-2 p-4">
        <div className="min-w-0">
          <h2 id={`${id}-h`} className="text-lg font-semibold">
            {title}
          </h2>
          {summary ? <p className="mt-0.5 text-xs text-muted">{summary}</p> : null}
        </div>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={isOpen}
          aria-controls={`${id}-body`}
          aria-label={`${isOpen ? "Collapse" : "Expand"} ${title}`}
          className="inline-flex min-h-[44px] shrink-0 items-center rounded-md border border-line px-3 text-sm font-medium text-mist transition-colors hover:border-muted"
        >
          {isOpen ? "Hide" : "Show"}
        </button>
      </div>
      <div id={`${id}-body`} hidden={!isOpen} className="border-t border-line p-4">
        {children}
      </div>
    </section>
  );
}

export function SermonReview({
  sermon,
  description,
  descriptionNeedsReview = false,
  hashtags = null,
  plan: initial,
  history: planHistory,
  sourceDurationSec,
  media,
  isLive: live,
  statusChip,
  onDelete,
  deleting = false,
  transcript,
  onSaveDetails,
  onRegenerateDescription,
  onRefresh,
  onToast,
  onUpload,
  enhanceDefault = true,
  onShowCompleted,
}: SermonReviewProps) {
  const [plan, setPlan] = useState(initial);
  const [startText, setStartText] = useState(formatCut(initial.startSec));
  const [endText, setEndText] = useState(formatCut(initial.endSec));
  const [offsetText, setOffsetText] = useState(initial.offsetSec.toFixed(1));
  const [applying, setApplying] = useState(false);
  const [uploading, setUploading] = useState(false);
  const applyInFlight = useRef(false);
  const uploadInFlight = useRef(false);
  const [confirmUploadNoDescription, setConfirmUploadNoDescription] = useState(false);
  const [enhance, setEnhance] = useState(enhanceDefault);
  const [refining, setRefining] = useState(false);
  const [notesText, setNotesText] = useState("");
  const [notesOpen, setNotesOpen] = useState(false);
  const [mockNotes, setMockNotes] = useState<{ revision: number; note: string }[]>([]);
  const [statusLog, setStatusLog] = useState<string[]>([]);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [selected, setSelected] = useState<"start" | "end" | null>(null);
  const [removeSegments, setRemoveSegments] = useState<UiCut[]>(
    () => initialCuts(initial.removeSegments),
  );
  const [cutPast, setCutPast] = useState<CutSnapshot[]>([]);
  const [cutFuture, setCutFuture] = useState<CutSnapshot[]>([]);
  const startRestore = useRef(initial.startSec);
  const endRestore = useRef(initial.endSec);
  const [selection, setSelection] = useState<TimelineRange | null>(null);
  const [removalError, setRemovalError] = useState<string | null>(null);
  const [playWindow, setPlayWindow] = useState<PlayWindow | null>(null);
  const [seek, setSeek] = useState<{ sec: number; n: number } | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [playerKind, setPlayerKind] = useState<string>(() => preferredKind(media));
  const [historyOpen, setHistoryOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  useEffect(() => {
    if (!detailsOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDetailsOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [detailsOpen]);
  const [form, setForm] = useState({
    title: sermon.title,
    speaker: sermon.speaker,
    series: sermon.series,
    date: sermon.date,
    description: description ?? "",
    hashtags: hashtags ?? "",
  });
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [savedForm, setSavedForm] = useState<typeof form | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [generated, setGenerated] = useState<Set<ApiMetadataField>>(() => new Set());
  const [generating, setGenerating] = useState<Set<ApiMetadataField>>(() => new Set());
  const [generateErrors, setGenerateErrors] = useState<
    Partial<Record<ApiMetadataField, string>>
  >({});
  const [descriptionReviewCleared, setDescriptionReviewCleared] = useState(false);
  const planKey = `${initial.sermonId}:${initial.revision}:${initial.startSec}:${initial.endSec}:${initial.offsetSec}:${initial.status}:${JSON.stringify(initial.removeSegments ?? [])}`;
  const planKeyRef = useRef(planKey);

  useEffect(() => {
    if (planKeyRef.current === planKey) return;
    planKeyRef.current = planKey;
    setPlan(initial);
    setStartText(formatCut(initial.startSec));
    setEndText(formatCut(initial.endSec));
    setOffsetText(initial.offsetSec.toFixed(1));
    setRemoveSegments(initialCuts(initial.removeSegments));
    setCutPast([]);
    setCutFuture([]);
    setSelection(null);
    setRemovalError(null);
  }, [initial, planKey]);

  useEffect(() => {
    setForm({
      title: sermon.title,
      speaker: sermon.speaker,
      series: sermon.series,
      date: sermon.date,
      description: description ?? "",
      hashtags: hashtags ?? "",
    });
  }, [
    sermon.title,
    sermon.speaker,
    sermon.series,
    sermon.date,
    description,
    hashtags,
  ]);

  useEffect(() => {
    setGenerated(new Set());
    setGenerateErrors({});
    setDescriptionReviewCleared(false);
    setSaveState("idle");
    setSavedForm(null);
    setSeek(null);
    setPlayhead(0);
    setPlayWindow(null);
  }, [sermon.id]);

  const noteRows = useMemo(() => {
    const fromPlan = (planHistory ?? [])
      .filter((row) => row.notes.trim().length > 0)
      .map((row) => ({ revision: row.revision, note: row.notes.trim() }));
    const merged = [...fromPlan, ...mockNotes];
    const seen = new Set<string>();
    return merged
      .filter((row) => {
        const key = `${row.revision}:${row.note}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => a.revision - b.revision);
  }, [planHistory, mockNotes]);

  const start = parseCut(startText);
  const end = parseCut(endText);
  const offset = parseCut(offsetText);

  const safeStart = start ?? plan.startSec;
  const safeEnd = end ?? plan.endSec;
  const sourceDuration =
    typeof sourceDurationSec === "number" && Number.isFinite(sourceDurationSec) && sourceDurationSec > 0
      ? sourceDurationSec
      : null;
  const knownDuration = [plan.endSec, ...media.items.map((item) => item.end_sec ?? 0)].reduce(
    (largest, value) => (Number.isFinite(value) && value > largest ? value : largest),
    1,
  );
  const timelineDuration = sourceDuration ?? knownDuration;
  const duration = start !== null && end !== null && end > start ? end - start : null;
  const removalValidation = useMemo(
    () =>
      normalizeUiRemoveSegments(
        removeSegments.filter((segment) => segment.enabled),
        safeStart,
        safeEnd,
      ),
    [removeSegments, safeStart, safeEnd],
  );
  const keptDuration =
    duration !== null
      ? Math.max(
          0,
          duration -
            removalValidation.segments.reduce(
              (total, segment) => total + segment.endSec - segment.startSec,
              0,
            ),
        )
      : null;
  const finalDuration = keptDuration ?? duration;
  const removedDuration = duration !== null && keptDuration !== null ? duration - keptDuration : null;
  const enabledRemoveSegments = removeSegments.filter((segment) => segment.enabled);

  const errors = useMemo(() => {
    const list: string[] = [];
    if (start === null) list.push("Start is not a valid time (mm:ss.s or seconds).");
    if (end === null) list.push("End is not a valid time (mm:ss.s or seconds).");
    if (offset === null) list.push("Offset is not a valid number (seconds, ±5).");
    if (start !== null && end !== null && end <= start) list.push("End time must be after the start time.");
    if (offset !== null && (offset < -5 || offset > 5)) list.push("Keep the offset within ±5 seconds.");
    list.push(...removalValidation.errors);
    if (removalError) list.push(removalError);
    return list;
  }, [end, offset, removalError, removalValidation.errors, start]);

  const detectionFailed = plan.detectionStatus === "unavailable";

  const clips = useMemo<TimelineClip[]>(() => {
    const windowFor = (kind: string, fallbackStart: number, fallbackEnd: number): TimelineClip => {
      const item = media.byKind[kind];
      const clipsStart = typeof item?.start_sec === "number" ? item.start_sec : fallbackStart;
      const clipsEnd = typeof item?.end_sec === "number" ? item.end_sec : fallbackEnd;
      return { id: kind, label: ARTIFACT_NOTES[kind] ? artifactLabel(kind) : kind, startSec: clipsStart, endSec: clipsEnd };
    };
    return [
      windowFor("snippet_start", Math.max(safeStart - 10, 0), safeStart + 10),
      windowFor("snippet_end", Math.max(safeEnd - 10, 0), safeEnd + 10),
      windowFor("snippet_ending", Math.max(safeStart, safeEnd - 30), safeEnd),
    ];
  }, [media.byKind, safeStart, safeEnd]);

  const activeKind = media.byKind[playerKind]?.available ? playerKind : preferredKind(media);
  const activeItem = media.byKind[activeKind];

  const primaryArtifacts = PRIMARY_KINDS.map((kind) => media.byKind[kind]).filter(
    (item): item is ApiMediaItem => !!item?.available,
  );
  const extraMediaArtifacts = media.items.filter(
    (item) =>
      item.available &&
      !(PRIMARY_KINDS as readonly string[]).includes(item.kind) &&
      !(TRANSCRIPT_KINDS as readonly string[]).includes(item.kind) &&
      !(PREVIEW_KINDS as readonly string[]).includes(item.kind),
  );
  const previewArtifacts = PREVIEW_KINDS.map((kind) => media.byKind[kind]).filter(
    (item): item is ApiMediaItem => !!item,
  );
  const availablePreviews = previewArtifacts.filter((item) => item.available);

  const requestSeek = (sec: number) => setSeek((previous) => ({ sec, n: (previous?.n ?? 0) + 1 }));

  const playRegion = (_id: string, startSec: number, endSec: number) => {
    requestSeek(startSec);
    setPlayWindow({ startSec, endSec, nonce: (playWindow?.nonce ?? 0) + 1 });
  };

  const playJoin = (segment: RemoveSegment) => {
    const sourceKind = media.byKind.source?.available ? "source" : preferredKind(media);
    if (media.byKind[sourceKind]?.available) setPlayerKind(sourceKind);
    const startSec = Math.max(safeStart, segment.startSec - JOIN_PREVIEW_SECONDS);
    const endSec = Math.min(safeEnd, segment.endSec + JOIN_PREVIEW_SECONDS);
    requestSeek(startSec);
    setPlayWindow({
      startSec,
      endSec,
      nonce: (playWindow?.nonce ?? 0) + 1,
      jumpAtSec: segment.startSec,
      jumpToSec: segment.endSec,
    });
  };

  const addRemoval = () => {
    if (!selection) return;
    if (selection.endSec - selection.startSec < MIN_CUT_SECONDS) {
      setRemovalError("Choose a range of at least 0.25 seconds.");
      return;
    }
    const next = normalizeUiRemoveSegments(
      [...enabledRemoveSegments, { startSec: selection.startSec, endSec: selection.endSec }],
      safeStart,
      safeEnd,
    );
    if (next.errors.length > 0) {
      setRemovalError(next.errors[0]);
      return;
    }
    setRemovalError(null);
    commitCut({
      cuts: [
        ...removeSegments.filter((segment) => !segment.enabled),
        ...next.segments.map((segment) => ({ ...segment, enabled: true })),
      ],
    });
    setSelection(null);
  };

  const undoRemoval = (index: number) => {
    commitCut({ cuts: removeSegments.filter((_, currentIndex) => currentIndex !== index) });
    setRemovalError(null);
  };

  const cutSnapshot = (): CutSnapshot => ({
    startText,
    endText,
    cuts: removeSegments.map((segment) => ({ ...segment })),
  });

  const applyCutSnapshot = (snapshot: CutSnapshot) => {
    setStartText(snapshot.startText);
    setEndText(snapshot.endText);
    setRemoveSegments(snapshot.cuts.map((segment) => ({ ...segment })));
    setSelection(null);
    setRemovalError(null);
  };

  const commitCut = (patch: Partial<CutSnapshot>) => {
    setCutPast((past) => [...past.slice(-49), cutSnapshot()]);
    setCutFuture([]);
    if (patch.startText !== undefined) setStartText(patch.startText);
    if (patch.endText !== undefined) setEndText(patch.endText);
    if (patch.cuts !== undefined) setRemoveSegments(patch.cuts);
  };

  const undoCut = () => {
    const previous = cutPast[cutPast.length - 1];
    if (!previous) return;
    setCutFuture((future) => [cutSnapshot(), ...future].slice(0, 50));
    setCutPast((past) => past.slice(0, -1));
    applyCutSnapshot(previous);
  };

  const redoCut = () => {
    const next = cutFuture[0];
    if (!next) return;
    setCutPast((past) => [...past.slice(-49), cutSnapshot()]);
    setCutFuture((future) => future.slice(1));
    applyCutSnapshot(next);
  };

  const toggleCut = (index: number, enabled: boolean) => {
    commitCut({
      cuts: removeSegments.map((segment, currentIndex) =>
        currentIndex === index ? { ...segment, enabled } : segment,
      ),
    });
  };

  const reset = () => {
    setStartText(formatCut(plan.startSec));
    setEndText(formatCut(plan.endSec));
    setOffsetText(plan.offsetSec.toFixed(1));
    setRemoveSegments(initialCuts(plan.removeSegments));
    setCutPast([]);
    setCutFuture([]);
    setSelection(null);
    setRemovalError(null);
  };

  const dirty =
    start !== plan.startSec ||
    end !== plan.endSec ||
    offset !== plan.offsetSec ||
    removeSegments.length !== (plan.removeSegments ?? []).length ||
    removeSegments.some(
      (segment, index) =>
        !segment.enabled ||
        segment.startSec !== plan.removeSegments?.[index]?.startSec ||
        segment.endSec !== plan.removeSegments?.[index]?.endSec,
    );

  const processedAvailable = !!media.byKind.processed?.available;
  const actions = sermonActionMatrix({ status: sermon.status, hasRender: processedAvailable });
  const applyVerb = actions.published ? "Re-render" : "Approve";

  const uploadExisting = (confirmMissingDescription: boolean) => {
    if (uploadInFlight.current) return;
    uploadInFlight.current = true;
    if (live) {
      setUploading(true);
      void writeApi
        .uploadOnly(sermon.id, { confirm_missing_description: confirmMissingDescription })
        .then(() => {
          uploadInFlight.current = false;
          setUploading(false);
          setConfirmUploadNoDescription(false);
          onToast("Upload of the existing render queued.");
        })
        .catch((e) => {
          uploadInFlight.current = false;
          setUploading(false);
          const err = e as ApiError;
          if (err?.code === "missing_description" && !confirmMissingDescription) {
            setConfirmUploadNoDescription(true);
            return;
          }
          if (err?.code === "job_active") {
            onToast("A job is already running for this teaching.", "info");
            return;
          }
          onToast(err?.message || "Could not queue the upload.", "error");
        });
      return;
    }
    setUploading(true);
    window.setTimeout(() => {
      uploadInFlight.current = false;
      setUploading(false);
      onToast("Upload of the existing render queued (demo).");
    }, 900);
  };

  const approve = (renderOnly: boolean) => {
    if (errors.length > 0 || applyInFlight.current) return;
    applyInFlight.current = true;
    if (live) {
      setApplying(true);
      void writeApi
        .applyPlan(sermon.id, {
          start: start ?? plan.startSec,
          end: end ?? plan.endSec,
          audio_offset: offset ?? plan.offsetSec,
          remove_segments: removalValidation.segments.map((segment) => ({
            start_sec: segment.startSec,
            end_sec: segment.endSec,
          })),
          render_only: renderOnly,
          enhance_audio: enhance,
          generate_metadata: !renderOnly,
        })
        .then(() => {
          applyInFlight.current = false;
          setApplying(false);
          onToast(renderOnly ? "Plan approved, render queued." : "Plan approved, render + upload queued.");
        })
        .catch((e) => {
          applyInFlight.current = false;
          setApplying(false);
          const msg = (e as Error).message;
          onToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`, /409/.test(msg) ? "info" : "error");
        });
      return;
    }
    setApplying(true);
    window.setTimeout(() => {
      applyInFlight.current = false;
      setApplying(false);
      setStatusLog((h) => [...h, `revision ${plan.revision} superseded`]);
      setPlan((p) => ({
        ...p,
        status: "applied_local",
        revision: p.revision + 1,
        revisionsTotal: p.revisionsTotal + 1,
        startSec: start ?? p.startSec,
        endSec: end ?? p.endSec,
        removeSegments: removalValidation.segments,
        offsetSec: offset ?? p.offsetSec,
      }));
      onToast(
        renderOnly
          ? "Plan approved, render queued (demo). Previous revision superseded."
          : "Plan approved, render + upload queued (demo). Previous revision superseded.",
      );
    }, 1200);
  };

  const submitRefine = () => {
    const note = notesText.trim();
    if (!note || refining) return;
    if (live) {
      setRefining(true);
      void writeApi
        .refinePlan(sermon.id, note)
        .then(() => {
          setRefining(false);
          setNotesText("");
          onRefresh?.();
          onToast("Re-detection queued with your notes. The panel updates when the new proposal is ready.");
        })
        .catch((e) => {
          setRefining(false);
          const msg = (e as Error).message;
          onToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`, /409/.test(msg) ? "info" : "error");
        });
      return;
    }
    setRefining(true);
    window.setTimeout(() => {
      setRefining(false);
      setNotesText("");
      const nextRevision = plan.revision + 1;
      setMockNotes((rows) => [...rows, { revision: nextRevision, note }]);
      setStatusLog((h) => [...h, `revision ${plan.revision} superseded`]);
      setPlan((p) => ({
        ...p,
        status: "pending_review",
        revision: nextRevision,
        revisionsTotal: Math.max(p.revisionsTotal, nextRevision),
        reasoning: `Re-ran detection against your note: "${note}".`,
      }));
      onToast("New cut proposal ready (demo). Previous revision superseded.");
    }, 900);
  };

  const reDetect = () => {
    if (refining) return;
    if (live) {
      setRefining(true);
      void writeApi
        .reDetectPlan(sermon.id)
        .then(() => {
          setRefining(false);
          onRefresh?.();
          onToast("Re-detection queued from scratch. Earlier revisions stay in the history.");
        })
        .catch((e) => {
          setRefining(false);
          const msg = (e as Error).message;
          onToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`, /409/.test(msg) ? "info" : "error");
        });
      return;
    }
    setRefining(true);
    window.setTimeout(() => {
      setRefining(false);
      const nextRevision = plan.revision + 1;
      setStatusLog((h) => [...h, `revision ${plan.revision} superseded (re-detect)`]);
      setPlan((p) => ({
        ...p,
        status: "pending_review",
        revision: nextRevision,
        revisionsTotal: Math.max(p.revisionsTotal, nextRevision),
        detectionStatus: "ok",
        reasoning: "Detection re-run from scratch without prior notes.",
      }));
      onToast("Detection re-run from scratch (demo). Earlier revisions kept in history.");
    }, 900);
  };

  const setMetadataValue = (field: ApiMetadataField, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setGenerated((current) => {
      if (!current.has(field)) return current;
      const next = new Set(current);
      next.delete(field);
      return next;
    });
  };

  const generateField = (field: ApiMetadataField) => {
    if (generating.has(field)) return;
    if (!live) {
      onToast("Metadata generation is available in the live console.", "info");
      return;
    }
    setGenerating((current) => new Set(current).add(field));
    setGenerateErrors((current) => ({ ...current, [field]: undefined }));
    void writeApi
      .generateMetadata(sermon.id, field)
      .then((result) => {
        setMetadataValue(field, result.value);
        setGenerated((current) => new Set(current).add(field));
        if (field === "description" && !result.needs_review) {
          setDescriptionReviewCleared(true);
        }
        onToast(`${field} generated.`);
      })
      .catch((e) => {
        const message = (e as Error).message || "Generation failed. Try again.";
        setGenerateErrors((current) => ({ ...current, [field]: message }));
      })
      .finally(() => {
        setGenerating((current) => {
          const next = new Set(current);
          next.delete(field);
          return next;
        });
      });
  };

  const saveDetails = () => {
    const patch: DetailsPatch = {
      title: form.title,
      speaker: form.speaker,
      series_title: form.series,
      recorded_date: form.date,
      description: form.description,
      hashtags: form.hashtags,
    };
    setSaveState("saving");
    Promise.resolve(onSaveDetails?.(patch))
      .then(() => {
        setSaveState("saved");
        setSavedForm({ ...form });
      })
      .catch(() => setSaveState("error"));
  };

  const regenerateDescription = () => {
    if (regenerating || !onRegenerateDescription) return;
    setRegenerating(true);
    Promise.resolve(onRegenerateDescription()).finally(() => setRegenerating(false));
  };

  const detailsDirty = savedForm
    ? (Object.keys(form) as (keyof typeof form)[]).some((key) => form[key] !== savedForm[key])
    : form.title !== sermon.title ||
      form.speaker !== sermon.speaker ||
      form.series !== sermon.series ||
      form.date !== sermon.date ||
      form.description !== (description ?? "") ||
      form.hashtags !== (hashtags ?? "");

  useEffect(() => {
    if (detailsDirty) setSaveState("idle");
  }, [detailsDirty]);

  const confidence =
    plan.confidence > 0 ? `${plan.confidence}% confidence` : null;
  const statusPills = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <Chip tone={planStatusTone[plan.status]}>Cut plan: {planStatusLabel[plan.status]}</Chip>
      {statusChip ? (
        <span className="inline-flex items-center gap-1 text-xs text-muted">
          Teaching status {statusChip}
        </span>
      ) : null}
      <span className="font-mono text-xs text-muted" data-testid="plan-meta">
        Revision {plan.revision} of {plan.revisionsTotal}
        {confidence ? ` · ${confidence}` : ""}
        {qaCopy(plan.qa) ? ` · ${qaCopy(plan.qa)}` : ""}
        {` · ${detectionFailed ? "Cut detection unavailable" : "Cuts found automatically"}`}
      </span>
    </div>
  );

  const toggleStartCut = (enabled: boolean) => {
    if (!enabled) {
      if (safeStart > 0) startRestore.current = safeStart;
      commitCut({ startText: formatCut(0) });
      return;
    }
    const restore = startRestore.current > 0 ? startRestore.current : plan.startSec;
    commitCut({ startText: formatCut(restore > 0 ? restore : 0.5) });
  };

  const toggleEndCut = (enabled: boolean) => {
    if (!enabled) {
      endRestore.current = safeEnd;
      commitCut({ endText: formatCut(timelineDuration) });
      return;
    }
    const restore = endRestore.current > 0 ? endRestore.current : plan.endSec;
    commitCut({ endText: formatCut(restore > 0 ? restore : timelineDuration) });
  };

  const cutRows = [
    {
      id: "start",
      testId: "removal-edge-start",
      durationTestId: "removal-duration-start",
      toggleTestId: "cut-toggle-start",
      label: "Opening trim",
      typeLabel: "Start",
      startSec: 0,
      endSec: safeStart,
      enabled: safeStart > 0,
      toggleLabel: "Include the opening trim",
      onToggle: toggleStartCut,
      removeLabel: "Remove the opening trim",
      removeText: "Remove",
      onRemove: () => toggleStartCut(false),
      previewLabel: "",
      previewText: "",
      onPreview: null as (() => void) | null,
    },
    {
      id: "end",
      testId: "removal-edge-end",
      durationTestId: "removal-duration-end",
      toggleTestId: "cut-toggle-end",
      label: "Closing trim",
      typeLabel: "End",
      startSec: safeEnd,
      endSec: timelineDuration,
      enabled: timelineDuration > safeEnd,
      toggleLabel: "Include the closing trim",
      onToggle: toggleEndCut,
      removeLabel: "Remove the closing trim",
      removeText: "Remove",
      onRemove: () => toggleEndCut(false),
      previewLabel: "",
      previewText: "",
      onPreview: null as (() => void) | null,
    },
    ...removeSegments.map((segment, index) => ({
      id: `interior-${index}`,
      testId: `removal-item-${index}`,
      durationTestId: `removal-duration-${index}`,
      toggleTestId: `cut-toggle-${index}`,
      label: `Cut ${index + 1}`,
      typeLabel: "Interior",
      startSec: segment.startSec,
      endSec: segment.endSec,
      enabled: segment.enabled,
      toggleLabel: `Include cut ${index + 1} in the plan`,
      onToggle: (enabled: boolean) => toggleCut(index, enabled),
      removeLabel: `Remove cut ${index + 1}`,
      removeText: "Remove",
      onRemove: () => undoRemoval(index),
      previewLabel: `Preview join ${index + 1}`,
      previewText: `Preview join ${index + 1}`,
      onPreview: () => playJoin(segment),
    })),
  ];

  const enhanceControl = (
    <Toggle
      checked={enhance}
      onChange={setEnhance}
      label="Enhance audio"
      testId="apply-enhance-audio"
      hint={
        enhance
          ? "Requested for this apply (defaults to Audio settings)."
          : "Skipped for this apply."
      }
    />
  );

  const notesPanel = notesOpen ? (
    <div className="rounded-md border border-line bg-ink p-3">
      <label htmlFor="refine-notes" className="text-sm font-semibold">
        Reject with notes
      </label>
      <p className="mt-1 max-w-prose text-xs text-muted">
        Say what the detector got wrong and it re-reads the transcript with every
        note so far, then returns a new revision. The old proposal is superseded.
      </p>
      <textarea
        id="refine-notes"
        value={notesText}
        onChange={(e) => setNotesText(e.target.value)}
        rows={3}
        disabled={refining}
        placeholder="e.g. Keep only the second of the two back-to-back classes and drop the earlier one."
        className="mt-2 w-full min-w-0 rounded-md border border-line bg-ink px-3 py-2 text-sm text-mist"
      />
      <div className="mt-2">
        <Button
          variant="primary"
          onClick={submitRefine}
          disabled={!notesText.trim() || refining}
          aria-busy={refining}
        >
          {refining ? "Queueing…" : "Re-run with notes"}
        </Button>
      </div>
    </div>
  ) : null;

  const detectionAlert = detectionFailed ? (
    <div role="alert" className="rounded-md border border-danger bg-ink p-3 text-sm text-danger">
      <span className="font-semibold">Cut detection failed.</span> No usable cut points were
      returned, so there is no proposal to review. Enter the start and end below, or re-run
      detection.
    </div>
  ) : null;

  const metadataFieldLabel: Record<ApiMetadataField, string> = {
    title: "title",
    description: "description",
    hashtags: "hashtags",
  };

  const generateControl = (field: ApiMetadataField) => {
    const busy = generating.has(field);
    const label = metadataFieldLabel[field];
    const run = () => generateField(field);
    if (!form[field].trim()) {
      return (
        <Button
          data-testid={`generate-${field}`}
          aria-label={`Generate ${label}`}
          aria-busy={busy}
          onClick={run}
          disabled={busy}
          className="min-w-[7rem] px-3"
        >
          {busy ? "Generating…" : "Generate"}
        </Button>
      );
    }
    return (
      <Menu
        label={`${label} generation options`}
        triggerTestId={`generate-${field}`}
        triggerClassName={buttonClass("secondary", "min-w-[7rem] px-3")}
        trigger={
          <span className="inline-flex items-center gap-2">
            Replace
            <Icon name="chevron" className="h-4 w-4" />
          </span>
        }
        items={[
          {
            label: `Replace ${label} with generated…`,
            onSelect: run,
            disabled: busy,
            testId: `replace-${field}`,
          },
        ]}
        menuClassName="w-64"
      />
    );
  };

  return (
    <div data-testid="sermon-review" className="flex flex-col gap-4">
      <PageHeader
        title={form.title}
        sub={`${form.speaker || "Unknown speaker"} · ${formatDate(form.date)}`}
        actions={
          onShowCompleted ? (
            <Button data-testid="show-completed-view" onClick={onShowCompleted}>
              Back to finished view
            </Button>
          ) : undefined
        }
      />

      <section
        data-testid="approval-summary"
        aria-label="Plan status"
        className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4"
      >
        {statusPills}
        {enhanceControl}
        {detectionAlert}
      </section>

      <div
        data-testid="approval-content"
        className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]"
      >
        <div className="flex min-w-0 flex-col gap-4 lg:order-1">
          <section
            id="player-plan"
            aria-labelledby="player-plan-h"
            className="rounded-lg border border-line bg-surface shadow-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 p-4">
              <div className="min-w-0">
                <h2 id="player-plan-h" className="text-lg font-semibold">
                  Player &amp; plan
                </h2>
                <p className="text-xs text-muted">drag / timeline / cut plan</p>
              </div>
            </div>
            <div className="flex min-w-0 flex-col gap-3 border-t border-line p-4">
              {live && media.error ? (
                <div role="alert" className="flex flex-wrap items-center gap-2 rounded-md border border-danger bg-ink p-3 text-sm text-danger">
                  <span className="min-w-0 flex-1">{media.error}</span>
                  <Button onClick={media.retry}>Retry media</Button>
                </div>
              ) : null}
              {live && !media.error ? (
                <MediaPlayer
                  sermonId={sermon.id}
                  kind={activeKind}
                  contentType={activeItem?.content_type}
                  available={!!activeItem?.available}
                  emptyMessage="No playable media for this teaching yet."
                  markers={[
                    { atSec: safeStart, label: "Start" },
                    { atSec: safeEnd, label: "End" },
                  ]}
                  markerJumps={false}
                  seekToSec={seek?.sec ?? null}
                  seekNonce={seek?.n}
                  playWindow={playWindow}
                  offsetSec={offset ?? plan.offsetSec}
                  onTime={setPlayhead}
                />
              ) : live ? null : (
                <p className="rounded-md border border-dashed border-line bg-ink px-3 py-6 text-center text-sm text-muted">
                  Preview available in the live console.
                </p>
              )}
              <Timeline
                durationSec={timelineDuration}
                startSec={safeStart}
                endSec={safeEnd}
                offsetSec={offset ?? plan.offsetSec}
                endingSec={safeEnd}
                currentSec={playhead}
                clips={clips}
                removeSegments={enabledRemoveSegments}
                selection={selection}
                onChangeSelection={(next) => {
                  setSelection(next);
                  setRemovalError(null);
                }}
                selected={selected}
                onSelect={setSelected}
                onChangeStart={(sec) => {
                  setStartText(formatCut(sec));
                  setSelected("start");
                  setRemovalError(null);
                }}
                onChangeEnd={(sec) => {
                  setEndText(formatCut(sec));
                  setSelected("end");
                  setRemovalError(null);
                }}
                onSeek={(sec, regionId) => {
                  requestSeek(sec);
                  if (regionId === "keep" || regionId.startsWith("snippet_")) {
                    const clip = clips.find((c) => c.id === regionId);
                    if (clip) playRegion(clip.id, clip.startSec, clip.endSec);
                  }
                }}
                onPlayRegion={(regionId, startSec, endSec) => {
                  if (regionId.startsWith("removal_join_")) {
                    const index = Number(regionId.replace("removal_join_", ""));
                    const segment = enabledRemoveSegments[index];
                    if (segment) playJoin(segment);
                    return;
                  }
                  playRegion(regionId, startSec, endSec);
                }}
              />
              {selection ? (
                <section
                  data-testid="removal-selection-panel"
                  aria-labelledby="removal-selection-heading"
                  className="rounded-md border border-warn bg-ink p-3 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 id="removal-selection-heading" className="text-sm font-semibold">
                        Selected range
                      </h3>
                      <p
                        data-testid="removal-selection-range"
                        className="mt-1 font-mono text-sm text-mist"
                      >
                        {formatCut(selection.startSec)} to {formatCut(selection.endSec)}
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        Nudge either handle with the arrow keys, then remove this range.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="danger" onClick={addRemoval}>
                        Cut this out
                      </Button>
                      <Button
                        onClick={() => {
                          setSelection(null);
                          setRemovalError(null);
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                  {removalError ? (
                    <p role="alert" className="mt-2 text-xs text-danger">
                      {removalError}
                    </p>
                  ) : null}
                </section>
              ) : null}
              <section
                data-testid="removal-list"
                aria-labelledby="cut-plan-heading"
                className="rounded-md border border-line bg-ink p-3 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 id="cut-plan-heading" className="text-sm font-semibold">
                      Cut plan
                    </h3>
                    <p className="mt-1 text-xs text-muted">
                      Preview each join, switch a cut off to keep it, then approve the plan.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      onClick={undoCut}
                      disabled={cutPast.length === 0}
                      aria-label="Undo cut edit"
                      data-testid="cut-undo"
                    >
                      Undo
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={redoCut}
                      disabled={cutFuture.length === 0}
                      aria-label="Redo cut edit"
                      data-testid="cut-redo"
                    >
                      Redo
                    </Button>
                  </div>
                </div>
                <div data-testid="cut-table" className="mt-3">
                  <div
                    aria-hidden="true"
                    className="hidden grid-cols-[minmax(0,1.4fr)_5.5rem_5.5rem_5.5rem_4rem_auto] gap-2 border-b border-line pb-1 text-xs font-semibold uppercase tracking-wide text-muted lg:grid"
                  >
                    <span>Cut</span>
                    <span>Start</span>
                    <span>End</span>
                    <span>Duration</span>
                    <span>Included</span>
                    <span className="text-right">Actions</span>
                  </div>
                  <ul className="flex flex-col">
                    {cutRows.map((row) => {
                      const durationSec = Math.max(0, row.endSec - row.startSec);
                      const key = row.id;
                      return (
                        <li
                          key={key}
                          data-testid={row.testId}
                          className="grid min-w-0 grid-cols-2 gap-x-3 gap-y-1 border-t border-line py-2 first:border-t-0 lg:grid-cols-[minmax(0,1.4fr)_5.5rem_5.5rem_5.5rem_4rem_auto] lg:items-center"
                        >
                          <div className="col-span-2 min-w-0 lg:col-span-1">
                            <p className="text-sm font-medium">{row.label}</p>
                            <p className="text-xs text-muted">
                              {row.typeLabel} · {formatDuration(durationSec)}
                            </p>
                          </div>
                          <div className="min-w-0">
                            <span className="text-xs text-muted lg:hidden">Start </span>
                            <span className="font-mono text-xs">{formatCut(row.startSec)}</span>
                          </div>
                          <div className="min-w-0">
                            <span className="text-xs text-muted lg:hidden">End </span>
                            <span className="font-mono text-xs">{formatCut(row.endSec)}</span>
                          </div>
                          <div className="min-w-0">
                            <span className="text-xs text-muted lg:hidden">Duration </span>
                            <span
                              data-testid={row.durationTestId}
                              className="font-mono text-xs"
                            >
                              {formatDuration(durationSec)}
                            </span>
                          </div>
                          <div className="justify-self-start lg:justify-self-center">
                            <Switch
                              checked={row.enabled}
                              onChange={row.onToggle}
                              label={row.toggleLabel}
                              testId={row.toggleTestId}
                            />
                          </div>
                          <div className="col-span-2 flex flex-wrap justify-end gap-2 lg:col-span-1">
                            {row.onPreview ? (
                              <button
                                type="button"
                                aria-label={row.previewLabel}
                                title="Play 10 seconds before and after this join"
                                onClick={row.onPreview}
                                className={chipButtonClass}
                              >
                                {row.previewText}
                              </button>
                            ) : null}
                            <button
                              type="button"
                              aria-label={row.removeLabel}
                              onClick={row.onRemove}
                              disabled={!row.enabled}
                              className="inline-flex min-h-[44px] items-center rounded-md border border-danger px-3 text-xs font-semibold text-danger transition-colors duration-150 hover:bg-danger hover:text-[var(--danger-ink)] disabled:cursor-not-allowed disabled:opacity-45"
                            >
                              {row.removeText}
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
                <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line pt-3">
                  <span data-testid="cut-kept-summary" className="text-sm font-semibold">
                    Kept {formatDuration(finalDuration)}
                  </span>
                  <span className="text-xs text-muted">
                    of {formatDuration(duration)} selected · {formatDuration(removedDuration)} removed ·{" "}
                    {formatCount(removalValidation.segments.length, "cut")}
                  </span>
                </div>
              </section>
              <div className="flex flex-wrap gap-2" aria-label="Clip previews">
                {clips.map((clip) => (
                  <button
                    key={clip.id}
                    type="button"
                    data-testid={`region-chip-${clip.id}`}
                    onClick={() => playRegion(clip.id, clip.startSec, clip.endSec)}
                    className={chipButtonClass}
                  >
                    Play {artifactLabel(clip.id)}
                  </button>
                ))}
              </div>
              <fieldset className="rounded-md border border-line bg-ink p-3">
                <legend className="px-1 text-sm font-semibold">Start &amp; end</legend>
                <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div>
                    <label htmlFor="cut-start" className="text-xs font-medium text-muted">
                      Start (mm:ss.s or seconds)
                    </label>
                    <input
                      id="cut-start"
                      value={startText}
                      onChange={(e) => setStartText(e.target.value)}
                      inputMode="decimal"
                      className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 font-mono text-sm text-mist"
                    />
                  </div>
                  <div>
                    <label htmlFor="cut-end" className="text-xs font-medium text-muted">
                      End (mm:ss.s or seconds)
                    </label>
                    <input
                      id="cut-end"
                      value={endText}
                      onChange={(e) => setEndText(e.target.value)}
                      inputMode="decimal"
                      className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 font-mono text-sm text-mist"
                    />
                  </div>
                  <div>
                    <label htmlFor="cut-offset" className="text-xs font-medium text-muted">
                      Audio offset, s (±5, 0.1 steps)
                    </label>
                    <input
                      id="cut-offset"
                      value={offsetText}
                      onChange={(e) => setOffsetText(e.target.value)}
                      inputMode="decimal"
                      step={0.1}
                      className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 font-mono text-sm text-mist"
                    />
                  </div>
                </div>
                <p className="mt-2 font-mono text-xs text-muted" aria-live="polite">
                  Kept duration: {formatDuration(finalDuration)}
                </p>
                {errors.length > 0 ? (
                  <ul className="mt-2 flex flex-col gap-1" role="alert">
                    {errors.map((e) => (
                      <li key={e} className="text-xs text-danger">
                        {e}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </fieldset>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={reset} disabled={!dirty || applying}>
                  Reset to plan values
                </Button>
                <Button
                  variant="danger"
                  onClick={() => setConfirmRestore(true)}
                  disabled={live}
                  title={live ? "Restore original is not available in the console yet." : undefined}
                >
                  Restore original
                </Button>
              </div>
            </div>
          </section>

          <section
            aria-label="Approval"
            data-testid="approval-bar"
            className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-lg"
          >
            <div className="flex flex-wrap items-center gap-2">
              {refining ? (
                <p role="status" className="basis-full text-xs text-muted">
                  Re-running cut detection. The proposal updates when the new revision is ready.
                </p>
              ) : null}
              {uploading ? (
                <p role="status" className="basis-full text-xs text-muted">
                  Uploading the existing render.
                </p>
              ) : null}
              <Button
                variant="primary"
                data-testid="approve-primary"
                className="min-w-0 flex-1 sm:flex-none"
                onClick={() => approve(false)}
                disabled={errors.length > 0 || applying}
                aria-busy={applying}
                title="Generates any empty title, description, or hashtags, then renders and uploads."
              >
                {applying ? "Queueing…" : `${applyVerb} & upload`}
              </Button>
              <Menu
                label="More actions"
                trigger={
                  <span className="inline-flex items-center gap-2">
                    More actions
                    <Icon name="chevron" className="h-4 w-4" />
                  </span>
                }
                side="top"
                triggerTestId="more-actions-trigger"
                menuTestId="more-actions"
                menuClassName="w-64"
                items={[
                  {
                    label: actions.published ? "Re-render only" : "Render only",
                    onSelect: () => approve(true),
                    disabled: errors.length > 0 || applying,
                    testId: "render-only-action",
                  },
                  ...(actions.canUploadExisting
                    ? [
                        {
                          label: uploading ? "Uploading…" : "Upload existing render",
                          onSelect: () => uploadExisting(false),
                          disabled: applying || uploading,
                          testId: "upload-existing-render",
                        },
                      ]
                    : []),
                  {
                    label: "Reject with notes",
                    onSelect: () => setNotesOpen((value) => !value),
                    expanded: notesOpen,
                    controls: "refine-notes",
                  },
                  {
                    label: "Re-detect",
                    onSelect: reDetect,
                    disabled: refining,
                  },
                  {
                    label: "History",
                    onSelect: () => setHistoryOpen(true),
                    testId: "open-history",
                  },
                  ...(onUpload && actions.canPublishLegacy
                    ? [{ label: "Push to SermonAudio", onSelect: () => onUpload() }]
                    : []),
                  ...(onDelete
                    ? [
                        {
                          label: deleting ? "Deleting…" : "Delete",
                          onSelect: onDelete,
                          disabled: deleting,
                          danger: true,
                          testId: "delete-sermon",
                        },
                      ]
                    : []),
                ]}
              />
            </div>
            {notesPanel}
          </section>

          <div className="flex flex-col gap-3">
            <CollapsibleSection id="files" title="Files" testId="files-panel">
              <ArtifactGroup id="files-media" title="Media">
                {primaryArtifacts.length === 0 && extraMediaArtifacts.length === 0 ? (
                  <p className="text-sm text-muted">No source, render, or keeper files recorded yet.</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {primaryArtifacts.map((item) => (
                      <ArtifactRow
                        key={item.kind}
                        sermonId={sermon.id}
                        item={item}
                        testId="artifact-primary-row"
                        live={live}
                      />
                    ))}
                    {extraMediaArtifacts.map((item) => (
                      <ArtifactRow
                        key={item.kind}
                        sermonId={sermon.id}
                        item={item}
                        testId="artifact-other-row"
                        live={live}
                        onOpen={setPlayerKind}
                      />
                    ))}
                  </ul>
                )}
              </ArtifactGroup>
            </CollapsibleSection>

            <CollapsibleSection id="transcript" title="Transcript" testId="transcript-panel" summary="Plain text and timecoded segments">
              {transcript ? (
                <div data-testid="transcript-entry">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold">Transcript</p>
                    <div className="flex flex-wrap items-center gap-2">
                      {transcript.open && transcript.plainText ? (
                        <button type="button" onClick={transcript.onCopy} className={chipButtonClass}>
                          {transcript.copied ? "Copied" : "Copy"}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={transcript.onToggle}
                        aria-expanded={transcript.open}
                        aria-controls="transcript-body"
                        className={chipButtonClass}
                      >
                        {transcript.open ? "Hide transcript" : "Show transcript"}
                      </button>
                    </div>
                  </div>
                  {transcript.open ? (
                    <div id="transcript-body" className="mt-2">
                      {!live ? (
                        <p className="text-sm text-muted">Transcripts are available in the live bridge.</p>
                      ) : transcript.loading ? (
                        <div className="flex flex-col gap-2"><Skeleton className="h-3 w-4/5" /><Skeleton className="h-3 w-3/5" /><Skeleton className="h-3 w-2/3" /></div>
                      ) : transcript.error ? (
                        <p className="font-mono text-xs text-danger">{transcript.error}</p>
                      ) : transcript.plainText || transcript.timestampsAvailable ? (
                        <>
                          {transcript.plainText ? (
                            <p className="mb-2 font-mono text-xs text-muted">
                              {transcript.totalLength} characters
                              {transcript.truncated ? " (truncated)" : ""}
                            </p>
                          ) : null}
                          <TranscriptViewer
                            id={sermon.id}
                            plainText={transcript.plainText}
                            timestampsAvailable={transcript.timestampsAvailable}
                            onSeek={requestSeek}
                          />
                        </>
                      ) : (
                        <p className="text-sm text-muted">No transcript recorded for this teaching.</p>
                      )}
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="text-sm text-muted">No transcript recorded for this teaching.</p>
              )}
            </CollapsibleSection>

            <CollapsibleSection id="previews" title="Previews" testId="previews-panel">
              {availablePreviews.length === 0 ? (
                <p data-testid="previews-empty" className="text-sm text-muted">
                  Previews appear after a render.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {availablePreviews.map((item) => (
                    <ArtifactRow
                      key={item.kind}
                      sermonId={sermon.id}
                      item={item}
                      testId="artifact-preview-row"
                      live={live}
                      onOpen={setPlayerKind}
                    />
                  ))}
                </ul>
              )}
            </CollapsibleSection>

            <CollapsibleSection
              id="history"
              title="History"
              open={historyOpen}
              onToggle={setHistoryOpen}
              testId="history-panel"
              summary={
                noteRows.length === 0
                  ? "No notes yet"
                  : `${noteRows.length} ${noteRows.length === 1 ? "note" : "notes"}`
              }
            >
              {noteRows.length > 0 ? (
                <ul className="flex flex-col gap-1">
                  {noteRows.map((row) => (
                    <li key={`${row.revision}:${row.note}`} className="text-xs text-muted">
                      <span className="font-mono">revision {row.revision}</span>: {row.note}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">No rejection notes yet.</p>
              )}
              {statusLog.length > 0 ? (
                <p className="mt-2 font-mono text-xs text-muted">{statusLog.join(" · ")}</p>
              ) : null}
              {!detectionFailed && plan.reasoning ? (
                <p className="mt-2 max-w-prose text-sm text-muted">
                  <span className="font-semibold">Reasoning:</span> {plan.reasoning}
                </p>
              ) : null}
              {!detectionFailed ? (
                <dl className="mt-2 grid grid-cols-1 gap-1 font-mono text-xs text-muted sm:grid-cols-3">
                  <div>
                    <dt className="inline">start </dt>
                    <dd className="inline text-mist">{formatCut(plan.startSec)}</dd>
                  </div>
                  <div>
                    <dt className="inline">end </dt>
                    <dd className="inline text-mist">{formatCut(plan.endSec)}</dd>
                  </div>
                  <div>
                    <dt className="inline">offset </dt>
                    <dd className="inline text-mist">
                      {plan.offsetSec >= 0 ? "+" : ""}
                      {plan.offsetSec.toFixed(1)}s
                    </dd>
                  </div>
                </dl>
              ) : null}
            </CollapsibleSection>
          </div>
        </div>

        <aside id="details" aria-labelledby="details-h" className="lg:order-2 lg:sticky lg:top-4 lg:self-start">
          <button
            type="button"
            onClick={() => setDetailsOpen((v) => !v)}
            aria-expanded={detailsOpen}
            aria-controls="details-panel"
            className="inline-flex min-h-[44px] w-full items-center justify-between rounded-md border border-line px-3 text-sm font-semibold text-mist lg:hidden"
          >
            Details
            <span aria-hidden="true" className="font-mono text-xs text-muted">
              {detailsOpen ? "close" : "open"}
            </span>
          </button>
          <div
            id="details-panel"
            data-testid="details-panel"
            className={`${
              detailsOpen
                ? "sheet-panel fixed inset-x-0 bottom-0 z-40 max-h-[80vh] overflow-y-auto rounded-t-2xl border-t border-line bg-surface p-4 shadow-2xl"
                : "hidden"
            } lg:static lg:z-auto lg:block lg:max-h-none lg:overflow-visible lg:rounded-lg lg:border lg:border-line lg:bg-surface lg:p-4 lg:shadow-none`}
          >
            <div className="flex items-center justify-between gap-2">
              <h2 id="details-h" className="text-lg font-semibold">
                Details
              </h2>
              <Button className="lg:hidden" onClick={() => setDetailsOpen(false)} aria-label="Close details">
                Close
              </Button>
            </div>
            <p className="mt-1 text-xs text-muted">Changes stay local until you press Save details.</p>
            <form
              className="mt-3 flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                saveDetails();
              }}
            >
              <details className="rounded-md border border-line p-3">
                <summary className="min-h-[44px] cursor-pointer text-xs font-semibold text-muted">
                  Edit title and speaker
                </summary>
                <div className="mt-2 flex flex-col gap-3">
                  <div>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <label htmlFor="details-title" className="text-xs font-medium text-muted">
                        Title
                      </label>
                      <div className="flex items-center gap-2">
                        {generated.has("title") ? (
                          <span data-testid="generated-title">
                            <Chip tone="info">Generated</Chip>
                          </span>
                        ) : null}
                        {generateControl("title")}
                      </div>
                    </div>
                    <input
                      id="details-title"
                      value={form.title}
                      onChange={(e) => setMetadataValue("title", e.target.value)}
                      aria-invalid={generateErrors.title ? true : undefined}
                      aria-describedby={generateErrors.title ? "generate-error-title" : undefined}
                      className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist"
                    />
                    {generateErrors.title ? (
                      <p
                        id="generate-error-title"
                        role="alert"
                        data-testid="generate-error-title"
                        className="mt-1 rounded-md border border-danger bg-ink px-2 py-1 text-xs text-danger"
                      >
                        {generateErrors.title}
                      </p>
                    ) : null}
                  </div>
                  <div>
                    <label htmlFor="details-speaker" className="text-xs font-medium text-muted">
                      Speaker
                    </label>
                    <input
                      id="details-speaker"
                      value={form.speaker}
                      onChange={(e) => setForm((f) => ({ ...f, speaker: e.target.value }))}
                      className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist"
                    />
                  </div>
                </div>
              </details>
              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <label htmlFor="details-series" className="text-xs font-medium text-muted">
                    Series
                  </label>
                  <input
                    id="details-series"
                    value={form.series}
                    onChange={(e) => setForm((f) => ({ ...f, series: e.target.value }))}
                    className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist"
                  />
                </div>
                <div className="min-w-0">
                  <label htmlFor="details-date" className="text-xs font-medium text-muted">
                    Date
                  </label>
                  <input
                    id="details-date"
                    type="date"
                    value={form.date}
                    onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                    className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist"
                  />
                  <p className="mt-1 text-xs text-muted">Recorded {formatDate(form.date)}</p>
                </div>
              </div>
              <div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label htmlFor="details-description" className="text-xs font-medium text-muted">
                    Description
                  </label>
                  <div className="flex items-center gap-2">
                    {generated.has("description") ? (
                      <span data-testid="generated-description">
                        <Chip tone="info">Generated</Chip>
                      </span>
                    ) : null}
                    {generateControl("description")}
                  </div>
                </div>
                <textarea
                  id="details-description"
                  value={form.description}
                  onChange={(e) => setMetadataValue("description", e.target.value)}
                  aria-invalid={generateErrors.description ? true : undefined}
                  aria-describedby={
                    generateErrors.description ? "generate-error-description" : undefined
                  }
                  rows={4}
                  className="mt-1 w-full min-w-0 rounded-md border border-line bg-ink px-3 py-2 text-sm text-mist"
                />
                {generateErrors.description ? (
                  <p
                    id="generate-error-description"
                    role="alert"
                    data-testid="generate-error-description"
                    className="mt-1 rounded-md border border-danger bg-ink px-2 py-1 text-xs text-danger"
                  >
                    {generateErrors.description}
                  </p>
                ) : null}
                {descriptionNeedsReview && !descriptionReviewCleared ? (
                  <div
                    role="alert"
                    className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-danger bg-ink p-3 text-sm text-danger"
                  >
                    <span className="font-semibold">Description generation failed - retry.</span>
                    {onRegenerateDescription ? (
                      <Button
                        variant="secondary"
                        onClick={regenerateDescription}
                        disabled={regenerating}
                        aria-busy={regenerating}
                      >
                        {regenerating ? "Queueing…" : "Retry generation"}
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label htmlFor="details-hashtags" className="text-xs font-medium text-muted">
                    Hashtags
                  </label>
                  <div className="flex items-center gap-2">
                    {generated.has("hashtags") ? (
                      <span data-testid="generated-hashtags">
                        <Chip tone="info">Generated</Chip>
                      </span>
                    ) : null}
                    {generateControl("hashtags")}
                  </div>
                </div>
                <input
                  id="details-hashtags"
                  value={form.hashtags}
                  onChange={(e) => setMetadataValue("hashtags", e.target.value)}
                  aria-invalid={generateErrors.hashtags ? true : undefined}
                  aria-describedby={generateErrors.hashtags ? "generate-error-hashtags" : undefined}
                  placeholder="#faith #hope"
                  className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist"
                />
                {generateErrors.hashtags ? (
                  <p
                    id="generate-error-hashtags"
                    role="alert"
                    data-testid="generate-error-hashtags"
                    className="mt-1 rounded-md border border-danger bg-ink px-2 py-1 text-xs text-danger"
                  >
                    {generateErrors.hashtags}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="submit"
                  variant="primary"
                  disabled={!onSaveDetails || !detailsDirty || saveState === "saving"}
                >
                  {saveState === "saving" ? "Saving…" : "Save details"}
                </Button>
                <span data-testid="details-save-state" className="text-xs text-muted" aria-live="polite">
                  {saveState === "saving"
                    ? "Saving…"
                    : saveState === "error"
                      ? "Save failed. Try again."
                      : saveState === "saved" && !detailsDirty
                        ? "Saved."
                        : detailsDirty
                          ? "Unsaved changes"
                          : "No unsaved changes"}
                </span>
              </div>
            </form>
          </div>
        </aside>
      </div>

      <ConfirmDialog
        open={confirmRestore}
        title={`Restore original for “${sermon.title}”?`}
        body="All applied cuts are discarded and the unedited source is kept. This cannot be undone."
        confirmLabel="Restore original"
        onClose={() => setConfirmRestore(false)}
        onConfirm={() => {
          setPlan((p) => ({ ...p, status: "draft", revision: 1 }));
          setStatusLog([]);
          onToast("Original restored (demo). Plan reset to draft.");
        }}
      />

      <ConfirmDialog
        open={confirmUploadNoDescription}
        title={`Upload “${sermon.title}” without a description?`}
        body="The description is empty because generation did not finish. Regenerate the description from the transcript before uploading, or upload anyway to publish the entry without one."
        confirmLabel="Upload anyway"
        onClose={() => setConfirmUploadNoDescription(false)}
        onConfirm={() => uploadExisting(true)}
      />
    </div>
  );
}

export function artifactLabel(kind: string): string {
  switch (kind) {
    case "source":
      return "Source media";
    case "processed":
      return "Rendered output";
    case "keeper":
      return "Keeper";
    case "enhanced":
      return "Enhanced audio";
    case "transcript":
      return "Transcript";
    case "transcript_timestamps":
      return "Transcript timestamps";
    case "snippet_start":
      return "Start cut";
    case "snippet_end":
      return "End cut";
    case "snippet_ending":
      return "Proposed ending";
    default:
      return kind;
  }
}

export function preferredKind(media: SermonMediaData): string {
  const order = [media.primary, "processed", "keeper", "source", media.audio, ...media.items.map((i) => i.kind)];
  for (const kind of order) {
    if (kind && media.byKind[kind]?.available) return kind;
  }
  return media.primary ?? "processed";
}
