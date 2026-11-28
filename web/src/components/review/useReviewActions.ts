import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError, writeApi } from "../../api/client";
import type { SermonMediaData } from "../../api/hooks";
import type { EditPlan, LibrarySermon } from "../../mock/data";
import { sermonActionMatrix } from "../sermonActions";
import type { CutEditor } from "./useCutEditor";

interface ReviewActionsOptions {
  initialPlan: EditPlan;
  sermon: LibrarySermon;
  media: SermonMediaData;
  isLive: boolean;
  onRefresh?: () => void;
  onToast: (message: string, variant?: "success" | "error" | "info") => void;
  onJobQueued?: (jobId: string, message: string) => void;
}

export function useReviewActions({
  initialPlan,
  sermon,
  media,
  isLive,
  onRefresh,
  onToast,
  onJobQueued,
}: ReviewActionsOptions) {
  const queryClient = useQueryClient();
  const [plan, setPlan] = useState(initialPlan);
  const [applying, setApplying] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [refining, setRefining] = useState(false);
  const [mockNotes, setMockNotes] = useState<{ revision: number; note: string }[]>([]);
  const [statusLog, setStatusLog] = useState<string[]>([]);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [confirmUploadNoDescription, setConfirmUploadNoDescription] = useState(false);
  const applyInFlight = useRef(false);
  const uploadInFlight = useRef(false);
  const mockJobSequence = useRef(2000);
  const nextMockJob = () => `job-${++mockJobSequence.current}`;
  const actions = sermonActionMatrix({ status: sermon.status, hasRender: !!media.byKind.processed?.available });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["sermon", sermon.id] });
    void queryClient.invalidateQueries({ queryKey: ["sermon-plan", sermon.id] });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    void queryClient.invalidateQueries({ queryKey: ["sermons"] });
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
          invalidate();
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
      const request = editor.applyRequest(renderOnly, !renderOnly);
      const jobId = nextMockJob();
      setStatusLog((history) => [...history, `revision ${plan.revision} superseded`]);
      setPlan((current) => ({
        ...current,
        status: "applied_local",
        revision: current.revision + 1,
        revisionsTotal: current.revisionsTotal + 1,
        startSec: request.start,
        endSec: request.end,
        removeSegments: request.remove_segments.map((segment) => ({ startSec: segment.start_sec, endSec: segment.end_sec })),
        offsetSec: request.audio_offset,
      }));
      onJobQueued?.(jobId, renderOnly ? "Rendering queued." : "Rendering, then upload queued.");
      onToast(renderOnly ? "Plan approved, render queued (demo). Previous revision superseded." : "Plan approved, render + upload queued (demo). Previous revision superseded.");
    }, 900);
  };

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
          invalidate();
          onJobQueued?.(result.job_id, "Upload queued.");
          onToast("Upload of the existing render queued.");
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
      const jobId = nextMockJob();
      invalidate();
      onJobQueued?.(jobId, "Upload queued.");
      onToast("Upload of the existing render queued (demo).");
    }, 900);
  };

  const restoreOriginal = () => {
    if (restoring) return;
    setConfirmRestore(false);
    if (!isLive) {
      setPlan((current) => ({ ...current, status: "draft", revision: 1 }));
      onToast("Original restored (demo). Plan reset to draft.");
      return;
    }
    setRestoring(true);
    void writeApi.restorePlan(sermon.id)
      .then((result) => {
        setRestoring(false);
        onRefresh?.();
        if (result.job_id) onJobQueued?.(result.job_id, "Original restored locally. Re-upload queued.");
        onToast(result.job_id ? "Original restored locally. Re-upload to SermonAudio queued." : "Original restored. The plan is reset to the full recording.");
      })
      .catch((error: unknown) => {
        setRestoring(false);
        onToast((error as ApiError)?.message || "Could not restore the original recording.", "error");
      });
  };

  const submitRefine = async (noteOverride: string): Promise<boolean> => {
    const note = noteOverride.trim();
    if (!note || refining) return false;
    if (isLive) {
      setRefining(true);
      try {
        const result = await writeApi.refinePlan(sermon.id, note);
        onRefresh?.();
        onJobQueued?.(result.job_id, "Re-detection queued with your notes.");
        onToast("Re-detection queued with your notes. The panel updates when the new proposal is ready.");
        return true;
      } catch (error) {
        const message = (error as Error).message;
        onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue: ${message}`, /409/.test(message) ? "info" : "error");
        return false;
      } finally {
        setRefining(false);
      }
    }
    setRefining(true);
    return new Promise<boolean>((resolve) => {
      window.setTimeout(() => {
        setRefining(false);
        const nextRevision = plan.revision + 1;
        const jobId = nextMockJob();
        setMockNotes((rows) => [...rows, { revision: nextRevision, note }]);
        setStatusLog((history) => [...history, `revision ${plan.revision} superseded`]);
        setPlan((current) => ({ ...current, status: "pending_review", revision: nextRevision, revisionsTotal: Math.max(current.revisionsTotal, nextRevision), reasoning: `Re-ran detection against your note: "${note}".` }));
        onJobQueued?.(jobId, "Re-detection queued with your notes.");
        onToast("New cut proposal ready (demo). Previous revision superseded.");
        resolve(true);
      }, 900);
    });
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
      const jobId = nextMockJob();
      setStatusLog((history) => [...history, `revision ${plan.revision} superseded (re-detect)`]);
      setPlan((current) => ({ ...current, status: "pending_review", revision: nextRevision, revisionsTotal: Math.max(current.revisionsTotal, nextRevision), detectionStatus: "ok", reasoning: "Detection re-run from scratch without prior notes." }));
      onJobQueued?.(jobId, "Re-detection queued.");
      onToast("Detection re-run from scratch (demo). Earlier revisions kept in history.");
    }, 900);
  };

  return {
    plan,
    actions,
    applying,
    uploading,
    restoring,
    refining,
    mockNotes,
    statusLog,
    confirmRestore,
    setConfirmRestore,
    confirmUploadNoDescription,
    setConfirmUploadNoDescription,
    approve,
    uploadExisting,
    restoreOriginal,
    submitRefine,
    reDetect,
  };
}

export type ReviewActions = ReturnType<typeof useReviewActions>;
