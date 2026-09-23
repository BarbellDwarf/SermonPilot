import { useMemo, useState, type ReactNode } from "react";
import { mediaStreamUrl, type ApiMediaItem } from "../api/client";
import type { SermonMediaData } from "../api/hooks";
import type { EditPlan, LibrarySermon } from "../mock/data";
import { formatBytes } from "../utils/files";
import { formatCut } from "../utils/time";
import { MediaPlayer } from "./MediaPlayer";
import { TranscriptViewer } from "./TranscriptViewer";
import {
  artifactLabel,
  planStatusLabel,
  preferredKind,
  type DetailsPatch,
  type TranscriptState,
} from "./SermonReview";
import { Button } from "./ui";

const SA_LINK_BASE = "https://www.sermonaudio.com/sermoninfo.asp?SID=";

const COMPLETED_KIND_ORDER = [
  "processed",
  "keeper",
  "source",
  "enhanced",
  "snippet_start",
  "snippet_end",
  "snippet_ending",
];

const linkClass =
  "inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-xs font-medium text-mist transition-colors hover:border-muted";

export interface SermonCompletedProps {
  sermon: LibrarySermon;
  description: string | null;
  descriptionNeedsReview?: boolean;
  media: SermonMediaData;
  isLive: boolean;
  statusChip?: ReactNode;
  headerActions?: ReactNode;
  transcript?: TranscriptState;
  history?: EditPlan[];
  sermonaudioId?: string | null;
  uploadedAt?: string | null;
  onEdit: () => void;
  onSaveDetails?: (patch: DetailsPatch) => Promise<void> | void;
  onRegenerateDescription?: () => void;
}

