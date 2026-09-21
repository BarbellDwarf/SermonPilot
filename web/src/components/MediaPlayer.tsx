import { useEffect, useRef, useState, type RefObject } from "react";
import { mediaStreamUrl } from "../api/client";
import { formatCut } from "../utils/time";

export interface MediaMarker {
  atSec: number;
  label: string;
}

interface MediaPlayerProps {
  sermonId: string;
  kind: string;
  contentType?: string | null;
  available: boolean;
  emptyMessage?: string;
  markers?: MediaMarker[];
  seekToSec?: number | null;
  seekNonce?: number;
  label?: string;
  className?: string;
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
  seekToSec = null,
  seekNonce = 0,
  label,
  className = "",
}: MediaPlayerProps) {
  const mediaRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null);
  const [failed, setFailed] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  const applySeek = (element: HTMLMediaElement | null) => {
    if (seekToSec == null || !element) return;
    try {
      element.currentTime = Math.max(0, seekToSec);
    } catch {
      // metadata not loaded yet; onLoadedMetadata re-applies the request
    }
  };

  useEffect(() => {
    applySeek(mediaRef.current);
  }, [seekToSec, seekNonce]);

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
    duration > 0 ? Math.min(100, Math.max(0, (sec / duration) * 100)) : 0;
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
            className="w-full rounded-md bg-ink"
            onError={() => setFailed(true)}
            onLoadedMetadata={(event) => {
              setDuration(event.currentTarget.duration || 0);
              applySeek(event.currentTarget);
            }}
            onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)}
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
              setDuration(event.currentTarget.duration || 0);
              applySeek(event.currentTarget);
            }}
            onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)}
          />
        )}
        {video
          ? markers.map((marker) => (
              <span
                key={`${marker.label}-${marker.atSec}`}
                aria-hidden="true"
                title={`${marker.label} at ${formatCut(marker.atSec)}`}
                className="pointer-events-none absolute top-0 h-2 w-1 rounded-b bg-warn"
                style={{ left: `${position(marker.atSec)}%` }}
              />
            ))
          : null}
      </div>

      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 font-mono text-xs text-muted">
        <span>
          {formatCut(current)} / {duration > 0 ? formatCut(duration) : "—"}
        </span>
        {label ? <span>{label}</span> : null}
      </div>

      {markers.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {markers.map((marker) => (
            <button
              key={`jump-${marker.label}-${marker.atSec}`}
              type="button"
              onClick={() => seek(marker.atSec)}
              className="inline-flex min-h-[32px] items-center rounded-md border border-line px-2 font-mono text-xs text-mist transition-colors hover:border-muted"
            >
              {marker.label} · {formatCut(marker.atSec)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
