import type { ReactNode } from "react";
import type { EditPlan, PlanStatus, RemoveSegment } from "../../mock/data";
import { formatDuration } from "../../utils/format";
import { Chip, Toggle, type ChipTone } from "../ui";

export const planStatusLabel: Record<PlanStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  applied_local: "Applied locally",
  processed: "Processed",
  superseded: "Superseded",
};

const planStatusTone: Record<PlanStatus, ChipTone> = {
  draft: "neutral",
  pending_review: "warn",
  applied_local: "info",
  processed: "ok",
  superseded: "neutral",
};

export function qaCopy(qa: string): string {
  const value = qa.trim().toLowerCase();
  if (!value || value === "—") return "";
  if (value === "pass") return "No problems found";
  if (value === "review") return "Check the cut points";
  if (value === "fail") return "Automated check flagged this plan";
  return `Automated check: ${qa}`;
}

interface PlanSummaryProps {
  plan: EditPlan;
  duration: number | null;
  keptDuration: number | null;
  timelineDuration: number;
  safeStart: number;
  safeEnd: number;
  enabledRemoveSegments: RemoveSegment[];
  statusChip?: ReactNode;
  enhance?: boolean;
  onEnhanceChange?: (enabled: boolean) => void;
  children?: ReactNode;
}

export function PlanSummary({
  plan,
  duration,
  keptDuration,
  timelineDuration,
  safeStart,
  safeEnd,
  enabledRemoveSegments,
  statusChip,
  enhance,
  onEnhanceChange,
  children,
}: PlanSummaryProps) {
  const boundaryTrims = Number(safeStart > 0) + Number(timelineDuration > safeEnd);
  const interiorCuts = enabledRemoveSegments.filter((segment) => segment.endSec > segment.startSec);
  const confidence = plan.confidence > 0 ? `${plan.confidence}% confidence` : null;
  const qaText = plan.detectionStatus === "unavailable" ? "" : qaCopy(plan.qa);
  const removedDuration = duration !== null && keptDuration !== null ? duration - keptDuration : null;

  return (
    <section data-testid="approval-summary" aria-label="Plan status" className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Chip tone={planStatusTone[plan.status]}>Cut plan: {planStatusLabel[plan.status]}</Chip>
        {statusChip}
        <span className="font-mono text-xs text-muted" data-testid="plan-meta">
          Revision {plan.revision} of {plan.revisionsTotal}
          {confidence ? ` · ${confidence}` : ""}
        </span>
        {qaText ? <span className="text-xs text-muted" data-testid="plan-qa">{qaText}</span> : null}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1" data-testid="cut-summary-counts">
        <span className="text-sm font-semibold" data-testid="cut-kept-summary">Kept {formatDuration(keptDuration)}</span>
        <span className="text-xs text-muted">
          of {formatDuration(duration)} selected · {formatDuration(removedDuration)} removed
        </span>
        <span className="text-xs text-muted" data-testid="boundary-trim-count">{boundaryTrims} boundary trims</span>
        <span className="text-xs text-muted" data-testid="interior-cut-count">{interiorCuts.length} interior cuts</span>
      </div>
      {enhance !== undefined && onEnhanceChange ? (
        <Toggle
          checked={enhance}
          onChange={onEnhanceChange}
          label="Enhance audio"
          testId="apply-enhance-audio"
          hint={enhance ? "Requested for this apply (defaults to Audio settings)." : "Skipped for this apply."}
        />
      ) : null}
      {children}
    </section>
  );
}
