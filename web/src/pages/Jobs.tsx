import { useEffect, useState } from "react";
import { type Job } from "../mock/data";
import { Button, Chip, ConfirmDialog, EmptyState, PageHeader, Skeleton, SkeletonList, Toast } from "../components/ui";
import { QueryError, useJobDetail, useJobsData } from "../api/hooks";
import { isLive, writeApi } from "../api/client";
import {
  STATUS_DOT,
  STATUS_TEXT,
  elapsedSince,
  firstErrorLine,
  jobContext,
  jobParameterLines,
  jobRowTitle,
  jobSermon,
  jobStatus,
  jobTypeLabel,
} from "./jobRow";

type Tab = "active" | "completed" | "failed";

const tabs: { id: Tab; label: string }[] = [
  { id: "active", label: "Active" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Failed" },
];

type PendingAction = { job: Job; action: "cancel" | "delete" };

function copyJobId(
  id: string,
  notify: (msg: string) => void,
  source: HTMLElement | null,
) {
  const selectAndTell = () => {
    if (source) {
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
    notify("Copy failed: clipboard unavailable. Job ID selected; press Ctrl/Cmd+C.");
  };
  if (!navigator.clipboard) {
    selectAndTell();
    return;
  }
  void navigator.clipboard.writeText(id).then(() => notify("Job id copied.")).catch(selectAndTell);
}

function JobRow({
  job,
  open,
  now,
  readOnly,
  onToggle,
  onAction,
  onNotify,
}: {
  job: Job;
  open: boolean;
  now: number;
  readOnly: boolean;
  onToggle: (id: string) => void;
  onAction: (a: PendingAction) => void;
  onNotify: (msg: string) => void;
}) {
  const detail = useJobDetail(job.id, open);
  const status = jobStatus(job);
  const title = jobRowTitle(job);
  const parameters = detail.parameters ?? job.parameters ?? null;
  const context = jobContext({ ...job, parameters });
  const lines = readOnly ? (detail.logs ?? []) : job.log;
  const errorLine = firstErrorLine(job.error);
  const progress = Math.max(0, Math.min(100, Math.round(job.progress || 0)));
  const elapsed = status === "RUNNING" ? elapsedSince(job.createdAt, now) : "";
  const parameterLines = open ? jobParameterLines(parameters) : [];

  const canCancel =
    job.state === "queued" || job.state === "running" || (readOnly && job.state === "failed");
  const canRetry = job.state === "failed";
  const canDelete = !readOnly && (job.state === "done" || job.state === "failed");

  const retry = () =>
    onNotify(
      readOnly
        ? "Retry is unavailable in the read-only bridge."
        : "Retry is unavailable in demo mode.",
    );

  return (
    <li className="min-w-0">
      <button
        type="button"
        onClick={() => onToggle(job.id)}
        aria-expanded={open}
        aria-controls={`job-detail-${job.id}`}
        data-testid={`job-row-${job.id}`}
        data-job-id={job.id}
        className="grid min-h-[56px] w-full grid-cols-[auto_minmax(0,1fr)_auto_1rem] items-center gap-x-3 gap-y-1 px-4 py-3 text-left transition-colors duration-150 hover:bg-raised sm:grid-cols-[8rem_minmax(0,1fr)_auto_1rem] sm:[grid-template-areas:'status_title_time_chev'_'extra_extra_extra_extra'] [grid-template-areas:'status_status_time_chev'_'title_title_title_title'_'extra_extra_extra_extra']"
      >
        <span className="[grid-area:status] inline-flex min-w-0 items-center gap-2 justify-self-start">
          <span
            aria-hidden="true"
            className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[status]}`}
          />
          <span
            className={`font-mono text-xs font-semibold uppercase tracking-wide ${STATUS_TEXT[status]}`}
          >
            {status}
          </span>
        </span>
        <span
          className="[grid-area:title] min-w-0 truncate text-sm font-semibold"
          title={title}
        >
          {title}
        </span>
        <time
          dateTime={job.createdAt ? job.createdAt.replace(" ", "T") : undefined}
          className="[grid-area:time] shrink-0 font-mono text-xs text-muted"
        >
          {job.created}
        </time>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
          className={`[grid-area:chev] h-4 w-4 text-muted transition-transform duration-150 ${
            open ? "rotate-180" : ""
          }`}
        >
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {status === "RUNNING" ? (
          <span className="[grid-area:extra] flex min-w-0 items-center gap-2">
            <span
              role="progressbar"
              aria-label={`Progress for ${jobSermon(job)}`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
              className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-raised"
            >
              <span
                className="block h-full rounded-full bg-accent"
                style={{ width: `${progress}%` }}
              />
            </span>
            <span className="shrink-0 font-mono text-xs text-muted">
              {progress}%{elapsed ? ` · ${elapsed}` : ""}
            </span>
          </span>
        ) : errorLine && (status === "FAILED" || status === "INTERRUPTED") ? (
          <span
            className={`[grid-area:extra] line-clamp-1 text-xs ${
              status === "INTERRUPTED" ? "text-warn" : "text-danger"
            }`}
          >
            {errorLine}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          id={`job-detail-${job.id}`}
          data-testid={`job-detail-${job.id}`}
          className="border-t border-line bg-ink/40 px-4 pb-4 pt-3"
        >
          {job.description ? (
            <p className="max-w-prose text-sm text-muted">{job.description}</p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <Chip tone="neutral">{jobTypeLabel(job)}</Chip>
            {context.speaker ? (
              <span>
                {context.speaker}
                {context.date ? ` · ${context.date}` : ""}
              </span>
            ) : null}
            <span className="font-mono">
              {status === "RUNNING" && elapsed ? elapsed : job.duration}
            </span>
            {job.finished ? <span>Finished {job.finished}</span> : null}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
            <span className="text-xs text-muted">Job ID</span>
            <code className="min-w-0 break-all font-mono text-xs text-mist">{job.id}</code>
            <button
              type="button"
              onClick={(event) =>
                copyJobId(
                  job.id,
                  onNotify,
                  event.currentTarget.parentElement?.querySelector("code") ?? null,
                )
              }
              className="inline-flex min-h-[44px] items-center rounded-md px-2 text-xs font-semibold text-accent hover:underline"
            >
              Copy
            </button>
          </div>

          {parameterLines.length > 0 ? (
            <section aria-label="Job parameters" className="mt-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                Parameters
              </h3>
              <ul className="mt-1 flex flex-col gap-1 font-mono text-xs text-muted">
                {parameterLines.map((line) => (
                  <li key={line} className="break-words">
                    {line}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-label="Job log" className="mt-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Log</h3>
            <div className="mt-1 max-h-64 overflow-auto rounded-md border border-line bg-surface p-3">
              {readOnly && detail.isLoading ? (
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-3 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              ) : readOnly && detail.error ? (
                <p className="font-mono text-xs text-danger">{detail.error}</p>
              ) : lines.length === 0 ? (
                <p className="font-mono text-xs text-muted">No log lines recorded.</p>
              ) : (
                <ol className="flex flex-col gap-1 font-mono text-xs text-muted">
                  {lines.map((line, index) => (
                    <li key={`${index}-${line}`}>{line}</li>
                  ))}
                </ol>
              )}
            </div>
          </section>

          {canCancel || canRetry || canDelete ? (
            <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-line pt-3">
              {canRetry ? <Button onClick={retry}>Retry</Button> : null}
              {canCancel ? (
                <Button
                  variant={job.state === "running" ? "danger" : undefined}
                  onClick={() => onAction({ job, action: "cancel" })}
                >
                  Cancel
                </Button>
              ) : null}
              {canDelete ? (
                <Button variant="danger" onClick={() => onAction({ job, action: "delete" })}>
                  Delete
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export function Jobs() {
  const [tab, setTab] = useState<Tab>("active");
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [removed, setRemoved] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const { data, isLoading: loading, error, retry } = useJobsData();

  const visible =
    tab === "active" ? data.active : tab === "completed" ? data.completed : data.failed;

  const rows = isLive ? visible : visible.filter((j) => !removed.includes(j.id));
  const hasRunning = rows.some((j) => j.state === "running");

  useEffect(() => {
    if (!hasRunning) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasRunning]);

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  };

  const toggle = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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
      <PageHeader title="Jobs" sub={isLive ? "Refreshes every 5 seconds." : undefined} />

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
                className={`rounded-sm border px-1.5 py-0.5 font-mono text-xs tabular-nums ${
                  t.id === "failed" ? "border-danger text-danger" : "border-line text-muted"
                }`}
                aria-label={`${count} ${t.label.toLowerCase()} jobs`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-muted" role="status" aria-live="polite">
        {successRate === null
          ? "No finished jobs yet."
          : `${successRate}% success across ${finished} finished ${finished === 1 ? "job" : "jobs"}.`}
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
        <ol className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
          {rows.map((j) => (
            <JobRow
              key={j.id}
              job={j}
              open={expanded.has(j.id)}
              now={now}
              readOnly={isLive}
              onToggle={toggle}
              onAction={setPending}
              onNotify={showToast}
            />
          ))}
        </ol>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pending?.action === "cancel" ? "Cancel this job?" : "Delete this job record?"}
        body={
          pending
            ? pending.action === "cancel"
              ? `${jobRowTitle(pending.job)} (${pending.job.id}) will be stopped. This cannot be undone.`
              : `${jobRowTitle(pending.job)} (${pending.job.id}) will be removed from this mock list. This cannot be undone.`
            : ""
        }
        confirmLabel={pending?.action === "cancel" ? "Cancel job" : "Delete"}
        onClose={() => setPending(null)}
        onConfirm={() => {
          if (pending) {
            if (isLive && pending.action === "cancel") {
              const id = pending.job.id;
              setPending(null);
              void writeApi
                .cancelJob(id)
                .then((res) => {
                  showToast(res.cancelled ? `Job ${id} cancelled.` : `Job ${id} could not be cancelled.`);
                  retry();
                })
                .catch((e) => showToast(`Could not cancel: ${(e as Error).message}`));
            } else {
              setRemoved((d) => [...d, pending.job.id]);
              showToast(pending.action === "cancel" ? `Job ${pending.job.id} cancelled (mock).` : `Job ${pending.job.id} deleted (mock).`);
            }
          }
        }}
      />
      <Toast message={toast} />
    </div>
  );
}
