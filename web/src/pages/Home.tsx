import { Link } from "react-router-dom";
import { type SermonStatus } from "../mock/data";
import { Chip, EmptyState, Meter, PageHeader, SkeletonList, buttonClass, staggerStyle } from "../components/ui";
import { QueryError, useHomeData } from "../api/hooks";
import { STATUS_DOT, STATUS_TEXT, jobRowTitle, jobStatus } from "./jobRow";

const sermonTone: Record<SermonStatus, string> = {
  ready: "ok",
  processing: "info",
  draft: "neutral",
  failed: "error",
};

const sermonLabel: Record<SermonStatus, string> = {
  ready: "Processed",
  processing: "Processing",
  draft: "Draft",
  failed: "Failed",
};

export function Home() {
  const { data, isLoading: loading, error, retry } = useHomeData();
  const { services, activeJobs, recentSermons } = data;
  const okCount = services.filter((s) => s.state === "ok").length;
  const queuedCount = activeJobs.filter((j) => j.state === "queued").length;
  const stats: [string, string][] = [
    ["Active jobs", String(activeJobs.length)],
    ["Queued", String(queuedCount)],
    ["Services ok", `${okCount}/${services.length}`],
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Home"
        actions={
          <Link to="/new" className={buttonClass("primary")}>
            New teaching
          </Link>
        }
      />

      {error ? <QueryError message={error} onRetry={retry} /> : null}

      <section aria-label="At a glance">
        <dl className="grid grid-cols-3 divide-x divide-line rounded-lg border border-line bg-surface">
          {stats.map(([term, value]) => (
            <div key={term} className="min-w-0 px-4 py-3">
              <dt className="truncate text-xs font-medium text-muted">{term}</dt>
              <dd className="mt-0.5 font-mono text-lg font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="health-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="health-h" className="text-lg font-semibold">
            Pipeline health
          </h2>
          <Link
            to="/settings"
            className="inline-flex min-h-[44px] items-center rounded-md px-2 text-sm font-medium text-accent hover:underline"
          >
            Settings
          </Link>
        </div>
        {services.length === 0 ? (
          <EmptyState
            title="No services reported"
            body="Service health appears once the API bridge answers. Check the bridge address in Settings."
            action={
              <Link to="/settings" className={buttonClass("secondary")}>
                Open settings
              </Link>
            }
            compact
          />
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {services.map((s, index) => (
              <li key={s.id} className="stagger-item flex items-center gap-3 px-4 py-3" style={staggerStyle(index)}>
                <Meter level={s.level} state={s.state} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold">{s.label}</p>
                    <Chip tone={s.state}>{s.state}</Chip>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted" title={s.detail}>
                    {s.detail}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="active-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="active-h" className="text-lg font-semibold">
            Active jobs
          </h2>
          <Link
            to="/jobs"
            className="inline-flex min-h-[44px] items-center rounded-md px-2 text-sm font-medium text-accent hover:underline"
          >
            View all
          </Link>
        </div>
        {loading ? (
          <SkeletonList rows={2} variant="row" rowHeight={56} />
        ) : activeJobs.length === 0 ? (
          <EmptyState
            title="No active jobs"
            body="Queued and running jobs appear here with live progress. Start one from New teaching."
            action={
              <Link to="/new" className={buttonClass("primary")}>
                Start a teaching
              </Link>
            }
            compact
          />
        ) : (
          <ol className="divide-y divide-line rounded-lg border border-line bg-surface">
            {activeJobs.map((job, index) => {
              const status = jobStatus(job);
              return (
                <li key={job.id} className="stagger-item" style={staggerStyle(index)}>
                  <Link
                    to="/jobs"
                    className="flex min-h-[56px] items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised"
                  >
                    <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[status]}`} aria-hidden="true" />
                    <span className={`w-[4.5rem] shrink-0 font-mono text-xs font-semibold uppercase tracking-wide ${STATUS_TEXT[status]}`}>
                      {status}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-semibold" title={jobRowTitle(job)}>
                      {jobRowTitle(job)}
                    </span>
                    <span className="shrink-0 font-mono text-xs text-muted">{job.created}</span>
                  </Link>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section aria-labelledby="recent-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="recent-h" className="text-lg font-semibold">
            Recent teachings
          </h2>
          <Link
            to="/library"
            className="inline-flex min-h-[44px] items-center rounded-md px-2 text-sm font-medium text-accent hover:underline"
          >
            Open library
          </Link>
        </div>
        {loading ? (
          <SkeletonList rows={2} variant="row" rowHeight={56} />
        ) : recentSermons.length === 0 ? (
          <EmptyState
            title="No teachings yet"
            body="Processed teachings appear here with their speaker and duration. Add the first one to get started."
            action={
              <Link to="/new" className={buttonClass("primary")}>
                Add the first teaching
              </Link>
            }
            compact
          />
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {recentSermons.map((s, index) => (
              <li key={s.id} className="stagger-item" style={staggerStyle(index)}>
                <Link
                  to={`/library/${s.id}`}
                  aria-label={`${s.title} by ${s.speaker}, ${sermonLabel[s.status]}`}
                  className="flex min-h-[56px] items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised"
                >
                  <Chip tone={sermonTone[s.status]}>{sermonLabel[s.status]}</Chip>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold" title={s.title}>
                      {s.title}
                    </span>
                    <span className="block truncate text-xs text-muted">
                      {s.speaker} · {s.updated}
                    </span>
                  </span>
                  <span className="hidden shrink-0 font-mono text-xs text-muted sm:inline">{s.duration}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
