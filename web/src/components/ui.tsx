import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-[var(--accent-ink)] hover:brightness-110 active:brightness-95 border border-transparent",
  secondary:
    "bg-raised text-mist border border-line hover:border-muted hover:brightness-110 active:brightness-95",
  danger:
    "bg-transparent text-danger border border-danger hover:bg-danger hover:text-[var(--danger-ink)] active:brightness-95",
  ghost: "bg-transparent text-muted border border-transparent hover:text-mist hover:bg-raised active:bg-ink",
};

export function buttonClass(variant: ButtonVariant = "secondary", extra = ""): string {
  return `inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-[background-color,border-color,color,filter] duration-150 ${variants[variant]} ${extra}`;
}

export function Button({ variant = "secondary", className = "", type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={`${buttonClass(variant)} disabled:cursor-not-allowed disabled:opacity-45 ${className}`}
      {...rest}
    />
  );
}

const chipTones: Record<string, string> = {
  ok: "text-ok border-ok",
  warn: "text-warn border-warn",
  error: "text-danger border-danger",
  info: "text-info border-info",
  neutral: "text-muted border-line",
  accent: "text-accent border-accent",
};

export function Chip({ tone = "neutral", children }: { tone?: keyof typeof chipTones | string; children: ReactNode }) {
  const toneClass = chipTones[tone] ?? chipTones.neutral;
  return (
    <span
      className={`inline-flex min-h-[24px] max-w-full items-center gap-1 rounded-sm border px-2 py-0.5 font-mono text-xs uppercase leading-4 tracking-wide ${toneClass}`}
    >
      {children}
    </span>
  );
}

const menuItemClass =
  "flex min-h-[44px] w-full items-center rounded-md px-3 text-left text-sm font-medium text-mist transition-colors hover:bg-raised disabled:cursor-not-allowed disabled:opacity-45";

export interface MenuItem {
  label: ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  danger?: boolean;
  testId?: string;
  expanded?: boolean;
  controls?: string;
}

interface MenuProps {
  items: MenuItem[];
  trigger: ReactNode;
  label: string;
  header?: ReactNode;
  align?: "left" | "right";
  side?: "top" | "bottom";
  triggerClassName?: string;
  menuClassName?: string;
  menuTestId?: string;
  triggerTestId?: string;
}

