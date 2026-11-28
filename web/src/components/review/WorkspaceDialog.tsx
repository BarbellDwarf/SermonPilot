import { useEffect, useId, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { Button } from "../ui";

export function WorkspaceDialog({
  open,
  title,
  onClose,
  children,
  testId,
  initialFocus = "close",
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
  initialFocus?: "close" | "content";
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = `dialog-${useId()}`;

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      if (initialFocus === "content") {
        dialog.querySelector<HTMLElement>("textarea, input, select")?.focus();
      }
    }
    if (!open && dialog.open) dialog.close();
  }, [initialFocus, open]);

  const trapFocus = (event: ReactKeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== "Tab") return;
    const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
    ));
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      data-testid={testId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onKeyDown={trapFocus}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const rect = event.currentTarget.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
      }}
      className="mb-[calc(3.5rem+env(safe-area-inset-bottom))] max-h-[80dvh] w-[min(30rem,calc(100vw-2rem))] overflow-y-auto rounded-t-2xl border border-line bg-surface p-5 text-mist shadow-2xl backdrop:bg-black/60 sm:mb-auto sm:rounded-xl"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
        <Button onClick={onClose} autoFocus={initialFocus === "close"} aria-label="Close">Close</Button>
      </div>
      <div className="mt-4">{children}</div>
    </dialog>
  );
}
