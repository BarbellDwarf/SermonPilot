import { useEffect, useRef, useSyncExternalStore, type ReactNode } from "react";

export type ToastVariant = "success" | "error" | "info";

export interface ToastAction {
  label: string;
  onSelect: () => void;
}

export interface ToastInput {
  message: ReactNode;
  variant?: ToastVariant;
  duration?: number;
  action?: ToastAction;
}

interface ToastItem extends ToastInput {
  id: number;
  variant: ToastVariant;
  duration: number;
}

const MAX_VISIBLE = 3;
const DEFAULT_DURATION = 5000;
const UNDO_DURATION = 8000;

let nextId = 1;
let items: ToastItem[] = [];
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function remove(id: number) {
  items = items.filter((item) => item.id !== id);
  emit();
}

export function dismissToast(id: number) {
  remove(id);
}

export function clearToasts() {
  items = [];
  emit();
}

export function pushToast(input: ToastInput): number {
  const item: ToastItem = {
    ...input,
    id: nextId++,
    variant: input.variant ?? "info",
    duration: input.duration ?? DEFAULT_DURATION,
  };
  const next = [...items, item];
  items = next.length > MAX_VISIBLE ? next.slice(next.length - MAX_VISIBLE) : next;
  emit();
  return item.id;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function snapshot() {
  return items;
}

export function useToast() {
  return {
    success: (message: ReactNode, options?: Omit<ToastInput, "message" | "variant">) =>
      pushToast({ ...options, message, variant: "success" }),
    error: (message: ReactNode, options?: Omit<ToastInput, "message" | "variant">) =>
      pushToast({ ...options, message, variant: "error", duration: options?.duration ?? 7000 }),
    info: (message: ReactNode, options?: Omit<ToastInput, "message" | "variant">) =>
      pushToast({ ...options, message, variant: "info" }),
    undo: (message: ReactNode, onUndo: () => void) =>
      pushToast({
        message,
        variant: "success",
        duration: UNDO_DURATION,
        action: { label: "Undo", onSelect: onUndo },
      }),
  };
}

const tone: Record<ToastVariant, string> = {
  success: "border-l-ok",
  error: "border-l-danger",
  info: "border-l-info",
};

const dot: Record<ToastVariant, string> = {
  success: "bg-ok",
  error: "bg-danger",
  info: "bg-info",
};

function ToastCard({ item }: { item: ToastItem }) {
  const remaining = useRef(item.duration);
  const timer = useRef<number | null>(null);
  const startedAt = useRef(0);

  const stop = () => {
    if (timer.current === null) return;
    window.clearTimeout(timer.current);
    timer.current = null;
    remaining.current = Math.max(0, remaining.current - (Date.now() - startedAt.current));
  };

  const start = () => {
    if (timer.current !== null || remaining.current <= 0) return;
    startedAt.current = Date.now();
    timer.current = window.setTimeout(() => remove(item.id), remaining.current);
  };

  useEffect(() => {
    start();
    return stop;
  }, []);

  return (
    <div
      role={item.variant === "error" ? "alert" : "status"}
      aria-live={item.variant === "error" ? "assertive" : "polite"}
      onMouseEnter={stop}
      onMouseLeave={start}
      onFocus={stop}
      onBlur={start}
      className={`toast-in pointer-events-auto flex w-full items-start gap-3 rounded-lg border border-l-4 border-line bg-raised px-4 py-3 text-sm shadow-xl ${tone[item.variant]}`}
    >
      <span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot[item.variant]}`} />
      <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">{item.message}</div>
      {item.action ? (
        <button
          type="button"
          onClick={() => {
            item.action?.onSelect();
            remove(item.id);
          }}
          className="min-h-[44px] shrink-0 rounded-md px-2 text-sm font-semibold text-accent underline underline-offset-2 hover:text-mist"
        >
          {item.action.label}
        </button>
      ) : (
        <button
          type="button"
          aria-label="Dismiss notification"
          onClick={() => remove(item.id)}
          className="min-h-[44px] min-w-[44px] shrink-0 rounded-md text-muted hover:text-mist"
        >
          ×
        </button>
      )}
    </div>
  );
}

export function ToastHost() {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  return (
    <div
      aria-label="Notifications"
      className="pointer-events-none fixed inset-x-4 bottom-[calc(8.5rem+env(safe-area-inset-bottom))] z-50 flex flex-col items-center gap-2 md:inset-x-auto md:bottom-6 md:right-6 md:items-end"
    >
      {current.map((item) => (
        <div key={item.id} className="w-full max-w-sm">
          <ToastCard item={item} />
        </div>
      ))}
    </div>
  );
}
