import type { LibrarySermonStatus } from "../mock/data";

export interface SermonActionState {
  status: LibrarySermonStatus;
  hasRender: boolean;
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
