import { useState } from "react";
import { Link } from "react-router-dom";
import { type LibrarySermon, type LibrarySermonStatus } from "../mock/data";
import { Chip, EmptyState, PageHeader, SkeletonList } from "../components/ui";
import { MediaPlayer } from "../components/MediaPlayer";
import { QueryError, useLibrarySermons, type LibrarySort } from "../api/hooks";
import { isLive } from "../api/client";

export const sermonStatusTone: Record<LibrarySermonStatus, string> = {
  draft: "neutral",
  rendered: "warn",
  processed: "ok",
  failed: "error",
};

export const sermonStatusLabel: Record<LibrarySermonStatus, string> = {
  draft: "Draft",
  rendered: "Rendered — not uploaded",
  processed: "Processed",
  failed: "Failed",
};

const sortOptions: { id: LibrarySort; label: string }[] = [
  { id: "date", label: "Date (newest)" },
  { id: "title", label: "Title (A–Z)" },
  { id: "duration", label: "Duration (longest)" },
];

function SermonCard({ sermon }: { sermon: LibrarySermon }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="flex flex-col rounded-lg border border-line bg-surface p-4">
      <Link
        to={`/library/${sermon.id}`}
        aria-label={`${sermon.title} by ${sermon.speaker}, ${sermonStatusLabel[sermon.status]}`}
        className="block text-left transition-colors hover:opacity-90"
      >
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={sermonStatusTone[sermon.status]}>{sermonStatusLabel[sermon.status]}</Chip>
          <span className="rounded border border-line px-1.5 py-0.5 font-mono text-xs text-muted">
            {sermon.series}
          </span>
          <span className="ml-auto font-mono text-xs text-muted">{sermon.duration}</span>
        </div>
        <p className="mt-2 text-base font-semibold [overflow-wrap:anywhere]">{sermon.title}</p>
        <p className="mt-0.5 truncate text-sm text-muted">
          {sermon.speaker} · {sermon.date}
        </p>
      </Link>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="mt-2 inline-flex min-h-[36px] w-fit items-center rounded-md border border-line px-2 font-mono text-xs text-muted transition-colors hover:border-muted hover:text-mist"
      >
        {open ? "Hide preview" : "Preview"}
      </button>
      {open ? (
        <div className="mt-2">
          <MediaPlayer
            sermonId={sermon.id}
            kind="processed"
            available={isLive}
            emptyMessage={isLive ? "Not rendered yet." : "Preview available in the live console."}
          />
        </div>
      ) : null}
    </li>
  );
}

export function Library() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<LibrarySort>("date");
  const [status, setStatus] = useState<"all" | LibrarySermonStatus>("all");
  const { items: rows, isLoading: loading, error, retry, total, hasMore, isLoadingMore, loadMore } =
    useLibrarySermons(query, sort);
  const visible = status === "all" ? rows : rows.filter((s) => s.status === status);

  const exportCsv = () => {
    const head = "id,title,speaker,date,duration,series,status";
    const esc = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const body = visible
      .map((s) => [s.id, s.title, s.speaker, s.date, s.duration, s.series, s.status].map(esc).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([[head, body].join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "library.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Library" sub={isLive ? "Teachings from the live database, with status, search, and sort." : "Mock teachings with status, search, and sort."} />

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <label htmlFor="library-search" className="sr-only">
          Search teachings
        </label>
        <input
          id="library-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search title, speaker, series…"
          className="min-h-[44px] min-w-0 flex-1 rounded-md border border-line bg-surface px-3 text-sm text-mist placeholder:text-muted"
        />
        <label htmlFor="library-sort" className="sr-only">
          Sort teachings
        </label>
        <select
          id="library-sort"
          value={sort}
          onChange={(e) => setSort(e.target.value as LibrarySort)}
          className="min-h-[44px] rounded-md border border-line bg-surface px-3 text-sm text-mist"
        >
          {sortOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="library-status" className="sr-only">
          Filter by status
        </label>
        <select
          id="library-status"
          value={status}
          onChange={(e) => setStatus(e.target.value as "all" | LibrarySermonStatus)}
          className="min-h-[44px] rounded-md border border-line bg-surface px-3 text-sm text-mist"
        >
          <option value="all">All statuses</option>
          {(Object.keys(sermonStatusLabel) as LibrarySermonStatus[]).map((s) => (
            <option key={s} value={s}>
              {sermonStatusLabel[s]}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => {
            setQuery("");
            setStatus("all");
          }}
          className="inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-sm font-medium text-muted transition-colors hover:border-muted hover:text-mist"
        >
          Clear
        </button>
        <button
          type="button"
          onClick={exportCsv}
          disabled={visible.length === 0}
          className="inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-sm font-medium text-muted transition-colors hover:border-muted hover:text-mist disabled:opacity-45"
        >
          Export CSV
        </button>
        <span className="ml-auto font-mono text-xs text-muted" role="status" aria-live="polite">
          {visible.length} of {isLive ? total : rows.length} loaded
        </span>
      </div>

      {loading ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <QueryError message={error} onRetry={retry} />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No teachings match"
          body="Try a different search term, or clear the search to see everything."
        />
      ) : (
        <>
          <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {visible.map((s) => (
              <SermonCard key={s.id} sermon={s} />
            ))}
          </ol>
          {hasMore ? (
            <button
              type="button"
              onClick={loadMore}
              disabled={isLoadingMore}
              className="inline-flex min-h-[44px] items-center justify-center rounded-md border border-line px-4 text-sm font-medium text-mist transition-colors hover:border-muted disabled:opacity-45"
            >
              {isLoadingMore ? "Loading…" : `Load more (${rows.length} of ${total})`}
            </button>
          ) : null}
        </>
      )}
    </div>
  );
}
