import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import { ConfirmDialog } from "../ui";

export function IntakeUnsavedChangesDialog({
  when,
  suppressed = false,
}: {
  when: boolean;
  suppressed?: boolean;
}) {
  const blocker = useUnsavedChanges(when);
  const blocked = blocker.state === "blocked";

  if (suppressed) return null;

  return (
    <ConfirmDialog
      open={blocked}
      title="Unsaved changes"
      body="This teaching has unsaved changes. Leave and discard them?"
      confirmLabel="Discard"
      cancelLabel="Stay"
      onConfirm={() => {
        if (blocked) blocker.proceed();
      }}
      onClose={() => {
        if (blocked) blocker.reset();
      }}
    />
  );
}
