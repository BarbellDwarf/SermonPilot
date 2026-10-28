import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { SermonReview, type DetailsPatch, type TranscriptState } from "../components/SermonReview";
import { SermonCompleted } from "../components/SermonCompleted";
import { sermonActionMatrix, sermonViewMode } from "../components/sermonActions";
import { sermonStatusLabel, sermonStatusTone } from "./Library";
import { Button, Chip, ConfirmDialog, EmptyState, PageHeader, SkeletonList, buttonClass } from "../components/ui";
import { useToast, dismissToast } from "../components/toast";
import { QueryError, useSermonDetail, useSermonMedia, useSermonPlan, useSermonTranscript } from "../api/hooks";
import { api, isLive, writeApi } from "../api/client";
import type { ApiTrashRecord } from "../api/client";
import { fieldValue, useConfigSection } from "../api/useConfigSection";
import { formatDate, formatDurationValue } from "../utils/format";

export function describeDeleteOutcome(records: ApiTrashRecord[]): string {
  const localMoved = records.filter((r) => r.mode === "local" && r.moved);
  const remoteMoved = records.filter((r) => r.mode === "remote" && r.moved);
  const remoteKept = records.filter((r) => r.mode === "remote-kept");
  const localKept = records.filter((r) => r.mode === "local" && !r.moved);
  const parts: string[] = [];
  if (localMoved.length > 0) {
    parts.push(`Local media moved to trash at ${localMoved[0].destination}.`);
  }
  if (remoteMoved.length > 0) {
    parts.push(`Cloud media moved to trash at ${remoteMoved[0].destination}.`);
  }
  if (remoteKept.length > 0) {
    parts.push("Cloud media stayed recoverable on its remote.");
  }
  if (localKept.length > 0) {
    parts.push("Local media could not be moved and was left in place.");
  }
  if (parts.length === 0) {
    parts.push("No media was destroyed.");
  }
  return parts.join(" ");
}

