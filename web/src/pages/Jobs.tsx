import { useState } from "react";
import { type Job } from "../mock/data";
import { Button, Card, Chip, ConfirmDialog, EmptyState, PageHeader, SkeletonList, Toast } from "../components/ui";
import { QueryError, useJobDetail, useJobsData } from "../api/hooks";
import { isLive } from "../api/client";

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
  cancelled: "neutral",
};

type PendingAction = { job: Job; action: "cancel" | "delete" };

function JobRow({ job, onAction, readOnly, onNotify }: { job: Job; onAction: (a: PendingAction) => void; readOnly: boolean; onNotify: (msg: string) => void }) {
  const [open, setOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const fullTitle = `${job.kind} — ${job.sermon}`;
  const detail = useJobDetail(job.id, open);
  const lines = readOnly ? (detail.logs ?? []) : job.log;

  const retry = () => {
    setRetrying(true);
    window.setTimeout(() => setRetrying(false), 1500);
  };

  return (
    <li className="min-w-0">
      <Card>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Chip tone={stateTone[job.state]}>{job.state}</Chip>
          <div className="min-w-0 flex-1 basis-40">
            <p className="truncate text-sm font-semibold sm:hidden" title={fullTitle}>
              {fullTitle}
            </p>
            <p className="hidden text-sm font-semibold [overflow-wrap:anywhere] sm:block">
              {fullTitle}
            </p>
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
            {readOnly ? (
              job.state === "failed" ? (
                <Button onClick={() => onNotify("Retry is unavailable in the read-only bridge.")}>
                  Retry
                </Button>
              ) : null
            ) : (
              <>
                {job.state === "running" ? (
                  <Button variant="danger" onClick={() => onAction({ job, action: "cancel" })}>
                    Cancel
                  </Button>
                ) : null}
                {job.state === "queued" ? (
                  <Button onClick={() => onAction({ job, action: "cancel" })}>
                    Cancel
                  </Button>
                ) : null}
                {job.state === "failed" ? (
                  <Button onClick={retry} disabled={retrying} aria-busy={retrying}>
                    {retrying ? "Retrying…" : "Retry"}
                  </Button>
                ) : null}
                {job.state === "done" || job.state === "failed" ? (
                  <Button variant="danger" onClick={() => onAction({ job, action: "delete" })}>
                    Delete
                  </Button>
                ) : null}
              </>
            )}
          </div>
        </div>
        {open ? (
          <div id={`log-${job.id}`} className="mt-3 rounded-md border border-line bg-ink p-3">
            {readOnly && detail.isLoading ? (
              <p className="font-mono text-xs text-muted">Loading log…</p>
            ) : readOnly && detail.error ? (
              <p className="font-mono text-xs text-danger">{detail.error}</p>
            ) : lines.length === 0 ? (
              <p className="font-mono text-xs text-muted">No log lines recorded.</p>
            ) : (
              <ol className="flex flex-col gap-1 font-mono text-xs text-muted">
                {lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ol>
            )}
          </div>
        ) : null}
      </Card>
    </li>
  );
}

export function Jobs() {
  const [tab, setTab] = useState<Tab>("active");
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [removed, setRemoved] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const { data, isLoading: loading, error, retry } = useJobsData();

  const visible =
    tab === "active" ? data.active : tab === "completed" ? data.completed : data.failed;

  const rows = isLive ? visible : visible.filter((j) => !removed.includes(j.id));

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  };

  const finished = data.completed.length + data.failed.length;
  const successRate = finished === 0 ? null : Math.round((data.completed.length / finished) * 100);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const idx = tabs.findIndex((t) => t.id === tab);
    const next = e.key === "ArrowRight" ? (idx + 1) % tabs.length : (idx - 1 + tabs.length) % tabs.length;
    setTab(tabs[next].id);
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Jobs" sub={isLive ? "Every run of the pipeline, with per-job logs. Refreshes every 5 seconds." : "Every run of the pipeline, with per-job logs."} />

      <div role="tablist" aria-label="Job states" onKeyDown={onKeyDown} className="flex gap-1 overflow-x-auto rounded-lg border border-line bg-surface p-1">
        {tabs.map((t) => {
          const selected = tab === t.id;
          const count = t.id === "active" ? data.active.length : t.id === "completed" ? data.completed.length : data.failed.length;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setTab(t.id)}
              className={`flex min-h-[44px] flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-md px-3 text-sm font-semibold transition-colors ${
                selected ? "bg-raised text-mist" : "text-muted hover:bg-raised hover:text-mist"
              }`}
            >
              {t.label}
              <span
                className={`rounded-full border px-2 py-0.5 font-mono text-xs ${
                  t.id === "failed" ? "border-danger text-danger" : "border-line text-muted"
                }`}
                aria-label={`${count} ${t.label.toLowerCase} jobs`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-muted" role="status" aria-live="polite">
        {data.active.length} active · {data.completed.length} completed · {data.failed.length} failed
        {successRate !== null ? ` · ${successRate}% success` : ""}
      </p>

      {loading ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <QueryError message={error} onRetry={retry} />
      ) : rows.length === 0 ? (
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
        <ol className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {rows.map((j) => (
            <JobRow key={j.id} job={j} onAction={setPending} readOnly={isLive} onNotify={showToast} />
          ))}
        </ol>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pending?.action === "cancel" ? "Cancel this job?" : "Delete this job record?"}
        body={
          pending
            ? pending.action === "cancel"
              ? `${pending.job.id} (${pending.job.kind} — ${pending.job.sermon}) will be stopped. This cannot be undone.`
              : `${pending.job.id} (${pending.job.kind} — ${pending.job.sermon}) will be removed from this mock list. This cannot be undone.`
            : ""
        }
        confirmLabel={pending?.action === "cancel" ? "Cancel job" : "Delete"}
        onClose={() => setPending(null)}
        onConfirm={() => {
          if (pending) {
            setRemoved((d) => [...d, pending.job.id]);
            showToast(pending.action === "cancel" ? `Job ${pending.job.id} cancelled (mock).` : `Job ${pending.job.id} deleted (mock).`);
          }
        }}
      />
      <Toast message={toast} />
    </div>
  );
}
