import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { mediaStreamUrl, type ApiMediaItem } from "../../api/client";
import type { SermonMediaData } from "../../api/hooks";
import type { EditPlan } from "../../mock/data";
import { formatBytes } from "../../utils/format";
import { formatCut } from "../../utils/time";
import { TranscriptViewer } from "../TranscriptViewer";
import { Skeleton } from "../ui";
import { artifactLabel } from "./media";
import type { TranscriptState } from "./types";

const INFO_TABS = [
  { id: "transcript", label: "Transcript" },
  { id: "files", label: "Files" },
  { id: "previews", label: "Previews" },
  { id: "history", label: "History" },
] as const;
export type InfoTab = (typeof INFO_TABS)[number]["id"];

const PRIMARY_KINDS = ["source", "processed", "keeper"] as const;
const PREVIEW_KINDS = ["snippet_start", "snippet_end", "snippet_ending"] as const;
const TRANSCRIPT_KINDS = ["transcript", "transcript_timestamps"] as const;
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
const linkClass = "inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted";

interface ReviewInfoProps {
  sermonId: string;
  media: SermonMediaData;
  isLive: boolean;
  transcript?: TranscriptState;
  plan: EditPlan;
  history?: EditPlan[];
  noteRows: { revision: number; note: string }[];
  statusLog: string[];
  infoTab: InfoTab;
  onInfoTabChange: (tab: InfoTab) => void;
  onSeek: (sec: number) => void;
  onOpenArtifact: (kind: string) => void;
}

function ArtifactGroup({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section data-testid={`artifact-group-${id}`} aria-labelledby={`${id}-group-h`} className="flex flex-col gap-2">
      <h2 id={`${id}-group-h`} className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h2>
      {children}
    </section>
  );
}

function ArtifactRow({ sermonId, item, testId, live, onOpen }: { sermonId: string; item: ApiMediaItem; testId: string; live: boolean; onOpen?: (kind: string) => void }) {
  return (
    <li data-testid={testId} className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-ink p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-sm font-semibold">{item.label || artifactLabel(item.kind)}</p>
        <p className="text-xs text-muted">{ARTIFACT_NOTES[item.kind] ?? "Additional processing artifact."} · {item.available ? formatBytes(item.size) : "not available"}</p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {item.available && live ? <a href={mediaStreamUrl(sermonId, item.kind)} download className={linkClass}>Download</a> : null}
        {item.available && live && onOpen ? <button type="button" onClick={() => onOpen(item.kind)} className={linkClass}>Open in player</button> : null}
      </div>
    </li>
  );
}

