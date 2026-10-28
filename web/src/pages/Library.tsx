import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { type LibrarySermon, type LibrarySermonStatus } from "../mock/data";
import { Button, Chip, EmptyState, Icon, Menu, PageHeader, SkeletonList, buttonClass, staggerStyle } from "../components/ui";
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
  rendered: "Rendered",
  processed: "Processed",
  failed: "Failed",
};

const sortOptions: { id: LibrarySort; label: string }[] = [
  { id: "date", label: "Date (newest)" },
  { id: "title", label: "Title (A–Z)" },
  { id: "duration", label: "Duration (longest)" },
];

const selectCls =
  "min-h-[44px] min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist transition-colors duration-150 hover:border-muted focus-visible:border-accent";

function SermonRow({ sermon, index }: { sermon: LibrarySermon; index: number }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const status = sermonStatusLabel[sermon.status];

  return (
    <li data-testid={`library-row-${sermon.id}`} className="stagger-item" style={staggerStyle(index)}>
      <div className="group relative">
        <Link
          to={`/library/${sermon.id}`}
          aria-label={`Open ${sermon.title} by ${sermon.speaker}, ${status}`}
          className="peer absolute inset-0 rounded-md"
        />
        <div className="flex min-h-[64px] items-center gap-3 px-4 py-2.5 transition-colors duration-150 group-hover:bg-raised peer-focus-visible:bg-raised">
          <div aria-hidden="true" className="flex min-w-0 flex-1 items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold" title={sermon.title}>
                {sermon.title}
              </p>
              <p className="mt-0.5 truncate text-xs text-muted">
                {sermon.speaker} · {sermon.date}
              </p>
            </div>
            <div className="hidden w-32 shrink-0 text-right sm:block">
              <p className="font-mono text-xs text-muted">{sermon.duration}</p>
              <p className="truncate text-xs text-muted" title={sermon.series}>
                {sermon.series}
              </p>
            </div>
            <Chip tone={sermonStatusTone[sermon.status]}>{status}</Chip>
          </div>
          <div className="relative z-10">
            <Menu
              label={`Actions for ${sermon.title}`}
              triggerTestId={`library-actions-${sermon.id}`}
              triggerClassName="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted transition-colors hover:bg-raised hover:text-mist"
              trigger={
                <Icon name="more" />
              }
              items={[
                { label: "Open teaching", onSelect: () => navigate(`/library/${sermon.id}`) },
                {
                  label: open ? "Hide preview" : "Preview",
                  onSelect: () => setOpen((value) => !value),
                  expanded: open,
                  controls: open ? `library-preview-${sermon.id}` : undefined,
                  testId: `library-preview-toggle-${sermon.id}`,
                },
              ]}
            />
          </div>
        </div>
      </div>
      {open ? (
        <div id={`library-preview-${sermon.id}`} className="border-t border-line p-3">
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
  const filtersActive = query.length > 0 || status !== "all";

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
      <PageHeader
        title="Library"
        actions={
          <Link to="/new" className={buttonClass("primary")}>
            New teaching
          </Link>
        }
      />

      <div className="flex flex-col gap-2">
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
            className="min-h-[44px] min-w-0 flex-1 rounded-md border border-line bg-ink px-3 text-sm text-mist transition-colors duration-150 placeholder:text-muted hover:border-muted focus-visible:border-accent"
          />
          <div className="flex min-w-0 items-center gap-2">
            <label htmlFor="library-status" className="sr-only">
              Filter by status
            </label>
            <select
              id="library-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as "all" | LibrarySermonStatus)}
              className={`${selectCls} flex-1 sm:flex-none`}
            >
              <option value="all">All statuses</option>
              {(Object.keys(sermonStatusLabel) as LibrarySermonStatus[]).map((s) => (
                <option key={s} value={s}>
                  {sermonStatusLabel[s]}
                </option>
              ))}
            </select>
            <label htmlFor="library-sort" className="sr-only">
              Sort teachings
            </label>
            <select
              id="library-sort"
              value={sort}
              onChange={(e) => setSort(e.target.value as LibrarySort)}
              className={`${selectCls} flex-1 sm:flex-none`}
            >
              {sortOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
            <Menu
              label="Library actions"
              triggerTestId="library-toolbar-menu"
              triggerClassName={buttonClass("secondary", "w-11 !px-0")}
              trigger={
                <Icon name="more" />
              }
              items={[
                {
                  label: "Export CSV",
                  onSelect: exportCsv,
                  disabled: visible.length === 0,
                  testId: "library-export-csv",
                },
                {
                  label: "Clear filters",
                  onSelect: () => {
                    setQuery("");
                    setStatus("all");
                  },
                  disabled: !filtersActive,
                  testId: "library-clear-filters",
                },
              ]}
            />
          </div>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="font-mono text-xs text-muted" role="status" aria-live="polite">
            {hasMore
              ? `${visible.length} of ${isLive ? total : rows.length} loaded`
              : `${visible.length} ${visible.length === 1 ? "teaching" : "teachings"}`}
          </span>
        </div>
      </div>

      {loading ? (
        <SkeletonList rows={6} variant="row" />
      ) : error ? (
        <QueryError message={error} onRetry={retry} />
      ) : visible.length === 0 ? (
        <EmptyState
          title={filtersActive ? "No teachings match" : "No teachings yet"}
          body={
            filtersActive
              ? "Try a different search term, or clear the filters to see everything."
              : "Teachings appear here after a run finishes, with speaker, date, duration, and series."
          }
          action={
            filtersActive ? (
              <Button
                onClick={() => {
                  setQuery("");
                  setStatus("all");
                }}
              >
                Clear filters
              </Button>
            ) : (
              <Link to="/new" className={buttonClass("primary")}>
                Add the first teaching
              </Link>
            )
          }
        />
      ) : (
        <>
          <ol className="divide-y divide-line rounded-lg border border-line bg-surface">
            {visible.map((s, index) => (
              <SermonRow key={s.id} sermon={s} index={index} />
            ))}
          </ol>
          {hasMore ? (
            <Button onClick={loadMore} disabled={isLoadingMore}>
              {isLoadingMore ? "Loading…" : `Load more (${rows.length} of ${total})`}
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}
