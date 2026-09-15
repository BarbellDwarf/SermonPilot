import { useState } from "react";
import { activeJobs, completedJobs, failedJobs, type Job } from "../mock/data";
import { Button, Card, Chip, ConfirmDialog, EmptyState } from "../components/ui";

type Tab = "active" | "completed" | "failed";

const tabs: { id: Tab; label: string }[] = [
  { id: "active", label: "Active" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Failed" },
];

const stateTone: Record<Job["state"], string> = {
  queued: "neutral",
  running: "accent",
  done: "ok",
  failed: "error",
};

function JobRow({ job, onDelete }: { job: Job; onDelete: (j: Job) => void }) {
  const [open, setOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const retry = () => {
    setRetrying(true);
    window.setTimeout(() => setRetrying(false), 1500);
  };

  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Chip tone={stateTone[job.state]}>{job.state}</Chip>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{job.kind} — {job.sermon}</p>
            <p className="truncate font-mono text-xs text-muted">
              {job.id} · created {job.created}{job.finished ? ` · finished ${job.finished}` : ""} · {job.duration}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-controls={`log-${job.id}`}
              className="inline-flex min-h-[44px] items-center rounded-md border border-line px-3 text-sm font-medium text-muted transition-colors hover:border-muted hover:text-mist disabled:opacity-45"
            >
              {open ? "Hide log" : "View log"}
            </button>
            {job.state === "failed" ? (
              <Button onClick={retry} disabled={retrying} aria-busy={retrying}>
                {retrying ? "Retrying…" : "Retry"}
              </Button>
            ) : null}
            <Button variant="danger" onClick={() => onDelete(job)}>
              Delete
            </Button>
          </div>
        </div>
        {open ? (
          <div id={`log-${job.id}`} className="mt-3 rounded-md border border-line bg-ink p-3">
            <ol className="flex flex-col gap-1 font-mono text-xs text-muted">
              {job.log.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ol>
          </div>
        ) : null}
      </Card>
    </li>
  );
}

export function Jobs() {
  const [tab, setTab] = useState<Tab>("active");
  const [pendingDelete, setPendingDelete] = useState<Job | null>(null);
  const [deleted, setDeleted] = useState<string[]>([]);

  const visible =
    tab === "active" ? activeJobs : tab === "completed" ? completedJobs : failedJobs;

  const rows = visible.filter((j) => !deleted.includes(j.id));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const idx = tabs.findIndex((t) => t.id === tab);
    const next = e.key === "ArrowRight" ? (idx + 1) % tabs.length : (idx - 1 + tabs.length) % tabs.length;
    setTab(tabs[next].id);
  };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Jobs</h1>
        <p className="text-sm text-muted">Every run of the pipeline, with per-job logs.</p>
      </div>

      <div role="tablist" aria-label="Job states" onKeyDown={onKeyDown} className="flex gap-1 rounded-lg border border-line bg-surface p-1">
        {tabs.map((t) => {
          const selected = tab === t.id;
          const count = t.id === "active" ? activeJobs.length : t.id === "completed" ? completedJobs.length : failedJobs.length;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setTab(t.id)}
              className={`flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold transition-colors ${
                selected ? "bg-raised text-mist" : "text-muted hover:bg-raised hover:text-mist"
              }`}
            >
              {t.label}
              <span
                className={`rounded-full px-2 py-0.5 font-mono text-xs ${
                  t.id === "failed" ? "text-danger" : "text-muted"
                }`}
                aria-label={`${count} ${t.label.toLowerCase} jobs`}
              >
                {count}
              </span>
              {selected ? <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" /> : null}
            </button>
          );
        })}
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title={tab === "failed" ? "No failed jobs" : tab === "active" ? "No active jobs" : "Nothing completed yet"}
          body={
            tab === "failed"
              ? "Failures land here with a Retry button next to each one."
              : tab === "active"
                ? "Start a run and it will appear here with live status."
                : "Finished runs appear here with their durations and logs."
          }
        />
      ) : (
        <ol className="flex flex-col gap-3">
          {rows.map((j) => (
            <JobRow key={j.id} job={j} onDelete={setPendingDelete} />
          ))}
        </ol>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this job record?"
        body={pendingDelete ? `${pendingDelete.id} (${pendingDelete.kind} — ${pendingDelete.sermon}) will be removed from this mock list. This cannot be undone.` : ""}
        confirmLabel="Delete"
        onClose={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) setDeleted((d) => [...d, pendingDelete.id]);
        }}
      />
    </div>
  );
}
