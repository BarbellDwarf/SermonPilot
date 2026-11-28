import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { type Job, retryMockJob } from "../mock/data";
import {
  Button,
  Chip,
  ConfirmDialog,
  EmptyState,
  Icon,
  PageHeader,
  Skeleton,
  SkeletonList,
  staggerStyle,
  buttonClass,
  selectedClass,
} from "../components/ui";
import { useToast } from "../components/toast";
import {
  ACTIVITY_PAGE_SIZE,
  QueryError,
  useActivityJobs,
  useJobDetail,
  type ActivityFilter,
} from "../api/hooks";
import { isLive, writeApi } from "../api/client";
import {
  STATUS_DOT,
  STATUS_TEXT,
  elapsedSince,
  firstErrorLine,
  jobActivityState,
  jobContext,
  jobParameterLines,
  jobRowTitle,
  jobSermon,
  jobSermonId,
  jobStatus,
  jobTypeLabel,
} from "./jobRow";
import { formatCount, formatDate, formatDurationValue, formatRelativeTime } from "../utils/format";

const FILTERS: { id: ActivityFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Failed" },
  { id: "interrupted", label: "Interrupted" },
];

const EMPTY_COPY: Record<ActivityFilter, { title: string; body: string }> = {
  all: {
    title: "No jobs yet",
    body: "Processing, metadata, and transcription jobs appear here with their logs and outcomes.",
  },
  active: {
    title: "No active jobs",
    body: "A job appears here as soon as it is queued, with live progress and elapsed time.",
  },
  completed: {
    title: "Nothing completed yet",
    body: "Finished jobs appear here with their duration and full log.",
  },
  failed: {
    title: "No failed jobs",
    body: "Failures and cancelled jobs land here with the first error line and a Retry action.",
  },
  interrupted: {
    title: "No interrupted jobs",
    body: "Jobs stopped by an app restart appear here so you can retry them.",
  },
};

type PendingAction = { job: Job; action: "stop" | "delete" };

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
  void navigator.clipboard.writeText(id).then(() => notify("Job ID copied.")).catch(selectAndTell);
}

