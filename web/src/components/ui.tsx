import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";

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

export function Button({ variant = "secondary", className = "", type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${variants[variant]} ${className}`}
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

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-line bg-surface p-6">
      <p className="text-base font-semibold">{title}</p>
      <p className="text-sm text-muted">{body}</p>
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
