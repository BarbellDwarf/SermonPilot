import { useState } from "react";
import { Link } from "react-router-dom";
import { type LibrarySermon, type LibrarySermonStatus } from "../mock/data";
import { Chip, EmptyState, PageHeader, SkeletonList } from "../components/ui";
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
  return (
    <li>
      <Link
        to={`/library/${sermon.id}`}
        aria-label={`${sermon.title} by ${sermon.speaker}, ${sermonStatusLabel[sermon.status]}`}
        className="block rounded-lg border border-line bg-surface p-4 text-left transition-colors hover:border-muted"
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
    </li>
  );
}

export function Library() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<LibrarySort>("date");
  const { items: rows, isLoading: loading, error, retry } = useLibrarySermons(query, sort);

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

      {loading ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <QueryError message={error} onRetry={retry} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No teachings match"
          body="Try a different search term, or clear the search to see everything."
        />
      ) : (
        <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((s) => (
            <SermonCard key={s.id} sermon={s} />
          ))}
        </ol>
      )}
    </div>
  );
}
