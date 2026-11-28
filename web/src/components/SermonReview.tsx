import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, writeApi } from "../api/client";
import type { SermonMediaData } from "../api/hooks";
import type { EditPlan, LibrarySermon } from "../mock/data";
import { formatDate } from "../utils/format";
import { sermonActionMatrix } from "./sermonActions";
import { Button, ConfirmDialog, PageHeader } from "./ui";
import { ApprovalBar } from "./review/ApprovalBar";
import { DetailsForm } from "./review/DetailsForm";
import { ReviewInfo, type InfoTab } from "./review/ReviewInfo";
import { ReviewPlayer } from "./review/ReviewPlayer";
import type { CutEditor } from "./review/useCutEditor";
import type { DetailsPatch, TranscriptState } from "./review/types";

export { artifactLabel, preferredKind } from "./review/media";
export { planStatusLabel } from "./review/PlanSummary";
export { CollapsibleSection } from "./review/CollapsibleSection";
export type { DetailsPatch, TranscriptState } from "./review/types";

export interface SermonReviewProps {
  sermon: LibrarySermon;
  description: string | null;
  descriptionNeedsReview?: boolean;
  hashtags?: string | null;
  plan: EditPlan;
  history?: EditPlan[];
  sourceDurationSec?: number | null;
  media: SermonMediaData;
  isLive: boolean;
  statusChip?: ReactNode;
  onDelete?: () => void;
  deleting?: boolean;
  transcript?: TranscriptState;
  onSaveDetails?: (patch: DetailsPatch) => Promise<void> | void;
  onRegenerateDescription?: () => Promise<void> | void;
  onRefresh?: () => void;
  onToast: (msg: string, variant?: "success" | "error" | "info") => void;
  onUpload?: () => void;
  enhanceDefault?: boolean;
  onShowCompleted?: () => void;
  onJobQueued?: (jobId: string, message: string) => void;
}

export function SermonReview(props: SermonReviewProps) {
  const planKey = `${props.plan.sermonId}:${props.plan.revision}:${props.plan.startSec}:${props.plan.endSec}:${props.plan.offsetSec}:${props.plan.status}:${JSON.stringify(props.plan.removeSegments ?? [])}`;
  return <SermonReviewSession key={`${props.sermon.id}:${planKey}`} {...props} />;
}

