import type { ReactNode } from "react";
import { mediaStreamUrl, type ApiMediaItem } from "../../api/client";
import type { SermonMediaData } from "../../api/hooks";
import type { EditPlan } from "../../mock/data";
import { formatBytes } from "../../utils/format";
import { formatCut } from "../../utils/time";
import { TranscriptViewer } from "../TranscriptViewer";
import { Skeleton } from "../ui";
import { artifactLabel } from "./media";
import { planStatusLabel } from "./PlanSummary";
import type { TranscriptState } from "./types";

const PRIMARY_KINDS = ["source", "processed", "keeper"] as const;
const PREVIEW_KINDS = ["snippet_start", "snippet_end", "snippet_ending"] as const;
const TRANSCRIPT_KINDS = ["transcript", "transcript_timestamps"] as const;
const linkClass = "inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted";

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
        <p className="text-xs text-muted">{item.available ? formatBytes(item.size) : "not available"}</p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {item.available && live ? <a href={mediaStreamUrl(sermonId, item.kind)} download className={linkClass}>Download</a> : null}
        {item.available && live && onOpen ? <button type="button" onClick={() => onOpen(item.kind)} className={linkClass}>Open in player</button> : null}
      </div>
    </li>
  );
}

export function TranscriptPanel({
  sermonId,
  isLive,
  transcript,
  onSeek,
}: {
  sermonId: string;
  isLive: boolean;
  transcript?: TranscriptState;
  onSeek: (sec: number) => void;
}) {
  return (
    <div data-testid="transcript-entry" className="flex flex-col gap-2">
      {transcript ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {mediaDownload(sermonId, isLive, "transcript")}
            <button type="button" onClick={transcript.onToggle} aria-expanded={transcript.open} className={linkClass}>{transcript.open ? "Hide transcript" : "Show transcript"}</button>
            {transcript.open && transcript.plainText ? <button type="button" onClick={transcript.onCopy} className={linkClass}>{transcript.copied ? "Copied" : "Copy"}</button> : null}
          </div>
          {!transcript.open ? <p className="text-sm text-muted">Load the transcript to read or copy it.</p>
            : !isLive ? <p className="text-sm text-muted">Transcripts are available in the live bridge.</p>
              : transcript.loading ? <div className="flex flex-col gap-2"><Skeleton className="h-3 w-4/5" /><Skeleton className="h-3 w-3/5" /></div>
                : transcript.error ? <p className="font-mono text-xs text-danger">{transcript.error}</p>
                  : transcript.plainText || transcript.timestampsAvailable ? (
                    <>
                      <p className="font-mono text-xs text-muted">{transcript.totalLength} characters{transcript.truncated ? " (truncated)" : ""}</p>
                      <TranscriptViewer id={sermonId} plainText={transcript.plainText} timestampsAvailable={transcript.timestampsAvailable} onSeek={onSeek} />
                    </>
                  ) : <p className="text-sm text-muted">No transcript recorded for this teaching.</p>}
        </>
      ) : <p className="text-sm text-muted">No transcript recorded for this teaching.</p>}
    </div>
  );
}

function mediaDownload(sermonId: string, live: boolean, kind: string) {
  return live ? <a href={mediaStreamUrl(sermonId, kind)} download className={linkClass}>Download</a> : null;
}

export function FilesPanel({
  sermonId,
  media,
  isLive,
  onOpenArtifact,
}: {
  sermonId: string;
  media: SermonMediaData;
  isLive: boolean;
  onOpenArtifact?: (kind: string) => void;
}) {
  const primary = PRIMARY_KINDS.map((kind) => media.byKind[kind]).filter((item): item is ApiMediaItem => !!item?.available);
  const extra = media.items.filter((item) => item.available && !(PRIMARY_KINDS as readonly string[]).includes(item.kind) && !(TRANSCRIPT_KINDS as readonly string[]).includes(item.kind) && !(PREVIEW_KINDS as readonly string[]).includes(item.kind));
  const previews = PREVIEW_KINDS.map((kind) => media.byKind[kind]).filter((item): item is ApiMediaItem => !!item?.available);
  return (
    <div className="flex flex-col gap-4">
      <ArtifactGroup id="files-media" title="Media">
        {primary.length === 0 && extra.length === 0 ? <p className="text-sm text-muted">No source, render, or keeper files recorded yet.</p> : (
          <ul className="flex flex-col gap-2">
            {primary.map((item) => <ArtifactRow key={item.kind} sermonId={sermonId} item={item} testId="artifact-primary-row" live={isLive} />)}
            {extra.map((item) => <ArtifactRow key={item.kind} sermonId={sermonId} item={item} testId="artifact-other-row" live={isLive} onOpen={onOpenArtifact} />)}
          </ul>
        )}
      </ArtifactGroup>
      {previews.length > 0 ? (
        <ArtifactGroup id="files-previews" title="Preview files">
          <ul className="flex flex-col gap-2">{previews.map((item) => <ArtifactRow key={item.kind} sermonId={sermonId} item={item} testId="artifact-preview-row" live={isLive} onOpen={onOpenArtifact} />)}</ul>
        </ArtifactGroup>
      ) : null}
    </div>
  );
}

