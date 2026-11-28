import type { ReactNode } from "react";
import type { SermonMediaData } from "../../api/hooks";
import type { EditPlan } from "../../mock/data";
import { formatDuration } from "../../utils/format";
import { formatCut } from "../../utils/time";
import { MediaPlayer } from "../MediaPlayer";
import { Timeline } from "../Timeline";
import { Button, Icon, Menu, Switch, buttonClass } from "../ui";
import { PlanSummary } from "./PlanSummary";
import { useCutEditor, type CutEditor } from "./useCutEditor";

interface ReviewPlayerProps {
  sermonId: string;
  plan: EditPlan;
  media: SermonMediaData;
  isLive: boolean;
  sourceDurationSec?: number | null;
  statusChip?: ReactNode;
  enhanceDefault?: boolean;
  readOnly?: boolean;
  applying?: boolean;
  restoring?: boolean;
  onRestore?: () => void;
  children?: (editor: CutEditor) => ReactNode;
}

interface CutRow {
  id: string;
  testId: string;
  durationTestId: string;
  toggleTestId: string;
  label: string;
  typeLabel: string;
  startSec: number;
  endSec: number;
  enabled: boolean;
  toggleLabel: string;
  onToggle: (enabled: boolean) => void;
  onPreview?: () => void;
}

const chipButtonClass =
  "inline-flex min-h-[44px] items-center rounded-md border border-line bg-raised px-3 text-xs font-semibold text-mist transition-[background-color,border-color,color,filter] duration-150 hover:border-muted hover:brightness-110 active:brightness-95";

