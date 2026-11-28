import { useState, type ReactNode } from "react";

export function CollapsibleSection({
  id,
  title,
  summary,
  defaultOpen = false,
  open,
  onToggle,
  testId,
  className = "",
  children,
}: {
  id: string;
  title: string;
  summary?: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onToggle?: (next: boolean) => void;
  testId?: string;
  className?: string;
  children: ReactNode;
}) {
  const [internal, setInternal] = useState(defaultOpen);
  const isOpen = open ?? internal;
  const toggle = () => {
    const next = !isOpen;
    if (onToggle) onToggle(next);
    else setInternal(next);
  };
  return (
    <section id={id} data-testid={testId} aria-labelledby={`${id}-h`} className={`rounded-lg border border-line bg-surface ${className}`}>
      <div className="flex items-center justify-between gap-2 p-4">
        <div className="min-w-0">
          <h2 id={`${id}-h`} className="text-lg font-semibold">{title}</h2>
          {summary ? <p className="mt-0.5 text-xs text-muted">{summary}</p> : null}
        </div>
        <button type="button" onClick={toggle} aria-expanded={isOpen} aria-controls={`${id}-body`} aria-label={`${isOpen ? "Collapse" : "Expand"} ${title}`} className="inline-flex min-h-[44px] shrink-0 items-center rounded-md border border-line px-3 text-sm font-medium text-mist transition-colors hover:border-muted">{isOpen ? "Hide" : "Show"}</button>
      </div>
      <div id={`${id}-body`} hidden={!isOpen} className="border-t border-line p-4">{children}</div>
    </section>
  );
}
