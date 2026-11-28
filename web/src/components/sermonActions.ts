import type { LibrarySermonStatus, PlanStatus } from "../mock/data";
import type { LifecycleState } from "../utils/lifecycle";

export interface SermonActionState {
  status: LibrarySermonStatus;
  hasRender: boolean;
}

export type SermonViewMode = "editing" | "completed";

/**
 * A sermon is finished once it has been published (record status ``processed``)
 * or its edit plan has reached ``processed``. Every other combination still has
 * edit work pending, so it keeps the editing interface.
 */
export function sermonViewMode({
  status,
  planStatus,
}: {
  status: LibrarySermonStatus;
  planStatus?: PlanStatus | null;
}): SermonViewMode {
  if (status === "processed" || planStatus === "processed") return "completed";
  return "editing";
}

export type WorkspacePrimaryKind = "approve" | "publish" | "view-job" | "publish-draft" | "detect" | "none";

export interface WorkspacePrimary {
  kind: WorkspacePrimaryKind;
  label: string | null;
}

export function workspacePrimary({
  state,
  hasPlan,
  hasRender,
}: {
  state: LifecycleState;
  hasPlan: boolean;
  hasRender: boolean;
}): WorkspacePrimary {
  if (state === "published") return { kind: "none", label: null };
  if (state === "processing") return { kind: "view-job", label: "View job" };
  if (state === "ready") return { kind: "publish", label: "Publish" };
  if (state === "draft") {
    return hasRender
      ? { kind: "publish-draft", label: "Publish draft" }
      : { kind: "detect", label: "Run cut detection" };
  }
  if (state === "failed") {
    return hasPlan
      ? { kind: "approve", label: "Retry approval" }
      : { kind: "detect", label: "Retry cut detection" };
  }
  return { kind: "approve", label: "Approve & upload" };
}

export interface SermonActions {
  /** The record already has a SermonAudio entry, so publish-only actions are stale. */
  published: boolean;
  /** Publish the render already on disk without re-rendering. */
  canUploadExisting: boolean;
  /** Legacy full publish path, for a record that has no edit plan to apply. */
  canPublishLegacy: boolean;
}

/**
 * Actions that can still succeed for a record in the given state. The two apply
 * actions both re-render, so they stay available for every state, including a
 * published one that needs a re-edit; only the publish-only actions drop away.
 */
export function sermonActionMatrix({ status, hasRender }: SermonActionState): SermonActions {
  const published = status === "processed";
  return {
    published,
    canUploadExisting: !published && hasRender,
    canPublishLegacy: !published && status !== "draft",
  };
}