function JobRow({
  job,
  index,
  open,
  now,
  readOnly,
  retrying,
  onToggle,
  onAction,
  onRetry,
  onNotify,
}: {
  job: Job;
  index: number;
  open: boolean;
  now: number;
  readOnly: boolean;
  retrying: boolean;
  onToggle: (id: string) => void;
  onAction: (action: PendingAction) => void;
  onRetry: (job: Job) => void;
  onNotify: (msg: string) => void;
}) {
  const active = job.state === "queued" || job.state === "running";
  const activityState = jobActivityState(job);
  const resolveTeaching = !active && activityState !== "completed" && !jobSermonId(job);
  const detail = useJobDetail(job.id, open || resolveTeaching, open && active);
  const status = jobStatus(job);
  const title = jobRowTitle(job);
  const parameters = detail.parameters ?? job.parameters ?? null;
  const context = jobContext({ ...job, parameters });
  const sermonId = jobSermonId({ ...job, parameters });
  const lines = readOnly ? (detail.logs ?? job.log) : job.log;
  const errorLine = firstErrorLine(job.error);
  const progress = Math.max(0, Math.min(100, Math.round(job.progress || 0)));
  const elapsed = status === "RUNNING" ? elapsedSince(job.createdAt, now) : "";
  const parameterLines = open ? jobParameterLines(parameters) : [];
  const canStop = active;
  const canRetry = activityState === "failed" || activityState === "interrupted";
  const canDelete = !readOnly && job.state === "done";

  const actions = (includeCopy: boolean) => (
    <div
      role="group"
      aria-label="Job actions"
      className="flex flex-wrap items-center gap-2"
    >
      {canRetry ? (
        <Button variant="primary" disabled={retrying} onClick={() => onRetry(job)}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      ) : null}
      {canStop ? (
        <Button variant="danger" onClick={() => onAction({ job, action: "stop" })}>
          Stop job
        </Button>
      ) : null}
      {canDelete ? (
        <Button variant="danger" onClick={() => onAction({ job, action: "delete" })}>
          Delete
        </Button>
      ) : null}
      {sermonId ? (
        <Link
          to={`/teaching/${encodeURIComponent(sermonId)}`}
          className={buttonClass("secondary", "px-3")}
        >
          View teaching
        </Link>
      ) : null}
      {includeCopy ? (
        <Button
          onClick={(event) =>
            copyJobId(
              job.id,
              onNotify,
              event.currentTarget.closest("[data-job-detail]")?.querySelector("code") ?? null,
            )
          }
        >
          Copy
        </Button>
      ) : null}
    </div>
  );

  return (
    <li className="stagger-item min-w-0" style={staggerStyle(index)}>
      <div className="flex min-w-0 flex-col sm:flex-row sm:items-stretch">
        <button
          type="button"
          onClick={() => onToggle(job.id)}
          aria-expanded={open}
          aria-controls={`job-detail-${job.id}`}
          data-testid={`job-row-${job.id}`}
          data-job-id={job.id}
          className="grid min-h-[56px] min-w-0 flex-1 grid-cols-[auto_minmax(0,1fr)_auto_1rem] items-center gap-x-3 gap-y-1 px-4 py-3 text-left transition-colors duration-150 hover:bg-selected max-sm:min-h-[84px] sm:grid-cols-[7rem_minmax(0,1fr)_auto_1rem] sm:[grid-template-areas:'status_title_time_chev'_'extra_extra_extra_extra'] [grid-template-areas:'status_status_time_chev'_'title_title_title_title'_'extra_extra_extra_extra']"
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
            title={job.createdAt ? formatRelativeTime(job.createdAt) : undefined}
            className="[grid-area:time] shrink-0 font-mono text-xs text-muted"
          >
            {job.created}
          </time>
          <Icon
            name="chevron"
            className={`[grid-area:chev] h-4 w-4 text-muted transition-transform duration-150 ${
              open ? "rotate-180" : ""
            }`}
          />
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
                  className="block h-full rounded-full bg-info"
                  style={{ width: `${progress}%` }}
                />
              </span>
              <span className="shrink-0 font-mono text-xs text-muted">
                {progress}%{elapsed ? ` · ${elapsed}` : ""}
              </span>
            </span>
          ) : errorLine &&
            (status === "FAILED" || status === "INTERRUPTED" || status === "CANCELLED") ? (
            <span
              className={`[grid-area:extra] line-clamp-1 text-xs ${
                status === "INTERRUPTED"
                  ? "text-warn"
                  : status === "CANCELLED"
                    ? "text-muted"
                    : "text-danger"
              }`}
            >
              {errorLine}
            </span>
          ) : null}
        </button>
        {!open && (canRetry || canStop || canDelete || sermonId) ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2 sm:border-l sm:border-t-0 sm:px-3">
            {actions(false)}
          </div>
        ) : null}
      </div>

      {open ? (
        <div
          id={`job-detail-${job.id}`}
          data-testid={`job-detail-${job.id}`}
          data-job-detail
          className="border-t border-line bg-ink/40 px-4 pb-4 pt-3"
        >
          <div className="border-b border-line pb-3">{actions(true)}</div>

          {job.description ? (
            <p className="mt-3 max-w-prose text-sm text-muted">{job.description}</p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <Chip tone="neutral">{jobTypeLabel(job)}</Chip>
            {context.speaker ? (
              <span>
                {context.speaker}
                {context.date ? ` · ${formatDate(context.date)}` : ""}
              </span>
            ) : null}
            <span className="font-mono">
              {status === "RUNNING" && elapsed ? elapsed : formatDurationValue(job.duration)}
            </span>
            {job.finished ? <span>Finished {job.finished}</span> : null}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">Job ID</span>
            <code className="min-w-0 break-all font-mono text-xs text-mist">{job.id}</code>
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
            <div
              tabIndex={0}
              aria-label="Scrollable job log"
              className="mt-1 max-h-64 overflow-y-auto overflow-x-hidden rounded-md border border-line bg-surface p-3"
            >
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
                <ol className="flex min-w-0 flex-col gap-1 break-words font-mono text-xs text-muted">
                  {lines.map((line, index) => (
                    <li key={`${index}-${line}`} className="min-w-0 [overflow-wrap:anywhere]">
                      {line}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </section>
        </div>
      ) : null}
    </li>
  );
}

export function Activity() {
  const location = useLocation();
  const navigate = useNavigate();
  const { id: routeId } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const notify = useToast();
  const searchParams = new URLSearchParams(location.search);
  const stateParam = searchParams.get("state");
  const state: ActivityFilter = FILTERS.some((filter) => filter.id === stateParam)
    ? (stateParam as ActivityFilter)
    : "all";
  const expandedId = routeId ?? searchParams.get("job");
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [removed, setRemoved] = useState<string[]>([]);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const data = useActivityJobs(state);
  const rows = isLive ? data.jobs : data.jobs.filter((job) => !removed.includes(job.id));
  const hasRunning = rows.some((job) => job.state === "running");

  useEffect(() => {
    if (stateParam === null || FILTERS.some((filter) => filter.id === stateParam)) return;
    const next = new URLSearchParams(location.search);
    next.delete("state");
    navigate({ pathname: location.pathname, search: next.toString() }, { replace: true });
  }, [location.pathname, location.search, navigate, stateParam]);

  useEffect(() => {
    if (!hasRunning) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasRunning]);

  const showToast = (message: string) => notify.info(message);

  const toggle = (id: string) => {
    const next = new URLSearchParams(location.search);
    next.delete("job");
    if (expandedId === id) {
      navigate({ pathname: "/activity", search: next.toString() });
      return;
    }
    navigate({ pathname: `/activity/${encodeURIComponent(id)}`, search: next.toString() });
  };

  const selectFilter = (filter: ActivityFilter) => {
    const next = new URLSearchParams(location.search);
    next.delete("job");
    if (filter === "all") next.delete("state");
    else next.set("state", filter);
    navigate({ pathname: "/activity", search: next.toString() });
  };

  const retry = async (job: Job) => {
    if (retryingId) return;
    setRetryingId(job.id);
    try {
      const result = isLive
        ? await writeApi.retryJob(job.id)
        : { job_id: retryMockJob(job).id, status: "queued" };
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["job", job.id] });
      void queryClient.invalidateQueries({ queryKey: ["job", result.job_id] });
      navigate({
        pathname: `/activity/${encodeURIComponent(result.job_id)}`,
        search: "?state=active",
      });
      notify.success(`Retry queued as job ${result.job_id}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Try again.";
      const status =
        typeof error === "object" && error !== null
          ? (error as { status?: number }).status
          : undefined;
      notify.error(
        status === 409
          ? `Job ${job.id} cannot be retried right now. ${message}`
          : `Could not retry job ${job.id}: ${message}`,
      );
    } finally {
      setRetryingId(null);
    }
  };

  const confirm = () => {
    if (!pending) return;
    const { job, action } = pending;
    setPending(null);
    if (action === "stop" && isLive) {
      void writeApi
        .cancelJob(job.id)
        .then((result) => {
          if (result.cancelled) {
            notify.success(
              `Job ${job.id} stopped. Finished work was kept; retry is available in Activity.`,
            );
            void queryClient.invalidateQueries({ queryKey: ["jobs"] });
            void queryClient.invalidateQueries({ queryKey: ["job", job.id] });
          } else {
            notify.error(`Job ${job.id} could not be stopped.`);
          }
        })
        .catch((error) => notify.error(`Could not stop job: ${(error as Error).message}`));
      return;
    }
    setRemoved((current) => [...current, job.id]);
    notify.undo(
      action === "stop"
        ? `Job ${job.id} stopped. Use Undo to restore it in this demo.`
        : `Job ${job.id} deleted.`,
      () => setRemoved((current) => current.filter((id) => id !== job.id)),
    );
  };

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader title="Activity" sub={isLive ? "Refreshes every 5 seconds." : undefined} />

      <div
        role="group"
        aria-label="Job filters"
        className="flex min-w-0 gap-2 overflow-x-auto pb-1"
      >
        {FILTERS.map((filter) => {
          const selected = state === filter.id;
          const count = data.counts[filter.id];
          return (
            <button
              key={filter.id}
              type="button"
              aria-pressed={selected}
              onClick={() => selectFilter(filter.id)}
              className={`inline-flex min-h-[44px] shrink-0 items-center gap-2 whitespace-nowrap rounded-full border px-3 text-sm font-semibold transition-colors ${
                selected
                  ? selectedClass
                  : "border-line bg-surface text-muted hover:border-muted hover:text-mist"
              }`}
            >
              {filter.label}
              <span
                className={`rounded-sm border px-1.5 py-0.5 font-mono text-xs tabular-nums ${
                  filter.id === "failed" ? "border-danger text-danger" : "border-line text-muted"
                }`}
              >
                {count.toLocaleString()}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <p role="status" aria-live="polite">
          {data.counts.completed + data.counts.failed + data.counts.interrupted === 0
            ? "No finished jobs yet."
            : `${Math.round(
                (data.counts.completed /
                  (data.counts.completed + data.counts.failed + data.counts.interrupted)) *
                  100,
              )}% success across ${formatCount(
                data.counts.completed + data.counts.failed + data.counts.interrupted,
                "finished job",
              )}.`}
        </p>
        <p className="font-mono">
          {data.total === 0
            ? "0 jobs"
            : `${data.page * ACTIVITY_PAGE_SIZE + 1}-${Math.min(
                (data.page + 1) * ACTIVITY_PAGE_SIZE,
                data.total,
              )} of ${formatCount(data.total, "job")}`}
        </p>
      </div>

      {data.isLoading ? (
        <SkeletonList rows={5} variant="row" rowHeight={64} />
      ) : data.error ? (
        <QueryError message={data.error} onRetry={data.retry} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={EMPTY_COPY[state].title}
          body={EMPTY_COPY[state].body}
          action={
            state === "all" ? (
              <Link to="/new" className={buttonClass("primary")}>
                Start a teaching
              </Link>
            ) : (
              <Button onClick={() => selectFilter("all")}>View all jobs</Button>
            )
          }
        />
      ) : (
        <ol
          role="list"
          className="flex min-w-0 flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface"
        >
          {rows.map((job, index) => (
            <JobRow
              key={job.id}
              job={job}
              index={index}
              open={expandedId === job.id}
              now={now}
              readOnly={isLive}
              retrying={retryingId === job.id}
              onToggle={toggle}
              onAction={setPending}
              onRetry={(job) => void retry(job)}
              onNotify={showToast}
            />
          ))}
        </ol>
      )}

      {data.pageCount > 1 ? (
        <nav aria-label="Job pages" className="flex items-center justify-end gap-2">
          <Button disabled={data.page === 0} onClick={data.previousPage}>
            Previous page
          </Button>
          <Button disabled={data.page + 1 >= data.pageCount} onClick={data.nextPage}>
            Next page
          </Button>
        </nav>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        title={pending?.action === "stop" ? "Stop this job?" : "Delete this job record?"}
        body={
          pending
            ? pending.action === "stop"
              ? isLive
                ? `${jobRowTitle(pending.job)} (${pending.job.id}) will stop now. Finished work is kept, and you can retry the job after it stops.`
                : `${jobRowTitle(pending.job)} (${pending.job.id}) will stop now. You can undo this from the toast.`
              : `${jobRowTitle(pending.job)} (${pending.job.id}) will be removed from this demo list. This cannot be undone.`
            : ""
        }
        confirmLabel={pending?.action === "stop" ? "Stop job" : "Delete"}
        onClose={() => setPending(null)}
        onConfirm={confirm}
      />
    </div>
  );
}
