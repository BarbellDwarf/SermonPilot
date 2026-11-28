import { useRef, useState, type ReactNode } from "react";
import type { EditPlan } from "../../mock/data";
import { LIFECYCLE_META, type LifecycleState } from "../../utils/lifecycle";
import { Button } from "../ui";
import { WorkspaceDialog } from "./WorkspaceDialog";

export function useWorkspaceDialogs({
  state,
  statusDetail,
  plan,
  onReplace,
}: {
  state: LifecycleState;
  statusDetail: string;
  plan: EditPlan | null;
  onReplace: (file: File) => Promise<void>;
}) {
  const [statusOpen, setStatusOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [notesText, setNotesText] = useState("");
  const [notesSubmitting, setNotesSubmitting] = useState(false);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [replacing, setReplacing] = useState(false);
  const [replaceError, setReplaceError] = useState<string | null>(null);
  const submitNotesRef = useRef<(note: string) => void>(() => undefined);

  const openNotes = () => {
    setNotesText("");
    setNotesSubmitting(false);
    setNotesOpen(true);
  };

  const openReplace = () => {
    setReplaceFile(null);
    setReplaceError(null);
    setReplaceOpen(true);
  };
  const submitReplace = () => {
    if (!replaceFile) return;
    setReplacing(true);
    setReplaceError(null);
    void onReplace(replaceFile)
      .then(() => {
        setReplaceOpen(false);
        setReplaceFile(null);
      })
      .catch((cause: unknown) => {
        setReplaceError(cause instanceof Error ? cause.message : "Could not queue the replacement.");
      })
      .finally(() => setReplacing(false));
  };
  const dialogs: ReactNode = (
    <>
      <WorkspaceDialog open={statusOpen} title="Review status" onClose={() => setStatusOpen(false)} testId="status-dialog">
        <div className="flex flex-col gap-2 text-sm">
          <p className="font-semibold">{LIFECYCLE_META[state].label}</p>
          <p className="text-muted">{statusDetail}</p>
          {plan ? <p className="font-mono text-xs text-muted">Revision {plan.revision} of {plan.revisionsTotal}</p> : null}
        </div>
      </WorkspaceDialog>
      <WorkspaceDialog open={notesOpen} title="Send back with note" onClose={() => { if (!notesSubmitting) setNotesOpen(false); }} testId="send-back-dialog" initialFocus="content">
        <form className="flex flex-col gap-3" onSubmit={(event) => {
          event.preventDefault();
          const note = notesText.trim();
          if (!note || notesSubmitting) return;
          setNotesSubmitting(true);
          submitNotesRef.current(note);
          setNotesOpen(false);
          setNotesText("");
          setNotesSubmitting(false);
        }}>
          <label htmlFor="send-back-note" className="text-sm font-semibold">Note</label>
          <textarea id="send-back-note" autoFocus rows={4} value={notesText} onChange={(event) => setNotesText(event.target.value)} disabled={notesSubmitting} className="min-h-[44px] w-full rounded-md border border-line bg-ink p-3 text-sm text-mist" placeholder="What should change in the next proposal?" />
          <Button type="submit" variant="secondary" className="w-fit" disabled={!notesText.trim() || notesSubmitting} aria-busy={notesSubmitting}>{notesSubmitting ? "Queueing…" : "Re-run with notes"}</Button>
        </form>
      </WorkspaceDialog>
      <WorkspaceDialog open={replaceOpen} title="Replace recording" onClose={() => { if (!replacing) setReplaceOpen(false); }} testId="replace-recording-dialog" initialFocus="content">
        <form className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); submitReplace(); }}>
          <p className="text-sm text-muted">The new file goes through the full processing pipeline and replaces the media on the existing SermonAudio entry.</p>
          <label htmlFor="replace-recording-file" className="text-xs font-medium text-muted">New video or audio file</label>
          <input id="replace-recording-file" type="file" accept="video/*,audio/*" autoFocus onChange={(event) => setReplaceFile(event.target.files?.[0] ?? null)} className="min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink p-2 text-sm text-mist" />
          {replaceError ? <p role="alert" className="text-sm text-danger">{replaceError}</p> : null}
          <Button type="submit" variant="secondary" disabled={!replaceFile || replacing} aria-busy={replacing}>{replacing ? "Queueing…" : "Replace and reprocess"}</Button>
        </form>
      </WorkspaceDialog>
    </>
  );

  return {
    openStatus: () => setStatusOpen(true),
    openNotes,
    openReplace,
    registerNotesHandler: (handler: (note: string) => void) => { submitNotesRef.current = handler; },
    dialogs,
  };
}
