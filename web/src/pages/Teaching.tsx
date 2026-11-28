import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { SermonReview, type SermonReviewView, type TranscriptState } from "../components/SermonReview";
import { CompletedDetails, SermonCompleted } from "../components/SermonCompleted";
import { workspacePrimary, type WorkspacePrimary } from "../components/sermonActions";
import { ConfirmDialog, EmptyState, PageHeader, SkeletonList, buttonClass, type MenuItem } from "../components/ui";
import { useToast, dismissToast } from "../components/toast";
import { QueryError, lifecycleOfSermon, useJobsData, useSermonDetail, useSermonMedia, useSermonPlan, useSermonTranscript } from "../api/hooks";
import { api, isLive, type ApiTrashRecord } from "../api/client";
import { fieldValue, useConfigSection } from "../api/useConfigSection";
import { formatDuration, formatDurationValue } from "../utils/format";
import { LIFECYCLE_META, type LifecycleState } from "../utils/lifecycle";
import { DecisionRail } from "../components/review/DecisionRail";
import { WorkspaceShell } from "../components/review/WorkspaceShell";
import { WorkspaceTabs, type WorkspaceTab } from "../components/review/WorkspaceTabs";
import { FilesPanel, HistoryPanel, TranscriptPanel } from "../components/review/WorkspacePanels";
import { DetailsForm } from "../components/review/DetailsForm";
import { qaCopy } from "../components/review/PlanSummary";
import { useTeachingActions } from "../components/review/useTeachingActions";
import { useWorkspaceDialogs } from "../components/review/useWorkspaceDialogs";
import { WorkspaceMenu } from "../components/review/WorkspaceMenu";

export function describeDeleteOutcome(records: ApiTrashRecord[]): string {
  const localMoved = records.filter((record) => record.mode === "local" && record.moved);
  const remoteMoved = records.filter((record) => record.mode === "remote" && record.moved);
  const remoteKept = records.filter((record) => record.mode === "remote-kept");
  const localKept = records.filter((record) => record.mode === "local" && !record.moved);
  const parts: string[] = [];
  if (localMoved.length > 0) parts.push(`Local media moved to trash at ${localMoved[0].destination}.`);
  if (remoteMoved.length > 0) parts.push(`Cloud media moved to trash at ${remoteMoved[0].destination}.`);
  if (remoteKept.length > 0) parts.push("Cloud media stayed recoverable on its remote.");
  if (localKept.length > 0) parts.push("Local media could not be moved and was left in place.");
  if (parts.length === 0) parts.push("No media was destroyed.");
  return parts.join(" ");
}

