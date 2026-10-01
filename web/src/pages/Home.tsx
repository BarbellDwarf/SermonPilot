import { Link } from "react-router-dom";
import { type Sermon, type SermonStatus } from "../mock/data";
import { Card, Chip, EmptyState, Meter, PageHeader, SkeletonList, buttonClass } from "../components/ui";
import { QueryError, useHomeData } from "../api/hooks";

/**
 * One label per record state, used on every page that shows a teaching. The
 * wording is what the operator would say out loud: it is on SermonAudio, it is
 * waiting on me, it is still to come, or it broke.
 */
export const sermonStatusLabel: Record<SermonStatus, string> = {
  uploaded: "Uploaded",
  draft: "Waiting for you",
  queued: "Queued",
  failed: "Failed",
};

export const sermonStatusTone: Record<SermonStatus, string> = {
  uploaded: "ok",
  draft: "warn",
  queued: "neutral",
  failed: "error",
};

export const serviceStateLabel: Record<string, string> = {
  ok: "OK",
  warn: "Warning",
  error: "Problem",
  unknown: "Not measured",
};

function NeedsYouRow({ sermon, verb }: { sermon: Sermon; verb: string }) {
  return (
    <li>
      <Link
        to={`/library/${sermon.id}`}
        className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-line bg-surface px-3 py-2 transition-colors hover:border-muted"
      >
        <Chip tone={sermonStatusTone[sermon.status]}>{sermonStatusLabel[sermon.status]}</Chip>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{sermon.title}</span>
        <span className="font-mono text-xs text-muted">{verb}</span>
      </Link>
    </li>
  );
}

export function Home() {
  const { data, isLoading: loading, error, retry } = useHomeData();
  const { services, activeJobs, recentSermons, upNext, needsReview, failed } = data;
  const okCount = services.filter((s) => s.state === "ok").length;
  const unknownCount = services.filter((s) => s.state === "unknown").length;
  const stats: [string, string][] = [
    ["Teachings", String(recentSermons.length)],
    ["Waiting for you", String(needsReview.length)],
    ["Active jobs", String(activeJobs.length)],
    ["Services ok", `${okCount}/${services.length}`],
  ];
  const needsYouCount = needsReview.length + failed.length;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Home"
        sub="What needs you next, then what the machine is doing."
        actions={
          <Link to="/new" className={buttonClass("primary")}>
            New teaching
          </Link>
        }
      />

      {error ? <QueryError message={error} onRetry={retry} /> : null}

      <section aria-label="At a glance">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map(([term, value]) => (
            <Card key={term} className="px-4 py-3">
              <dt className="text-xs font-medium uppercase tracking-wide text-muted">{term}</dt>
              <dd className="mt-0.5 font-mono text-xl font-semibold">{value}</dd>
            </Card>
          ))}
        </dl>
      </section>

      <section aria-labelledby="needs-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="needs-h" className="text-lg font-semibold">Needs you</h2>
          <Link
            to="/library"
            className="inline-flex min-h-[44px] items-center rounded-md px-2 text-sm font-medium text-accent hover:underline"
          >
            Open library
          </Link>
        </div>
        {loading ? (
          <SkeletonList rows={2} />
        ) : needsYouCount === 0 ? (
          <EmptyState
            title="Nothing is waiting on you"
            body="Every teaching is uploaded or still queued. New work lands here the moment it needs a decision."
            action={
              <Link to="/new" className={buttonClass()}>
                New teaching
              </Link>
            }
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {needsReview.map((s) => (
              <NeedsYouRow key={`review-${s.id}`} sermon={s} verb="Review and publish" />
            ))}
            {failed.map((s) => (
              <NeedsYouRow key={`failed-${s.id}`} sermon={s} verb="Retry or re-run" />
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="status-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="status-h" className="text-lg font-semibold">System status</h2>
          {unknownCount > 0 ? (
            <p className="text-xs text-muted">
              {unknownCount} of {services.length} could not be measured.
            </p>
          ) : null}
        </div>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {services.map((s) => (
            <li key={s.id}>
              <Card className="flex items-center gap-4">
                <Meter level={s.level} state={s.state} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">{s.label}</p>
                    <Chip tone={s.state}>{serviceStateLabel[s.state]}</Chip>
                  </div>
                  <p className="mt-1 text-sm text-muted [overflow-wrap:anywhere]">{s.detail}</p>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="active-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="active-h" className="text-lg font-semibold">Active jobs</h2>
          <Link
            to="/jobs"
            className="inline-flex min-h-[44px] items-center rounded-md px-2 text-sm font-medium text-accent hover:underline"
          >
            View all
          </Link>
        </div>
        {loading ? (
          <SkeletonList rows={2} />
        ) : activeJobs.length === 0 ? (
          <EmptyState
            title="No jobs running"
            body="Everything is idle. Start a new teaching and it will show up here."
            action={
              <Link to="/new" className={buttonClass("primary")}>
                New teaching
              </Link>
            }
          />
        ) : (
          <ol className="flex flex-col gap-2">
            {activeJobs.map((j) => (
              <li key={j.id}>
                <Card className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <Chip tone={j.state === "running" ? "accent" : "neutral"}>{j.state}</Chip>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{j.kind}</p>
                    <p className="truncate font-mono text-xs text-muted">{j.sermon} · since {j.created}</p>
                  </div>
                  <span className="font-mono text-xs text-muted">{j.duration}</span>
                </Card>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="queue-h">
        <h2 id="queue-h" className="mb-2 text-lg font-semibold">Up next</h2>
        {upNext.length === 0 ? (
          <EmptyState
            title="Queue is clear"
            body="Nothing is waiting. When jobs pile up, the next three appear here."
            action={
              <Link to="/jobs" className={buttonClass()}>
                Open Jobs
              </Link>
            }
          />
        ) : (
          <ol className="flex flex-col gap-2">
            {upNext.map((j) => (
              <li key={j.id}>
                <Card className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <Chip tone="neutral">{j.state}</Chip>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{j.kind}</p>
                    <p className="truncate font-mono text-xs text-muted">{j.sermon} · since {j.created}</p>
                  </div>
                </Card>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="recent-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="recent-h" className="text-lg font-semibold">Recent teachings</h2>
          <Link
            to="/library"
            className="inline-flex min-h-[44px] items-center rounded-md px-2 text-sm font-medium text-accent hover:underline"
          >
            Open library
          </Link>
        </div>
        {loading ? (
          <SkeletonList rows={2} />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {recentSermons.map((s) => (
              <li key={s.id}>
                <Link
                  to={`/library/${s.id}`}
                  aria-label={`${s.title} by ${s.speaker}, ${sermonStatusLabel[s.status]}`}
                  className="block w-full rounded-lg border border-line bg-surface p-4 text-left transition-colors hover:border-muted"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Chip tone={sermonStatusTone[s.status]}>{sermonStatusLabel[s.status]}</Chip>
                    <span className="font-mono text-xs text-muted">{s.duration}</span>
                  </div>
                  <p className="mt-2 text-base font-semibold [overflow-wrap:anywhere]">{s.title}</p>
                  <p className="truncate text-sm text-muted">
                    {s.speaker} · {s.updated}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}