import { Link, NavLink, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { isLive, type AuthUser } from "../api/client";
import { Chip, Menu } from "./ui";

const items: { to: string; end?: boolean; label: string; short: string; path: string }[] = [
  { to: "/", end: true, label: "Home", short: "Home", path: "M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z" },
  { to: "/new", label: "New teaching", short: "New", path: "M12 5v14M5 12h14" },
  { to: "/library", label: "Library", short: "Library", path: "M4 5h7v14H4zM13 5h7v14h-7z" },
  { to: "/jobs", label: "Jobs", short: "Jobs", path: "M4 6h16M4 12h16M4 18h16" },
  { to: "/settings", label: "Settings", short: "Settings", path: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 12h2M18 12h2M12 4v2M12 18v2" },
];

function Icon({ path, className = "h-5 w-5" }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className={`${className} shrink-0`} aria-hidden="true">
      <path d={path} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

interface ShellProps {
  dark: boolean;
  onToggleTheme: () => void;
  user?: AuthUser | null;
  onLogout?: () => void;
  children: ReactNode;
}

export function Shell({ dark, onToggleTheme, user, onLogout, children }: ShellProps) {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-ink text-mist">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-[var(--accent-ink)]">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-ink/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-shell items-center gap-3 px-4 lg:px-8">
          <Link to="/" className="flex min-h-[44px] min-w-0 items-center gap-2 rounded-md" aria-label="SermonPilot home">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-accent font-mono text-sm font-bold text-[var(--accent-ink)]" aria-hidden="true">
              SP
            </span>
            <span className="truncate text-base font-bold tracking-tight">SermonPilot</span>
            <span className="shrink-0 rounded border border-line px-1.5 py-0.5 font-mono text-xs text-muted" title={isLive ? "Live data" : "Sample data, no server"}>
              {isLive ? "live" : "demo"}
            </span>
          </Link>
          <div className="ml-auto flex min-w-0 items-center">
            {user ? (
              <Menu
                label={`Account menu for ${user.display_name}`}
                triggerTestId="account-menu-trigger"
                triggerClassName="inline-flex min-h-[44px] max-w-full items-center gap-2 rounded-md px-1.5 text-mist transition-colors hover:bg-raised"
                menuClassName="w-60"
                header={
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-raised font-mono text-xs font-bold uppercase" aria-hidden="true">
                      {initials(user.display_name)}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{user.display_name}</p>
                      <Chip tone={user.role === "admin" ? "accent" : "neutral"}>{user.role}</Chip>
                    </div>
                  </div>
                }
                trigger={
                  <>
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-raised font-mono text-xs font-bold uppercase" aria-hidden="true">
                      {initials(user.display_name)}
                    </span>
                    <span className="max-w-24 truncate text-sm font-medium">{user.display_name}</span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4 shrink-0 text-muted" aria-hidden="true">
                      <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </>
                }
                items={[
                  { label: "Settings", onSelect: () => navigate("/settings") },
                  {
                    label: dark ? "Switch to light theme" : "Switch to dark theme",
                    onSelect: onToggleTheme,
                  },
                  { label: "Log out", onSelect: () => onLogout?.(), danger: true },
                ]}
              />
            ) : null}
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-shell items-stretch gap-6 px-4 pb-24 pt-6 md:pb-6 lg:px-8">
        <nav aria-label="Sections" className="sticky top-24 hidden h-fit w-52 shrink-0 flex-col gap-1 md:flex">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex min-h-[44px] w-full items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors ${
                  isActive ? "bg-raised text-mist" : "text-muted hover:bg-raised hover:text-mist"
                }`
              }
            >
              <Icon path={item.path} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main id="main" className="min-w-0 flex-1">
          {children}
        </main>
      </div>

      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-ink/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      >
        <div className="mx-auto flex max-w-shell">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 px-1 text-[0.6875rem] font-semibold transition-colors ${
                  isActive ? "text-accent" : "text-muted hover:text-mist"
                }`
              }
            >
              <Icon path={item.path} />
              {item.short}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
