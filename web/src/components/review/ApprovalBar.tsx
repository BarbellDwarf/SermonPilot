import type { SermonActions } from "../sermonActions";
import { Button, Icon, Menu } from "../ui";
import type { CutEditor } from "./useCutEditor";

interface ApprovalBarProps {
  editor: CutEditor;
  actions: SermonActions;
  published: boolean;
  applying: boolean;
  uploading: boolean;
  refining: boolean;
  deleting: boolean;
  notesOpen: boolean;
  notesText: string;
  onNotesTextChange: (value: string) => void;
  onToggleNotes: () => void;
  onSubmitNotes: () => void;
  onApprove: (renderOnly: boolean) => void;
  onUploadExisting: () => void;
  onReDetect: () => void;
  onHistory: () => void;
  onLegacyUpload?: () => void;
  onDelete?: () => void;
}

export function ApprovalBar({
  editor,
  actions,
  published,
  applying,
  uploading,
  refining,
  deleting,
  notesOpen,
  notesText,
  onNotesTextChange,
  onToggleNotes,
  onSubmitNotes,
  onApprove,
  onUploadExisting,
  onReDetect,
  onHistory,
  onLegacyUpload,
  onDelete,
}: ApprovalBarProps) {
  const applyVerb = published ? "Re-render" : "Approve";
  return (
    <section aria-label="Approval" data-testid="approval-bar" className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom)+0.5rem)] z-20 flex flex-col gap-3 rounded-lg border border-line bg-surface/95 p-4 shadow-[0_-8px_24px_-16px_rgba(0,0,0,0.8)] backdrop-blur md:bottom-0">
      <div className="flex flex-wrap items-center gap-2">
        {refining ? <p role="status" className="basis-full text-xs text-muted">Re-running cut detection. The proposal updates when the new revision is ready.</p> : null}
        {uploading ? <p role="status" className="basis-full text-xs text-muted">Uploading the existing render.</p> : null}
        <Button
          variant="primary"
          data-testid="approve-primary"
          className="min-w-0 flex-1 sm:flex-none"
          onClick={() => onApprove(false)}
          disabled={editor.errors.length > 0 || applying}
          aria-busy={applying}
          title="Generates any empty title, description, or hashtags, then renders and uploads."
        >
          {applying ? "Queueing…" : `${applyVerb} & upload`}
        </Button>
        <Menu
          label="More actions"
          trigger={<span className="inline-flex items-center gap-2">More actions<Icon name="chevron" className="h-4 w-4" /></span>}
          side="top"
          triggerTestId="more-actions-trigger"
          menuTestId="more-actions"
          menuClassName="w-64"
          items={[
            { label: published ? "Re-render only" : "Render only", onSelect: () => onApprove(true), disabled: editor.errors.length > 0 || applying, testId: "render-only-action" },
            ...(actions.canUploadExisting ? [{ label: uploading ? "Uploading…" : "Upload existing render", onSelect: onUploadExisting, disabled: applying || uploading, testId: "upload-existing-render" }] : []),
            { label: "Reject with notes", onSelect: onToggleNotes, expanded: notesOpen, controls: "refine-notes" },
            { label: "Re-detect", onSelect: onReDetect, disabled: refining },
            { label: "History", onSelect: onHistory, testId: "open-history" },
            ...(onLegacyUpload && actions.canPublishLegacy ? [{ label: "Push to SermonAudio", onSelect: onLegacyUpload }] : []),
            ...(onDelete ? [{ label: deleting ? "Deleting…" : "Delete", onSelect: onDelete, disabled: deleting, danger: true, testId: "delete-sermon" }] : []),
          ]}
        />
      </div>
      {notesOpen ? (
        <div className="rounded-md border border-line bg-ink p-3">
          <label htmlFor="refine-notes" className="text-sm font-semibold">Reject with notes</label>
          <p className="mt-1 max-w-prose text-xs text-muted">Say what the detector got wrong and it re-reads the transcript with every note so far, then returns a new revision. The old proposal is superseded.</p>
          <textarea id="refine-notes" value={notesText} onChange={(event) => onNotesTextChange(event.target.value)} rows={3} disabled={refining} placeholder="e.g. Keep only the second of the two back-to-back classes and drop the earlier one." className="mt-2 w-full min-w-0 rounded-md border border-line bg-ink px-3 py-2 text-sm text-mist" />
          <div className="mt-2"><Button variant="secondary" onClick={onSubmitNotes} disabled={!notesText.trim() || refining} aria-busy={refining}>{refining ? "Queueing…" : "Re-run with notes"}</Button></div>
        </div>
      ) : null}
    </section>
  );
}
