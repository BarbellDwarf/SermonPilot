import type { RemoveSegment } from "../../mock/data";

export interface UiCut extends RemoveSegment {
  enabled: boolean;
}

export const MIN_CUT_SECONDS = 0.25;

export function initialCuts(segments: RemoveSegment[] | undefined): UiCut[] {
  return (segments ?? []).map((segment) => ({ ...segment, enabled: true }));
}

export function normalizeUiRemoveSegments(
  segments: RemoveSegment[],
  startSec: number,
  endSec: number,
): { segments: RemoveSegment[]; errors: string[] } {
  const errors: string[] = [];
  const parsed = segments
    .map((segment, index) => ({ ...segment, index }))
    .sort((left, right) => left.startSec - right.startSec || left.endSec - right.endSec);
  const normalized: RemoveSegment[] = [];
  for (const segment of parsed) {
    if (
      !Number.isFinite(segment.startSec) ||
      !Number.isFinite(segment.endSec) ||
      segment.endSec <= segment.startSec
    ) {
      errors.push(`Cut ${segment.index + 1} must end after it starts.`);
      continue;
    }
    if (segment.endSec - segment.startSec < MIN_CUT_SECONDS) {
      errors.push(`Cut ${segment.index + 1} needs at least 0.25 seconds.`);
      continue;
    }
    if (segment.startSec <= startSec || segment.endSec >= endSec) {
      errors.push(`Cut ${segment.index + 1} must stay inside the keep window.`);
      continue;
    }
    const previous = normalized[normalized.length - 1];
    if (previous && segment.startSec < previous.endSec) {
      errors.push(`Cut ${segment.index + 1} overlaps another cut.`);
      continue;
    }
    if (previous && segment.startSec === previous.endSec) {
      previous.endSec = segment.endSec;
    } else {
      normalized.push({ startSec: segment.startSec, endSec: segment.endSec });
    }
  }
  return { segments: normalized, errors };
}
