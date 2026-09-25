import { useRef, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";

export interface TimelineClip {
  id: string;
  label: string;
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
  selected?: "start" | "end" | null;
  onSelect?: (handle: "start" | "end") => void;
  onChangeStart?: (sec: number) => void;
  onChangeEnd?: (sec: number) => void;
  onSeek?: (sec: number, regionId: string) => void;
  onPlayRegion?: (regionId: string, startSec: number, endSec: number) => void;
}

const MIN_GAP_SEC = 0.1;

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

export function Timeline({
  durationSec,
  startSec,
  endSec,
  offsetSec = 0,
  endingSec,
  currentSec = 0,
  clips = [],
  selected = null,
  onSelect,
  onChangeStart,
  onChangeEnd,
  onSeek,
  onPlayRegion,
}: TimelineProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<"start" | "end" | null>(null);
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

  const secFromClientX = (clientX: number): number => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return 0;
    const ratio = (clientX - rect.left) / rect.width;
    return roundTenths(clamp(ratio * span, 0, span));
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
    const handle = dragRef.current;
    if (!handle) return;
    event.preventDefault();
    const sec = secFromClientX(event.clientX);
    if (handle === "start") {
      onChangeStart?.(roundTenths(clamp(sec, 0, startMax)));
    } else {
      onChangeEnd?.(roundTenths(clamp(sec, endMin, span)));
    }
  };

  const endDrag = () => {
    dragRef.current = null;
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

  const seekFromTrack = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current) return;
    if (event.target !== event.currentTarget) return;
    const sec = secFromClientX(event.clientX);
    onSeek?.(sec, "track");
  };

  return (
    <div data-testid="timeline" className="flex flex-col gap-2">
      <div
        ref={trackRef}
        data-testid="timeline-track"
        data-span-sec={span}
        className="relative h-14 w-full touch-pan-y select-none overflow-visible rounded-md border border-line bg-ink"
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
          className="absolute inset-y-0 bg-raised/70"
        />
        <div
          data-testid="timeline-region-cut-after"
          data-region="cut-after"
          data-start-sec={endSec}
          data-end-sec={span}
          style={{ left: `${keepRight}%`, width: `${Math.max(100 - keepRight, 0)}%` }}
          className="absolute inset-y-0 bg-raised/70"
        />
        {clips.map((clip) => {
          const left = pct(clip.startSec);
          const width = Math.max(pct(clip.endSec) - left, 0);
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
              style={{ left: `${left}%`, width: `${Math.max(width, 0.6)}%`, touchAction: "none" }}
              className="absolute bottom-0 z-20 h-2 rounded-t border border-accent/60 bg-accent/40 before:absolute before:-top-9 before:inset-x-0 before:h-11 before:content-['']"
            />
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
          className="absolute inset-y-0 z-10 border-x border-accent bg-accent/25 transition-colors hover:bg-accent/35"
        />
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
          className="absolute inset-y-0 z-30 w-0.5 -translate-x-1/2 bg-mist"
        />
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
            className={`absolute inset-y-0 left-1/2 w-4 -translate-x-1/2 border border-accent bg-surface ${
              selected === "start" ? "ring-2 ring-accent" : ""
            }`}
          />
          <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-accent" />
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
            className={`absolute inset-y-0 left-1/2 w-4 -translate-x-1/2 border border-accent bg-surface ${
              selected === "end" ? "ring-2 ring-accent" : ""
            }`}
          />
          <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-accent" />
        </button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-xs text-muted">
        <span data-testid="timeline-offset">offset {offsetSec >= 0 ? "+" : ""}{offsetSec.toFixed(1)}s</span>
        <span data-testid="timeline-labels">
          keep {startSec.toFixed(1)}s – {endSec.toFixed(1)}s · ending {ending.toFixed(1)}s
        </span>
      </div>
    </div>
  );
}
