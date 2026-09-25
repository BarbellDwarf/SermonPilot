import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { mediaStreamUrl, writeApi, type ApiMediaItem, ApiError } from "../api/client";
import type { SermonMediaData } from "../api/hooks";
import type { EditPlan, LibrarySermon, PlanStatus, RemoveSegment } from "../mock/data";
import { formatCut, parseCut } from "../utils/time";
import { formatBytes } from "../utils/files";
import { MediaPlayer, type PlayWindow } from "./MediaPlayer";
import { Timeline, type TimelineClip, type TimelineRange } from "./Timeline";
import { TranscriptViewer } from "./TranscriptViewer";
import { sermonActionMatrix } from "./sermonActions";
import { Button, Chip, ConfirmDialog } from "./ui";

export const planStatusLabel: Record<PlanStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  applied_local: "Applied — local",
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

const MOBILE_BREAKPOINT_PX = 1024;

const MOBILE_APPROVAL_BAR_PX = 64;

const menuItemClass =
  "flex min-h-[44px] w-full items-center rounded-md px-3 text-left text-sm font-medium text-mist transition-colors hover:bg-raised disabled:cursor-not-allowed disabled:opacity-45";

function useIsNarrow(breakpoint = MOBILE_BREAKPOINT_PX): boolean {
  const query = `(max-width: ${breakpoint - 1}px)`;
  const read = () =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false;
  const [narrow, setNarrow] = useState(read);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(query);
    const onChange = () => setNarrow(mql.matches);
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, [query]);
  return narrow;
}

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
      errors.push(`Cut ${segment.index + 1} must be at least 0.25 seconds.`);
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

function sameRemoveSegments(left: RemoveSegment[], right: RemoveSegment[]): boolean {
  if (left.length !== right.length) return false;
  return left.every(
    (segment, index) =>
      segment.startSec === right[index]?.startSec && segment.endSec === right[index]?.endSec,
  );
}

export interface DetailsPatch {
  title?: string;
  speaker?: string;
  series_title?: string;
  recorded_date?: string;
  description?: string;
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
  plan: EditPlan;
  history?: EditPlan[];
  sourceDurationSec?: number | null;
  media: SermonMediaData;
  isLive: boolean;
  statusChip?: ReactNode;
  headerActions?: ReactNode;
  transcript?: TranscriptState;
  onSaveDetails?: (patch: DetailsPatch) => Promise<void> | void;
  onRegenerateDescription?: () => void;
  onRefresh?: () => void;
  onToast: (msg: string) => void;
  onUpload?: () => void;
  enhanceDefault?: boolean;
  onShowCompleted?: () => void;
}

function CollapsibleSection({
  id,
  title,
  summary,
  defaultOpen = true,
  open,
  onToggle,
  className = "",
  children,
}: {
  id: string;
  title: string;
  summary?: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onToggle?: (next: boolean) => void;
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
      aria-labelledby={`${id}-h`}
      className={`rounded-lg border border-line bg-surface ${className}`}
    >
      <div className="flex items-center justify-between gap-2 p-3">
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
      <div id={`${id}-body`} hidden={!isOpen} className="border-t border-line p-3">
        {children}
      </div>
    </section>
  );
}