export function ReviewPlayer({
  sermonId,
  plan,
  media,
  isLive,
  sourceDurationSec,
  statusChip,
  enhanceDefault,
  readOnly = false,
  applying = false,
  restoring = false,
  onRestore,
  children,
}: ReviewPlayerProps) {
  const editor = useCutEditor({ initialPlan: plan, media, sourceDurationSec, enhanceDefault });
  const rows: CutRow[] = [
    {
      id: "start",
      testId: "removal-edge-start",
      durationTestId: "removal-duration-start",
      toggleTestId: "cut-toggle-start",
      label: "Opening trim",
      typeLabel: "Boundary",
      startSec: 0,
      endSec: editor.safeStart,
      enabled: editor.safeStart > 0,
      toggleLabel: "Include the opening trim",
      onToggle: editor.toggleStartCut,
    },
    {
      id: "end",
      testId: "removal-edge-end",
      durationTestId: "removal-duration-end",
      toggleTestId: "cut-toggle-end",
      label: "Closing trim",
      typeLabel: "Boundary",
      startSec: editor.safeEnd,
      endSec: editor.timelineDuration,
      enabled: editor.timelineDuration > editor.safeEnd,
      toggleLabel: "Include the closing trim",
      onToggle: editor.toggleEndCut,
    },
    ...editor.removeSegments.map((segment, index) => ({
      id: `interior-${index}`,
      testId: `removal-item-${index}`,
      durationTestId: `removal-duration-${index}`,
      toggleTestId: `cut-toggle-${index}`,
      label: `Cut ${index + 1}`,
      typeLabel: "Interior",
      startSec: segment.startSec,
      endSec: segment.endSec,
      enabled: segment.enabled,
      toggleLabel: `Include cut ${index + 1} in the plan`,
      onToggle: (enabled: boolean) => editor.toggleCut(index, enabled),
      onPreview: () => editor.playJoin(segment),
    })),
  ].filter((row) => row.endSec > row.startSec);

  return (
    <>
      <PlanSummary
        plan={plan}
        duration={editor.duration}
        keptDuration={editor.keptDuration}
        timelineDuration={editor.timelineDuration}
        safeStart={editor.safeStart}
        safeEnd={editor.safeEnd}
        enabledRemoveSegments={editor.enabledRemoveSegments}
        statusChip={statusChip}
        enhance={readOnly ? undefined : editor.enhance}
        onEnhanceChange={readOnly ? undefined : editor.setEnhance}
      >
        {plan.detectionStatus === "unavailable" ? (
          <div role="alert" className="rounded-md border border-danger bg-ink p-3 text-sm text-danger">
            <span className="font-semibold">Cut detection failed.</span> Enter the start and end, or re-run detection.
          </div>
        ) : null}
      </PlanSummary>
      <section id="player-plan" aria-label="Playback and cut plan" className="rounded-lg border border-line bg-surface shadow-sm">
        <div className="flex min-w-0 flex-col gap-3 p-4">
          {isLive && media.error ? (
            <div role="alert" className="flex flex-wrap items-center gap-2 rounded-md border border-danger bg-ink p-3 text-sm text-danger">
              <span className="min-w-0 flex-1">{media.error}</span>
              <Button onClick={media.retry}>Retry media</Button>
            </div>
          ) : null}
          {isLive && !media.error ? (
            <MediaPlayer
              sermonId={sermonId}
              kind={editor.activeKind}
              contentType={editor.activeItem?.content_type}
              available={!!editor.activeItem?.available}
              emptyMessage="No playable media for this teaching yet."
              markers={[{ atSec: editor.safeStart, label: "Start" }, { atSec: editor.safeEnd, label: "End" }]}
              markerJumps={false}
              seekToSec={editor.seek?.sec ?? null}
              seekNonce={editor.seek?.n}
              playWindow={editor.playWindow}
              offsetSec={readOnly ? 0 : editor.offset ?? plan.offsetSec}
              syncStartSec={editor.safeStart}
              onTime={editor.setPlayhead}
            />
          ) : isLive ? null : (
            <p className="rounded-md border border-dashed border-line bg-ink px-3 py-6 text-center text-sm text-muted">Preview available in the live console.</p>
          )}
          {!readOnly ? (
            <Timeline
              sermonId={sermonId}
              durationSec={editor.timelineDuration}
              startSec={editor.safeStart}
              endSec={editor.safeEnd}
              offsetSec={editor.offset ?? plan.offsetSec}
              endingSec={editor.safeEnd}
              currentSec={editor.playhead}
              clips={editor.clips}
              removeSegments={editor.enabledRemoveSegments}
              onRemoveSegment={(index) => {
                const segment = editor.enabledRemoveSegments[index];
                const fullIndex = editor.removeSegments.indexOf(segment);
                if (fullIndex >= 0) editor.undoRemoval(fullIndex);
              }}
              selection={editor.selection}
              onChangeSelection={(next) => { editor.setSelection(next); editor.setRemovalError(null); }}
              selected={editor.selected}
              selectedCut={editor.selectedCut}
              onSelect={(handle) => editor.selectCut(handle)}
              onSelectCut={editor.selectCut}
              onChangeStart={(sec) => { editor.setStartText(formatCut(sec)); editor.selectCut("start"); editor.setRemovalError(null); }}
              onChangeEnd={(sec) => { editor.setEndText(formatCut(sec)); editor.selectCut("end"); editor.setRemovalError(null); }}
              onSeek={(sec, regionId) => {
                editor.requestSeek(sec);
                if (regionId === "keep" || regionId.startsWith("snippet_")) {
                  const clip = editor.clips.find((item) => item.id === regionId);
                  if (clip) editor.playRegion(clip.id, clip.startSec, clip.endSec);
                }
              }}
              onPlayRegion={(regionId, startSec, endSec) => {
                if (regionId.startsWith("removal_join_")) {
                  const index = Number(regionId.replace("removal_join_", ""));
                  const segment = editor.enabledRemoveSegments[index];
                  if (segment) editor.playJoin(segment);
                  return;
                }
                editor.playRegion(regionId, startSec, endSec);
              }}
            />
          ) : null}
          {!readOnly && editor.selection ? (
            <section data-testid="removal-selection-panel" aria-labelledby="removal-selection-heading" className="rounded-md border border-warn bg-ink p-3 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 id="removal-selection-heading" className="text-sm font-semibold">Selected range</h2>
                  <p data-testid="removal-selection-range" className="mt-1 font-mono text-sm text-mist">{formatCut(editor.selection.startSec)} to {formatCut(editor.selection.endSec)}</p>
                  <p className="mt-1 text-xs text-muted">Nudge either handle with the arrow keys, then remove this range.</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={editor.addRemoval}>Cut this out</Button>
                  <Button onClick={() => { editor.setSelection(null); editor.setRemovalError(null); }}>Cancel</Button>
                </div>
              </div>
              {editor.removalError ? <p role="alert" className="mt-2 text-xs text-danger">{editor.removalError}</p> : null}
            </section>
          ) : null}
          <section data-testid="removal-list" aria-labelledby="cut-plan-heading" className="rounded-md border border-line bg-ink p-3 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 id="cut-plan-heading" className="text-sm font-semibold">Cut plan</h2>
                <p className="mt-1 text-xs text-muted">{readOnly ? "Included cuts in this proposal." : "Preview each join, switch a cut off to keep it, then approve the plan."}</p>
              </div>
              {!readOnly ? (
                <div className="flex items-center gap-2">
                  <Button variant="ghost" onClick={editor.undoCut} disabled={editor.cutPast.length === 0} aria-label="Undo cut edit" data-testid="cut-undo">Undo</Button>
                  <Button variant="ghost" onClick={editor.redoCut} disabled={editor.cutFuture.length === 0} aria-label="Redo cut edit" data-testid="cut-redo">Redo</Button>
                </div>
              ) : null}
            </div>
            <div data-testid="cut-table" className="mt-3">
              <ul className="flex flex-col">
                {rows.map((row) => (
                  <li key={row.id} data-testid={row.testId} aria-current={editor.selectedCut === row.id ? "true" : undefined} className={`flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 border-t border-line py-2 first:border-t-0 ${editor.selectedCut === row.id ? "bg-warn/10" : ""}`}>
                    <button type="button" aria-label={`Select ${row.label}`} aria-pressed={editor.selectedCut === row.id} onClick={() => editor.selectCut(row.id)} className="min-h-[44px] min-w-0 flex-1 text-left">
                      <span className="flex flex-wrap items-baseline gap-x-2"><span className="text-sm font-medium">{row.label}</span><span className="text-xs text-muted">{row.typeLabel}</span></span>
                      {!readOnly ? <span className="block font-mono text-xs text-muted">{formatCut(row.startSec)} – {formatCut(row.endSec)} · <span data-testid={row.durationTestId}>{formatDuration(row.endSec - row.startSec)}</span></span> : <span className="block text-xs text-muted">{formatDuration(row.endSec - row.startSec)}</span>}
                    </button>
                    {!readOnly ? (
                      <>
                        <Switch checked={row.enabled} onChange={row.onToggle} label={row.toggleLabel} testId={row.toggleTestId} />
                        <Menu
                          label={`Actions for ${row.label}`}
                          trigger={<Icon name="more" className="h-4 w-4" />}
                          triggerClassName={buttonClass("secondary", "w-11 px-0")}
                          triggerTestId={`cut-menu-${row.id}`}
                          menuTestId={`cut-menu-panel-${row.id}`}
                          menuClassName="w-56"
                          items={[
                            ...(row.onPreview ? [{ label: "Preview join", onSelect: row.onPreview, testId: `preview-join-${row.id}` }] : []),
                            ...(row.id === "start" ? [{ label: "Restore start", onSelect: () => editor.toggleStartCut(true), disabled: row.enabled, testId: "restore-start" }] : []),
                            ...(row.id === "end" ? [{ label: "Restore end", onSelect: () => editor.toggleEndCut(true), disabled: row.enabled, testId: "restore-end" }] : []),
                            { label: "Delete cut", onSelect: () => row.onToggle(false), disabled: !row.enabled, testId: `delete-cut-${row.id}` },
                          ]}
                        />
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
            <p className="mt-3 border-t border-line pt-3 text-xs text-muted">{editor.enabledRemoveSegments.filter((segment) => segment.endSec > segment.startSec).length} interior cuts included</p>
          </section>
          {!readOnly ? (
            <>
              <div className="flex flex-wrap gap-2" aria-label="Clip previews">
                {editor.clips.map((clip) => (
                  <button key={clip.id} type="button" data-testid={`region-chip-${clip.id}`} onClick={() => editor.playRegion(clip.id, clip.startSec, clip.endSec)} className={chipButtonClass}>Play {clip.label}</button>
                ))}
              </div>
              <details className="rounded-md border border-line bg-ink p-3">
                <summary className="cursor-pointer px-1 text-sm font-semibold">Exact times</summary>
                <fieldset className="mt-2">
                  <legend className="px-1 text-sm font-semibold">Start &amp; end</legend>
                  <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
                    {[
                      { id: "start", label: "Start (mm:ss.s or seconds)", value: editor.startText, set: editor.setStartText },
                      { id: "end", label: "End (mm:ss.s or seconds)", value: editor.endText, set: editor.setEndText },
                      { id: "offset", label: "Audio offset, s (+ delays, - advances)", value: editor.offsetText, set: editor.setOffsetText },
                    ].map((field) => (
                      <div key={field.id}>
                        <label htmlFor={`cut-${field.id}`} className="text-xs font-medium text-muted">{field.label}</label>
                        <input id={`cut-${field.id}`} value={field.value} onChange={(event) => field.set(event.target.value)} inputMode="decimal" step={field.id === "offset" ? 0.1 : undefined} className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 font-mono text-sm text-mist" />
                      </div>
                    ))}
                  </div>
                  {editor.errors.length > 0 ? <ul className="mt-2 flex flex-col gap-1" role="alert">{editor.errors.map((error) => <li key={error} className="text-xs text-danger">{error}</li>)}</ul> : null}
                </fieldset>
              </details>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={editor.reset} disabled={!editor.dirty || applying}>Reset to plan values</Button>
                {onRestore ? <Button onClick={onRestore} disabled={restoring || applying} title="Discard the applied cut and keep the unedited recording.">{restoring ? "Restoring…" : "Restore original"}</Button> : null}
              </div>
            </>
          ) : null}
        </div>
      </section>
      {children?.(editor)}
    </>
  );
}
