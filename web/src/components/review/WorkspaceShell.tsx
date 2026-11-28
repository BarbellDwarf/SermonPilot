import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { LibrarySermon } from "../../mock/data";
import type { LifecycleState } from "../../utils/lifecycle";
import { LIFECYCLE_META } from "../../utils/lifecycle";
import { formatDate } from "../../utils/format";
import { StatusChip } from "../StatusChip";

export function WorkspaceShell({
  sermon,
  state,
  statusDetail,
  onStatusOpen,
  body,
  tabs,
  decision,
}: {
  sermon: LibrarySermon;
  state: LifecycleState;
  statusDetail: string;
  onStatusOpen: () => void;
  body: ReactNode;
  tabs: ReactNode;
  decision: ReactNode;
}) {
  return (
    <div data-testid="teaching-workspace" className="flex flex-col gap-4 pb-44 md:pb-28 lg:pb-0">
      <header className="min-w-0 lg:col-start-1">
        <Link to="/" className="inline-flex min-h-[44px] w-fit items-center rounded-md px-2 text-sm font-medium text-accent hover:underline">← Inbox</Link>
        <div className="mt-1 flex min-w-0 flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="line-clamp-2 text-2xl font-bold leading-tight tracking-tight [overflow-wrap:anywhere]" title={sermon.title}>{sermon.title}</h1>
            <p className="mt-1 max-w-prose text-sm text-muted">{sermon.speaker || "Unknown speaker"} · {formatDate(sermon.date)}</p>
          </div>
          <div className="hidden lg:block"><StatusChip state={state} /></div>
        </div>
        <button
          type="button"
          data-testid="mobile-status-trigger"
          title={statusDetail}
          onClick={onStatusOpen}
          className="mt-3 inline-flex min-h-[44px] w-full items-center rounded-md border border-line bg-surface px-3 text-left text-xs text-muted lg:hidden"
        >
          <span className="truncate">{LIFECYCLE_META[state].label} · {statusDetail}</span>
        </button>
      </header>
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <div className="flex min-w-0 flex-col gap-4 lg:col-start-1 lg:row-start-1">{body}</div>
        <div className="min-w-0 lg:col-start-2 lg:row-start-1 lg:row-span-2">{decision}</div>
        <div className="min-w-0 lg:col-start-1 lg:row-start-2">{tabs}</div>
      </div>
    </div>
  );
}
