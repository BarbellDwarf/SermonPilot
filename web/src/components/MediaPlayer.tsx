import { useEffect, useRef, useState, type RefObject } from "react";
import { mediaStreamUrl } from "../api/client";
import { formatCut } from "../utils/time";

export interface MediaMarker {
  atSec: number;
  label: string;
}

export interface PlayWindow {
  startSec: number;
  endSec: number;
  nonce: number;
  jumpAtSec?: number;
  jumpToSec?: number;
}

interface MediaPlayerProps {
  sermonId: string;
  kind: string;
  contentType?: string | null;
  available: boolean;
  emptyMessage?: string;
  markers?: MediaMarker[];
  markerJumps?: boolean;
  seekToSec?: number | null;
  seekNonce?: number;
  playWindow?: PlayWindow | null;
  onTime?: (sec: number) => void;
  label?: string;
  timeLabel?: string;
  className?: string;
  offsetSec?: number;
}

export function isVideoContent(contentType?: string | null, kind = ""): boolean {
  if (contentType?.startsWith("video/")) return true;
  if (contentType?.startsWith("audio/")) return false;
  return kind === "keeper" || kind.startsWith("snippet_");
}

export function MediaPlayer({
  sermonId,
  kind,
  contentType,
  available,
  emptyMessage,
  markers = [],
  markerJumps = true,
  seekToSec = null,
  seekNonce = 0,
  playWindow = null,
  onTime,
  label,
  timeLabel = "Playback",
  className = "",
  offsetSec = 0,
}: MediaPlayerProps) {
  const mediaRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [failed, setFailed] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  const offset = Number.isFinite(offsetSec) ? (offsetSec as number) : 0;
  const applySeek = (element: HTMLMediaElement | null) => {
    if (seekToSec == null || !element) return;
    try {
      element.currentTime = Math.max(0, seekToSec);
      const audio = audioRef.current;
      if (audio && offset !== 0) {
        const desired = Math.max(0, seekToSec + offset);
        if (Number.isFinite(desired)) audio.currentTime = desired;
      }
    } catch {
      // metadata not loaded yet; onLoadedMetadata re-applies the request
    }
  };

  useEffect(() => {
    setFailed(false);
  }, [sermonId, kind]);

  useEffect(() => {
    applySeek(mediaRef.current);
  }, [seekToSec, seekNonce]);

  useEffect(() => {
    const element = mediaRef.current;
    if (!playWindow || !element) return;
    try {
      element.currentTime = Math.max(0, playWindow.startSec);
    } catch {
      // metadata not loaded yet; playback starts from the beginning
    }
    let jumped = false;
    const stopAt = () => {
      if (
        playWindow.jumpAtSec !== undefined &&
        playWindow.jumpToSec !== undefined &&
        !jumped &&
        element.currentTime >= playWindow.jumpAtSec
      ) {
        jumped = true;
        try {
          element.currentTime = Math.max(0, playWindow.jumpToSec);
        } catch {
        }
      }
      if (element.currentTime >= playWindow.endSec) {
        try {
          element.pause();
        } catch {
          // pause is best-effort
        }
        element.removeEventListener("timeupdate", stopAt);
      }
    };
    element.addEventListener("timeupdate", stopAt);
    try {
      const result = element.play();
      if (result && typeof result.catch === "function") void result.catch(() => {});
    } catch {
      // autoplay may be blocked; the user can press play
    }
    return () => element.removeEventListener("timeupdate", stopAt);
  }, [playWindow?.nonce]);

  if (!available || failed) {
    return (
      <div
        data-testid="media-empty"
        className={`flex min-h-[64px] items-center justify-center rounded-md border border-dashed border-line bg-ink px-3 py-6 ${className}`}
      >
        <p className="text-center text-sm text-muted">
          {failed ? "Preview unavailable." : (emptyMessage ?? "Not rendered yet.")}
        </p>
      </div>
    );
  }

  const src = mediaStreamUrl(sermonId, kind);
  const video = isVideoContent(contentType, kind);
  const position = (sec: number) =>
    Number.isFinite(duration) && duration > 0 ? Math.min(100, Math.max(0, (sec / duration) * 100)) : 0;
  const seek = (sec: number) => {
    const element = mediaRef.current;
    if (element) element.currentTime = Math.max(0, sec);
  };

  return (
    <div className={className}>
      <div className="relative">
        {video ? (
          <video
            ref={mediaRef as RefObject<HTMLVideoElement>}
            controls
            preload="metadata"
            playsInline
            src={src}
            data-media-kind={kind}
            data-media-element="video"
            muted={offset !== 0}
            className="w-full rounded-md bg-ink"
            onError={() => setFailed(true)}
            onLoadedMetadata={(event) => {
              setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0);
              applySeek(event.currentTarget);
            }}
            onTimeUpdate={(event) => {
              setCurrent(event.currentTarget.currentTime);
              onTime?.(event.currentTarget.currentTime);
              if (offset !== 0) {
                const audio = audioRef.current;
                if (audio) {
                  const target = Math.max(0, event.currentTarget.currentTime + offset);
                  if (Number.isFinite(target) && Math.abs(audio.currentTime - target) > 0.1) {
                    try { audio.currentTime = target; } catch { }
                  }
                }
              }
            }}
          />
        ) : (
          <audio
            ref={mediaRef as RefObject<HTMLAudioElement>}
            controls
            preload="metadata"
            src={src}
            data-media-kind={kind}
            data-media-element="audio"
            className="w-full"
            onError={() => setFailed(true)}
            onLoadedMetadata={(event) => {
              setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0);
              applySeek(event.currentTarget);
            }}
            onTimeUpdate={(event) => {
              setCurrent(event.currentTarget.currentTime);
              onTime?.(event.currentTarget.currentTime);
            }}
          />
        )}
        {video && offset !== 0 ? (
        <audio
          ref={audioRef}
          preload="metadata"
          src={src}
          aria-hidden="true"
          className="sr-only"
        />
      ) : null}
      {video
          ? markers.map((marker) => (
              <span
                key={`${marker.label}-${marker.atSec}`}
                data-testid="media-marker"
                aria-hidden="true"
                title={`${marker.label} at ${formatCut(marker.atSec)}`}
                className="pointer-events-none absolute bottom-0 h-2 w-1 rounded-t bg-warn"
                style={{ left: `${position(marker.atSec)}%` }}
              />
            ))
          : null}
      </div>

      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 font-mono text-xs text-muted">
        <span>
          {timeLabel}: {Number.isFinite(current) ? formatCut(current) : "00:00.0"} / {Number.isFinite(duration) && duration > 0 ? formatCut(duration) : "—"}
        </span>
        {label ? <span>{label}</span> : null}
      </div>

      {markerJumps && markers.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {markers.map((marker) => (
            <button
              key={`jump-${marker.label}-${marker.atSec}`}
              type="button"
              onClick={() => seek(marker.atSec)}
              className="inline-flex min-h-[44px] items-center rounded-md border border-line px-2 font-mono text-xs text-mist transition-colors hover:border-muted"
            >
              {marker.label} · {formatCut(marker.atSec)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