function useDesktopWorkspace(): boolean {
  const [desktop, setDesktop] = useState(() =>
    typeof window.matchMedia === "function" && window.matchMedia("(min-width: 768px)").matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(min-width: 768px)");
    const update = () => setDesktop(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return desktop;
}

export function Teaching() {
  const { id } = useParams();
  return <TeachingWorkspace key={id ?? "missing"} id={id} />;
}

function TeachingWorkspace({ id }: { id?: string }) {
  const notify = useToast();
  const queryClient = useQueryClient();
  const desktop = useDesktopWorkspace();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);
  const [trash, setTrash] = useState<ApiTrashRecord[]>([]);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [editingOverride, setEditingOverride] = useState(false);
  const [activeTab, setActiveTab] = useState<WorkspaceTab["id"]>("details");

  const { data: detail, isLoading, error, retry } = useSermonDetail(id);
  const { plan, history: planHistory, isLoading: planLoading, error: planError, retry: retryPlan } = useSermonPlan(id);
  const media = useSermonMedia(id, isLive && !deleted);
  const transcript = useSermonTranscript(id, transcriptOpen);
  const jobs = useJobsData();
  const audioConfig = useConfigSection("audio");
  const showToast = (message: string, variant: "success" | "error" | "info" = "success") => notify[variant](message);
  const actions = useTeachingActions({ id, onToast: showToast });
  const {
    queueing, detectingPlan, setDetectingPlan, queuedJob, clearQueuedJob, captureJob, publish, detectPlan,
    regenerateDescription, pushMetadata, replaceRecording, saveDetails,
  } = actions;
  const enhanceDefault =
    fieldValue<boolean>(audioConfig.fields, "metadata_processing.process_audio", true) !== false &&
    fieldValue<string>(audioConfig.fields, "audio_enhancement_method", "deepfilternet") !== "none";
  const sermon = detail?.sermon;
  const lifecycleSermon = sermon ? { ...sermon, plan_status: plan?.status ?? sermon.plan_status } : undefined;
  const state: LifecycleState = !lifecycleSermon ? "draft" : sermon?.status === "processed" || sermon?.edit_status === "uploaded" ? "published" : lifecycleOfSermon(lifecycleSermon);
  const hasRender = !!media.byKind.processed?.available;
  const primary = workspacePrimary({ state, hasPlan: !!plan, hasRender });
  const activeJob = jobs.data?.active.find((job) => job.parameters?.sermon_id === sermon?.id);
  const jobHref = activeJob ? `/activity/${activeJob.id}` : "/activity";
  const showCompleted = state === "published" && !editingOverride;
  const selectedDuration = plan ? Math.max(0, plan.endSec - plan.startSec) : 0;
  const removedInterior = plan?.removeSegments.reduce((total, segment) => total + Math.max(0, segment.endSec - segment.startSec), 0) ?? 0;
  const keptPercent = selectedDuration > 0 ? Math.round((Math.max(0, selectedDuration - removedInterior) / selectedDuration) * 100) : 0;
  const statusDetail = !sermon ? "" : showCompleted
    ? "Published to SermonAudio"
    : plan
      ? `${plan.removeSegments.length} cuts · kept ${formatDuration(Math.max(0, selectedDuration - removedInterior))} · ${keptPercent}% · ${qaCopy(plan.qa) || "check cut points"}`
      : `No cut plan · ${formatDurationValue(sermon.duration)}`;
  const dialogs = useWorkspaceDialogs({ state, statusDetail, plan: plan ?? null, onReplace: replaceRecording });

  useEffect(() => {
    if (plan) setDetectingPlan(false);
  }, [plan, setDetectingPlan]);

  useEffect(() => {
    if (!queuedJob || !jobs.data) return;
    const active = jobs.data.active.some((job) => job.id === queuedJob.id);
    const known = [...jobs.data.active, ...jobs.data.completed, ...jobs.data.failed].some((job) => job.id === queuedJob.id);
    if (known && !active) {
      if (id) {
        void queryClient.invalidateQueries({ queryKey: ["sermon", id] });
        void queryClient.invalidateQueries({ queryKey: ["sermon-plan", id] });
        void queryClient.invalidateQueries({ queryKey: ["sermons"] });
      }
      clearQueuedJob();
    }
  }, [clearQueuedJob, id, jobs.data, queryClient, queuedJob]);

  useEffect(() => {
    if (!detectingPlan || !id) return;
    const refresh = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["sermon-plan", id] });
    }, 4000);
    const stop = window.setTimeout(() => setDetectingPlan(false), 180000);
    return () => {
      window.clearInterval(refresh);
      window.clearTimeout(stop);
    };
  }, [detectingPlan, id, queryClient, setDetectingPlan]);

  if (isLoading) return <div className="flex flex-col gap-4"><PageHeader title="Teaching" /><SkeletonList rows={3} /></div>;
  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="/" className="inline-flex min-h-[44px] w-fit items-center rounded-md px-2 text-sm font-medium text-accent hover:underline">← Inbox</Link>
        <h1 className="text-2xl font-bold">Teaching</h1>
        <QueryError message={error} onRetry={retry} />
      </div>
    );
  }
  if (!sermon) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="sr-only">Teaching not found</h1>
        <EmptyState title="Teaching not found" body="This teaching may have been applied or removed. Open the Inbox to find the current entry." action={<Link to="/" className={buttonClass("primary")}>Back to Inbox</Link>} />
      </div>
    );
  }
  if (deleted) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="sr-only">Teaching deleted</h1>
        <EmptyState
          title="Teaching deleted"
          body={isLive ? pendingDelete ? `“${sermon.title}” is being removed. Local media moves to trash and cloud media stays recoverable.` : `“${sermon.title}” was removed from the database. ${describeDeleteOutcome(trash)}` : `“${sermon.title}” was removed from this demo list. Nothing was uploaded or lost.`}
          action={<Link to="/" className={buttonClass("primary")}>Back to Inbox</Link>}
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
      void api.deleteSermon(targetId)
        .then((result) => {
          setPendingDelete(false);
          setTrash(result?.trash ?? []);
          void queryClient.invalidateQueries({ queryKey: ["sermons"] });
          queryClient.removeQueries({ queryKey: ["sermon", targetId] });
          notify.success(`“${sermon.title}” deleted.`);
        })
        .catch((cause: unknown) => {
          setPendingDelete(false);
          setDeleted(false);
          notify.error(`Could not delete: ${(cause as Error).message}`);
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

  const transcriptState: TranscriptState = {
    open: transcriptOpen,
    onToggle: () => setTranscriptOpen((value) => !value),
    loading: transcript.isLoading,
    error: transcript.error,
    plainText: transcript.data?.transcript ?? "",
    totalLength: transcript.data?.total_length ?? 0,
    truncated: transcript.data?.truncated ?? false,
    timestampsAvailable: media.byKind.transcript_timestamps?.available ?? false,
    copied,
    onCopy: () => {
      if (!navigator.clipboard) {
        showToast("Copy failed: clipboard unavailable.", "error");
        return;
      }
      void navigator.clipboard.writeText(transcript.data?.transcript ?? "")
        .then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 2000);
        })
        .catch(() => showToast("Copy failed.", "error"));
    },
  };

  const moreMenu = (items: MenuItem[]) => <WorkspaceMenu items={items} />;
  const summary = <div className="flex flex-col gap-1"><p className="text-sm font-semibold">{LIFECYCLE_META[state].label}</p><p className="text-xs text-muted">{statusDetail}</p></div>;
  const shell = ({ body, tabs, actionPrimary, onPrimary, onSendBack, menu, disabled = false, busy = false }: {
    body: ReactNode;
    tabs: ReactNode;
    actionPrimary: WorkspacePrimary;
    onPrimary: () => void;
    onSendBack?: () => void;
    menu: ReactNode;
    disabled?: boolean;
    busy?: boolean;
  }) => (
    <WorkspaceShell
      sermon={sermon}
      state={state}
      statusDetail={statusDetail}
      onStatusOpen={dialogs.openStatus}
      body={body}
      tabs={tabs}
      decision={<DecisionRail primary={actionPrimary} onPrimary={onPrimary} primaryDisabled={disabled || !!queuedJob} primaryBusy={busy} queued={queuedJob} onSendBack={queuedJob ? undefined : onSendBack} moreActions={menu} summary={summary} jobHref={jobHref} />}
    />
  );

  const workView = (view: SermonReviewView) => {
    dialogs.registerNotesHandler((note) => view.actions.submitRefine(note));
    const tabs: WorkspaceTab[] = [
      { id: "details", label: "Details", content: view.details },
      { id: "transcript", label: "Transcript", content: view.transcript },
      { id: "files", label: "Files", content: view.files },
      { id: "history", label: "History", content: view.history },
    ];
    const runPrimary = () => {
      if (primary.kind === "approve") view.actions.approve(view.editor, false);
      else if (primary.kind === "publish" || primary.kind === "publish-draft") publish();
      else if (primary.kind === "detect") detectPlan();
    };
    const menu = moreMenu([
      ...(view.onShowCompleted ? [{ label: "Back to published view", onSelect: view.onShowCompleted, testId: "show-completed-view" }] : []),
      { label: "Render only", onSelect: () => view.actions.approve(view.editor, true), disabled: view.actions.applying || state === "processing" || !!queuedJob || view.editor.errors.length > 0, testId: "render-only-action" },
      ...(view.actions.actions.canUploadExisting ? [{ label: view.actions.uploading ? "Uploading…" : "Upload existing render", onSelect: () => view.actions.uploadExisting(false), disabled: view.actions.applying || view.actions.uploading || !!queuedJob, testId: "upload-existing-render" }] : []),
      { label: "Send back with note", onSelect: dialogs.openNotes, disabled: !!queuedJob },
      { label: "Re-detect", onSelect: view.actions.reDetect, disabled: view.actions.refining || !!queuedJob },
      { label: "History", onSelect: () => setActiveTab("history"), testId: "open-history" },
      { label: "Regenerate description", onSelect: () => void regenerateDescription(), disabled: !!queuedJob },
      { label: "Push metadata", onSelect: () => void pushMetadata(), disabled: !!queuedJob },
      { label: "Replace recording", onSelect: dialogs.openReplace, disabled: !!queuedJob, testId: "replace-recording" },
      { label: "Delete", onSelect: () => setConfirmDelete(true), danger: true, testId: "delete-sermon" },
    ]);
    return (
      <div data-testid="sermon-review">
        {shell({
          body: view.player,
          tabs: <WorkspaceTabs tabs={tabs} active={activeTab} onChange={setActiveTab} />,
          actionPrimary: primary,
          onPrimary: runPrimary,
          onSendBack: dialogs.openNotes,
          menu,
          disabled: primary.kind === "approve" && view.editor.errors.length > 0,
          busy: view.actions.applying || queueing,
        })}
      </div>
    );
  };

  const completedTabs: WorkspaceTab[] = [
    { id: "details", label: "Details", content: <CompletedDetails sermon={sermon} description={detail?.description ?? null} descriptionNeedsReview={detail?.descriptionNeedsReview ?? false} hashtags={detail?.hashtags ?? null} isLive={isLive} sermonaudioId={detail?.sermonaudioId ?? null} uploadedAt={detail?.uploadedAt ?? null} bibleText={detail?.bibleText ?? null} scriptureReference={detail?.scriptureReference ?? null} onSaveDetails={saveDetails} onRegenerateDescription={regenerateDescription} onToast={showToast} /> },
    { id: "transcript", label: "Transcript", content: <TranscriptPanel sermonId={sermon.id} isLive={isLive} transcript={transcriptState} onSeek={() => undefined} /> },
    { id: "files", label: "Files", content: <FilesPanel sermonId={sermon.id} media={media} isLive={isLive} /> },
    { id: "history", label: "History", content: plan ? <HistoryPanel plan={plan} history={planHistory} noteRows={[]} statusLog={[]} /> : <p className="text-sm text-muted">No edit history recorded.</p> },
  ];
  const completedMenu = moreMenu([
    { label: "Edit teaching", onSelect: () => setEditingOverride(true), testId: "edit-sermon" },
    { label: "Regenerate description", onSelect: () => void regenerateDescription(), disabled: !!queuedJob },
    { label: "Push metadata", onSelect: () => void pushMetadata(), disabled: !!queuedJob },
    ...(detail?.sermonaudioId ? [{ label: "Replace recording", onSelect: dialogs.openReplace, disabled: !!queuedJob, testId: "replace-recording" }] : []),
    { label: "Delete", onSelect: () => setConfirmDelete(true), danger: true, testId: "delete-sermon" },
  ]);

  return (
    <>
      {showCompleted ? shell({
        body: <SermonCompleted sermon={sermon} media={media} isLive={isLive} />,
        tabs: <WorkspaceTabs tabs={completedTabs} active={activeTab} onChange={setActiveTab} />,
        actionPrimary: primary,
        onPrimary: () => undefined,
        menu: completedMenu,
      }) : planLoading ? (
        <div className="flex flex-col gap-4"><PageHeader title={sermon.title} sub={`${sermon.speaker} · ${LIFECYCLE_META[state].label}`} /><SkeletonList rows={3} /></div>
      ) : planError ? (
        <div className="flex flex-col gap-4"><h1 className="text-2xl font-bold">{sermon.title}</h1><QueryError message={planError} onRetry={retryPlan} /></div>
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
          enhanceDefault={enhanceDefault}
          readOnly={!desktop}
          onSaveDetails={saveDetails}
          onRegenerateDescription={regenerateDescription}
          onRefresh={retryPlan}
          onToast={showToast}
          onSendBack={dialogs.openNotes}
          onJobQueued={captureJob}
          onShowCompleted={state === "published" ? () => setEditingOverride(false) : undefined}
        >
          {workView}
        </SermonReview>
      ) : (
        shell({
          body: <EmptyState title="No edit plan yet" body="Detect the opening and closing cuts, then review and approve them before the recording is re-rendered." />,
          tabs: <WorkspaceTabs tabs={[
            { id: "details", label: "Details", content: <DetailsForm sermon={sermon} description={detail?.description ?? null} hashtags={detail?.hashtags ?? null} isLive={isLive} readOnly={!desktop} onSaveDetails={saveDetails} onToast={showToast} /> },
            { id: "transcript", label: "Transcript", content: <TranscriptPanel sermonId={sermon.id} isLive={isLive} transcript={transcriptState} onSeek={() => undefined} /> },
            { id: "files", label: "Files", content: <FilesPanel sermonId={sermon.id} media={media} isLive={isLive} /> },
            { id: "history", label: "History", content: <p className="text-sm text-muted">No edit history recorded.</p> },
          ]} active={activeTab} onChange={setActiveTab} />,
          actionPrimary: primary,
          onPrimary: detectPlan,
          menu: moreMenu([
            { label: "History", onSelect: () => setActiveTab("history") },
            { label: "Replace recording", onSelect: dialogs.openReplace, testId: "replace-recording" },
            { label: "Delete", onSelect: () => setConfirmDelete(true), danger: true, testId: "delete-sermon" },
          ]),
          busy: queueing || detectingPlan,
        })
      )}
      {dialogs.dialogs}
      <ConfirmDialog open={confirmDelete} title={`Delete “${sermon.title}”?`} body={isLive ? `“${sermon.title}” by ${sermon.speaker} will be removed from the database. Local media moves to trash and cloud media stays recoverable. You can undo for 8 seconds.` : `“${sermon.title}” by ${sermon.speaker} will be removed from this demo list. You can undo from the notification.`} confirmLabel="Delete" onClose={() => setConfirmDelete(false)} onConfirm={remove} />
    </>
  );
}
