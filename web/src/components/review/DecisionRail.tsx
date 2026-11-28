import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button, buttonClass } from "../ui";
import type { WorkspacePrimary } from "../sermonActions";

export interface QueuedWorkspaceJob {
  id: string;
  message: string;
}

export function DecisionRail({
  primary,
  onPrimary,
  primaryDisabled = false,
  primaryBusy = false,
  queued,
  onSendBack,
  moreActions,
  summary,
  jobHref = "/activity",
}: {
  primary: WorkspacePrimary;
  onPrimary: () => void;
  primaryDisabled?: boolean;
  primaryBusy?: boolean;
  queued: QueuedWorkspaceJob | null;
  onSendBack?: () => void;
  moreActions: ReactNode;
  summary: ReactNode;
  jobHref?: string;
}) {
  return (
    <aside
      aria-label="Teaching decision"
      data-testid="approval-bar"
      className="fixed inset-x-0 bottom-[calc(var(--chrome-bottom)+0.5rem)] z-20 border-t border-line bg-surface/95 p-1.5 shadow-sticky backdrop-blur md:bottom-3 md:p-3 lg:sticky lg:inset-auto lg:bottom-auto lg:top-20 lg:rounded-lg lg:border lg:border-line lg:p-4 lg:shadow-sm"
    >
      <div className="hidden lg:block">{summary}</div>
      {queued ? (
        <div role="status" data-testid="queued-state" className="flex flex-col gap-2 text-sm">
          <p>Queued as job {queued.id} · {queued.message}</p>
          <Link to={`/activity/${queued.id}`} data-testid="queued-job-link" className={buttonClass("secondary", "w-fit")}>View job</Link>
        </div>
      ) : primary.kind === "none" ? (
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-muted">Published to SermonAudio.</p>
          {moreActions}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {primary.kind === "view-job" ? (
            <Link to={jobHref} data-testid="approve-primary" className={buttonClass("primary", "min-w-0 flex-1 lg:flex-none")}>{primary.label}</Link>
          ) : (
            <Button
              variant="primary"
              data-testid="approve-primary"
              className="min-w-0 flex-1 lg:flex-none"
              onClick={onPrimary}
              disabled={primaryDisabled}
              aria-busy={primaryBusy}
            >
              {primaryBusy ? "Queueing…" : primary.label}
            </Button>
          )}
          {onSendBack ? <Button onClick={onSendBack} aria-label="Send back with note" className="shrink-0 px-3"><span className="sm:hidden">Send back</span><span className="hidden sm:inline">Send back with note</span></Button> : null}
          {moreActions}
        </div>
      )}
    </aside>
  );
}
