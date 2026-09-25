import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Timeline, timelinePercent, timelineSpan, type TimelineRange } from "./Timeline";

const clips = [
  { id: "snippet_start", label: "Start cut", startSec: 0, endSec: 18.5 },
  { id: "snippet_end", label: "End cut", startSec: 2412.3, endSec: 2432.3 },
  { id: "snippet_ending", label: "Proposed ending", startSec: 2482.3, endSec: 2512.3 },
];

function baseProps() {
  return {
    durationSec: 2512.3,
    startSec: 8.5,
    endSec: 2512.3,
    offsetSec: 0.4,
    endingSec: 2512.3,
    clips,
  };
}

describe("Timeline", () => {
  it("derives region positions from the plan seconds", () => {
    render(<Timeline {...baseProps()} />);

    const keep = screen.getByTestId("timeline-region-keep");
    expect(keep.getAttribute("data-start-sec")).toBe("8.5");
    expect(keep.getAttribute("data-end-sec")).toBe("2512.3");
    expect(parseFloat(keep.style.left)).toBeCloseTo((8.5 / 2512.3) * 100, 4);
    expect(parseFloat(keep.style.width)).toBeCloseTo(((2512.3 - 8.5) / 2512.3) * 100, 4);

    const before = screen.getByTestId("timeline-region-cut-before");
    expect(parseFloat(before.style.width)).toBeCloseTo((8.5 / 2512.3) * 100, 4);

    const ending = screen.getByTestId("timeline-region-ending");
    expect(parseFloat(ending.style.left)).toBeCloseTo(100, 4);

    const tick = screen.getByTestId("timeline-clip-snippet_start");
    expect(tick.getAttribute("data-start-sec")).toBe("0");
    expect(tick.getAttribute("data-end-sec")).toBe("18.5");
  });

  it("moves the start marker when the start seconds change", () => {
    const { rerender } = render(<Timeline {...baseProps()} />);
    const before = screen.getByTestId("timeline-region-keep").style.left;

    rerender(<Timeline {...baseProps()} startSec={900} />);
    const after = screen.getByTestId("timeline-region-keep").style.left;
    expect(after).not.toBe(before);
    expect(parseFloat(after)).toBeCloseTo((900 / 2512.3) * 100, 4);
    expect(screen.getByTestId("timeline-handle-start").getAttribute("aria-valuenow")).toBe("900");
  });

  it("emits a seek with the region time when a region is clicked", async () => {
    const user = userEvent.setup();
    const onSeek = vi.fn();
    render(<Timeline {...baseProps()} onSeek={onSeek} />);

    await user.click(screen.getByTestId("timeline-region-keep"));
    expect(onSeek).toHaveBeenCalledWith(8.5, "keep");

    await user.click(screen.getByTestId("timeline-clip-snippet_end"));
    expect(onSeek).toHaveBeenCalledWith(2412.3, "snippet_end");
  });

  it("plays a clip window from its region chip", async () => {
    const user = userEvent.setup();
    const onPlayRegion = vi.fn();
    render(<Timeline {...baseProps()} onPlayRegion={onPlayRegion} />);

    await user.click(screen.getByTestId("timeline-clip-snippet_ending"));
    expect(onPlayRegion).toHaveBeenCalledWith("snippet_ending", 2482.3, 2512.3);
  });

  it("nudges the selected handle with the arrow keys", async () => {
    const user = userEvent.setup();
    const onChangeStart = vi.fn();
    const onChangeEnd = vi.fn();
    render(<Timeline {...baseProps()} onChangeStart={onChangeStart} onChangeEnd={onChangeEnd} />);

    const start = screen.getByTestId("timeline-handle-start");
    start.focus();
    await user.keyboard("{ArrowRight}");
    expect(onChangeStart).toHaveBeenCalledWith(9.5);

    await user.keyboard("{Shift>}{ArrowRight}{/Shift}");
    expect(onChangeStart).toHaveBeenCalledWith(18.5);

    const end = screen.getByTestId("timeline-handle-end");
    end.focus();
    await user.keyboard("{ArrowLeft}");
    expect(onChangeEnd).toHaveBeenCalledWith(2511.3);
  });

  it("does not let either handle cross the other handle", async () => {
    const user = userEvent.setup();
    const onChangeStart = vi.fn();
    const onChangeEnd = vi.fn();
    render(
      <Timeline
        {...baseProps()}
        startSec={20}
        endSec={20.5}
        onChangeStart={onChangeStart}
        onChangeEnd={onChangeEnd}
      />,
    );

    screen.getByTestId("timeline-handle-start").focus();
    await user.keyboard("{ArrowRight}");
    expect(onChangeStart).toHaveBeenCalledWith(20.4);

    screen.getByTestId("timeline-handle-end").focus();
    await user.keyboard("{ArrowLeft}");
    expect(onChangeEnd).toHaveBeenCalledWith(20.1);
  });

  it("keeps keyboard nudges inside the source and shared handle bounds", async () => {
    const user = userEvent.setup();
    const onChangeStart = vi.fn();
    const onChangeEnd = vi.fn();
    const { rerender } = render(
      <Timeline
        {...baseProps()}
        durationSec={3000}
        startSec={0}
        endSec={0.05}
        onChangeStart={onChangeStart}
        onChangeEnd={onChangeEnd}
      />,
    );

    screen.getByTestId("timeline-handle-start").focus();
    await user.keyboard("{ArrowRight}");
    expect(onChangeStart).toHaveBeenCalledWith(0);

    rerender(
      <Timeline
        {...baseProps()}
        durationSec={3000}
        startSec={100}
        endSec={2999.5}
        onChangeStart={onChangeStart}
        onChangeEnd={onChangeEnd}
      />,
    );
    screen.getByTestId("timeline-handle-end").focus();
    await user.keyboard("{ArrowRight}");
    expect(onChangeEnd).toHaveBeenCalledWith(3000);
  });

  it("clamps the start bound when an incoming end exceeds the source duration", async () => {
    const user = userEvent.setup();
    const onChangeStart = vi.fn();
    render(
      <Timeline
        {...baseProps()}
        durationSec={3000}
        startSec={2999}
        endSec={3500}
        onChangeStart={onChangeStart}
      />,
    );

    screen.getByTestId("timeline-handle-start").focus();
    await user.keyboard("{ArrowRight}");
    expect(onChangeStart).toHaveBeenCalledWith(2999.9);
  });

  it("exposes slider semantics on both handles", () => {
    render(<Timeline {...baseProps()} />);
    const start = screen.getByRole("slider", { name: "Keep start" });
    const end = screen.getByRole("slider", { name: "Keep end" });
    expect(start.getAttribute("aria-valuenow")).toBe("8.5");
    expect(end.getAttribute("aria-valuenow")).toBe("2512.3");
    expect(start.getAttribute("aria-valuemax")).toBe("2512.2");
    expect(end.getAttribute("aria-valuemin")).toBe("8.6");
  });

  it("gives each drag handle a 44px-wide touch target", () => {
    render(<Timeline {...baseProps()} />);
    for (const id of ["timeline-handle-start", "timeline-handle-end"]) {
      expect(screen.getByTestId(id).className).toContain("w-11");
    }
  });

  it("keeps endpoint handle targets outside the track clipping boundary", () => {
    render(<Timeline {...baseProps()} />);
    expect(screen.getByTestId("timeline-track").className).toContain("overflow-visible");
  });

  it("uses the supplied duration as the stable scale", () => {
    expect(timelineSpan(2400, 1000, 1000, clips)).toBe(2400);
  });

  it("map helpers clamp to the span", () => {
    expect(timelineSpan(100, 90, 95, clips)).toBe(100);
    expect(timelinePercent(-5, 100)).toBe(0);
    expect(timelinePercent(150, 100)).toBe(100);
    expect(timelinePercent(50, 100)).toBe(50);
  });

  it("maps a pointer drag to a new start second", () => {
    const onChangeStart = vi.fn();
    render(<Timeline {...baseProps()} startSec={100} endSec={1000} onChangeStart={onChangeStart} />);

    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      right: 1000,
      bottom: 56,
      width: 1000,
      height: 56,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);

    const handle = screen.getByTestId("timeline-handle-start");
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 100 });
    fireEvent.pointerMove(track, { pointerId: 1, clientX: 400 });
    expect(onChangeStart).toHaveBeenCalled();
    const calls = onChangeStart.mock.calls;
    const last = calls[calls.length - 1]?.[0] as number;
    expect(last).toBeGreaterThan(900);
    expect(last).toBeLessThan(1000);
    fireEvent.pointerUp(track);
  });

  it("keeps vertical panning available on the track", () => {
    render(<Timeline {...baseProps()} />);
    const track = screen.getByTestId("timeline-track");
    expect(track.className).toContain("touch-pan-y");
  });

  it("renders removals separately from trims and counts them", () => {
    render(
      <Timeline
        {...baseProps()}
        removeSegments={[{ startSec: 900, endSec: 930 }]}
      />,
    );

    const removal = screen.getByTestId("timeline-removal-0");
    expect(removal.getAttribute("data-region")).toBe("removal");
    expect(removal.className).toContain("danger");
    expect(screen.getByTestId("timeline-labels").textContent).toContain("1 cut removed");
  });

  it("selects an interior range and exposes keyboard nudging handles", async () => {
    const user = userEvent.setup();

    function Harness() {
      const [selection, setSelection] = useState<TimelineRange | null>(null);
      return (
        <Timeline
          {...baseProps()}
          selection={selection}
          onChangeSelection={setSelection}
        />
      );
    }

    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Select a range to cut" }));

    expect(screen.getByRole("slider", { name: "Removal selection start" })).toBeTruthy();
    expect(screen.getByRole("slider", { name: "Removal selection end" })).toBeTruthy();

    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      right: 1000,
      bottom: 56,
      width: 1000,
      height: 56,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
    const surface = screen.getByTestId("timeline-selection-surface");
    fireEvent.pointerDown(surface, { pointerId: 1, clientX: 200 });
    fireEvent.pointerMove(track, { pointerId: 1, clientX: 400 });
    fireEvent.pointerUp(track);

    expect(screen.getByRole("button", { name: "Select a range to cut" })).toBeTruthy();
    expect(screen.getByTestId("timeline-selection")).toBeTruthy();
    const startHandle = screen.getByRole("slider", { name: "Removal selection start" });
    const endHandle = screen.getByRole("slider", { name: "Removal selection end" });
    expect(startHandle).toBeTruthy();
    expect(endHandle).toBeTruthy();
    expect(startHandle.tabIndex).toBe(0);
    expect(endHandle.tabIndex).toBe(0);

    const beforeNudge = startHandle.getAttribute("aria-valuenow");
    startHandle.focus();
    await user.keyboard("{ArrowRight}");
    expect(startHandle.getAttribute("aria-valuenow")).not.toBe(beforeNudge);
  });
});