export function Menu({
  items,
  trigger,
  label,
  header,
  align = "right",
  side = "bottom",
  triggerClassName,
  menuClassName = "",
  menuTestId,
  triggerTestId,
}: MenuProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = `menu-${useId()}`;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)')?.focus();
  }, [open]);

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const entries = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? [],
    );
    if (entries.length === 0) return;
    const current = entries.indexOf(document.activeElement as HTMLElement);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = (current + 1) % entries.length;
    if (event.key === "ArrowUp") next = (current - 1 + entries.length) % entries.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = entries.length - 1;
    if (next === null) return;
    event.preventDefault();
    entries[next]?.focus();
  };

  return (
    <div ref={wrapRef} className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        id={`${menuId}-trigger`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={label}
        data-testid={triggerTestId}
        onClick={() => setOpen((value) => !value)}
        className={triggerClassName ?? buttonClass()}
      >
        {trigger}
      </button>
      {open ? (
        <div
          data-side={side}
          className={`menu-panel absolute z-40 flex w-56 flex-col rounded-lg border border-line bg-surface p-2 shadow-2xl ${
            align === "right" ? "right-0" : "left-0"
          } ${side === "top" ? "bottom-full mb-2 origin-bottom" : "top-full mt-2 origin-top"} ${menuClassName}`}
        >
          {header ? <div className="border-b border-line px-3 pb-2 pt-1">{header}</div> : null}
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label={label}
            data-testid={menuTestId}
            onKeyDown={onMenuKeyDown}
            className="flex flex-col gap-1 pt-1"
          >
            {items.map((item, index) => (
              <button
                key={index}
                type="button"
                role="menuitem"
                data-testid={item.testId}
                disabled={item.disabled}
                aria-expanded={item.expanded}
                aria-controls={item.controls}
                onClick={() => {
                  setOpen(false);
                  triggerRef.current?.focus();
                  item.onSelect();
                }}
                className={`${menuItemClass} ${item.danger ? "text-danger" : ""}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function EnvSourceBadge({ source }: { source: string | undefined }) {
  if (!source || source === "db" || source === "default") return null;
  return (
    <span
      className="inline-flex min-h-[24px] max-w-full items-center gap-1 rounded-sm border border-info px-2 py-0.5 font-mono text-xs text-info"
      title={`This value is supplied by the ${source} environment variable and overrides the saved setting while it is set.`}
    >
      <span aria-hidden="true">env</span>
      <span className="truncate">{source}</span>
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-surface p-4 ${className}`}>{children}</div>;
}

export function PageHeader({
  title,
  sub,
  actions,
}: {
  title: string;
  sub?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold leading-tight tracking-tight [overflow-wrap:anywhere]">{title}</h1>
        {sub ? <p className="mt-1 max-w-prose text-sm text-muted">{sub}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function SectionCard({
  n,
  title,
  sub,
  children,
}: {
  n?: number;
  title: string;
  sub?: string;
  children: ReactNode;
}) {
  return (
    <section aria-label={title} className="rounded-lg border border-line bg-surface p-4">
      <div className="flex items-start gap-3">
        {n !== undefined ? (
          <span
            aria-hidden="true"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-raised font-mono text-sm font-bold text-accent"
          >
            {n}
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-snug">{title}</h2>
          {sub ? <p className="mt-1 max-w-prose text-sm text-muted">{sub}</p> : null}
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export const inputCls =
  "min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist transition-colors duration-150 placeholder:text-muted hover:border-muted focus-visible:border-accent";
export const labelCls = "text-xs font-medium text-muted";

export function Field({ label, htmlFor, children, hint }: { label: string; htmlFor: string; children: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0">
      <label htmlFor={htmlFor} className={labelCls}>
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  source,
  testId,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
  source?: string;
  testId?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      data-testid={testId}
      onClick={() => onChange(!checked)}
      className="flex min-h-[44px] w-full items-start gap-3 rounded-md border border-line p-3 text-left transition-colors duration-150 hover:border-muted"
    >
      <span
        aria-hidden="true"
        className={`mt-0.5 flex h-6 w-11 shrink-0 items-center rounded-full border border-line p-0.5 transition-colors duration-150 ${
          checked ? "justify-end border-accent bg-accent" : "justify-start bg-ink"
        }`}
      >
        <span className="h-4 w-4 rounded-full bg-white shadow-sm" />
      </span>
      <span className="min-w-0 text-sm">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{label}</span>
          <EnvSourceBadge source={source} />
        </span>
        {hint ? <span className="block text-muted">{hint}</span> : null}
      </span>
    </button>
  );
}

export function Fieldset({
  legend,
  help,
  children,
}: {
  legend: string;
  help?: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="min-w-0 rounded-md border border-line p-3">
      <legend className="px-1 text-sm font-semibold">{legend}</legend>
      {help ? <p className="mt-0.5 text-xs text-muted">{help}</p> : null}
      <div className="mt-2 flex flex-col gap-3">{children}</div>
    </fieldset>
  );
}

export function Advanced({
  label = "Advanced",
  children,
  open = false,
}: {
  label?: string;
  children: ReactNode;
  open?: boolean;
}) {
  return (
    <details open={open} className="min-w-0 rounded-md border border-line p-3">
      <summary className="min-h-[44px] cursor-pointer text-xs font-semibold text-muted">
        {label}
      </summary>
      <div className="mt-2 flex flex-col gap-3">{children}</div>
    </details>
  );
}

export interface DirtyRegistry {
  set: (id: string, dirty: boolean) => void;
  remove: (id: string) => void;
}

export const DirtyRegistryContext = createContext<DirtyRegistry | null>(null);

function useDirtyRegistration(dirty: boolean) {
  const registry = useContext(DirtyRegistryContext);
  const id = useId();
  useEffect(() => {
    if (!registry) return;
    registry.set(id, dirty);
    return () => registry.remove(id);
  }, [registry, id, dirty]);
}

export function SaveBar({
  dirty,
  saved,
  busy = false,
  error = null,
  onSave,
  label = "Save",
}: {
  dirty: boolean;
  saved: boolean;
  busy?: boolean;
  error?: string | null;
  onSave: () => void;
  label?: string;
}) {
  useDirtyRegistration(dirty);
  return (
    <div className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom)+0.5rem)] z-10 -mx-4 -mb-4 mt-4 flex flex-wrap items-center gap-2 border-t border-line bg-surface/95 px-4 py-3 shadow-[0_-8px_24px_-16px_rgba(0,0,0,0.8)] backdrop-blur md:static md:mx-0 md:mb-0 md:border-0 md:bg-transparent md:p-0 md:shadow-none">
      <Button variant="primary" onClick={onSave} disabled={!dirty || busy} aria-busy={busy}>
        {busy ? "Saving…" : label}
      </Button>
      {error ? (
        <span className="text-xs text-danger" role="alert">
          {error}
        </span>
      ) : !dirty ? (
        <span className="text-xs text-muted">{saved ? "Saved." : "No unsaved changes."}</span>
      ) : (
        <span className="text-xs text-warn" role="status">
          Unsaved changes.
        </span>
      )}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div aria-hidden="true" className={`skeleton-shimmer rounded-md bg-raised ${className}`} />
  );
}

export function SkeletonList({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-hidden="true" aria-label="Loading" className="flex flex-col gap-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-lg border border-line bg-surface p-4">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="mt-2 h-4 w-4/5" />
          <Skeleton className="mt-2 h-3 w-1/3" />
        </div>
      ))}
    </div>
  );
}

export function useBriefLoading(delayMs = 650): boolean {
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const t = window.setTimeout(() => setLoading(false), delayMs);
    return () => window.clearTimeout(t);
  }, [delayMs]);
  return loading;
}

export function EmptyState({
  title,
  body,
  action,
  compact = false,
}: {
  title: string;
  body: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-start gap-2 rounded-lg border border-dashed border-line bg-surface ${
        compact ? "p-3" : "p-6"
      }`}
    >
      <p className={`font-semibold ${compact ? "text-sm" : "text-base"}`}>{title}</p>
      <p className="max-w-prose text-sm text-muted">{body}</p>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="w-[min(26rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-6 text-mist backdrop:bg-black/60"
    >
      <h2 id="confirm-title" className="text-lg font-semibold">
        {title}
      </h2>
      <p className="mt-2 text-sm text-muted">{body}</p>
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={onClose}>{cancelLabel}</Button>
        <Button
          variant="danger"
          onClick={() => {
            onConfirm();
            onClose();
          }}
        >
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}

export function Toast({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-24 left-1/2 z-50 w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-line bg-raised px-4 py-3 text-sm font-medium text-mist shadow-lg md:bottom-4"
    >
      {message}
    </div>
  );
}

export function Meter({ level, state }: { level: number; state: "ok" | "warn" | "error" }) {
  return (
    <div
      className="meter-track h-16 w-1.5 shrink-0 overflow-hidden rounded-full"
      role="img"
      aria-label={`level ${level} percent, ${state}`}
    >
      <div className="flex h-full flex-col justify-end">
        <div className={`meter-fill-${state} w-full`} style={{ height: `${level}%` }} />
      </div>
    </div>
  );
}
