import { useMemo, useRef, useState } from "react";
import type { SermonMediaData } from "../../api/hooks";
import type { EditPlan, RemoveSegment } from "../../mock/data";
import { formatCut, parseCut } from "../../utils/time";
import type { PlayWindow } from "../MediaPlayer";
import type { TimelineClip, TimelineRange } from "../Timeline";
import { preferredKind } from "./media";
import { initialCuts, MIN_CUT_SECONDS, normalizeUiRemoveSegments, type UiCut } from "./cutUtils";

export type { UiCut } from "./cutUtils";

interface CutSnapshot {
  startText: string;
  endText: string;
  cuts: UiCut[];
}

export interface CutEditorOptions {
  initialPlan: EditPlan;
  media: SermonMediaData;
  sourceDurationSec?: number | null;
  enhanceDefault?: boolean;
}

const JOIN_PREVIEW_SECONDS = 10;
const ARTIFACT_LABELS: Record<string, string> = {
  snippet_start: "Start cut",
  snippet_end: "End cut",
  snippet_ending: "Proposed ending",
};

export function useCutEditor({
  initialPlan,
  media,
  sourceDurationSec,
  enhanceDefault = true,
}: CutEditorOptions) {
  const [startText, setStartText] = useState(formatCut(initialPlan.startSec));
  const [endText, setEndText] = useState(formatCut(initialPlan.endSec));
  const [offsetText, setOffsetText] = useState(initialPlan.offsetSec.toFixed(1));
  const [enhance, setEnhance] = useState(enhanceDefault);
  const [removeSegments, setRemoveSegments] = useState<UiCut[]>(() =>
    initialCuts(initialPlan.removeSegments),
  );
  const [cutPast, setCutPast] = useState<CutSnapshot[]>([]);
  const [cutFuture, setCutFuture] = useState<CutSnapshot[]>([]);
  const [selection, setSelection] = useState<TimelineRange | null>(null);
  const [selected, setSelected] = useState<"start" | "end" | null>(null);
  const [selectedCut, setSelectedCut] = useState<string | null>(null);
  const [removalError, setRemovalError] = useState<string | null>(null);
  const [playWindow, setPlayWindow] = useState<PlayWindow | null>(null);
  const [seek, setSeek] = useState<{ sec: number; n: number } | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [playerKind, setPlayerKind] = useState(() => {
    const preferred = preferredKind(media);
    const preferredEnd = media.byKind[preferred]?.end_sec ?? 0;
    if (media.byKind.source?.available && initialPlan.endSec > preferredEnd + 1) return "source";
    return preferred;
  });
  const startRestore = useRef(initialPlan.startSec);
  const endRestore = useRef(initialPlan.endSec);

  const start = parseCut(startText);
  const end = parseCut(endText);
  const offset = parseCut(offsetText);
  const safeStart = start ?? initialPlan.startSec;
  const safeEnd = end ?? initialPlan.endSec;
  const sourceDuration =
    typeof sourceDurationSec === "number" && Number.isFinite(sourceDurationSec) && sourceDurationSec > 0
      ? sourceDurationSec
      : null;
  const knownDuration = [initialPlan.endSec, ...media.items.map((item) => item.end_sec ?? 0)].reduce(
    (largest, value) => (Number.isFinite(value) && value > largest ? value : largest),
    1,
  );
  const timelineDuration = sourceDuration ?? knownDuration;
  const duration = start !== null && end !== null && end > start ? end - start : null;
  const enabledRemoveSegments = removeSegments.filter((segment) => segment.enabled);
  const removalValidation = useMemo(
    () => normalizeUiRemoveSegments(enabledRemoveSegments, safeStart, safeEnd),
    [enabledRemoveSegments, safeStart, safeEnd],
  );
  const keptDuration =
    duration !== null
      ? Math.max(
          0,
          duration -
            removalValidation.segments.reduce(
              (total, segment) => total + segment.endSec - segment.startSec,
              0,
            ),
        )
      : null;
  const errors = useMemo(() => {
    const list: string[] = [];
    if (start === null) list.push("Start is not a valid time (mm:ss.s or seconds).");
    if (end === null) list.push("End is not a valid time (mm:ss.s or seconds).");
    if (offset === null) list.push("Offset is not a valid number (seconds, ±5).");
    if (start !== null && end !== null && end <= start) list.push("End time must be after the start time.");
    if (offset !== null && (offset < -5 || offset > 5)) list.push("Keep the offset within ±5 seconds.");
    list.push(...removalValidation.errors);
    if (removalError) list.push(removalError);
    return list;
  }, [end, offset, removalError, removalValidation.errors, start]);

  const clips = useMemo<TimelineClip[]>(() => {
    const windowFor = (kind: string, fallbackStart: number, fallbackEnd: number): TimelineClip => {
      const item = media.byKind[kind];
      return {
        id: kind,
        label: ARTIFACT_LABELS[kind] ?? kind,
        startSec: typeof item?.start_sec === "number" ? item.start_sec : fallbackStart,
        endSec: typeof item?.end_sec === "number" ? item.end_sec : fallbackEnd,
      };
    };
    return [
      windowFor("snippet_start", Math.max(safeStart - 10, 0), safeStart + 10),
      windowFor("snippet_end", Math.max(safeEnd - 10, 0), safeEnd + 10),
      windowFor("snippet_ending", Math.max(safeStart, safeEnd - 30), safeEnd),
    ];
  }, [media.byKind, safeEnd, safeStart]);

  const activeKind = media.byKind[playerKind]?.available ? playerKind : preferredKind(media);
  const activeItem = media.byKind[activeKind];
  const requestSeek = (sec: number) => setSeek((previous) => ({ sec, n: (previous?.n ?? 0) + 1 }));
  const playRegion = (_id: string, startSec: number, endSec: number) => {
    requestSeek(startSec);
    setPlayWindow({ startSec, endSec, nonce: (playWindow?.nonce ?? 0) + 1 });
  };
  const playJoin = (segment: RemoveSegment) => {
    const sourceKind = media.byKind.preview?.available
      ? "preview"
      : media.byKind.source?.available
        ? "source"
        : preferredKind(media);
    if (media.byKind[sourceKind]?.available) setPlayerKind(sourceKind);
    const startSec = Math.max(safeStart, segment.startSec - JOIN_PREVIEW_SECONDS);
    const endSec = Math.min(safeEnd, segment.endSec + JOIN_PREVIEW_SECONDS);
    requestSeek(startSec);
    setPlayWindow({
      startSec,
      endSec,
      nonce: (playWindow?.nonce ?? 0) + 1,
      jumpAtSec: segment.startSec,
      jumpToSec: segment.endSec,
    });
  };

  const cutSnapshot = (): CutSnapshot => ({
    startText,
    endText,
    cuts: removeSegments.map((segment) => ({ ...segment })),
  });
  const applyCutSnapshot = (snapshot: CutSnapshot) => {
    setStartText(snapshot.startText);
    setEndText(snapshot.endText);
    setRemoveSegments(snapshot.cuts.map((segment) => ({ ...segment })));
    setSelection(null);
    setSelectedCut(null);
    setRemovalError(null);
  };
  const commitCut = (patch: Partial<CutSnapshot>) => {
    setCutPast((past) => [...past.slice(-49), cutSnapshot()]);
    setCutFuture([]);
    if (patch.startText !== undefined) setStartText(patch.startText);
    if (patch.endText !== undefined) setEndText(patch.endText);
    if (patch.cuts !== undefined) setRemoveSegments(patch.cuts);
  };
  const undoCut = () => {
    const previous = cutPast[cutPast.length - 1];
    if (!previous) return;
    setCutFuture((future) => [cutSnapshot(), ...future].slice(0, 50));
    setCutPast((past) => past.slice(0, -1));
    applyCutSnapshot(previous);
  };
  const redoCut = () => {
    const next = cutFuture[0];
    if (!next) return;
    setCutPast((past) => [...past.slice(-49), cutSnapshot()]);
    setCutFuture((future) => future.slice(1));
    applyCutSnapshot(next);
  };
  const toggleCut = (index: number, enabled: boolean) => {
    if (!enabled) {
      setSelectedCut(null);
      setSelection(null);
    }
    commitCut({
      cuts: removeSegments.map((segment, currentIndex) =>
        currentIndex === index ? { ...segment, enabled } : segment,
      ),
    });
  };
  const undoRemoval = (index: number) => {
    commitCut({ cuts: removeSegments.filter((_, currentIndex) => currentIndex !== index) });
    setSelectedCut(null);
    setSelection(null);
    setRemovalError(null);
  };
  const addRemoval = () => {
    if (!selection) return;
    if (selection.endSec - selection.startSec < MIN_CUT_SECONDS) {
      setRemovalError("Choose a range of at least 0.25 seconds.");
      return;
    }
    const next = normalizeUiRemoveSegments(
      [...enabledRemoveSegments, selection],
      safeStart,
      safeEnd,
    );
    if (next.errors.length > 0) {
      setRemovalError(next.errors[0]);
      return;
    }
    setRemovalError(null);
    commitCut({
      cuts: [
        ...removeSegments.filter((segment) => !segment.enabled),
        ...next.segments.map((segment) => ({ ...segment, enabled: true })),
      ],
    });
    setSelection(null);
  };
  const toggleStartCut = (enabled: boolean) => {
    if (!enabled) {
      setSelectedCut(null);
      setSelection(null);
      if (safeStart > 0) startRestore.current = safeStart;
      commitCut({ startText: formatCut(0) });
      return;
    }
    const restore = startRestore.current > 0 ? startRestore.current : initialPlan.startSec;
    commitCut({ startText: formatCut(restore > 0 ? restore : 0.5) });
  };
  const toggleEndCut = (enabled: boolean) => {
    if (!enabled) {
      setSelectedCut(null);
      setSelection(null);
      endRestore.current = safeEnd;
      commitCut({ endText: formatCut(timelineDuration) });
      return;
    }
    const restore = endRestore.current > 0 ? endRestore.current : initialPlan.endSec;
    commitCut({ endText: formatCut(restore > 0 ? restore : timelineDuration) });
  };
  const selectCut = (id: string | null) => {
    setSelectedCut(id);
    if (id === "start" || id === "end") {
      setSelected(id);
      setSelection(null);
      return;
    }
    setSelected(null);
    const index = id?.startsWith("interior-") ? Number(id.replace("interior-", "")) : -1;
    const segment = removeSegments[index];
    setSelection(segment ? { startSec: segment.startSec, endSec: segment.endSec } : null);
  };
  const reset = () => {
    setStartText(formatCut(initialPlan.startSec));
    setEndText(formatCut(initialPlan.endSec));
    setOffsetText(initialPlan.offsetSec.toFixed(1));
    setRemoveSegments(initialCuts(initialPlan.removeSegments));
    setCutPast([]);
    setCutFuture([]);
    setSelection(null);
    setSelectedCut(null);
    setRemovalError(null);
  };
  const dirty =
    start !== initialPlan.startSec ||
    end !== initialPlan.endSec ||
    offset !== initialPlan.offsetSec ||
    removeSegments.length !== (initialPlan.removeSegments ?? []).length ||
    removeSegments.some(
      (segment, index) =>
        !segment.enabled ||
        segment.startSec !== initialPlan.removeSegments?.[index]?.startSec ||
        segment.endSec !== initialPlan.removeSegments?.[index]?.endSec,
    );
  const applyRequest = (renderOnly: boolean, generateMetadata: boolean) => ({
    start: start ?? initialPlan.startSec,
    end: end ?? initialPlan.endSec,
    audio_offset: offset ?? initialPlan.offsetSec,
    remove_segments: removalValidation.segments.map((segment) => ({
      start_sec: segment.startSec,
      end_sec: segment.endSec,
    })),
    render_only: renderOnly,
    enhance_audio: enhance,
    generate_metadata: generateMetadata,
  });

  return {
    startText, endText, offsetText, setStartText, setEndText, setOffsetText, offset,
    safeStart, safeEnd, duration, timelineDuration, keptDuration, enabledRemoveSegments,
    removeSegments, selection, setSelection, selected, setSelected, selectedCut, selectCut,
    removalError, setRemovalError, playWindow, setPlayWindow, seek, requestSeek, playhead,
    setPlayhead, playerKind, setPlayerKind, activeKind, activeItem, clips, enhance, setEnhance,
    playRegion, playJoin, addRemoval, undoRemoval, cutPast, cutFuture, toggleCut, undoCut,
    redoCut, toggleStartCut, toggleEndCut, reset, dirty, errors, applyRequest,
  };
}

export type CutEditor = ReturnType<typeof useCutEditor>;
