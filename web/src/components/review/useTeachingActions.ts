import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api, isLive, writeApi } from "../../api/client";
import type { QueuedWorkspaceJob } from "./DecisionRail";
import type { DetailsPatch } from "./types";

interface TeachingActionsOptions {
  id?: string;
  onToast: (message: string, variant?: "success" | "error" | "info") => void;
}

export function useTeachingActions({ id, onToast }: TeachingActionsOptions) {
  const queryClient = useQueryClient();
  const [queueing, setQueueing] = useState(false);
  const [detectingPlan, setDetectingPlan] = useState(false);
  const [queuedJob, setQueuedJob] = useState<QueuedWorkspaceJob | null>(null);
  const mockJobSequence = useRef(3000);
  const nextMockJob = () => `job-${++mockJobSequence.current}`;

  const clearQueuedJob = useCallback(() => setQueuedJob(null), []);
  const captureJob = useCallback((jobId: string, message: string) => {
    setQueuedJob({ id: jobId, message });
    if (!isLive) {
      window.setTimeout(() => {
        setQueuedJob((current) => current?.id === jobId ? null : current);
      }, 1200);
    }
    void queryClient.invalidateQueries({ queryKey: ["sermon", id] });
    void queryClient.invalidateQueries({ queryKey: ["sermon-plan", id] });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    void queryClient.invalidateQueries({ queryKey: ["sermons"] });
  }, [id, queryClient]);

  const publish = () => {
    if (!id || queueing || queuedJob) return;
    if (!isLive) {
      setQueueing(true);
      window.setTimeout(() => {
        setQueueing(false);
        captureJob(nextMockJob(), "Upload queued.");
        onToast("Publish queued (demo).", "info");
      }, 300);
      return;
    }
    setQueueing(true);
    void writeApi.uploadNow(id)
      .then((result) => {
        setQueueing(false);
        captureJob(result.job_id, "Upload queued.");
        onToast("Publish queued.", "info");
      })
      .catch((cause: unknown) => {
        setQueueing(false);
        const message = (cause as Error).message;
        onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue: ${message}`, /409/.test(message) ? "info" : "error");
      });
  };

  const detectPlan = () => {
    if (!id || detectingPlan || queuedJob) return;
    if (!isLive) {
      setDetectingPlan(true);
      window.setTimeout(() => {
        setDetectingPlan(false);
        captureJob(nextMockJob(), "Cut detection queued.");
        onToast("Cut detection queued (demo).", "info");
      }, 300);
      return;
    }
    setDetectingPlan(true);
    void writeApi.reDetectPlan(id)
      .then((result) => {
        captureJob(result.job_id, "Cut detection queued.");
        onToast("Cut detection queued. This page updates when the plan is ready.", "info");
      })
      .catch((cause: unknown) => {
        setDetectingPlan(false);
        const message = (cause as Error).message;
        onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue detection: ${message}`, /409/.test(message) ? "info" : "error");
      });
  };

  const regenerateDescription = () => {
    if (!id || queuedJob) return Promise.resolve();
    if (!isLive) {
      captureJob(nextMockJob(), "Description regeneration queued.");
      onToast("Description regeneration queued (demo).");
      return Promise.resolve();
    }
    return writeApi.regenerateDescription(id)
      .then((result) => {
        captureJob(result.job_id, "Description regeneration queued.");
        onToast("Description regeneration queued.");
      })
      .catch((cause: unknown) => {
        const message = (cause as Error).message;
        onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue: ${message}`, /409/.test(message) ? "info" : "error");
      });
  };

  const pushMetadata = () => {
    if (!id || queuedJob) return Promise.resolve();
    if (!isLive) {
      captureJob(nextMockJob(), "Metadata push queued.");
      onToast("Metadata push queued (demo).");
      return Promise.resolve();
    }
    return writeApi.pushMetadata(id, true)
      .then((result) => {
        captureJob(result.job_id, "Metadata push queued.");
        onToast("Metadata push queued.");
      })
      .catch((cause: unknown) => {
        const message = (cause as Error).message;
        onToast(/409/.test(message) ? "A job is already running for this teaching." : `Could not queue: ${message}`, /409/.test(message) ? "info" : "error");
      });
  };

  const replaceRecording = (file: File) => {
    if (!id) return Promise.reject(new Error("Teaching not found."));
    if (!isLive) {
      captureJob(nextMockJob(), "Replacement queued.");
      onToast("Replacement queued (demo).");
      return Promise.resolve();
    }
    return writeApi.replaceRecording(id, file)
      .then((result) => {
        captureJob(result.job_id, "Replacement queued.");
        onToast("Replacement queued.");
      })
      .catch((cause: unknown) => {
        const active = cause instanceof ApiError && cause.status === 409;
        throw new Error(active ? "A job is already running for this teaching." : `Could not queue the replacement: ${(cause as Error).message}`);
      });
  };

  const saveDetails = (patch: DetailsPatch) => {
    if (!id) return Promise.resolve();
    if (!isLive) {
      onToast("Details saved (demo).");
      return Promise.resolve();
    }
    return api.updateSermon(id, patch)
      .then(() => {
        void queryClient.invalidateQueries({ queryKey: ["sermon", id] });
        onToast("Details saved.");
      })
      .catch((cause: unknown) => {
        onToast(`Could not save details: ${(cause as Error).message}`, "error");
        throw cause;
      });
  };

  return {
    queueing,
    detectingPlan,
    setDetectingPlan,
    queuedJob,
    clearQueuedJob,
    captureJob,
    publish,
    detectPlan,
    regenerateDescription,
    pushMetadata,
    replaceRecording,
    saveDetails,
  };
}