function SermonReviewSession({
  sermon,
  description,
  descriptionNeedsReview = false,
  hashtags = null,
  plan: initialPlan,
  history: planHistory,
  sourceDurationSec,
  media,
  isLive,
  statusChip,
  onDelete,
  deleting = false,
  transcript,
  onSaveDetails,
  onRegenerateDescription,
  onRefresh,
  onToast,
  onUpload,
  enhanceDefault = true,
  onShowCompleted,
  onJobQueued,
}: SermonReviewProps) {
  const queryClient = useQueryClient();
  const [plan, setPlan] = useState(initialPlan);
  const [applying, setApplying] = useState(false);
  const [uploading, setUploading] = useState(false);
  const applyInFlight = useRef(false);
  const uploadInFlight = useRef(false);
  const [confirmUploadNoDescription, setConfirmUploadNoDescription] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [refining, setRefining] = useState(false);
  const [notesText, setNotesText] = useState("");
  const [notesOpen, setNotesOpen] = useState(false);
  const [mockNotes, setMockNotes] = useState<{ revision: number; note: string }[]>([]);
  const [statusLog, setStatusLog] = useState<string[]>([]);
  const [infoTab, setInfoTab] = useState<InfoTab>("transcript");
  const planKey = `${plan.sermonId}:${plan.revision}:${plan.startSec}:${plan.endSec}:${plan.offsetSec}:${plan.status}:${JSON.stringify(plan.removeSegments ?? [])}`;

  useEffect(() => {
    setNotesText("");
    setNotesOpen(false);
    setMockNotes([]);
    setStatusLog([]);
    setInfoTab("transcript");
  }, [sermon.id]);

  const noteRows = useMemo(() => {
    const fromPlan = (planHistory ?? []).filter((row) => row.notes.trim().length > 0).map((row) => ({ revision: row.revision, note: row.notes.trim() }));
    const seen = new Set<string>();
    return [...fromPlan, ...mockNotes]
      .filter((row) => {
        const key = `${row.revision}:${row.note}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((left, right) => left.revision - right.revision);
  }, [planHistory, mockNotes]);

  const processedAvailable = !!media.byKind.processed?.available;
  const actions = sermonActionMatrix({ status: sermon.status, hasRender: processedAvailable });
  const queueMessage = (message: string) => onToast(message);

  const uploadExisting = (confirmMissingDescription: boolean) => {
    if (uploadInFlight.current) return;
    uploadInFlight.current = true;
    if (isLive) {
      setUploading(true);
      void writeApi.uploadOnly(sermon.id, { confirm_missing_description: confirmMissingDescription })
        .then((result) => {
          uploadInFlight.current = false;
          setUploading(false);
          setConfirmUploadNoDescription(false);
          onJobQueued?.(result.job_id, "Upload of the existing render queued.");
          queueMessage("Upload of the existing render queued.");
        })
        .catch((error: unknown) => {
          uploadInFlight.current = false;
          setUploading(false);
          const err = error as ApiError;
          if (err?.code === "missing_description" && !confirmMissingDescription) {
            setConfirmUploadNoDescription(true);
            return;
          }
          if (err?.code === "job_active") {
            onToast("A job is already running for this teaching.", "info");
            return;
          }
          onToast(err?.message || "Could not queue the upload.", "error");
        });
      return;
    }
    setUploading(true);
    window.setTimeout(() => {
      uploadInFlight.current = false;
      setUploading(false);
      queueMessage("Upload of the existing render queued (demo).");
    }, 900);
  };

  const restoreOriginal = () => {
    if (restoring) return;
    setConfirmRestore(false);
    if (!isLive) {
      setPlan((current) => ({ ...current, status: "draft", revision: 1 }));
      setStatusLog([]);
      onToast("Original restored (demo). Plan reset to draft.");
      return;
    }
    setRestoring(true);
    void writeApi.restorePlan(sermon.id)
      .then((result) => {
        setRestoring(false);
        setStatusLog([]);
        onRefresh?.();
        if (result.job_id) onJobQueued?.(result.job_id, "Original restored locally. Re-upload queued.");
        onToast(result.job_id ? "Original restored locally. Re-upload to SermonAudio queued." : "Original restored. The plan is reset to the full recording.");
      })
      .catch((error: unknown) => {
        setRestoring(false);
        onToast((error as ApiError)?.message || "Could not restore the original recording.", "error");
      });
  };

  const approve = (editor: CutEditor, renderOnly: boolean) => {
    if (editor.errors.length > 0 || applyInFlight.current) return;
    applyInFlight.current = true;
    if (isLive) {
      setApplying(true);
      void writeApi.applyPlan(sermon.id, editor.applyRequest(renderOnly, !renderOnly))
        .then((result) => {
          applyInFlight.current = false;
          setApplying(false);
          void queryClient.invalidateQueries({ queryKey: ["sermon", sermon.id] });
          void queryClient.invalidateQueries({ queryKey: ["sermon-plan", sermon.id] });
          void queryClient.invalidateQueries({ queryKey: ["jobs"] });
          void queryClient.invalidateQueries({ queryKey: ["sermons"] });
          onJobQueued?.(result.job_id, renderOnly ? "Rendering queued." : "Rendering, then upload queued.");
          onToast(renderOnly ? "Plan approved, render queued." : "Plan approved, render + upload queued.");
        })
        .catch((error: unknown) => {
          applyInFlight.current = false;
          setApplying(false);
          const message = (error as Error).message;
          onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue: ${message}`, /409/.test(message) ? "info" : "error");
        });
      return;
    }
    setApplying(true);
    window.setTimeout(() => {
      applyInFlight.current = false;
      setApplying(false);
      setStatusLog((history) => [...history, `revision ${plan.revision} superseded`]);
      setPlan((current) => ({
        ...current,
        status: "applied_local",
        revision: current.revision + 1,
        revisionsTotal: current.revisionsTotal + 1,
        startSec: editor.safeStart,
        endSec: editor.safeEnd,
        removeSegments: editor.applyRequest(renderOnly, !renderOnly).remove_segments.map((segment) => ({ startSec: segment.start_sec, endSec: segment.end_sec })),
        offsetSec: editor.offset ?? current.offsetSec,
      }));
      onToast(renderOnly ? "Plan approved, render queued (demo). Previous revision superseded." : "Plan approved, render + upload queued (demo). Previous revision superseded.");
    }, 1200);
  };

  const submitRefine = () => {
    const note = notesText.trim();
    if (!note || refining) return;
    if (isLive) {
      setRefining(true);
      void writeApi.refinePlan(sermon.id, note)
        .then((result) => {
          setRefining(false);
          setNotesText("");
          onRefresh?.();
          onJobQueued?.(result.job_id, "Re-detection queued with your notes.");
          onToast("Re-detection queued with your notes. The panel updates when the new proposal is ready.");
        })
        .catch((error: unknown) => {
          setRefining(false);
          const message = (error as Error).message;
          onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue: ${message}`, /409/.test(message) ? "info" : "error");
        });
      return;
    }
    setRefining(true);
    window.setTimeout(() => {
      setRefining(false);
      setNotesText("");
      const nextRevision = plan.revision + 1;
      setMockNotes((rows) => [...rows, { revision: nextRevision, note }]);
      setStatusLog((history) => [...history, `revision ${plan.revision} superseded`]);
      setPlan((current) => ({ ...current, status: "pending_review", revision: nextRevision, revisionsTotal: Math.max(current.revisionsTotal, nextRevision), reasoning: `Re-ran detection against your note: "${note}".` }));
      onToast("New cut proposal ready (demo). Previous revision superseded.");
    }, 900);
  };

  const reDetect = () => {
    if (refining) return;
    if (isLive) {
      setRefining(true);
      void writeApi.reDetectPlan(sermon.id)
        .then((result) => {
          setRefining(false);
          onRefresh?.();
          onJobQueued?.(result.job_id, "Re-detection queued.");
          onToast("Re-detection queued from scratch. Earlier revisions stay in the history.");
        })
        .catch((error: unknown) => {
          setRefining(false);
          const message = (error as Error).message;
          onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue: ${message}`, /409/.test(message) ? "info" : "error");
        });
      return;
    }
    setRefining(true);
    window.setTimeout(() => {
      setRefining(false);
      const nextRevision = plan.revision + 1;
      setStatusLog((history) => [...history, `revision ${plan.revision} superseded (re-detect)`]);
      setPlan((current) => ({ ...current, status: "pending_review", revision: nextRevision, revisionsTotal: Math.max(current.revisionsTotal, nextRevision), detectionStatus: "ok", reasoning: "Detection re-run from scratch without prior notes." }));
      onToast("Detection re-run from scratch (demo). Earlier revisions kept in history.");
    }, 900);
  };

  return (
    <div data-testid="sermon-review" className="flex flex-col gap-4">
      <PageHeader title={sermon.title} sub={`${sermon.speaker || "Unknown speaker"} · ${formatDate(sermon.date)}`} actions={onShowCompleted ? <Button data-testid="show-completed-view" onClick={onShowCompleted}>Back to finished view</Button> : undefined} />
      <div data-testid="approval-content" className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-4 lg:order-1">
          <ReviewPlayer
            key={planKey}
            sermonId={sermon.id}
            plan={plan}
            media={media}
            isLive={isLive}
            sourceDurationSec={sourceDurationSec}
            statusChip={statusChip}
            enhanceDefault={enhanceDefault}
            applying={applying}
            restoring={restoring}
            onRestore={() => setConfirmRestore(true)}
          >
            {(editor) => (
              <>
                <ApprovalBar
                  editor={editor}
                  actions={actions}
                  published={actions.published}
                  applying={applying}
                  uploading={uploading}
                  refining={refining}
                  deleting={deleting}
                  notesOpen={notesOpen}
                  notesText={notesText}
                  onNotesTextChange={setNotesText}
                  onToggleNotes={() => setNotesOpen((value) => !value)}
                  onSubmitNotes={submitRefine}
                  onApprove={(renderOnly) => approve(editor, renderOnly)}
                  onUploadExisting={() => uploadExisting(false)}
                  onReDetect={reDetect}
                  onHistory={() => setInfoTab("history")}
                  onLegacyUpload={onUpload}
                  onDelete={onDelete}
                />
                <ReviewInfo
                  sermonId={sermon.id}
                  media={media}
                  isLive={isLive}
                  transcript={transcript}
                  plan={plan}
                  history={planHistory}
                  noteRows={noteRows}
                  statusLog={statusLog}
                  infoTab={infoTab}
                  onInfoTabChange={setInfoTab}
                  onSeek={editor.requestSeek}
                  onOpenArtifact={editor.setPlayerKind}
                />
              </>
            )}
          </ReviewPlayer>
        </div>
        <aside id="details" aria-labelledby="details-h" className="rounded-lg border border-line bg-surface p-4 lg:order-2 lg:sticky lg:top-4 lg:self-start">
          <h2 id="details-h" className="text-lg font-semibold">Details</h2>
          <p className="mt-1 text-xs text-muted">Changes stay local until you press Save details.</p>
          <div className="mt-3">
            <DetailsForm key={sermon.id} sermon={sermon} description={description} descriptionNeedsReview={descriptionNeedsReview} hashtags={hashtags} isLive={isLive} onSaveDetails={onSaveDetails} onRegenerateDescription={onRegenerateDescription} onToast={onToast} />
          </div>
        </aside>
      </div>
      <ConfirmDialog open={confirmRestore} title={`Restore original for “${sermon.title}”?`} body="All applied cuts are discarded and the unedited source is kept. This cannot be undone." confirmLabel="Restore original" onClose={() => setConfirmRestore(false)} onConfirm={restoreOriginal} />
      <ConfirmDialog open={confirmUploadNoDescription} title={`Upload “${sermon.title}” without a description?`} body="The description is empty because generation did not finish. Regenerate the description from the transcript before uploading, or upload anyway to publish the entry without one." confirmLabel="Upload anyway" onClose={() => setConfirmUploadNoDescription(false)} onConfirm={() => uploadExisting(true)} />
    </div>
  );
}
