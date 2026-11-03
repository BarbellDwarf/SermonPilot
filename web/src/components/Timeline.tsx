import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { mediaApi } from "../api/client";
import { formatCut } from "../utils/time";

export interface TimelineClip {
  id: string;
  label: string;
  startSec: number;
  endSec: number;
}

export interface TimelineRange {
  startSec: number;
  endSec: number;
}

export interface TimelineProps {
  durationSec: number;
  startSec: number;
  endSec: number;
  offsetSec?: number;
  endingSec?: number;
  currentSec?: number;
  clips?: TimelineClip[];
  removeSegments?: TimelineRange[];
  selection?: TimelineRange | null;
  onChangeSelection?: (range: TimelineRange | null) => void;
  selected?: "start" | "end" | null;
  onSelect?: (handle: "start" | "end") => void;
  onChangeStart?: (sec: number) => void;
  onChangeEnd?: (sec: number) => void;
  onSeek?: (sec: number, regionId: string) => void;
  onPlayRegion?: (regionId: string, startSec: number, endSec: number) => void;
  onRemoveSegment?: (index: number) => void;
  sermonId?: string;
}

const MIN_GAP_SEC = 0.1;
const MIN_SELECTION_SEC = 0.25;
const WAVEFORM_BARS = 120;
const waveformCache = new Map<string, number[]>();

const ZOOM_OPTIONS = [
  { value: 0, label: "Fit" },
  { value: 120, label: "2m" },
  { value: 60, label: "1m" },
  { value: 30, label: "30s" },
] as const;

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function roundTenths(value: number): number {
  return Math.round(value * 10) / 10;
}

export function timelineSpan(
  durationSec: number | null | undefined,
  _endSec: number,
  _endingSec: number,
  clips: TimelineClip[],
): number {
  if (typeof durationSec === "number" && Number.isFinite(durationSec) && durationSec > 0) {
    return durationSec;
  }
  return clips.reduce(
    (acc, clip) => (Number.isFinite(clip.endSec) && clip.endSec > acc ? clip.endSec : acc),
    1,
  );
}

export function timelinePercent(sec: number, span: number): number {
  return clamp((sec / span) * 100, 0, 100);
}

function shortCut(sec: number): string {
  return formatCut(sec).replace(/\.0$/, "");
}

function Waveform({
  peaks,
  span,
  windowStart,
  windowEnd,
}: {
  peaks: number[] | null;
  span: number;
  windowStart: number;
  windowEnd: number;
}) {
  const bars = useMemo(() => {
    if (!peaks || peaks.length === 0 || span <= 0) {
      return Array.from({ length: WAVEFORM_BARS }, (_, index) => 0.08 + 0.03 * Math.sin(index * 1.7));
    }
    const width = Math.max(windowEnd - windowStart, 0.001);
    return Array.from({ length: WAVEFORM_BARS }, (_, index) => {
      const from = windowStart + (width * index) / WAVEFORM_BARS;
      const to = windowStart + (width * (index + 1)) / WAVEFORM_BARS;
      const first = clamp(Math.floor((from / span) * peaks.length), 0, peaks.length - 1);
      const last = clamp(Math.ceil((to / span) * peaks.length), first + 1, peaks.length);
      let peak = 0;
      for (let cursor = first; cursor < last; cursor += 1) {
        peak = Math.max(peak, peaks[cursor] ?? 0);
      }
      return peak;
    });
  }, [peaks, span, windowStart, windowEnd]);

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 flex items-center gap-px px-1">
      {bars.map((peak, index) => (
        <span
          key={index}
          className="min-h-[2px] flex-1 rounded-full bg-accent/50"
          style={{ height: `${Math.max(peak * 100, 3)}%` }}
        />
      ))}
    </div>
  );
}