export function ReviewInfo({
  sermonId,
  media,
  isLive,
  transcript,
  plan,
  history,
  noteRows,
  statusLog,
  infoTab,
  onInfoTabChange,
  onSeek,
  onOpenArtifact,
}: ReviewInfoProps) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const primaryArtifacts = PRIMARY_KINDS.map((kind) => media.byKind[kind]).filter((item): item is ApiMediaItem => !!item?.available);
  const extraMediaArtifacts = media.items.filter((item) => item.available && !(PRIMARY_KINDS as readonly string[]).includes(item.kind) && !(TRANSCRIPT_KINDS as readonly string[]).includes(item.kind) && !(PREVIEW_KINDS as readonly string[]).includes(item.kind));
  const availablePreviews = PREVIEW_KINDS.map((kind) => media.byKind[kind]).filter((item): item is ApiMediaItem => !!item?.available);
  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (index + 1) % INFO_TABS.length;
    if (event.key === "ArrowLeft") next = (index - 1 + INFO_TABS.length) % INFO_TABS.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = INFO_TABS.length - 1;
    if (next === null) return;
    event.preventDefault();
    onInfoTabChange(INFO_TABS[next].id);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-surface" data-testid="info-panel">
      <div role="tablist" aria-label="Teaching information" className="flex gap-1 overflow-x-auto border-b border-line p-1">
        {INFO_TABS.map((tab, index) => (
          <button
            key={tab.id}
            ref={(element) => { tabRefs.current[index] = element; }}
            type="button"
            role="tab"
            id={`info-tab-${tab.id}`}
            aria-selected={infoTab === tab.id}
            aria-controls={`info-${tab.id}`}
            tabIndex={infoTab === tab.id ? 0 : -1}
            onClick={() => onInfoTabChange(tab.id)}
            onKeyDown={(event) => onTabKeyDown(event, index)}
            className={`min-h-[44px] shrink-0 rounded-md px-3 text-sm font-semibold ${infoTab === tab.id ? "bg-accent/15 text-mist underline decoration-accent decoration-2 underline-offset-4" : "text-muted hover:text-mist"}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="p-3">
        <div role="tabpanel" id="info-transcript" aria-labelledby="info-tab-transcript" data-testid="transcript-panel" hidden={infoTab !== "transcript"} tabIndex={infoTab === "transcript" ? 0 : -1}>
          <div data-testid="transcript-entry">
            {transcript ? (
              !isLive ? <p className="text-sm text-muted">Transcripts are available in the live bridge.</p>
                : transcript.loading ? <div className="flex flex-col gap-2"><Skeleton className="h-3 w-4/5" /><Skeleton className="h-3 w-3/5" /></div>
                  : transcript.error ? <p className="font-mono text-xs text-danger">{transcript.error}</p>
                    : transcript.plainText || transcript.timestampsAvailable ? (
                      <>
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <p className="font-mono text-xs text-muted">{transcript.totalLength} characters{transcript.truncated ? " (truncated)" : ""}</p>
                          {transcript.plainText ? <button type="button" onClick={transcript.onCopy} className={linkClass}>{transcript.copied ? "Copied" : "Copy"}</button> : null}
                        </div>
                        <TranscriptViewer id={sermonId} plainText={transcript.plainText} timestampsAvailable={transcript.timestampsAvailable} onSeek={onSeek} />
                      </>
                    ) : <p className="text-sm text-muted">No transcript recorded for this teaching.</p>
            ) : <p className="text-sm text-muted">No transcript recorded for this teaching.</p>}
          </div>
        </div>
        <div role="tabpanel" id="info-files" aria-labelledby="info-tab-files" data-testid="files-panel" hidden={infoTab !== "files"} tabIndex={infoTab === "files" ? 0 : -1}>
          <ArtifactGroup id="files-media" title="Media">
            {primaryArtifacts.length === 0 && extraMediaArtifacts.length === 0 ? <p className="text-sm text-muted">No source, render, or keeper files recorded yet.</p> : (
              <ul className="flex flex-col gap-2">
                {primaryArtifacts.map((item) => <ArtifactRow key={item.kind} sermonId={sermonId} item={item} testId="artifact-primary-row" live={isLive} />)}
                {extraMediaArtifacts.map((item) => <ArtifactRow key={item.kind} sermonId={sermonId} item={item} testId="artifact-other-row" live={isLive} onOpen={onOpenArtifact} />)}
              </ul>
            )}
          </ArtifactGroup>
        </div>
        <div role="tabpanel" id="info-previews" aria-labelledby="info-tab-previews" data-testid="previews-panel" hidden={infoTab !== "previews"} tabIndex={infoTab === "previews" ? 0 : -1}>
          {availablePreviews.length === 0 ? <p data-testid="previews-empty" className="text-sm text-muted">Previews appear after a render.</p> : (
            <ul className="flex flex-col gap-2">{availablePreviews.map((item) => <ArtifactRow key={item.kind} sermonId={sermonId} item={item} testId="artifact-preview-row" live={isLive} onOpen={onOpenArtifact} />)}</ul>
          )}
        </div>
        <div role="tabpanel" id="info-history" aria-labelledby="info-tab-history" data-testid="history-panel" hidden={infoTab !== "history"} tabIndex={infoTab === "history" ? 0 : -1}>
          {noteRows.length > 0 ? <ul className="flex flex-col gap-1">{noteRows.map((row) => <li key={`${row.revision}:${row.note}`} className="text-xs text-muted"><span className="font-mono">revision {row.revision}</span>: {row.note}</li>)}</ul> : <p className="text-sm text-muted">No rejection notes yet.</p>}
          {statusLog.length > 0 ? <p className="mt-2 font-mono text-xs text-muted">{statusLog.join(" · ")}</p> : null}
          {plan.detectionStatus !== "unavailable" && plan.reasoning ? <p className="mt-2 max-w-prose text-sm text-muted"><span className="font-semibold">Reasoning:</span> {plan.reasoning}</p> : null}
          {plan.detectionStatus !== "unavailable" ? (
            <dl className="mt-2 grid grid-cols-1 gap-1 font-mono text-xs text-muted sm:grid-cols-3">
              <div><dt className="inline">start </dt><dd className="inline text-mist">{formatCut(plan.startSec)}</dd></div>
              <div><dt className="inline">end </dt><dd className="inline text-mist">{formatCut(plan.endSec)}</dd></div>
              <div><dt className="inline">offset </dt><dd className="inline text-mist">{plan.offsetSec >= 0 ? "+" : ""}{plan.offsetSec.toFixed(1)}s</dd></div>
            </dl>
          ) : null}
          {history && history.length > 0 ? <p className="mt-2 text-xs text-muted">{history.length} revisions recorded</p> : null}
        </div>
      </div>
    </div>
  );
}
