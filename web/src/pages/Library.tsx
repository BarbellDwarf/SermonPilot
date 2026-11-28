import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { type LibrarySermon } from "../mock/data";
import { Button, ClampText, EmptyState, Field, Icon, Menu, PageHeader, Sheet, SkeletonList, buttonClass, staggerStyle } from "../components/ui";
import { StatusChip } from "../components/StatusChip";
import { MediaPlayer } from "../components/MediaPlayer";
import { QueryError, lifecycleOfSermon, useLibrarySermons, type LibrarySort } from "../api/hooks";
import { isLive } from "../api/client";
import { formatCount, formatDate, formatDurationValue } from "../utils/format";
import { LIFECYCLE_META, type LifecycleState } from "../utils/lifecycle";

const lifecycleOrder: LifecycleState[] = [
  "needs_review",
  "ready",
  "processing",
  "failed",
  "draft",
  "published",
];

function filterLabel(state: LifecycleState): string {
  return state === "draft" ? "Drafts" : LIFECYCLE_META[state].label;
}

const sortOptions: { id: LibrarySort; label: string }[] = [
  { id: "date", label: "Date (newest)" },
  { id: "title", label: "Title (A–Z)" },
  { id: "duration", label: "Duration (longest)" },
];

const selectCls =
  "min-h-[44px] min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist transition-colors duration-150 hover:border-muted focus-visible:border-accent";

function parseState(value: string | null): "all" | LifecycleState {
  return value && lifecycleOrder.includes(value as LifecycleState)
    ? (value as LifecycleState)
    : "all";
}

function parseSort(value: string | null): LibrarySort {
  return sortOptions.some((option) => option.id === value) ? (value as LibrarySort) : "date";
}

