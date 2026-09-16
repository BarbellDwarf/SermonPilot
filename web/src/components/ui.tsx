import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variants: Record<ButtonVariant, string> = {
  primary: "bg-accent text-[var(--accent-ink)] hover:brightness-110 border border-transparent",
  secondary: "bg-raised text-mist border border-line hover:border-muted",
  danger: "bg-transparent text-danger border border-danger hover:bg-danger hover:text-[var(--danger-ink)]",
  ghost: "bg-transparent text-muted border border-transparent hover:text-mist hover:bg-raised",
};

export function buttonClass(variant: ButtonVariant = "secondary", extra = ""): string {
  return `inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors ${variants[variant]} ${extra}`;
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
    <span className={`inline-flex min-h-[28px] items-center rounded-full border px-2.5 font-mono text-xs uppercase tracking-wide ${toneClass}`}>
      {children}
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
  sub: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight [overflow-wrap:anywhere]">{title}</h1>
        <p className="mt-0.5 max-w-prose text-sm text-muted">{sub}</p>
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
          <h2 className="text-lg font-semibold">{title}</h2>
          {sub ? <p className="mt-0.5 max-w-prose text-sm text-muted">{sub}</p> : null}
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export const inputCls =
  "min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 text-sm text-mist placeholder:text-muted";
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
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex min-h-[44px] cursor-pointer items-start gap-3 rounded-md border border-line p-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={(e) => {
          e.preventDefault();
          onChange(!checked);
        }}
        className={`mt-0.5 flex h-6 w-11 shrink-0 items-center rounded-full border border-line p-0.5 transition-colors ${
          checked ? "justify-end bg-accent" : "justify-start bg-ink"
        }`}
      >
        <span className="h-4 w-4 rounded-full bg-white" aria-hidden="true" />
      </button>
      <span className="min-w-0 text-sm">
        <span className="font-semibold">{label}</span>
        {hint ? <span className="block text-muted">{hint}</span> : null}
      </span>
    </label>
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

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-line bg-surface p-6">
      <p className="text-base font-semibold">{title}</p>
      <p className="max-w-prose text-sm text-muted">{body}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({ open, title, body, confirmLabel, onConfirm, onClose }: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open ]);

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
        <Button onClick={onClose}>Cancel</Button>
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
      className="fixed bottom-4 left-1/2 z-50 w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-line bg-raised px-4 py-3 text-sm font-medium text-mist shadow-lg"
    >
      {message}
    </div>
  );
}

export function Meter({ level, state }: { level: number; state: "ok" | "warn" | "error" }) {
  return (
    <div
      className="meter-track h-16 w-2 shrink-0 overflow-hidden rounded-sm"
      role="img"
      aria-label={`level ${level} percent, ${state}`}
    >
      <div className="flex h-full flex-col justify-end">
        <div className={`meter-fill-${state} w-full`} style={{ height: `${level}%` }} />
      </div>
    </div>
  );
}