export function SermonReview({
  sermon,
  description,
  descriptionNeedsReview = false,
  plan: initial,
  history: planHistory,
  sourceDurationSec,
  media,
  isLive: live,
  statusChip,
  headerActions,
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
  const [confirmUploadNoDescription, setConfirmUploadNoDescription] = useState(false);
  const [enhance, setEnhance] = useState(enhanceDefault);
  const [refining, setRefining] = useState(false);
  const [notesText, setNotesText] = useState("");
  const [notesOpen, setNotesOpen] = useState(false);
  const [mockNotes, setMockNotes] = useState<{ revision: number; note: string }[]>([]);
  const [statusLog, setStatusLog] = useState<string[]>([]);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [selected, setSelected] = useState<"start" | "end" | null>(null);
  const [removeSegments, setRemoveSegments] = useState<RemoveSegment[]>(
    () => [...(initial.removeSegments ?? [])],
  );
  const [selection, setSelection] = useState<TimelineRange | null>(null);
  const [removalError, setRemovalError] = useState<string | null>(null);
  const [playWindow, setPlayWindow] = useState<PlayWindow | null>(null);
  const [seek, setSeek] = useState<{ sec: number; n: number } | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [playerKind, setPlayerKind] = useState<string>(() => preferredKind(media));
  const [allFilesOpen, setAllFilesOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement | null>(null);
  const narrow = useIsNarrow();
  const [filesOpen, setFilesOpen] = useState(!narrow);
  const [adjustOpen, setAdjustOpen] = useState(!narrow);
  const [form, setForm] = useState({
    title: sermon.title,
    speaker: sermon.speaker,
    series: sermon.series,
    date: sermon.date,
    description: description ?? "",
  });
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    if (!moreOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (moreRef.current && !moreRef.current.contains(event.target as Node)) {
        setMoreOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMoreOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [moreOpen]);

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
    () => normalizeUiRemoveSegments(removeSegments, safeStart, safeEnd),
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

  const errors = useMemo(() => {
    const list: string[] = [];
    if (start === null) list.push("Start is not a valid time (mm:ss.s or seconds).");
    if (end === null) list.push("End is not a valid time (mm:ss.s or seconds).");
    if (offset === null) list.push("Offset is not a valid number (seconds, ±5).");
    if (start !== null && end !== null && end <= start) list.push("End must be after start.");
    if (offset !== null && (offset < -5 || offset > 5)) list.push("Offset must be within ±5 seconds.");
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
  const hasHiddenFiles = previewArtifacts.length > 0;

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
      jumpAtSec: segment.endSec,
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
      [...removeSegments, { startSec: selection.startSec, endSec: selection.endSec }],
      safeStart,
      safeEnd,
    );
    if (next.errors.length > 0) {
      setRemovalError(next.errors[0]);
      return;
    }
    setRemovalError(null);
    setRemoveSegments(next.segments);
    setSelection(null);
  };

  const undoRemoval = (index: number) => {
    setRemoveSegments((current) => current.filter((_, currentIndex) => currentIndex !== index));
    setRemovalError(null);
  };

  const reset = () => {
    setStartText(formatCut(plan.startSec));
    setEndText(formatCut(plan.endSec));
    setOffsetText(plan.offsetSec.toFixed(1));
    setRemoveSegments([...(plan.removeSegments ?? [])]);
    setSelection(null);
    setRemovalError(null);
  };

  const dirty =
    start !== plan.startSec ||
    end !== plan.endSec ||
    offset !== plan.offsetSec ||
    !sameRemoveSegments(removeSegments, plan.removeSegments ?? []);

  const processedAvailable = !!media.byKind.processed?.available;
  const actions = sermonActionMatrix({ status: sermon.status, hasRender: processedAvailable });
  const applyVerb = actions.published ? "Re-render" : "Approve";

  const uploadExisting = (confirmMissingDescription: boolean) => {
    if (uploading) return;
    if (live) {
      setUploading(true);
      void writeApi
        .uploadOnly(sermon.id, { confirm_missing_description: confirmMissingDescription })
        .then(() => {
          setUploading(false);
          setConfirmUploadNoDescription(false);
          onToast("Upload of the existing render queued.");
        })
        .catch((e) => {
          setUploading(false);
          const err = e as ApiError;
          if (err?.code === "missing_description" && !confirmMissingDescription) {
            setConfirmUploadNoDescription(true);
            return;
          }
          if (err?.code === "job_active") {
            onToast("A job is already running for this teaching.");
            return;
          }
          onToast(err?.message || "Could not queue the upload.");
        });
      return;
    }
    setUploading(true);
    window.setTimeout(() => {
      setUploading(false);
      onToast("Upload of the existing render queued (mock).");
    }, 900);
  };

  const approve = (renderOnly: boolean) => {
    if (errors.length > 0 || applying) return;
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
        })
        .then(() => {
          setApplying(false);
          onToast(renderOnly ? "Plan approved, render queued." : "Plan approved, render + upload queued.");
        })
        .catch((e) => {
          setApplying(false);
          const msg = (e as Error).message;
          onToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`);
        });
      return;
    }
    setApplying(true);
    window.setTimeout(() => {
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
          ? "Plan approved, render queued (mock). Previous revision superseded."
          : "Plan approved, render + upload queued (mock). Previous revision superseded.",
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
          onToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`);
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
      onToast("New cut proposal ready (mock). Previous revision superseded.");
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
          onToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`);
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
      onToast("Detection re-run from scratch (mock). Earlier revisions kept in history.");
    }, 900);
  };

  const saveDetails = () => {
    const patch: DetailsPatch = {
      title: form.title,
      speaker: form.speaker,
      series_title: form.series,
      recorded_date: form.date,
      description: form.description,
    };
    setSaveState("saving");
    Promise.resolve(onSaveDetails?.(patch))
      .then(() => setSaveState("saved"))
      .catch(() => setSaveState("error"));
  };

  const detailsDirty =
    form.title !== sermon.title ||
    form.speaker !== sermon.speaker ||
    form.series !== sermon.series ||
    form.date !== sermon.date ||
    form.description !== (description ?? "");

  const statusPills = (
    <div className="flex flex-wrap items-center gap-2">
      <Chip tone={planStatusTone[plan.status]}>Plan: {planStatusLabel[plan.status]}</Chip>
      <span className="font-mono text-xs text-muted">
        revision {plan.revision} of {plan.revisionsTotal}
      </span>
      <span className="font-mono text-xs text-muted">confidence {plan.confidence}%</span>
      <Chip tone={plan.qa === "Pass" ? "ok" : "warn"}>QA: {plan.qa}</Chip>
      <Chip tone={detectionFailed ? "error" : "ok"}>
        Detection: {detectionFailed ? "unavailable" : "ok"}
      </Chip>
    </div>
  );

  const enhanceControl = (
    <label className="flex w-fit flex-wrap items-center gap-2 text-sm text-mist">
      <input
        type="checkbox"
        checked={enhance}
        onChange={(e) => setEnhance(e.target.checked)}
        data-testid="apply-enhance-audio"
        className="h-4 w-4"
      />
      Enhance audio
      <span className="text-xs text-muted">
        {enhance
          ? "requested for this apply (defaults to Audio settings)"
          : "skipped for this apply"}
      </span>
    </label>
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

  return (
    <div data-testid="sermon-review" className="flex flex-col gap-4">
      <header className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight [overflow-wrap:anywhere]">{form.title}</h1>
            <p className="mt-0.5 max-w-prose text-sm text-muted">
              {form.speaker} · {form.date}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {onShowCompleted ? (
              <Button
                data-testid="show-completed-view"
                onClick={onShowCompleted}
              >
                Back to finished view
              </Button>
            ) : null}
            {statusChip}
            {headerActions}
          </div>
        </div>
      </header>

      {narrow ? (
        <section
          data-testid="approval-summary"
          aria-label="Plan status"
          className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3"
        >
          {statusPills}
          {enhanceControl}
        </section>
      ) : null}

      <section
        aria-label="Approval"
        data-testid="approval-bar"
        style={narrow ? { height: MOBILE_APPROVAL_BAR_PX, marginBottom: -MOBILE_APPROVAL_BAR_PX } : undefined}
        className={
          narrow
            ? "sticky top-16 z-20 flex items-center gap-2 rounded-lg border border-line bg-surface px-3 shadow-lg"
            : "flex flex-col gap-2 rounded-lg border border-line bg-surface p-3 shadow-lg lg:static lg:z-auto lg:shadow-none"
        }
      >
        {narrow ? (
          <>
            <Button
              variant="primary"
              className="min-w-0 flex-1 whitespace-nowrap"
              onClick={() => approve(false)}
              disabled={errors.length > 0 || applying}
              aria-busy={applying}
            >
              {applying ? "Queueing…" : applyVerb}
            </Button>
            <div ref={moreRef} className="relative shrink-0">
              <Button
                onClick={() => setMoreOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={moreOpen}
                aria-controls="more-actions"
              >
                More actions
              </Button>
              {moreOpen ? (
                <div
                  id="more-actions"
                  data-testid="more-actions"
                  role="menu"
                  aria-label="More actions"
                  className="absolute right-0 top-full z-40 mt-2 flex w-64 flex-col gap-1 rounded-lg border border-line bg-surface p-2 shadow-2xl"
                >
                  <button
                    type="button"
                    role="menuitem"
                    className={menuItemClass}
                    onClick={() => {
                      setMoreOpen(false);
                      approve(true);
                    }}
                    disabled={errors.length > 0 || applying}
                  >
                    {applyVerb} · Render-only
                  </button>
                  {actions.canUploadExisting ? (
                    <button
                      type="button"
                      role="menuitem"
                      data-testid="upload-existing-render"
                      className={menuItemClass}
                      onClick={() => {
                        setMoreOpen(false);
                        uploadExisting(false);
                      }}
                      disabled={applying || uploading}
                    >
                      {uploading ? "Uploading…" : "Upload existing render"}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    role="menuitem"
                    className={menuItemClass}
                    onClick={() => {
                      setMoreOpen(false);
                      setNotesOpen((v) => !v);
                    }}
                    aria-expanded={notesOpen}
                    aria-controls="refine-notes"
                  >
                    Reject with notes
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className={menuItemClass}
                    onClick={() => {
                      setMoreOpen(false);
                      reDetect();
                    }}
                    disabled={refining}
                  >
                    Re-detect
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className={menuItemClass}
                    onClick={() => {
                      setMoreOpen(false);
                      setHistoryOpen((v) => !v);
                    }}
                    aria-expanded={historyOpen}
                    aria-controls="history"
                  >
                    History
                  </button>
                  {onUpload && actions.canPublishLegacy ? (
                    <button
                      type="button"
                      role="menuitem"
                      className={menuItemClass}
                      onClick={() => {
                        setMoreOpen(false);
                        onUpload();
                      }}
                    >
                      Upload
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <>
            {statusPills}
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="primary" onClick={() => approve(true)} disabled={errors.length > 0 || applying} aria-busy={applying}>
                {applying ? "Queueing…" : `${applyVerb} · Render-only`}
              </Button>
              <Button
                onClick={() => approve(false)}
                disabled={errors.length > 0 || applying}
              >
                {applyVerb} · Render+upload
              </Button>
              {actions.canUploadExisting ? (
                <Button
                  data-testid="upload-existing-render"
                  onClick={() => uploadExisting(false)}
                  disabled={applying || uploading}
                  aria-busy={uploading}
                  title="Publish the render already on disk without re-rendering."
                >
                  {uploading ? "Uploading…" : "Upload existing render"}
                </Button>
              ) : null}
              <Button
                className="w-full min-[480px]:w-auto"
                onClick={() => setNotesOpen((v) => !v)}
                aria-expanded={notesOpen}
                aria-controls="refine-notes"
              >
                Reject with notes
              </Button>
              <Button className="w-full min-[480px]:w-auto" onClick={reDetect} disabled={refining}>
                Re-detect
              </Button>
              <Button onClick={() => setHistoryOpen((v) => !v)} aria-expanded={historyOpen} aria-controls="history">
                History
              </Button>
            </div>
            {enhanceControl}
            {notesPanel}
            {detectionAlert}
          </>
        )}
      </section>

      <div
        data-testid="approval-content"
        style={narrow ? { paddingTop: MOBILE_APPROVAL_BAR_PX } : undefined}
        className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]"
      >
        <div className="flex min-w-0 flex-col gap-4 lg:order-1">
          {narrow ? notesPanel : null}
          {narrow ? detectionAlert : null}
          <CollapsibleSection id="player-plan" title="Player & plan">
            <div className="flex min-w-0 flex-col gap-3">
              {live ? (
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
                  seekToSec={seek?.sec ?? null}
                  seekNonce={seek?.n}
                  playWindow={playWindow}
                  onTime={setPlayhead}
                />
              ) : (
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
                removeSegments={removeSegments}
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
                    const segment = removeSegments[index];
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
                  className="rounded-md border border-warn bg-ink p-3"
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
              {removeSegments.length > 0 ? (
                <section
                  data-testid="removal-list"
                  aria-labelledby="removal-list-heading"
                  className="rounded-md border border-line bg-ink p-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h3 id="removal-list-heading" className="text-sm font-semibold">
                        Interior cuts
                      </h3>
                      <p className="mt-1 text-xs text-muted">
                        Preview each join before approving the plan.
                      </p>
                    </div>
                    <span className="font-mono text-xs text-muted" aria-live="polite">
                      {removeSegments.length === 1
                        ? "1 cut removed"
                        : `${removeSegments.length} cuts removed`}
                    </span>
                  </div>
                  <ul className="mt-3 flex flex-col gap-2">
                    {removeSegments.map((segment, index) => (
                      <li
                        key={`${segment.startSec}-${segment.endSec}-${index}`}
                        data-testid={`removal-item-${index}`}
                        className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium">Cut {index + 1}</p>
                          <p
                            data-testid={`removal-range-${index}`}
                            className="font-mono text-xs text-muted"
                          >
                            {formatCut(segment.startSec)} to {formatCut(segment.endSec)} ·{" "}
                            {formatCut(segment.endSec - segment.startSec)} removed
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            aria-label={`Preview join ${index + 1}`}
                            title="Play 10 seconds before and after this join"
                            onClick={() => playJoin(segment)}
                            className="inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                          >
                            Preview join
                          </button>
                          <button
                            type="button"
                            aria-label={`Undo removal ${index + 1}`}
                            onClick={() => undoRemoval(index)}
                            className="inline-flex min-h-[44px] items-center rounded-md border border-danger px-3 text-xs font-medium text-danger transition-colors hover:bg-danger hover:text-[var(--danger-ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-danger"
                          >
                            Undo
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {clips.map((clip) => (
                  <button
                    key={clip.id}
                    type="button"
                    data-testid={`region-chip-${clip.id}`}
                    onClick={() => playRegion(clip.id, clip.startSec, clip.endSec)}
                    className="inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted"
                  >
                    Play {artifactLabel(clip.id)} · {formatCut(clip.startSec)}
                  </button>
                ))}
              </div>
              <div className="rounded-md border border-line bg-ink">
                <button
                  type="button"
                  data-testid="adjust-cuts-disclosure"
                  onClick={() => setAdjustOpen((v) => !v)}
                  aria-expanded={adjustOpen}
                  aria-controls="adjust-cuts-body"
                  className="flex min-h-[44px] w-full items-center justify-between gap-2 px-3 text-left text-sm font-semibold text-mist"
                >
                  <span>Adjust cuts</span>
                  <span aria-hidden="true" className="font-mono text-xs text-muted">
                    {adjustOpen ? "Hide" : "Show"}
                  </span>
                </button>
                {!adjustOpen ? (
                  <p
                    data-testid="adjust-cuts-summary"
                    className="border-t border-line px-3 py-2 font-mono text-xs text-muted"
                  >
                    Start {formatCut(safeStart)} · End {formatCut(safeEnd)} ·{" "}
                    {finalDuration !== null ? formatCut(finalDuration) : "—"}
                  </p>
                ) : null}
                <fieldset id="adjust-cuts-body" hidden={!adjustOpen} className="border-t border-line p-3">
                  <legend className="sr-only">Adjust cuts</legend>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
                    Computed duration: {duration !== null ? formatCut(duration) : "—"}
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
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={reset} disabled={!dirty || applying}>
                  Reset to plan values
                </Button>
                <Button variant="danger" onClick={() => setConfirmRestore(true)}>
                  Restore original
                </Button>
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection
            id="files"
            title="Files"
            open={filesOpen}
            onToggle={setFilesOpen}
          >
            <div className="flex flex-col gap-3">
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

              <ArtifactGroup id="files-transcripts" title="Transcripts">
                {transcript ? (
                  <div
                    data-testid="transcript-entry"
                    className="rounded-md border border-line bg-ink p-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold">Transcript</p>
                      <div className="flex flex-wrap items-center gap-2">
                        {transcript.open && transcript.plainText ? (
                          <button
                            type="button"
                            onClick={transcript.onCopy}
                            className="inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted"
                          >
                            {transcript.copied ? "Copied" : "Copy"}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={transcript.onToggle}
                          aria-expanded={transcript.open}
                          aria-controls="transcript-body"
                          className="inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted"
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
                          <p className="font-mono text-xs text-muted">Loading transcript…</p>
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
              </ArtifactGroup>

              {hasHiddenFiles ? (
                <div className="flex flex-col gap-3">
                  <button
                    type="button"
                    data-testid="artifacts-disclosure"
                    onClick={() => setAllFilesOpen((v) => !v)}
                    aria-expanded={allFilesOpen}
                    aria-controls="all-files"
                    className="inline-flex min-h-[44px] w-fit items-center rounded-md border border-line px-3 text-sm font-medium text-mist transition-colors hover:border-muted"
                  >
                    {allFilesOpen ? "Hide files" : "Show all files"}
                  </button>
                  <div id="all-files" hidden={!allFilesOpen} className="flex flex-col gap-3">
                    <ArtifactGroup id="files-previews" title="Previews">
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
                    </ArtifactGroup>
                  </div>
                </div>
              ) : null}
            </div>
          </CollapsibleSection>

          <CollapsibleSection
            id="history"
            title="History"
            open={historyOpen}
            onToggle={setHistoryOpen}
            summary={`${noteRows.length} note(s)`}
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
                ? "fixed inset-x-0 bottom-0 z-40 max-h-[80vh] overflow-y-auto rounded-t-2xl border-t border-line bg-surface p-4 shadow-2xl"
                : "hidden"
            } lg:static lg:z-auto lg:block lg:max-h-none lg:overflow-visible lg:rounded-lg lg:border lg:border-line lg:bg-surface lg:p-4 lg:shadow-none`}
          >
            <h2 id="details-h" className="text-lg font-semibold">
              Details
            </h2>
            <form
              className="mt-3 flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                saveDetails();
              }}
            >
              <div>
                <label htmlFor="details-title" className="text-xs font-medium text-muted">
                  Title
                </label>
                <input
                  id="details-title"
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist"
                />
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
                </div>
              </div>
              <div>
                <label htmlFor="details-description" className="text-xs font-medium text-muted">
                  Description
                </label>
                <textarea
                  id="details-description"
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  rows={4}
                  className="mt-1 w-full min-w-0 rounded-md border border-line bg-ink px-3 py-2 text-sm text-mist"
                />
                {descriptionNeedsReview ? (
                  <div
                    role="alert"
                    className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-danger bg-ink p-3 text-sm text-danger"
                  >
                    <span className="font-semibold">Description generation failed - retry.</span>
                    {onRegenerateDescription ? (
                      <Button variant="secondary" onClick={onRegenerateDescription}>
                        Retry generation
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button type="submit" variant="primary" disabled={!detailsDirty || saveState === "saving"}>
                  {saveState === "saving" ? "Saving…" : "Save details"}
                </Button>
                <span data-testid="details-save-state" className="text-xs text-muted" aria-live="polite">
                  {saveState === "saved" ? "Saved" : saveState === "error" ? "Save failed" : ""}
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
          onToast("Original restored (mock). Plan reset to draft.");
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
