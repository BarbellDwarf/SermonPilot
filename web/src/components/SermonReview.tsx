import { useMemo, type ReactNode } from "react";
import type { SermonMediaData } from "../api/hooks";
import type { EditPlan, LibrarySermon } from "../mock/data";
import { ConfirmDialog } from "./ui";
import { CutEditorSession } from "./review/CutEditorSession";
import { DetailsForm } from "./review/DetailsForm";
import { ReviewPlayerBody } from "./review/ReviewPlayer";
import { FilesPanel, HistoryPanel, TranscriptPanel } from "./review/WorkspacePanels";
import type { CutEditor } from "./review/useCutEditor";
import { useReviewActions, type ReviewActions } from "./review/useReviewActions";
import type { DetailsPatch, TranscriptState } from "./review/types";

export { artifactLabel, preferredKind } from "./review/media";
export { planStatusLabel } from "./review/PlanSummary";
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
  readOnly?: boolean;
  statusChip?: ReactNode;
  transcript?: TranscriptState;
  onSaveDetails?: (patch: DetailsPatch) => Promise<void> | void;
  onRegenerateDescription?: () => Promise<void> | void;
  onRefresh?: () => void;
  onToast: (msg: string, variant?: "success" | "error" | "info") => void;
  enhanceDefault?: boolean;
  onShowCompleted?: () => void;
  onSendBack?: () => void;
  onJobQueued?: (jobId: string, message: string) => void;
  children: (view: SermonReviewView) => ReactNode;
}

export interface SermonReviewView {
  player: ReactNode;
  details: ReactNode;
  transcript: ReactNode;
  files: ReactNode;
  history: ReactNode;
  confirmDialogs: ReactNode;
  editor: CutEditor;
  actions: ReviewActions;
  onShowCompleted?: () => void;
}

function planKey(plan: EditPlan): string {
  return `${plan.sermonId}:${plan.revision}:${plan.startSec}:${plan.endSec}:${plan.offsetSec}:${plan.status}:${JSON.stringify(plan.removeSegments ?? [])}`;
}

export function SermonReview(props: SermonReviewProps) {
  return <SermonReviewSession key={`${props.sermon.id}:${planKey(props.plan)}`} {...props} />;
}

function SermonReviewSession({
  sermon,
  description,
  descriptionNeedsReview,
  hashtags,
  plan: initialPlan,
  history,
  sourceDurationSec,
  media,
  isLive,
  readOnly = false,
  statusChip,
  transcript,
  onSaveDetails,
  onRegenerateDescription,
  onRefresh,
  onToast,
  enhanceDefault,
  onShowCompleted,
  onSendBack,
  onJobQueued,
  children,
}: SermonReviewProps) {
  const reviewActions = useReviewActions({ initialPlan, sermon, media, isLive, onRefresh, onToast, onJobQueued });
  const noteRows = useMemo(() => {
    const fromPlan = (history ?? []).filter((row) => row.notes.trim().length > 0).map((row) => ({ revision: row.revision, note: row.notes.trim() }));
    const seen = new Set<string>();
    return [...fromPlan, ...reviewActions.mockNotes]
      .filter((row) => {
        const key = `${row.revision}:${row.note}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((left, right) => left.revision - right.revision);
  }, [history, reviewActions.mockNotes]);

  return (
    <CutEditorSession key={planKey(reviewActions.plan)} options={{ initialPlan: reviewActions.plan, media, sourceDurationSec, enhanceDefault }}>
      {(editor) => {
        const view: SermonReviewView = {
          editor,
          actions: reviewActions,
          onShowCompleted,
          player: (
            <ReviewPlayerBody
              sermonId={sermon.id}
              editor={editor}
              plan={reviewActions.plan}
              media={media}
              isLive={isLive}
              statusChip={statusChip}
              readOnly={readOnly}
              applying={reviewActions.applying}
              restoring={reviewActions.restoring}
              onRestore={() => reviewActions.setConfirmRestore(true)}
            />
          ),
          details: (
            <DetailsForm
              key={`${sermon.id}:${readOnly}`}
              sermon={sermon}
              description={description}
              descriptionNeedsReview={descriptionNeedsReview}
              hashtags={hashtags}
              isLive={isLive}
              readOnly={readOnly}
              onSaveDetails={onSaveDetails}
              onRegenerateDescription={onRegenerateDescription}
              onSendBack={onSendBack}
              onToast={onToast}
            />
          ),
          transcript: <TranscriptPanel sermonId={sermon.id} isLive={isLive} transcript={transcript} onSeek={editor.requestSeek} />,
          files: <FilesPanel sermonId={sermon.id} media={media} isLive={isLive} onOpenArtifact={editor.setPlayerKind} />,
          history: <HistoryPanel plan={reviewActions.plan} history={history} noteRows={noteRows} statusLog={reviewActions.statusLog} />,
          confirmDialogs: (
            <>
              <ConfirmDialog open={reviewActions.confirmRestore} title={`Restore original for “${sermon.title}”?`} body="All applied cuts are discarded and the unedited source is kept. This cannot be undone." confirmLabel="Restore original" onClose={() => reviewActions.setConfirmRestore(false)} onConfirm={reviewActions.restoreOriginal} />
              <ConfirmDialog open={reviewActions.confirmUploadNoDescription} title={`Upload “${sermon.title}” without a description?`} body="The description is empty because generation did not finish. Regenerate the description from the transcript before uploading, or upload anyway to publish the entry without one." confirmLabel="Upload anyway" onClose={() => reviewActions.setConfirmUploadNoDescription(false)} onConfirm={() => reviewActions.uploadExisting(true)} />
            </>
          ),
        };
        return <>{children(view)}{view.confirmDialogs}</>;
      }}
    </CutEditorSession>
  );
}