export function LibraryDetail() {
  const { id } = useParams();
  const notify = useToast();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);
  const [trash, setTrash] = useState<ApiTrashRecord[]>([]);
  const [pushing, setPushing] = useState(false);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [editingOverride, setEditingOverride] = useState(false);

  useEffect(() => {
    setEditingOverride(false);
    setDeleted(false);
    setConfirmDelete(false);
    setPendingDelete(false);
    setTrash([]);
    setTranscriptOpen(false);
    setCopied(false);
    setPushing(false);
  }, [id]);

  const { data: detail, isLoading, error, retry } = useSermonDetail(id);
  const { plan, history: planHistory, isLoading: planLoading, error: planError, retry: retryPlan } = useSermonPlan(id);
  const media = useSermonMedia(id, isLive && !deleted);
  const transcript = useSermonTranscript(id, transcriptOpen);
  const audioConfig = useConfigSection("audio");
  const enhanceDefault =
    fieldValue<boolean>(audioConfig.fields, "metadata_processing.process_audio", true) !== false &&
    fieldValue<string>(audioConfig.fields, "audio_enhancement_method", "deepfilternet") !== "none";

  const showToast = (msg: string, variant: "success" | "error" | "info" = "success") => {
    notify[variant](msg);
  };

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Teaching" />
        <SkeletonList rows={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="/library" className="inline-flex min-h-[44px] w-fit items-center rounded-md px-2 text-sm font-medium text-accent hover:underline">
          ← Library
        </Link>
        <QueryError message={error} onRetry={retry} />
      </div>
    );
  }

  const sermon = detail?.sermon;

  if (!sermon) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          title="Teaching not found"
          body={
            isLive
              ? "This teaching may have been applied or removed. Open the library to find the current entry."
              : "This demo library has only a handful of sample teachings. The link may be stale."
          }
          action={
            <Link to="/library" className={buttonClass("primary")}>
              Back to library
            </Link>
          }
        />
      </div>
    );
  }

  if (deleted) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          title="Teaching deleted"
          body={
            isLive
              ? pendingDelete
                ? `“${sermon.title}” is being removed. Local media moves to trash and cloud media stays recoverable.`
                : `“${sermon.title}” was removed from the database. ${describeDeleteOutcome(trash)}`
              : `“${sermon.title}” was removed from this demo list. Nothing was uploaded or lost.`
          }
          action={
            <Link to="/library" className={buttonClass("primary")}>
              Back to library
            </Link>
          }
        />
      </div>
    );
  }

  const remove = () => {
    if (!id) return;
    setConfirmDelete(false);
    setDeleted(true);
    setPendingDelete(true);
    setTrash([]);
    if (!isLive) {
      setPendingDelete(false);
      notify.undo(`“${sermon.title}” removed from this demo list.`, () => {
        setDeleted(false);
        notify.info("Delete undone.");
      });
      return;
    }
    const targetId = id;
    let undone = false;
    let undoToast = 0;
    const timer = window.setTimeout(() => {
      if (undone) return;
      dismissToast(undoToast);
      void api
        .deleteSermon(targetId)
        .then((result) => {
          setPendingDelete(false);
          setTrash(result?.trash ?? []);
          void queryClient.invalidateQueries({ queryKey: ["sermons"] });
          queryClient.removeQueries({ queryKey: ["sermon", targetId] });
          notify.success(`“${sermon.title}” deleted.`);
        })
        .catch((e) => {
          setPendingDelete(false);
          setDeleted(false);
          notify.error(`Could not delete: ${(e as Error).message}`);
        });
    }, 8000);
    undoToast = notify.undo(`“${sermon.title}” deleted.`, () => {
      undone = true;
      window.clearTimeout(timer);
      setPendingDelete(false);
      setDeleted(false);
      notify.info("Delete undone.");
    });
  };

  const push = () => {
    if (!id) return;
    if (isLive) {
      setPushing(true);
      void writeApi
        .uploadNow(id)
        .then(() => {
          setPushing(false);
          showToast("Upload queued.");
        })
        .catch((e) => {
          setPushing(false);
          const msg = (e as Error).message;
          showToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`, /409/.test(msg) ? "info" : "error");
        });
      return;
    }
    setPushing(true);
    window.setTimeout(() => {
      setPushing(false);
      showToast("Push to SermonAudio queued (demo).");
    }, 1200);
  };

  const regenerateDescription = () => {
    if (!id) return Promise.resolve();
    if (isLive) {
      return writeApi
        .regenerateDescription(id)
        .then(() => {
          showToast("Description regeneration queued.");
        })
        .catch((e) => {
          const msg = (e as Error).message;
          showToast(
            /409/.test(msg)
              ? "A job is already running for this teaching."
              : `Could not queue: ${msg}`,
            /409/.test(msg) ? "info" : "error",
          );
        });
    }
    showToast("Description regeneration queued (demo).");
    return Promise.resolve();
  };

  const pushDetails = () => {
    if (!id) return Promise.resolve();
    if (isLive) {
      return writeApi
        .pushMetadata(id, true)
        .then(() => {
          showToast("Metadata push queued.");
        })
        .catch((e) => {
          const msg = (e as Error).message;
          showToast(
            /409/.test(msg)
              ? "A job is already running for this teaching."
              : `Could not queue: ${msg}`,
            /409/.test(msg) ? "info" : "error",
          );
        });
    }
    showToast("Metadata push queued (demo).");
    return Promise.resolve();
  };

  const saveDetails = (patch: DetailsPatch) => {
    if (!id) return Promise.resolve();
    if (isLive) {
      return api
        .updateSermon(id, patch)
        .then(() => {
          retry();
          showToast("Details saved.");
        })
        .catch((e) => {
          showToast(`Could not save details: ${(e as Error).message}`, "error");
          throw e;
        });
    }
    showToast("Details saved (demo).");
    return Promise.resolve();
  };

  const transcriptState: TranscriptState = {
    open: transcriptOpen,
    onToggle: () => setTranscriptOpen((v) => !v),
    loading: transcript.isLoading,
    error: transcript.error,
    plainText: transcript.data?.transcript ?? "",
    totalLength: transcript.data?.total_length ?? 0,
    truncated: transcript.data?.truncated ?? false,
    timestampsAvailable: media.byKind["transcript_timestamps"]?.available ?? false,
    copied,
    onCopy: () => {
      if (!navigator.clipboard) {
        showToast("Copy failed: clipboard unavailable.", "error");
        return;
      }
      void navigator.clipboard
        .writeText(transcript.data?.transcript ?? "")
        .then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 2000);
        })
        .catch(() => showToast("Copy failed.", "error"));
    },
  };

  const actions = sermonActionMatrix({
    status: sermon.status,
    hasRender: !!media.byKind["processed"]?.available,
  });

  const viewMode = sermonViewMode({ status: sermon.status, planStatus: plan?.status });
  const showCompleted = viewMode === "completed" && !editingOverride;

  const headerActions = (
    <>
      {actions.canPublishLegacy ? (
        <Button variant="primary" onClick={push} disabled={pushing} aria-busy={pushing}>
          {pushing ? "Pushing…" : "Push to SermonAudio"}
        </Button>
      ) : null}
      <Button variant="danger" onClick={() => setConfirmDelete(true)}>
        Delete
      </Button>
    </>
  );

  return (
    <div className="flex flex-col gap-4">
      <Link to="/library" className="inline-flex min-h-[44px] w-fit items-center rounded-md px-2 text-sm font-medium text-accent hover:underline">
        ← Library
      </Link>

      {showCompleted ? (
        <SermonCompleted
          sermon={sermon}
          description={detail?.description ?? null}
          descriptionNeedsReview={detail?.descriptionNeedsReview ?? false}
          media={media}
          isLive={isLive}
          statusChip={<Chip tone={sermonStatusTone[sermon.status]}>{sermonStatusLabel[sermon.status]}</Chip>}
          onDelete={() => setConfirmDelete(true)}
          deleting={false}
          transcript={transcriptState}
          history={planHistory}
          sermonaudioId={detail?.sermonaudioId ?? null}
          uploadedAt={detail?.uploadedAt ?? null}
          bibleText={detail?.bibleText ?? null}
          scriptureReference={detail?.scriptureReference ?? null}
          onEdit={() => setEditingOverride(true)}
          onSaveDetails={saveDetails}
          onRegenerateDescription={regenerateDescription}
          onPushDetails={pushDetails}
        />
      ) : planLoading ? (
        <SkeletonList rows={3} />
      ) : planError ? (
        <QueryError message={planError} onRetry={retryPlan} />
      ) : plan ? (
        <SermonReview
          sermon={sermon}
          description={detail?.description ?? null}
          descriptionNeedsReview={detail?.descriptionNeedsReview ?? false}
          hashtags={detail?.hashtags ?? null}
          plan={plan}
          history={planHistory}
          sourceDurationSec={detail?.durationSeconds}
          media={media}
          isLive={isLive}
          statusChip={<Chip tone={sermonStatusTone[sermon.status]}>{sermonStatusLabel[sermon.status]}</Chip>}
          onDelete={() => setConfirmDelete(true)}
          deleting={false}
          transcript={transcriptState}
          onSaveDetails={saveDetails}
          onRegenerateDescription={regenerateDescription}
          onRefresh={retryPlan}
          onToast={showToast}
          onUpload={push}
          enhanceDefault={enhanceDefault}
          onShowCompleted={viewMode === "completed" ? () => setEditingOverride(false) : undefined}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <PageHeader
            title={sermon.title}
            sub={`${sermon.speaker || "Unknown speaker"} · ${formatDate(sermon.date)} · ${formatDurationValue(sermon.duration)}`}
            actions={
              <>
                <Chip tone={sermonStatusTone[sermon.status]}>{sermonStatusLabel[sermon.status]}</Chip>
                {headerActions}
              </>
            }
          />
          <EmptyState
            title="No auto-edit plan"
            body="This teaching has no proposed cuts to review yet. A plan appears here after detection runs."
            action={<Button onClick={retryPlan}>Check for a plan</Button>}
          />
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete “${sermon.title}”?`}
        body={
          isLive
            ? `“${sermon.title}” by ${sermon.speaker} will be removed from the database. Local media moves to trash and cloud media stays recoverable. You can undo for 8 seconds.`
            : `“${sermon.title}” by ${sermon.speaker} will be removed from this demo list. You can undo from the notification.`
        }
        confirmLabel="Delete"
        onClose={() => setConfirmDelete(false)}
        onConfirm={remove}
      />
    </div>
  );
}