export function Timeline({
  durationSec,
  startSec,
  endSec,
  endingSec,
  currentSec = 0,
  clips = [],
  removeSegments = [],
  selection: controlledSelection,
  onChangeSelection,
  selected = null,
  onSelect,
  onChangeStart,
  onChangeEnd,
  onSeek,
  onPlayRegion,
  onRemoveSegment,
  sermonId,
}: TimelineProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const detailRef = useRef<HTMLDivElement | null>(null);
  const selectionStartRef = useRef<HTMLButtonElement | null>(null);
  const focusSelectionOnActivate = useRef(false);
  const dragRef = useRef<"start" | "end" | null>(null);
  const selectionDragRef = useRef<number | null>(null);
  const detailDragRef = useRef<"start" | "end" | "sel-start" | "sel-end" | null>(null);
  const detailSelectionRef = useRef<{ anchor: number; moved: boolean } | null>(null);
  const positionedRef = useRef(false);
  const lastCurrentRef = useRef(currentSec);
  const [selecting, setSelecting] = useState(false);
  const [zoomSec, setZoomSec] = useState(60);
  const [windowStart, setWindowStart] = useState(() => Math.max(startSec - 15, 0));
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [internalSelection, setInternalSelection] = useState<TimelineRange | null>(null);
  const selection = controlledSelection === undefined ? internalSelection : controlledSelection;

  useEffect(() => {
    if (!focusSelectionOnActivate.current || !selecting || !selection) return;
    focusSelectionOnActivate.current = false;
    selectionStartRef.current?.focus();
  }, [selecting, selection]);

  useEffect(() => {
    if (!sermonId) {
      setPeaks(null);
      return;
    }
    const cached = waveformCache.get(sermonId);
    if (cached) {
      setPeaks(cached);
      return;
    }
    let cancelled = false;
    if (!mediaApi?.waveform) return;
    mediaApi
      .waveform(sermonId)
      .then((payload) => {
        const next = Array.isArray(payload.peaks) ? payload.peaks : [];
        waveformCache.set(sermonId, next);
        if (!cancelled) setPeaks(next);
      })
      .catch(() => {
        if (!cancelled) setPeaks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [sermonId]);

  const ending = endingSec ?? endSec;
  const span = timelineSpan(durationSec, endSec, ending, clips);
  const boundedStart = clamp(startSec, 0, span);
  const boundedEnd = clamp(endSec, 0, span);
  const startMax = roundTenths(clamp(boundedEnd - MIN_GAP_SEC, 0, span));
  const endMin = roundTenths(clamp(boundedStart + MIN_GAP_SEC, 0, span));
  const pct = (sec: number) => timelinePercent(sec, span);
  const keepLeft = pct(startSec);
  const keepRight = pct(endSec);
  const keepWidth = Math.max(keepRight - keepLeft, 0);
  const zoom = zoomSec > 0 ? Math.min(zoomSec, span) : span;
  const windowEnd = Math.min(windowStart + zoom, span);

  useEffect(() => {
    if (zoom >= span) {
      setWindowStart(0);
      return;
    }
    const max = Math.max(span - zoom, 0);
    if (!positionedRef.current) {
      positionedRef.current = true;
      lastCurrentRef.current = currentSec;
      setWindowStart((previous) => clamp(previous, 0, max));
      return;
    }
    const headMoved = currentSec !== lastCurrentRef.current;
    lastCurrentRef.current = currentSec;
    setWindowStart((previous) => {
      const current = clamp(previous, 0, max);
      if (!headMoved) return current;
      const head = clamp(currentSec, 0, span);
      if (head < current + zoom * 0.18 || head > current + zoom * 0.82) {
        return roundTenths(clamp(head - zoom / 2, 0, max));
      }
      return current;
    });
  }, [currentSec, span, zoom]);

  const detailPct = (sec: number) => clamp(((sec - windowStart) / Math.max(zoom, 0.001)) * 100, 0, 100);
  const detailVisible = (from: number, to: number) => to >= windowStart && from <= windowEnd;

  const secFromClientX = (clientX: number): number => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return 0;
    const ratio = (clientX - rect.left) / rect.width;
    return roundTenths(clamp(ratio * span, 0, span));
  };

  const secFromDetailX = (clientX: number): number => {
    const rect = detailRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return windowStart;
    const ratio = (clientX - rect.left) / rect.width;
    return roundTenths(clamp(windowStart + ratio * zoom, 0, span));
  };

  const setSelection = (next: TimelineRange | null) => {
    if (controlledSelection === undefined) setInternalSelection(next);
    onChangeSelection?.(next);
  };

  const defaultSelection = (): TimelineRange => {
    const minStart = startSec + MIN_SELECTION_SEC;
    const maxEnd = endSec - MIN_SELECTION_SEC;
    const width = Math.min(1, Math.max(MIN_SELECTION_SEC, maxEnd - minStart));
    const first = roundTenths(
      clamp((minStart + maxEnd) / 2 - width / 2, minStart, maxEnd - width),
    );
    return { startSec: first, endSec: roundTenths(first + width) };
  };

  const toggleSelecting = () => {
    if (selecting) {
      setSelecting(false);
      return;
    }
    focusSelectionOnActivate.current = true;
    setSelecting(true);
    if (!selection) setSelection(defaultSelection());
  };

  const beginDrag = (handle: "start" | "end") => (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    dragRef.current = handle;
    onSelect?.(handle);
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // pointer capture is best-effort; bubbling pointer events still work
    }
  };

  const moveDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const sec = secFromClientX(event.clientX);
    if (selectionDragRef.current !== null) {
      event.preventDefault();
      const anchor = selectionDragRef.current;
      setSelection({
        startSec: roundTenths(Math.min(anchor, sec)),
        endSec: roundTenths(Math.max(anchor, sec)),
      });
      return;
    }
    const handle = dragRef.current;
    if (!handle) return;
    event.preventDefault();
    if (handle === "start") {
      onChangeStart?.(roundTenths(clamp(sec, 0, startMax)));
    } else {
      onChangeEnd?.(roundTenths(clamp(sec, endMin, span)));
    }
  };

  const beginSelection = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!selecting || selectionDragRef.current !== null) return;
    const sec = secFromClientX(event.clientX);
    if (sec <= startSec || sec >= endSec) return;
    event.preventDefault();
    event.stopPropagation();
    selectionDragRef.current = sec;
    setSelection({ startSec: sec, endSec: sec });
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // optional
    }
  };

  const endDrag = () => {
    if (selectionDragRef.current !== null) setSelecting(false);
    dragRef.current = null;
    selectionDragRef.current = null;
  };

  const beginDetailDrag =
    (handle: "start" | "end" | "sel-start" | "sel-end") =>
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
      detailDragRef.current = handle;
      if (handle === "start" || handle === "end") onSelect?.(handle);
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // optional
      }
    };

  const beginDetailSelection = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    const sec = secFromDetailX(event.clientX);
    if (sec <= startSec || sec >= endSec) return;
    event.preventDefault();
    detailSelectionRef.current = { anchor: sec, moved: false };
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // optional
    }
  };

  const moveDetail = (event: ReactPointerEvent<HTMLDivElement>) => {
    const sec = secFromDetailX(event.clientX);
    const selectionDrag = detailSelectionRef.current;
    if (selectionDrag) {
      if (Math.abs(sec - selectionDrag.anchor) >= MIN_SELECTION_SEC) {
        selectionDrag.moved = true;
        setSelection({
          startSec: roundTenths(Math.min(selectionDrag.anchor, sec)),
          endSec: roundTenths(Math.max(selectionDrag.anchor, sec)),
        });
      }
      return;
    }
    const handle = detailDragRef.current;
    if (!handle) return;
    event.preventDefault();
    if (handle === "start") {
      onChangeStart?.(roundTenths(clamp(sec, 0, startMax)));
      return;
    }
    if (handle === "end") {
      onChangeEnd?.(roundTenths(clamp(sec, endMin, span)));
      return;
    }
    if (!selection) return;
    if (handle === "sel-start") {
      setSelection({
        ...selection,
        startSec: roundTenths(clamp(sec, startSec, selection.endSec - MIN_SELECTION_SEC)),
      });
      return;
    }
    setSelection({
      ...selection,
      endSec: roundTenths(clamp(sec, selection.startSec + MIN_SELECTION_SEC, endSec)),
    });
  };

  const endDetail = () => {
    const selectionDrag = detailSelectionRef.current;
    if (selectionDrag && !selectionDrag.moved) {
      onSeek?.(selectionDrag.anchor, "detail");
    }
    detailSelectionRef.current = null;
    detailDragRef.current = null;
  };

  const nudge = (handle: "start" | "end") => (event: KeyboardEvent<HTMLButtonElement>) => {
    const step = event.shiftKey ? 10 : event.altKey ? 0.1 : 1;
    let delta = 0;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") delta = -step;
    else if (event.key === "ArrowRight" || event.key === "ArrowUp") delta = step;
    else return;
    event.preventDefault();
    onSelect?.(handle);
    if (handle === "start") {
      onChangeStart?.(roundTenths(clamp(startSec + delta, 0, startMax)));
    } else {
      onChangeEnd?.(roundTenths(clamp(endSec + delta, endMin, span)));
    }
  };

  const nudgeSelection = (handle: "start" | "end") => (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!selection) return;
    const step = event.shiftKey ? 10 : event.altKey ? 0.1 : 1;
    let delta = 0;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") delta = -step;
    else if (event.key === "ArrowRight" || event.key === "ArrowUp") delta = step;
    else return;
    event.preventDefault();
    if (handle === "start") {
      const next = roundTenths(
        clamp(selection.startSec + delta, startSec, selection.endSec - MIN_SELECTION_SEC),
      );
      setSelection({ ...selection, startSec: next });
    } else {
      const next = roundTenths(
        clamp(selection.endSec + delta, selection.startSec + MIN_SELECTION_SEC, endSec),
      );
      setSelection({ ...selection, endSec: next });
    }
  };

  const seekFromTrack = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current || selectionDragRef.current || selecting) return;
    if (event.target !== event.currentTarget) return;
    const sec = secFromClientX(event.clientX);
    onSeek?.(sec, "track");
  };

  const middleJump = removeSegments[0]?.startSec ?? (startSec + endSec) / 2;

  return (
    <div data-testid="timeline" className="flex flex-col gap-3">
      <div
        ref={trackRef}
        data-testid="timeline-track"
        data-span-sec={span}
        className="relative h-12 w-full touch-pan-y select-none overflow-visible rounded-md border border-line bg-surface shadow-inner"
        onPointerDown={seekFromTrack}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div
          data-testid="timeline-region-cut-before"
          data-region="cut-before"
          data-start-sec={0}
          data-end-sec={startSec}
          style={{ left: "0%", width: `${keepLeft}%` }}
          className="absolute inset-y-0 bg-raised/20"
        />
        <div
          data-testid="timeline-region-cut-after"
          data-region="cut-after"
          data-start-sec={endSec}
          data-end-sec={span}
          style={{ left: `${keepRight}%`, width: `${Math.max(100 - keepRight, 0)}%` }}
          className="absolute inset-y-0 bg-raised/20"
        />
        {zoom < span ? (
          <div
            aria-hidden="true"
            data-testid="timeline-window"
            style={{ left: `${pct(windowStart)}%`, width: `${pct(windowEnd) - pct(windowStart)}%` }}
            className="pointer-events-none absolute inset-y-0 z-[5] border-x border-mist/30 bg-mist/5"
          />
        ) : null}
        {clips.map((clip) => {
          const left = pct(clip.startSec);
          return (
            <button
              key={clip.id}
              type="button"
              data-testid={`timeline-clip-${clip.id}`}
              data-region="clip"
              data-start-sec={clip.startSec}
              data-end-sec={clip.endSec}
              aria-label={`${clip.label} clip, ${clip.startSec}s to ${clip.endSec}s`}
              title={clip.label}
              onClick={(event) => {
                event.stopPropagation();
                onSeek?.(clip.startSec, clip.id);
                onPlayRegion?.(clip.id, clip.startSec, clip.endSec);
              }}
              style={{ left: `${left}%`, touchAction: "none" }}
              className="absolute bottom-0 z-20 h-11 min-w-[44px] -translate-x-1/2 rounded-t border border-transparent bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              <span
                aria-hidden="true"
                className="absolute inset-x-0 bottom-0 h-2 rounded-sm bg-accent/60"
              />
            </button>
          );
        })}
        <button
          type="button"
          data-testid="timeline-region-keep"
          data-region="keep"
          data-start-sec={startSec}
          data-end-sec={endSec}
          aria-label={`Keep region, ${startSec}s to ${endSec}s`}
          onClick={(event) => {
            event.stopPropagation();
            onSeek?.(startSec, "keep");
            onPlayRegion?.("keep", startSec, endSec);
          }}
          style={{ left: `${keepLeft}%`, width: `${keepWidth}%`, touchAction: "none" }}
          className="absolute inset-y-0 z-10 rounded-[3px] border-x border-accent/70 bg-accent/25 transition-colors hover:bg-accent/35"
        />
        <div
          data-testid="timeline-selection-surface"
          onPointerDown={beginSelection}
          onClick={(event) => event.stopPropagation()}
          style={{ left: `${keepLeft}%`, width: `${keepWidth}%` }}
          className={`absolute inset-y-0 z-[15] touch-none ${
            selecting ? "pointer-events-auto cursor-crosshair" : "pointer-events-none"
          }`}
        />
        {removeSegments.map((segment, index) => {
          const left = pct(segment.startSec);
          const width = Math.max(pct(segment.endSec) - left, 0);
          return (
            <button
              key={`${segment.startSec}-${segment.endSec}-${index}`}
              type="button"
              data-testid={`timeline-removal-${index}`}
              data-region="removal"
              data-start-sec={segment.startSec}
              data-end-sec={segment.endSec}
              aria-label={`Removal ${index + 1}, ${segment.startSec}s to ${segment.endSec}s`}
              title={`Removal ${index + 1}`}
              onClick={(event) => {
                event.stopPropagation();
                onSeek?.(segment.startSec, `removal_${index}`);
                onPlayRegion?.(`removal_join_${index}`, segment.startSec, segment.endSec);
              }}
              style={{ left: `${left}%`, width: `${Math.max(width, 0.6)}%` }}
              className="absolute bottom-0 z-30 h-11 min-w-[24px] bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-danger"
            >
              <span
                aria-hidden="true"
                className="absolute inset-x-0 bottom-0 h-1 border-y border-danger/60 bg-danger/60"
              />
            </button>
          );
        })}
        {selection ? (
          <>
            <div
              data-testid="timeline-selection"
              data-start-sec={selection.startSec}
              data-end-sec={selection.endSec}
              style={{
                left: `${pct(selection.startSec)}%`,
                width: `${Math.max(pct(selection.endSec) - pct(selection.startSec), 0.6)}%`,
              }}
              className="pointer-events-none absolute inset-y-2 z-40 rounded-sm border border-warn bg-warn/12"
            />
            <button
              ref={selectionStartRef}
              type="button"
              role="slider"
              data-testid="timeline-selection-handle-start"
              aria-label="Removal selection start"
              aria-orientation="horizontal"
              aria-valuemin={startSec}
              aria-valuemax={Math.max(startSec, selection.endSec - MIN_SELECTION_SEC)}
              aria-valuenow={selection.startSec}
              tabIndex={0}
              style={{ left: `${pct(selection.startSec)}%` }}
              onKeyDown={nudgeSelection("start")}
              className="absolute inset-y-0 z-50 w-11 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-warn"
            >
              <span aria-hidden="true" className="absolute inset-y-2 left-1/2 w-0.5 -translate-x-1/2 bg-warn" />
              <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-warn" />
            </button>
            <button
              type="button"
              role="slider"
              data-testid="timeline-selection-handle-end"
              aria-label="Removal selection end"
              aria-orientation="horizontal"
              aria-valuemin={Math.min(endSec, selection.startSec + MIN_SELECTION_SEC)}
              aria-valuemax={endSec}
              aria-valuenow={selection.endSec}
              tabIndex={0}
              style={{ left: `${pct(selection.endSec)}%` }}
              onKeyDown={nudgeSelection("end")}
              className="absolute inset-y-0 z-50 w-11 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-warn"
            >
              <span aria-hidden="true" className="absolute inset-y-2 left-1/2 w-0.5 -translate-x-1/2 bg-warn" />
              <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-warn" />
            </button>
          </>
        ) : null}
        <div
          data-testid="timeline-region-ending"
          data-region="ending"
          data-start-sec={ending}
          data-end-sec={ending}
          title="Ending card"
          style={{ left: `${pct(ending)}%` }}
          className="absolute inset-y-0 z-20 w-1 -translate-x-1/2 bg-warn"
        />
        <div
          data-testid="timeline-playhead"
          data-current-sec={currentSec}
          aria-hidden="true"
          style={{ left: `${pct(currentSec)}%` }}
          className="absolute inset-y-0 z-30 w-0.5 -translate-x-1/2 rounded-full bg-mist shadow-[0_0_8px_rgba(233,237,239,0.4)]"
        >
          <span
            aria-hidden="true"
            className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-mist shadow"
          />
        </div>
        <button
          type="button"
          role="slider"
          data-testid="timeline-handle-start"
          aria-label="Keep start"
          aria-orientation="horizontal"
          aria-valuemin={0}
          aria-valuemax={startMax}
          aria-valuenow={clamp(startSec, 0, startMax)}
          tabIndex={0}
          style={{ left: `${keepLeft}%`, touchAction: "none" }}
          onPointerDown={beginDrag("start")}
          onKeyDown={nudge("start")}
          className="absolute inset-y-0 z-40 w-11 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span
            aria-hidden="true"
            className={`absolute left-1/2 top-1/2 h-5 w-6 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-accent/70 bg-surface shadow-sm ${
              selected === "start" ? "ring-2 ring-accent" : ""
            }`}
          />
          <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-3 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-accent" />
        </button>
        <button
          type="button"
          role="slider"
          data-testid="timeline-handle-end"
          aria-label="Keep end"
          aria-orientation="horizontal"
          aria-valuemin={endMin}
          aria-valuemax={span}
          aria-valuenow={clamp(endSec, endMin, span)}
          tabIndex={0}
          style={{ left: `${keepRight}%`, touchAction: "none" }}
          onPointerDown={beginDrag("end")}
          onKeyDown={nudge("end")}
          className="absolute inset-y-0 z-40 w-11 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span
            aria-hidden="true"
            className={`absolute left-1/2 top-1/2 h-5 w-6 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-accent/70 bg-surface shadow-sm ${
              selected === "end" ? "ring-2 ring-accent" : ""
            }`}
          />
          <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-3 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-accent" />
        </button>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-between px-1 font-mono text-[9px] text-muted">
          <span>{shortCut(0)}</span>
          <span>{shortCut(span / 2)}</span>
          <span>{shortCut(span)}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1">
          <span className="px-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Jump</span>
          <button
            type="button"
            onClick={() => onSeek?.(startSec, "jump-start")}
            className="min-h-[36px] rounded-md border border-line bg-raised px-2 text-[11px] font-semibold text-mist transition-colors hover:border-accent"
          >
            Opening
          </button>
          <button
            type="button"
            onClick={() => onSeek?.(middleJump, "jump-middle")}
            className="min-h-[36px] rounded-md border border-line bg-raised px-2 text-[11px] font-semibold text-mist transition-colors hover:border-accent"
          >
            Middle
          </button>
          <button
            type="button"
            onClick={() => onSeek?.(endSec, "jump-end")}
            className="min-h-[36px] rounded-md border border-line bg-raised px-2 text-[11px] font-semibold text-mist transition-colors hover:border-accent"
          >
            Closing
          </button>
        </div>
        <div className="flex items-center gap-1">
          <span className="px-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Zoom</span>
          {ZOOM_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={zoomSec === option.value}
              onClick={() => setZoomSec(option.value)}
              className={`min-h-[36px] rounded-md border px-2 text-[11px] font-semibold transition-colors ${
                zoomSec === option.value
                  ? "border-accent bg-accent/15 text-accent"
                  : "border-line bg-raised text-mist hover:border-accent"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-md border border-line bg-surface p-2 shadow-inner">
        <div className="mx-3">
          <div
            ref={detailRef}
            data-testid="timeline-detail"
            data-window-start={windowStart}
            data-window-end={windowEnd}
            className="relative h-28 w-full touch-none select-none overflow-visible rounded-sm bg-ink/60"
            onPointerDown={beginDetailSelection}
            onPointerMove={moveDetail}
            onPointerUp={endDetail}
            onPointerCancel={endDetail}
          >
            <Waveform peaks={peaks} span={span} windowStart={windowStart} windowEnd={windowEnd} />
            {detailVisible(0, startSec) ? (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 left-0 bg-raised/40"
                style={{ width: `${detailPct(startSec)}%` }}
              />
            ) : null}
            {detailVisible(endSec, span) ? (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 right-0 bg-raised/40"
                style={{ width: `${Math.max(100 - detailPct(endSec), 0)}%` }}
              />
            ) : null}
            {removeSegments.map((segment, index) => {
              if (!detailVisible(segment.startSec, segment.endSec)) return null;
              const left = detailPct(segment.startSec);
              const width = Math.max(detailPct(segment.endSec) - left, 0.6);
              return (
                <div
                  key={`detail-${segment.startSec}-${segment.endSec}-${index}`}
                  data-testid={`timeline-detail-removal-${index}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`Cut ${index + 1}, ${shortCut(segment.startSec)} to ${shortCut(segment.endSec)}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSeek?.(segment.startSec, `detail_removal_${index}`);
                  }}
                  onKeyDown={(event) => {
                    if (event.key !== "Enter" && event.key !== " ") return;
                    event.preventDefault();
                    onSeek?.(segment.startSec, `detail_removal_${index}`);
                  }}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  className="absolute inset-y-0 z-10 cursor-pointer border-x-2 border-danger/80 bg-danger/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-danger"
                >
                  <button
                    type="button"
                    aria-label={`Delete cut ${index + 1} on timeline`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemoveSegment?.(index);
                    }}
                    className="absolute -top-2 right-0 z-20 grid h-6 w-6 place-items-center rounded-full border border-danger/60 bg-ink text-xs text-danger shadow"
                  >
                    ×
                  </button>
                </div>
              );
            })}
            {selection && detailVisible(selection.startSec, selection.endSec) ? (
              <>
                <div
                  aria-hidden="true"
                  style={{
                    left: `${detailPct(selection.startSec)}%`,
                    width: `${Math.max(detailPct(selection.endSec) - detailPct(selection.startSec), 0.6)}%`,
                  }}
                  className="pointer-events-none absolute inset-y-0 z-20 border border-warn bg-warn/15"
                />
                <button
                  type="button"
                  role="slider"
                  data-testid="timeline-detail-selection-handle-start"
                  aria-label="Detail removal selection start"
                  aria-valuemin={startSec}
                  aria-valuemax={Math.max(startSec, selection.endSec - MIN_SELECTION_SEC)}
                  aria-valuenow={selection.startSec}
                  style={{ left: `${detailPct(selection.startSec)}%` }}
                  onPointerDown={beginDetailDrag("sel-start")}
                  onKeyDown={nudgeSelection("start")}
                  className="absolute inset-y-0 z-40 w-8 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-warn"
                >
                  <span aria-hidden="true" className="absolute inset-y-1 left-1/2 w-0.5 -translate-x-1/2 bg-warn" />
                </button>
                <button
                  type="button"
                  role="slider"
                  data-testid="timeline-detail-selection-handle-end"
                  aria-label="Detail removal selection end"
                  aria-valuemin={Math.min(endSec, selection.startSec + MIN_SELECTION_SEC)}
                  aria-valuemax={endSec}
                  aria-valuenow={selection.endSec}
                  style={{ left: `${detailPct(selection.endSec)}%` }}
                  onPointerDown={beginDetailDrag("sel-end")}
                  onKeyDown={nudgeSelection("end")}
                  className="absolute inset-y-0 z-40 w-8 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-warn"
                >
                  <span aria-hidden="true" className="absolute inset-y-1 left-1/2 w-0.5 -translate-x-1/2 bg-warn" />
                </button>
              </>
            ) : null}
            {detailVisible(ending, ending) ? (
              <div
                aria-hidden="true"
                style={{ left: `${detailPct(ending)}%` }}
                className="pointer-events-none absolute inset-y-0 z-20 w-0.5 -translate-x-1/2 bg-warn"
              />
            ) : null}
            <div
              aria-hidden="true"
              style={{ left: `${detailPct(currentSec)}%` }}
              className="pointer-events-none absolute inset-y-0 z-30 w-0.5 -translate-x-1/2 bg-mist shadow-[0_0_8px_rgba(233,237,239,0.4)]"
            >
              <span className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-mist" />
            </div>
            {detailVisible(startSec, startSec) ? (
              <button
                type="button"
                role="slider"
                data-testid="timeline-detail-handle-start"
                aria-label="Detail keep start"
                aria-valuemin={0}
                aria-valuemax={startMax}
                aria-valuenow={clamp(startSec, 0, startMax)}
                style={{ left: `${detailPct(startSec)}%` }}
                onPointerDown={beginDetailDrag("start")}
                onKeyDown={nudge("start")}
                className="absolute inset-y-0 z-40 w-11 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
              >
                <span aria-hidden="true" className="absolute inset-y-2 left-1/2 w-1.5 -translate-x-1/2 rounded-full bg-accent shadow-[0_0_10px_rgba(139,92,246,0.55)]" />
                <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-ink" />
              </button>
            ) : null}
            {detailVisible(endSec, endSec) ? (
              <button
                type="button"
                role="slider"
                data-testid="timeline-detail-handle-end"
                aria-label="Detail keep end"
                aria-valuemin={endMin}
                aria-valuemax={span}
                aria-valuenow={clamp(endSec, endMin, span)}
                style={{ left: `${detailPct(endSec)}%` }}
                onPointerDown={beginDetailDrag("end")}
                onKeyDown={nudge("end")}
                className="absolute inset-y-0 z-40 w-11 -translate-x-1/2 cursor-ew-resize bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
              >
                <span aria-hidden="true" className="absolute inset-y-2 left-1/2 w-1.5 -translate-x-1/2 rounded-full bg-accent shadow-[0_0_10px_rgba(139,92,246,0.55)]" />
                <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-ink" />
              </button>
            ) : null}
          </div>
          <div className="mt-1 flex justify-between font-mono text-[10px] text-muted">
            <span>{shortCut(windowStart)}</span>
            <span>{shortCut(windowStart + zoom / 2)}</span>
            <span>{shortCut(windowEnd)}</span>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          data-testid="timeline-select-removal"
          aria-pressed={selecting}
          onClick={toggleSelecting}
          className="inline-flex min-h-[44px] items-center rounded-md border border-line bg-raised px-3 text-xs font-semibold text-mist transition-colors hover:border-warn focus-visible:outline focus-visible:outline-2 focus-visible:outline-warn"
        >
          {selecting ? "Finish selecting range" : "Select a range to cut"}
        </button>
        <span className="font-mono text-xs text-muted" aria-live="polite">
          {removeSegments.length === 1 ? "1 cut removed" : `${removeSegments.length} cuts removed`}
        </span>
      </div>
    </div>
  );
}
