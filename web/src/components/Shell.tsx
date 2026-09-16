import { NavLink } from "react-router-dom";
import { useEffect, useState, type ReactNode } from "react";

export type Section = "home" | "new" | "library" | "jobs" | "settings";

const items: { to: string; end?: boolean; label: string; path: string }[] = [
  { to: "/", end: true, label: "Home", path: "M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z" },
  { to: "/new", label: "New Sermon", path: "M12 5v14M5 12h14" },
  { to: "/library", label: "Library", path: "M4 5h7v14H4zM13 5h7v14h-7z" },
  { to: "/jobs", label: "Jobs", path: "M4 6h16M4 12h16M4 18h16" },
  { to: "/settings", label: "Settings", path: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 12h2M18 12h2M12 4v2M12 18v2" },
];

function Icon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5 shrink-0" aria-hidden="true">
      <path d={path} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

interface ShellProps {
  dark: boolean;
  onToggleTheme: () => void;
  children: ReactNode;
}

export function Shell({ dark, onToggleTheme, children }: ShellProps) {
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawer(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  const link = (to: string, end: boolean | undefined, label: string, path: string) => (
    <NavLink
      key={to}
      to={to}
      end={end}
      onClick={() => setDrawer(false)}
      className={({ isActive }) =>
        `flex min-h-[44px] w-full items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors ${
          isActive ? "bg-raised text-mist" : "text-muted hover:bg-raised hover:text-mist"
        }`
      }
    >
      <Icon path={path} />
      {label}
    </NavLink>
  );

  return (
    <div className="min-h-screen bg-ink text-mist">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-[var(--accent-ink)]">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-ink/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-shell items-center gap-2 px-4">
          <button
            type="button"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted hover:bg-raised hover:text-mist md:hidden"
            aria-label="Open navigation"
            aria-expanded={drawer}
            onClick={() => setDrawer(true)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-6 w-6" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
            </svg>
          </button>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-accent font-mono text-sm font-bold text-[var(--accent-ink)]" aria-hidden="true">
              SP
            </span>
            <span className="text-base font-bold tracking-tight">SermonPilot</span>
            <span className="hidden rounded border border-line px-1.5 py-0.5 font-mono text-xs text-muted sm:inline">mock</span>
          </div>
          <div className="ml-auto">
            <button
              type="button"
              onClick={onToggleTheme}
              aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
              className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted hover:bg-raised hover:text-mist"
            >
              {dark ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden="true">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4" strokeLinecap="round" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5" aria-hidden="true">
                  <path d="M20 13.5A8 8 0 0 1 10.5 4 6.5 6.5 0 1 0 20 13.5z" strokeLinejoin="round" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-shell items-stretch gap-6 px-4 py-6">
        <nav aria-label="Sections" className="sticky top-24 hidden h-fit w-52 shrink-0 flex-col gap-1 md:flex">
          {items.map((i) => link(i.to, i.end, i.label, i.path))}
        </nav>
        <main id="main" className="min-w-0 flex-1">
          {children}
        </main>
      </div>

      {drawer ? (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Sections">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrawer(false)} />
          <nav aria-label="Sections" className="absolute left-0 top-0 flex h-full w-64 flex-col gap-1 border-r border-line bg-surface p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-bold">Sections</span>
              <button
                type="button"
                onClick={() => setDrawer(false)}
                aria-label="Close navigation"
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted hover:bg-raised hover:text-mist"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            {items.map((i) => link(i.to, i.end, i.label, i.path))}
          </nav>
        </div>
      ) : null}
    </div>
  );
}
