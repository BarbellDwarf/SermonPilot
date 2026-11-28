import { Button } from "../ui";

export interface RunSummaryProps {
  source: string;
  title: string;
  speaker: string;
  date: string;
  eventType: string;
  output: string;
  dryRun: boolean;
  processing: string;
  readiness: string;
  starting: boolean;
  valid: boolean;
}

function SummaryRow({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={`min-w-0 py-1.5 ${className}`}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-mist [overflow-wrap:anywhere]">{value}</dd>
    </div>
  );
}

export function RunSummary({
  source,
  title,
  speaker,
  date,
  eventType,
  output,
  dryRun,
  processing,
  readiness,
  starting,
  valid,
}: RunSummaryProps) {
  return (
    <aside
      aria-label="Selection summary"
      className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-20 border-t border-line bg-ink/95 shadow-[0_-8px_24px_-16px_rgba(0,0,0,0.8)] backdrop-blur md:bottom-0 lg:sticky lg:inset-auto lg:top-24 lg:z-auto lg:rounded-lg lg:border lg:border-line lg:bg-surface lg:shadow-none lg:backdrop-blur-none"
    >
      <div className="flex items-center gap-3 px-4 py-1.5 sm:px-4 sm:py-3 lg:block lg:p-4">
        <div className="hidden items-center justify-between gap-3 lg:flex">
          <h2 className="text-lg font-semibold">Run summary</h2>
          <span className="text-xs font-semibold text-muted">{dryRun ? "Dry run" : "Live upload"}</span>
        </div>

        <p className="min-w-0 flex-1 truncate text-xs text-mist sm:hidden" title={`${source} · ${title} · ${speaker} · ${date}${dryRun ? " · Dry run" : ""}`}>
          <span className="font-semibold">{title}</span> · {speaker} · {date} · {source}
          {dryRun ? " · Dry run" : ""}
        </p>

        <dl className="hidden grid-cols-4 gap-x-4 sm:grid lg:grid-cols-1">
          <SummaryRow label="Source" value={source} />
          <SummaryRow label="Title" value={title} />
          <SummaryRow label="Speaker" value={speaker} />
          <SummaryRow label="Date" value={date} />
          <SummaryRow label="Output" value={output} />
          <SummaryRow label="Mode" value={dryRun ? "Dry run" : "Live upload"} />
          <SummaryRow label="Event type" value={eventType} />
          <SummaryRow label="Processing" value={processing} className="sm:col-span-4 lg:col-span-1" />
        </dl>

        <div className="ml-auto min-w-0 sm:mt-2 sm:flex sm:items-center sm:gap-3 lg:mt-2 lg:block">
          <p
            id="ns-readiness"
            className="sr-only min-w-0 truncate text-xs text-muted sm:not-sr-only"
            role="status"
            aria-live="polite"
          >
            {readiness}
          </p>
          <Button
            variant="primary"
            type="submit"
            data-testid="start-processing"
            disabled={!valid || starting}
            aria-busy={starting}
            aria-describedby="ns-readiness"
            className="shrink-0 sm:w-auto lg:mt-3 lg:w-full"
          >
            {starting ? "Queueing…" : "Start processing"}
          </Button>
        </div>
      </div>
    </aside>
  );
}