function SermonRow({ sermon, index }: { sermon: LibrarySermon; index: number }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const state = lifecycleOfSermon(sermon);
  const status = LIFECYCLE_META[state].label;

  return (
    <li data-testid={`library-row-${sermon.id}`} className="stagger-item" style={staggerStyle(index)}>
      <div className="group relative">
        <Link
          to={`/teaching/${sermon.id}`}
          aria-label={`Open ${sermon.title} by ${sermon.speaker}, ${status}`}
          className="peer absolute inset-0 rounded-md"
        />
        <div className="grid min-h-[64px] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-2.5 transition-colors duration-150 group-hover:bg-selected peer-focus-visible:bg-selected lg:grid-cols-[minmax(0,1fr)_8rem_auto_44px]">
          <div aria-hidden="true" className="col-start-1 row-start-1 min-w-0">
            <ClampText text={sermon.title} className="text-sm font-semibold" />
          </div>
          <div aria-hidden="true" className="col-start-1 row-start-2 mt-0.5 flex min-w-0 text-xs text-muted">
            <span className="truncate" title={`${sermon.speaker || "Unknown speaker"} · ${formatDate(sermon.date)}`}>
              {sermon.speaker || "Unknown speaker"} · {formatDate(sermon.date)}
            </span>
            <span className="shrink-0 lg:hidden"> · {formatDurationValue(sermon.duration)}</span>
            {sermon.series ? (
              <span className="hidden min-w-0 truncate md:inline lg:hidden" title={sermon.series}>
                {" "}· {sermon.series}
              </span>
            ) : null}
          </div>
          <div aria-hidden="true" className="hidden w-32 shrink-0 text-right lg:col-start-2 lg:row-start-1 lg:row-span-2 lg:block">
            <p className="font-mono text-xs text-muted">{formatDurationValue(sermon.duration)}</p>
            <ClampText text={sermon.series || "No series"} className="text-xs text-muted" />
          </div>
          <div aria-hidden="true" className="col-start-2 row-start-2 justify-self-end lg:col-start-3 lg:row-start-1 lg:row-span-2">
            <StatusChip state={state} />
          </div>
          <div className="relative z-10 col-start-2 row-start-1 justify-self-end lg:col-start-4 lg:row-start-1 lg:row-span-2">
            <Menu
              label={`Actions for ${sermon.title}`}
              triggerTestId={`library-actions-${sermon.id}`}
              triggerClassName="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted transition-colors hover:bg-selected hover:text-mist"
              trigger={
                <Icon name="more" />
              }
              items={[
                { label: "Open teaching", onSelect: () => navigate(`/teaching/${sermon.id}`) },
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
  const [params, setParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const query = params.get("q") ?? "";
  const stateFilter = parseState(params.get("state"));
  const sort = parseSort(params.get("sort"));
  const { items: rows, isLoading: loading, error, retry, total, hasMore, isLoadingMore, loadMore, counts } =
    useLibrarySermons(query, sort);
  const visible =
    stateFilter === "all" ? rows : rows.filter((s) => lifecycleOfSermon(s) === stateFilter);
  const filtersActive = query.length > 0 || stateFilter !== "all" || sort !== "date";

  const setParam = (key: string, value: string, fallback: string) => {
    const next = new URLSearchParams(params);
    if (!value || value === fallback) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const clearFilters = () => setParams({}, { replace: true });

  const exportCsv = () => {
    const head = "id,title,speaker,date,duration,series,status";
    const esc = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const body = visible
      .map((s) => [s.id, s.title, s.speaker, s.date, s.duration, s.series, lifecycleOfSermon(s)].map(esc).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([[head, body].join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "library.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const statusOptions = lifecycleOrder.map((state) => (
    <option key={state} value={state}>
      {filterLabel(state)} ({counts[state]})
    </option>
  ));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Library" />

      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <label htmlFor="library-search" className="sr-only">
            Search teachings
          </label>
          <input
            id="library-search"
            type="search"
            value={query}
            onChange={(e) => setParam("q", e.target.value, "")}
            placeholder="Search title, speaker, series…"
            className="min-h-[44px] min-w-0 flex-1 rounded-md border border-line bg-ink px-3 text-sm text-mist transition-colors duration-150 placeholder:text-muted hover:border-muted focus-visible:border-accent"
          />
          <div className="flex min-w-0 items-center gap-2">
            <div className="hidden min-w-0 flex-1 items-center gap-2 sm:flex">
              <label htmlFor="library-status" className="sr-only">
                Filter by status
              </label>
              <select
                id="library-status"
                value={stateFilter}
                onChange={(e) => setParam("state", e.target.value, "all")}
                className={`${selectCls} flex-1 lg:flex-none`}
              >
                <option value="all">All ({counts.total})</option>
                {statusOptions}
              </select>
              <label htmlFor="library-sort" className="sr-only">
                Sort teachings
              </label>
              <select
                id="library-sort"
                value={sort}
                onChange={(e) => setParam("sort", e.target.value, "date")}
                className={`${selectCls} flex-1 lg:flex-none`}
              >
                {sortOptions.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <Button
              className="min-w-0 flex-1 sm:hidden"
              onClick={() => setFiltersOpen(true)}
              data-testid="library-filters-trigger"
            >
              Filters
              {stateFilter !== "all" ? <span className="font-mono text-xs text-muted">1</span> : null}
            </Button>
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
                  onSelect: clearFilters,
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
              : formatCount(visible.length, "teaching")}
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
              <Button onClick={clearFilters}>
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
        <ol className="divide-y divide-line rounded-lg border border-line bg-surface">
          {visible.map((s, index) => (
            <SermonRow key={s.id} sermon={s} index={index} />
          ))}
        </ol>
      )}
      {!loading && !error && hasMore ? (
        <Button onClick={loadMore} disabled={isLoadingMore}>
          {isLoadingMore ? "Loading…" : `Load more (${rows.length} of ${total})`}
        </Button>
      ) : null}

      <Sheet
        open={filtersOpen}
        title="Filters"
        onClose={() => setFiltersOpen(false)}
        testId="library-filters-sheet"
      >
        <Field label="Lifecycle" htmlFor="library-sheet-status">
          <select
            id="library-sheet-status"
            value={stateFilter}
            onChange={(e) => setParam("state", e.target.value, "all")}
            className={`${selectCls} w-full`}
          >
            <option value="all">All ({counts.total})</option>
            {statusOptions}
          </select>
        </Field>
        <Field label="Sort by" htmlFor="library-sheet-sort">
          <select
            id="library-sheet-sort"
            value={sort}
            onChange={(e) => setParam("sort", e.target.value, "date")}
            className={`${selectCls} w-full`}
          >
            {sortOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        <Button onClick={clearFilters} disabled={!filtersActive}>
          Clear filters
        </Button>
      </Sheet>
    </div>
  );
}
