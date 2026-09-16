import { Link } from "react-router-dom";
import { activeJobs, recentSermons, services, type SermonStatus } from "../mock/data";
import { Button, Card, Chip, EmptyState, Meter } from "../components/ui";

const sermonTone: Record<SermonStatus, string> = {
  ready: "ok",
  processing: "info",
  draft: "neutral",
  failed: "error",
};

export function Home() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Home</h1>
          <p className="text-sm text-muted">Pipeline health, active work, and recent teachings.</p>
        </div>
        <Link to="/new">
          <Button variant="primary">Start new sermon</Button>
        </Link>
      </div>

      <section aria-labelledby="status-h">
        <h2 id="status-h" className="mb-2 text-lg font-semibold">System status</h2>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {services.map((s) => (
            <li key={s.id}>
              <Card className="flex items-center gap-4">
                <Meter level={s.level} state={s.state} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">{s.label}</p>
                    <Chip tone={s.state}>{s.state}</Chip>
                  </div>
                  <p className="mt-1 truncate text-sm text-muted">{s.detail}</p>
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
        {activeJobs.length === 0 ? (
          <EmptyState
            title="No jobs running"
            body="Everything is idle. Start a new sermon and it will show up here."
            action={
              <Link to="/new">
                <Button variant="primary">Start new sermon</Button>
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
                    <p className="truncate font-mono text-xs text-muted">{j.id} · {j.sermon} · since {j.created}</p>
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
        <EmptyState
          title="Queue is clear"
          body="Nothing is waiting. When jobs pile up, the next three appear here."
          action={
            <Link to="/jobs">
              <Button>Open Jobs</Button>
            </Link>
          }
        />
      </section>

      <section aria-labelledby="recent-h">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id="recent-h" className="text-lg font-semibold">Recent sermons</h2>
          <Link
            to="/library"
            className="inline-flex min-h-[44px] items-center rounded-md px-2 text-sm font-medium text-accent hover:underline"
          >
            Open library
          </Link>
        </div>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {recentSermons.map((s) => (
            <li key={s.id}>
              <Link
                to={`/library/${s.id}`}
                aria-label={`${s.title} by ${s.speaker}, status ${s.status}`}
                className="block w-full rounded-lg border border-line bg-surface p-4 text-left transition-colors hover:border-muted"
              >
                <div className="flex items-center justify-between gap-2">
                  <Chip tone={sermonTone[s.status]}>{s.status}</Chip>
                  <span className="font-mono text-xs text-muted">{s.duration}</span>
                </div>
                <p className="mt-2 text-base font-semibold [overflow-wrap:anywhere]">{s.title}</p>
                <p className="truncate text-sm text-muted">{s.speaker} · {s.updated}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
