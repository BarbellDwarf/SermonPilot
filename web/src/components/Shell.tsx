import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { isLive, type AuthUser } from "../api/client";
import { pageTitle } from "../utils/pageTitle";
import { Chip, Icon, Menu, selectedClass, type IconName } from "./ui";

interface NavItem {
  to: string;
  end?: boolean;
  label: string;
  short: string;
  ariaLabel?: string;
  icon: IconName;
  badge?: ReactNode;
}

const items: NavItem[] = [
  { to: "/", end: true, label: "Inbox", short: "Inbox", icon: "home" },
  { to: "/library", label: "Library", short: "Library", icon: "library" },
  { to: "/new", label: "New teaching", short: "New", ariaLabel: "New teaching", icon: "plus" },
  { to: "/activity", label: "Activity", short: "Activity", icon: "jobs" },
  { to: "/settings", label: "Settings", short: "Settings", icon: "settings" },
];

function useRouteMeta(main: { current: HTMLElement | null }) {
  const { pathname } = useLocation();
  const previousPath = useRef(pathname);

  useEffect(() => {
    document.title = pageTitle(pathname);
    if (previousPath.current === pathname) return;
    previousPath.current = pathname;
    main.current?.focus({ preventScroll: true });
  }, [pathname, main]);
}

function NavBadge({ item, mobile }: { item: NavItem; mobile?: boolean }) {
  if (item.badge === undefined || item.badge === null) return null;
  return (
    <span
      data-testid={`nav-badge-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
      className={
        mobile
          ? "absolute right-2 top-1.5 flex min-w-4 items-center justify-center rounded-full border border-line bg-raised px-1 font-mono text-xs leading-4 text-muted"
          : "ml-auto flex min-w-5 items-center justify-center rounded-full border border-line bg-raised px-1 font-mono text-xs leading-4 text-muted"
      }
    >
      {item.badge}
    </span>
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
  badges?: Partial<Record<string, ReactNode>>;
  children: ReactNode;
}

export function Shell({ dark, onToggleTheme, user, onLogout, badges, children }: ShellProps) {
  const navigate = useNavigate();
  const main = useRef<HTMLElement>(null);
  useRouteMeta(main);
  const navItems = badges
    ? items.map((item) => ({ ...item, badge: badges[item.label] ?? item.badge }))
    : items;

  return (
    <div className="min-h-dvh bg-ink text-mist">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-sm focus:bg-accent focus:px-3 focus:py-2 focus:text-[var(--accent-ink)]">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-ink/95 pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="mx-auto flex h-16 max-w-shell items-center gap-3 px-4 lg:px-8">
          <Link to="/" className="flex min-h-[44px] min-w-0 items-center gap-2 rounded-md">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-accent font-mono text-sm font-bold text-[var(--accent-ink)]" aria-hidden="true">
              SP
            </span>
            <span className="truncate text-base font-bold tracking-tight">SermonPilot</span>
            <span className="shrink-0 rounded-sm border border-line px-1.5 py-0.5 font-mono text-xs text-muted" title={isLive ? "Live data" : "Sample data, no server"}>
              {isLive ? "live" : "demo"}
            </span>
          </Link>
          <div className="ml-auto flex min-w-0 items-center">
            {user ? (
              <Menu
                label={`Account menu for ${initials(user.display_name)} ${user.display_name}`}
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
                    </span>{" "}
                    <span className="hidden max-w-24 truncate text-sm font-medium sm:inline">{user.display_name}</span>
                    <Icon name="chevron" className="h-4 w-4 text-muted" />
                  </>
                }
                items={[
                  { label: "Settings", onSelect: () => navigate("/settings") },
                  {
                    label: dark ? "Switch to light theme" : "Switch to dark theme",
                    onSelect: onToggleTheme,
                  },
                  { label: "Sign out", onSelect: () => onLogout?.(), danger: true },
                ]}
              />
            ) : null}
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-shell items-stretch gap-6 px-4 pb-[calc(var(--chrome-bottom)+2.5rem)] pt-6 md:pb-6 lg:px-8">
        <nav aria-label="Sections" className="sticky top-24 hidden h-fit w-52 shrink-0 flex-col gap-1 md:flex">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `relative flex min-h-[44px] w-full items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors duration-150 ${
                  isActive
                    ? `${selectedClass} before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-full before:bg-accent`
                    : "text-muted hover:bg-selected hover:text-mist"
                }`
              }
            >
              <Icon name={item.icon} />
              <span className="min-w-0 truncate">{item.label}</span>
              <NavBadge item={item} />
            </NavLink>
          ))}
        </nav>
        <main id="main" ref={main} tabIndex={-1} className="min-w-0 max-w-[78rem] flex-1">
          {children}
        </main>
      </div>

      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-ink/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      >
        <div className="mx-auto flex max-w-shell">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              aria-label={item.ariaLabel}
              title={item.ariaLabel}
              className={({ isActive }) =>
                `relative flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 px-1 text-xs font-semibold transition-colors duration-150 ${
                  isActive
                    ? "text-accent after:absolute after:inset-x-0 after:top-0 after:mx-auto after:h-0.5 after:w-10 after:rounded-full after:bg-accent"
                    : "text-muted hover:text-mist"
                }`
              }
            >
              <Icon name={item.icon} />
              {item.short}
              <NavBadge item={item} mobile />
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
