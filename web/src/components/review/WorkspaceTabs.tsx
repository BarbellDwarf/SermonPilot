import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface WorkspaceTab {
  id: "details" | "transcript" | "files" | "history";
  label: string;
  content: ReactNode;
}

export function WorkspaceTabs({
  tabs,
  active,
  onChange,
  idPrefix = "workspace",
}: {
  tabs: WorkspaceTab[];
  active: WorkspaceTab["id"];
  onChange: (id: WorkspaceTab["id"]) => void;
  idPrefix?: string;
}) {
  const [desktop, setDesktop] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(min-width: 768px)").matches
      : false,
  );
  const panelRefs = useRef<Record<string, HTMLDetailsElement | null>>({});
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(min-width: 768px)");
    const update = () => setDesktop(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    for (const tab of tabs) {
      const panel = panelRefs.current[tab.id];
      if (panel) panel.open = tab.id === active;
    }
  }, [active]);

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].id);
    tabRefs.current[next]?.focus();
  };

  if (!desktop) {
    return (
      <section aria-label="Teaching information" className="overflow-hidden rounded-lg border border-line bg-surface">
        {tabs.map((tab) => (
          <details
            key={tab.id}
            ref={(element) => { panelRefs.current[tab.id] = element; }}
            name={`${idPrefix}-accordion`}
            className="border-b border-line last:border-b-0"
            data-testid={`${idPrefix}-accordion-${tab.id}`}
          >
            <summary
              onClick={(event) => {
                if (active === tab.id) return;
                event.preventDefault();
                onChange(tab.id);
              }}
              className="min-h-[56px] cursor-pointer px-4 py-3 text-sm font-semibold marker:text-muted"
            >
              {tab.label}
            </summary>
            <div className="border-t border-line p-4" data-testid={`${idPrefix}-panel-${tab.id}`}>{tab.content}</div>
          </details>
        ))}
      </section>
    );
  }

  return (
    <section aria-label="Teaching information" className="overflow-hidden rounded-lg border border-line bg-surface" data-testid={`${idPrefix}-tabs`}>
      <div role="tablist" aria-label="Teaching information" className="flex gap-1 overflow-x-auto border-b border-line p-1">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={(element) => { tabRefs.current[index] = element; }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${tab.id}`}
            aria-selected={active === tab.id}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={active === tab.id ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onTabKeyDown(event, index)}
            className={`min-h-[44px] shrink-0 rounded-md px-3 text-sm font-semibold ${active === tab.id ? "bg-accent/15 text-mist underline decoration-accent decoration-2 underline-offset-4" : "text-muted hover:text-mist"}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${idPrefix}-panel-${tab.id}`}
          aria-labelledby={`${idPrefix}-tab-${tab.id}`}
          hidden={active !== tab.id}
          tabIndex={active === tab.id ? 0 : -1}
          className="p-4"
          data-testid={`${idPrefix}-panel-${tab.id}`}
        >
          {tab.content}
        </div>
      ))}
    </section>
  );
}
