import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EditPlan } from "../../mock/data";
import type { SermonMediaData } from "../../api/hooks";
import { useCutEditor } from "./useCutEditor";

const plan: EditPlan = {
  sermonId: "s-1",
  status: "pending_review",
  revision: 1,
  revisionsTotal: 1,
  confidence: 87,
  qa: "Pass",
  evidence: "",
  startSec: 10,
  endSec: 1000,
  removeSegments: [{ startSec: 100, endSec: 130 }],
  offsetSec: 0,
  detectionStatus: "ok",
  reasoning: "",
  notes: "",
};

const media: SermonMediaData = {
  items: [],
  byKind: {},
  primary: null,
  audio: null,
  isLoading: false,
  error: null,
  retry: () => {},
};

describe("useCutEditor", () => {
  it("restores a boundary trim and shares the selected interior cut", () => {
    const { result } = renderHook(() => useCutEditor({ initialPlan: plan, media }));

    act(() => result.current.toggleStartCut(false));
    expect(result.current.safeStart).toBe(0);
    act(() => result.current.undoCut());
    expect(result.current.safeStart).toBe(10);

    act(() => result.current.selectCut("interior-0"));
    expect(result.current.selectedCut).toBe("interior-0");
    expect(result.current.selection).toEqual({ startSec: 100, endSec: 130 });
  });

  it("builds an apply request from enabled cuts only", () => {
    const { result } = renderHook(() => useCutEditor({ initialPlan: plan, media }));
    act(() => result.current.toggleCut(0, false));

    expect(result.current.applyRequest(false, true)).toMatchObject({
      start: 10,
      end: 1000,
      audio_offset: 0,
      render_only: false,
      generate_metadata: true,
      remove_segments: [],
    });
  });
});
