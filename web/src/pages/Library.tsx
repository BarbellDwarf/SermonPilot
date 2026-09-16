import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { librarySermons, type LibrarySermon, type LibrarySermonStatus } from "../mock/data";
import { Chip, EmptyState, PageHeader, SkeletonList, useBriefLoading } from "../components/ui";

export const sermonStatusTone: Record<LibrarySermonStatus, string> = {
  draft: "neutral",
  rendered: "warn",
  processed: "ok",
};

export const sermonStatusLabel: Record<LibrarySermonStatus, string> = {
  draft: "Draft",
  rendered: "Rendered — not uploaded",
  processed: "Processed",
};

type SortKey = "date" | "title" | "duration";

const sortOptions: { id: SortKey; label: string }[] = [
  { id: "date", label: "Date (newest)" },
  { id: "title", label: "Title (A–Z)" },
  { id: "duration", label: "Duration (longest)" },
];

function toSeconds(d: string): number {
  const parts = d.split(":").map(Number);
  if (parts.some((n) => !Number.isFinite(n))) return 0;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

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
  const [sort, setSort] = useState<SortKey>("date");
  const loading = useBriefLoading();

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? librarySermons.filter((s) =>
          [s.title, s.speaker, s.series].some((f) => f.toLowerCase().includes(q)),
        )
      : [...librarySermons];
    filtered.sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      if (sort === "duration") return toSeconds(b.duration) - toSeconds(a.duration);
      return b.date.localeCompare(a.date);
    });
    return filtered;
  }, [query, sort]);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Library" sub="Mock teachings with status, search, and sort." />

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
          onChange={(e) => setSort(e.target.value as SortKey)}
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
      ) : rows.length === 0 ? (
        <EmptyState
          title="No teachings match"
          body="Try a different search term, or clear the search to see everything."
        />
      ) : (
        <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {rows.map((s) => (
            <SermonCard key={s.id} sermon={s} />
          ))}
        </ol>
      )}
    </div>
  );
}