export function SermonCompleted({
  sermon,
  description,
  descriptionNeedsReview = false,
  media,
  isLive,
  statusChip,
  headerActions,
  transcript,
  history,
  sermonaudioId,
  uploadedAt,
  onEdit,
  onSaveDetails,
  onRegenerateDescription,
}: SermonCompletedProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [seek, setSeek] = useState<{ sec: number; n: number } | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [form, setForm] = useState({
    title: sermon.title,
    speaker: sermon.speaker,
    series: sermon.series,
    date: sermon.date,
    description: description ?? "",
  });

  const requestSeek = (sec: number) => setSeek((previous) => ({ sec, n: (previous?.n ?? 0) + 1 }));

  const activeKind = preferredKind(media);
  const activeItem = media.byKind[activeKind];

  const files = useMemo(() => {
    const seen = new Set<string>();
    const rows: ApiMediaItem[] = [];
    for (const kind of [...COMPLETED_KIND_ORDER, ...media.items.map((item) => item.kind)]) {
      if (seen.has(kind)) continue;
      seen.add(kind);
      const item = media.byKind[kind];
      if (item?.available) rows.push(item);
    }
    return rows;
  }, [media.byKind, media.items]);

  const detailsDirty =
    form.title !== sermon.title ||
    form.speaker !== sermon.speaker ||
    form.series !== sermon.series ||
    form.date !== sermon.date ||
    form.description !== (description ?? "");

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

  const publicationLink = sermonaudioId
    ? `${SA_LINK_BASE}${encodeURIComponent(sermonaudioId)}`
    : null;

  return (
    <div data-testid="sermon-completed" className="flex flex-col gap-4">
      <header className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight [overflow-wrap:anywhere]">{form.title}</h1>
            <p className="mt-0.5 max-w-prose text-sm text-muted">
              {form.speaker} · {form.date}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {statusChip}
            <Button variant="primary" data-testid="edit-sermon" onClick={onEdit}>
              Edit this sermon
            </Button>
            {headerActions}
          </div>
        </div>
      </header>

      <section
        data-testid="completed-player"
        aria-label="Playback"
        className="rounded-lg border border-line bg-surface p-3"
      >
        {isLive ? (
          <MediaPlayer
            sermonId={sermon.id}
            kind={activeKind}
            contentType={activeItem?.content_type}
            available={!!activeItem?.available}
            emptyMessage="No playable media for this teaching yet."
            seekToSec={seek?.sec ?? null}
            seekNonce={seek?.n}
          />
        ) : (
          <p className="rounded-md border border-dashed border-line bg-ink px-3 py-6 text-center text-sm text-muted">
            Preview available in the live console.
          </p>
        )}
      </section>

      <section
        data-testid="completed-details"
        aria-labelledby="completed-details-h"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="completed-details-h" className="text-lg font-semibold">
            Details
          </h2>
          <button
            type="button"
            data-testid="edit-details"
            onClick={() => setDetailsOpen((value) => !value)}
            aria-expanded={detailsOpen}
            aria-controls="completed-details-form"
            className={linkClass}
          >
            {detailsOpen ? "Close" : "Edit details"}
          </button>
        </div>

        {detailsOpen ? (
          <form
            id="completed-details-form"
            className="mt-3 flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
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
                onChange={(event) => setForm((f) => ({ ...f, title: event.target.value }))}
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
                onChange={(event) => setForm((f) => ({ ...f, speaker: event.target.value }))}
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
                  onChange={(event) => setForm((f) => ({ ...f, series: event.target.value }))}
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
                  onChange={(event) => setForm((f) => ({ ...f, date: event.target.value }))}
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
                onChange={(event) => setForm((f) => ({ ...f, description: event.target.value }))}
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
        ) : (
          <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div data-testid="detail-title" className="min-w-0">
              <dt className="text-xs font-medium text-muted">Title</dt>
              <dd className="mt-0.5 text-sm text-mist [overflow-wrap:anywhere]">{form.title}</dd>
            </div>
            <div data-testid="detail-speaker" className="min-w-0">
              <dt className="text-xs font-medium text-muted">Speaker</dt>
              <dd className="mt-0.5 text-sm text-mist [overflow-wrap:anywhere]">{form.speaker}</dd>
            </div>
            <div data-testid="detail-series" className="min-w-0">
              <dt className="text-xs font-medium text-muted">Series</dt>
              <dd className="mt-0.5 text-sm text-mist [overflow-wrap:anywhere]">{form.series || "—"}</dd>
            </div>
            <div data-testid="detail-date" className="min-w-0">
              <dt className="text-xs font-medium text-muted">Date</dt>
              <dd className="mt-0.5 text-sm text-mist [overflow-wrap:anywhere]">{form.date || "—"}</dd>
            </div>
            <div data-testid="detail-description" className="min-w-0 sm:col-span-2">
              <dt className="text-xs font-medium text-muted">Description</dt>
              <dd className="mt-0.5 max-w-prose whitespace-pre-wrap text-sm text-mist [overflow-wrap:anywhere]">
                {form.description || "No description recorded."}
              </dd>
            </div>
          </dl>
        )}
      </section>

      <section
        data-testid="completed-publication"
        aria-labelledby="completed-publication-h"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <h2 id="completed-publication-h" className="text-lg font-semibold">
          Publication
        </h2>
        <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="text-xs font-medium text-muted">SermonAudio ID</dt>
            <dd className="mt-0.5 text-sm text-mist">
              {publicationLink ? (
                <a href={publicationLink} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  {sermonaudioId}
                </a>
              ) : (
                "Not recorded"
              )}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs font-medium text-muted">Uploaded</dt>
            <dd className="mt-0.5 text-sm text-mist">{uploadedAt || "Not recorded"}</dd>
          </div>
        </dl>
      </section>

      <section
        data-testid="completed-transcript"
        aria-labelledby="completed-transcript-h"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="completed-transcript-h" className="text-lg font-semibold">
            Transcript
          </h2>
          {transcript ? (
            <div className="flex flex-wrap items-center gap-2">
              {media.byKind["transcript"]?.available ? (
                <a href={mediaStreamUrl(sermon.id, "transcript")} download className={linkClass}>
                  Download
                </a>
              ) : null}
              {transcript.open && transcript.plainText ? (
                <button type="button" onClick={transcript.onCopy} className={linkClass}>
                  {transcript.copied ? "Copied" : "Copy"}
                </button>
              ) : null}
              <button
                type="button"
                onClick={transcript.onToggle}
                aria-expanded={transcript.open}
                aria-controls="completed-transcript-body"
                className={linkClass}
              >
                {transcript.open ? "Hide transcript" : "Show transcript"}
              </button>
            </div>
          ) : null}
        </div>
        {transcript?.open ? (
          <div id="completed-transcript-body" className="mt-2">
            {!isLive ? (
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
      </section>

      <section
        data-testid="completed-files"
        aria-labelledby="completed-files-h"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <h2 id="completed-files-h" className="text-lg font-semibold">
          Files
        </h2>
        {files.length > 0 ? (
          <ul className="mt-3 flex flex-col gap-2">
            {files.map((item) => (
              <li
                key={item.kind}
                data-testid="completed-file-row"
                className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-ink p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{item.label || artifactLabel(item.kind)}</p>
                  <p className="text-xs text-muted">{formatBytes(item.size)}</p>
                </div>
                {isLive ? (
                  <a
                    href={mediaStreamUrl(sermon.id, item.kind)}
                    download
                    className={`${linkClass} shrink-0`}
                  >
                    Download
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted">No files recorded for this teaching.</p>
        )}
      </section>

      <section
        data-testid="completed-history"
        aria-labelledby="completed-history-h"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <h2 id="completed-history-h" className="text-lg font-semibold">
          Edit history
        </h2>
        {history && history.length > 0 ? (
          <ol className="mt-3 flex flex-col gap-2">
            {history.map((row) => (
              <li
                key={row.revision}
                data-testid="completed-history-row"
                className="rounded-md border border-line bg-ink p-3"
              >
                <p className="font-mono text-xs text-muted">
                  revision {row.revision} · {planStatusLabel[row.status]}
                </p>
                <p className="mt-1 font-mono text-xs text-muted">
                  start {formatCut(row.startSec)} · end {formatCut(row.endSec)} · offset{" "}
                  {row.offsetSec >= 0 ? "+" : ""}
                  {row.offsetSec.toFixed(1)}s
                </p>
                {row.notes ? <p className="mt-1 text-sm text-mist">{row.notes}</p> : null}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-2 text-sm text-muted">No edit history recorded.</p>
        )}
      </section>
    </div>
  );
}