export function HistoryPanel({
  plan,
  history,
  noteRows,
  statusLog,
}: {
  plan: EditPlan;
  history?: EditPlan[];
  noteRows: { revision: number; note: string }[];
  statusLog: string[];
}) {
  return (
    <div className="flex flex-col gap-3">
      {noteRows.length > 0 ? (
        <ul className="flex flex-col gap-1">{noteRows.map((row) => <li key={`${row.revision}:${row.note}`} className="text-xs text-muted"><span className="font-mono">revision {row.revision}</span>: {row.note}</li>)}</ul>
      ) : <p className="text-sm text-muted">No rejection notes yet.</p>}
      {statusLog.length > 0 ? <p className="font-mono text-xs text-muted">{statusLog.join(" · ")}</p> : null}
      {plan.detectionStatus !== "unavailable" && plan.reasoning ? <p className="max-w-prose text-sm text-muted"><span className="font-semibold">Reasoning:</span> {plan.reasoning}</p> : null}
      {history && history.length > 0 ? (
        <ol className="flex flex-col gap-2">
          {history.map((row) => (
            <li key={row.revision} data-testid="history-row" className="rounded-md border border-line bg-ink p-3">
              <p className="font-mono text-xs text-muted">revision {row.revision} · {planStatusLabel[row.status]}</p>
              <p className="mt-1 font-mono text-xs text-muted">start {formatCut(row.startSec)} · end {formatCut(row.endSec)} · offset {row.offsetSec >= 0 ? "+" : ""}{row.offsetSec.toFixed(1)}s</p>
              {row.notes ? <p className="mt-1 text-sm text-mist">{row.notes}</p> : null}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

export function PublicationRows({
  sermonaudioId,
  uploadedAt,
  bibleText,
  scriptureReference,
}: {
  sermonaudioId?: string | null;
  uploadedAt?: string | null;
  bibleText?: string | null;
  scriptureReference?: string | null;
}) {
  const publicationLink = sermonaudioId ? `https://www.sermonaudio.com/sermoninfo.asp?SID=${encodeURIComponent(sermonaudioId)}` : null;
  return (
    <>
      <section data-testid="completed-publication" aria-labelledby="publication-h" className="mt-4 border-t border-line pt-4">
        <h2 id="publication-h" className="text-lg font-semibold">Publication</h2>
        <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><dt className="text-xs font-medium text-muted">SermonAudio ID</dt><dd className="mt-0.5 text-sm text-mist">{publicationLink ? <a href={publicationLink} target="_blank" rel="noreferrer" className="text-accent hover:underline">{sermonaudioId}</a> : "Not recorded"}</dd></div>
          <div><dt className="text-xs font-medium text-muted">Uploaded</dt><dd className="mt-0.5 text-sm text-mist">{uploadedAt || "Not recorded"}</dd></div>
        </dl>
      </section>
      {scriptureReference || bibleText ? (
        <div data-testid="detail-scripture" className="mt-4 border-t border-line pt-4">
          {scriptureReference ? <p className="text-xs font-medium text-muted">Scripture</p> : null}
          {scriptureReference ? <p className="mt-0.5 text-sm text-mist [overflow-wrap:anywhere]">{scriptureReference}</p> : null}
          {bibleText ? <p className="mt-1 whitespace-pre-wrap text-sm text-mist [overflow-wrap:anywhere]">{bibleText}</p> : null}
        </div>
      ) : null}
    </>
  );
}
