import type { LibrarySermonStatus, PlanStatus } from "../mock/data";

export interface SermonActionState {
  status: LibrarySermonStatus;
  hasRender: boolean;
}

export type SermonViewMode = "editing" | "completed";

/**
 * A teaching is finished once it has been uploaded (record status ``uploaded``)
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
  if (status === "uploaded" || planStatus === "processed") return "completed";
  return "editing";
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
 * actions both re-render, so they stay available for every state, including an
 * uploaded one that needs a re-edit; only the publish-only actions drop away.
 */
export function sermonActionMatrix({ status, hasRender }: SermonActionState): SermonActions {
  const published = status === "uploaded";
  return {
    published,
    canUploadExisting: !published && hasRender,
    // A queued record has not been processed and a draft has not been approved,
    // so neither has anything worth publishing yet. Offering the upload as the
    // primary action on both put a button that could only fail in front of the
    // operator. A record that already carries a render, or one whose last run
    // failed partway through publishing, can still be pushed.
    canPublishLegacy: !published && (hasRender || status === "failed"),
  };
}
