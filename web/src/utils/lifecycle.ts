export type LifecycleState =
  | "draft"
  | "needs_review"
  | "processing"
  | "ready"
  | "published"
  | "failed";

export type LifecycleTone = "neutral" | "warn" | "info" | "accent" | "ok" | "danger";

export interface LifecycleInput {
  status?: string | null;
  edit_status?: string | null;
  upload_status?: string | null;
  plan_status?: string | null;
}

export interface LifecycleMeta {
  label: string;
  tone: LifecycleTone;
  primary: string | null;
}

function normalize(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

// Order is the plan's precedence, first match wins. Applied outranks a
// pending_review plan because the render job already accepted it.
export function deriveLifecycleState(sermon: LifecycleInput): LifecycleState {
  const status = normalize(sermon.status);
  const edit = normalize(sermon.edit_status);
  const upload = normalize(sermon.upload_status);
  const plan = normalize(sermon.plan_status);

  if (status === "error" || upload === "failed" || edit === "failed") return "failed";
  if (edit === "applied") return "processing";
  if (edit === "rendered") return "ready";
  if (plan === "pending_review" || edit === "pending_review") return "needs_review";
  if (edit === "uploaded" || status === "processed") return "published";
  return "draft";
}

export const LIFECYCLE_META: Record<LifecycleState, LifecycleMeta> = {
  draft: { label: "Draft", tone: "neutral", primary: "Continue" },
  needs_review: { label: "Needs review", tone: "warn", primary: "Review" },
  processing: { label: "Processing", tone: "info", primary: "View job" },
  ready: { label: "Ready to publish", tone: "ok", primary: "Publish" },
  published: { label: "Published", tone: "ok", primary: null },
  failed: { label: "Failed", tone: "danger", primary: "Retry" },
};

export function lifecycleTone(state: LifecycleState): LifecycleTone {
  return LIFECYCLE_META[state].tone;
}

export interface LifecycleCounts extends Record<LifecycleState, number> {
  total: number;
}

export function lifecycleCounts(items: readonly LifecycleInput[]): LifecycleCounts {
  const counts: LifecycleCounts = {
    draft: 0,
    needs_review: 0,
    processing: 0,
    ready: 0,
    published: 0,
    failed: 0,
    total: 0,
  };
  for (const item of items) {
    counts[deriveLifecycleState(item)] += 1;
    counts.total += 1;
  }
  return counts;
}
