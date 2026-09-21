import { useMemo, useState } from "react";
import { isLive, writeApi } from "../api/client";
import { useSermonMedia, type SermonMediaData } from "../api/hooks";
import type { EditPlan, PlanStatus } from "../mock/data";
import { formatCut, parseCut } from "../utils/time";
import { MediaPlayer } from "./MediaPlayer";
import { Button, Card, Chip, ConfirmDialog } from "./ui";

const planStatusLabel: Record<PlanStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  applied_local: "Applied — local",
  processed: "Processed",
  superseded: "Superseded",
};

const planStatusTone: Record<PlanStatus, string> = {
  draft: "neutral",
  pending_review: "warn",
  applied_local: "info",
  processed: "ok",
  superseded: "neutral",
};

function CutPreview({
  label,
  kind,
  atSec,
  note,
  sermonId,
  media,
  onSeek,
}: {
  label: string;
  kind: string;
  atSec: number;
  note: string;
  sermonId: string;
  media: SermonMediaData;
  onSeek: (sec: number) => void;
}) {
  const item = media.byKind[kind];
  const available = isLive && !!item?.available;
  const fallbackKind = media.byKind["keeper"]?.available
    ? "keeper"
    : media.byKind["processed"]?.available
      ? "processed"
      : media.byKind["source"]?.available
        ? "source"
        : null;
  const fallbackItem = fallbackKind ? media.byKind[fallbackKind] : undefined;
  const fallbackAvailable = isLive && !!fallbackItem?.available;
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1 rounded-md border border-line bg-ink p-3">
      {available ? (
        <MediaPlayer
          sermonId={sermonId}
          kind={kind}
          contentType={item?.content_type}
          available
          label={label}
        />
      ) : fallbackAvailable && fallbackKind ? (
        <MediaPlayer
          sermonId={sermonId}
          kind={fallbackKind}
          contentType={fallbackItem?.content_type}
          available
          seekToSec={atSec}
          label={`Seek · ${formatCut(atSec)}`}
        />
      ) : (
        <button
          type="button"
          onClick={() => onSeek(atSec)}
          className="flex min-h-[64px] w-full items-center justify-center rounded bg-raised px-2 text-center font-mono text-xs text-muted transition-colors hover:text-mist"
        >
          {isLive ? "Snippet not rendered yet" : "Preview available in the live console"} · jump to{" "}
          {formatCut(atSec)}
        </button>
      )}
      <p className="text-xs font-semibold">{label}</p>
      <p className="font-mono text-xs text-muted">{note}</p>
    </div>
  );
}

interface ReviewPanelProps {
  plan: EditPlan;
  sermonId: string;
  sermonTitle: string;
  onToast: (msg: string) => void;
}

export function ReviewPanel({ plan: initial, sermonId, sermonTitle, onToast }: ReviewPanelProps) {
  const [plan, setPlan] = useState(initial);
  const [startText, setStartText] = useState(formatCut(initial.startSec));
  const [endText, setEndText] = useState(formatCut(initial.endSec));
  const [offsetText, setOffsetText] = useState(initial.offsetSec.toFixed(1));
  const [target, setTarget] = useState<"render" | "upload">("render");
  const [applying, setApplying] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const media = useSermonMedia(sermonId, isLive);
  const [seek, setSeek] = useState<{ sec: number; n: number } | null>(null);

  const requestSeek = (sec: number) =>
    setSeek((previous) => ({ sec, n: (previous?.n ?? 0) + 1 }));
  const reviewKind = media.byKind["source"]?.available
    ? "source"
    : media.byKind["processed"]?.available
      ? "processed"
      : "keeper";
  const reviewItem = media.byKind[reviewKind];

  const start = parseCut(startText);
  const end = parseCut(endText);
  const offset = parseCut(offsetText);

  const errors = useMemo(() => {
    const list: string[] = [];
    if (start === null) list.push("Start is not a valid time (mm:ss.s or seconds).");
    if (end === null) list.push("End is not a valid time (mm:ss.s or seconds).");
    if (offset === null) list.push("Offset is not a valid number (seconds, ±5).");
    if (start !== null && end !== null && end <= start) list.push("End must be after start.");
    if (offset !== null && (offset < -5 || offset > 5)) list.push("Offset must be within ±5 seconds.");
    return list;
  }, [start, end, offset]);

  const duration = start !== null && end !== null && end > start ? end - start : null;

  const reset = () => {
    setStartText(formatCut(plan.startSec));
    setEndText(formatCut(plan.endSec));
    setOffsetText(plan.offsetSec.toFixed(1));
  };

  const dirty =
    start !== plan.startSec || end !== plan.endSec || offset !== plan.offsetSec;

  const approve = () => {
    if (errors.length > 0 || applying) return;
    if (isLive) {
      setApplying(true);
      void writeApi
        .applyPlan(sermonId, {
          start: start ?? plan.startSec,
          end: end ?? plan.endSec,
          audio_offset: offset ?? plan.offsetSec,
          render_only: target === "render",
        })
        .then(() => {
          setApplying(false);
          onToast(
            target === "render"
              ? "Plan approved, render queued."
              : "Plan approved, render + upload queued.",
          );
        })
        .catch((e) => {
          setApplying(false);
          const msg = (e as Error).message;
          onToast(/409/.test(msg) ? "A job is already running for this teaching." : `Could not queue: ${msg}`);
        });
      return;
    }
    setApplying(true);
    window.setTimeout(() => {
      setApplying(false);
      setHistory((h) => [...h, `revision ${plan.revision} superseded`]);
      setPlan((p) => ({
        ...p,
        status: "applied_local",
        revision: p.revision + 1,
        revisionsTotal: p.revisionsTotal + 1,
        startSec: start ?? p.startSec,
        endSec: end ?? p.endSec,
        offsetSec: offset ?? p.offsetSec,
      }));
      onToast(
        target === "render"
          ? `Plan approved, render queued (mock). Previous revision superseded.`
          : `Plan approved, render + upload queued (mock). Previous revision superseded.`,
      );
    }, 1200);
  };

  return (
    <section aria-labelledby="review-h" className="flex flex-col gap-3">
      <h2 id="review-h" className="text-lg font-semibold">Review auto-edit plan</h2>
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={planStatusTone[plan.status]}>{planStatusLabel[plan.status]}</Chip>
          <span className="font-mono text-xs text-muted">
            revision {plan.revision} of {plan.revisionsTotal}
          </span>
          <span className="font-mono text-xs text-muted">confidence {plan.confidence}%</span>
          <Chip tone={plan.qa === "Pass" ? "ok" : "warn"}>QA: {plan.qa}</Chip>
        </div>
        <p className="mt-2 max-w-prose text-sm text-muted">{plan.evidence}</p>
        {history.length > 0 ? (
          <p className="mt-1 font-mono text-xs text-muted">{history.join(" · ")}</p>
        ) : null}

        <div className="mt-3 rounded-md border border-line bg-ink p-3">
          <p className="text-sm font-semibold">Proposed cuts</p>
          <dl className="mt-1 grid grid-cols-1 gap-1 font-mono text-xs text-muted sm:grid-cols-3">
            <div><dt className="inline">start </dt><dd className="inline text-mist">{formatCut(plan.startSec)}</dd></div>
            <div><dt className="inline">end </dt><dd className="inline text-mist">{formatCut(plan.endSec)}</dd></div>
            <div><dt className="inline">offset </dt><dd className="inline text-mist">{plan.offsetSec >= 0 ? "+" : ""}{plan.offsetSec.toFixed(1)}s</dd></div>
          </dl>
        </div>

        <div className="mt-3 rounded-md border border-line bg-ink p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold">Cut preview</p>
            <div className="flex flex-wrap gap-1">
              <Button onClick={() => requestSeek(plan.startSec)}>Jump to start</Button>
              <Button onClick={() => requestSeek(plan.endSec)}>Jump to end</Button>
            </div>
          </div>
          <div className="mt-2">
            <MediaPlayer
              sermonId={sermonId}
              kind={reviewKind}
              contentType={reviewItem?.content_type}
              available={isLive && !!reviewItem?.available}
              emptyMessage={
                isLive
                  ? "Preview unavailable until the source media is present."
                  : "Preview available in the live console."
              }
              markers={[
                { atSec: plan.startSec, label: "Start" },
                { atSec: plan.endSec, label: "End" },
              ]}
              seekToSec={seek?.sec ?? null}
              seekNonce={seek?.n}
              label={reviewItem?.label}
            />
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <CutPreview
            label="Start cut"
            kind="snippet_start"
            atSec={plan.startSec}
            note={`${formatCut(plan.startSec)} · 10s window`}
            sermonId={sermonId}
            media={media}
            onSeek={requestSeek}
          />
          <CutPreview
            label="End cut"
            kind="snippet_end"
            atSec={plan.endSec}
            note={`${formatCut(plan.endSec)} · 10s window`}
            sermonId={sermonId}
            media={media}
            onSeek={requestSeek}
          />
          <CutPreview
            label="Proposed ending"
            kind="snippet_ending"
            atSec={plan.endSec}
            note="ending card · 6s hold"
            sermonId={sermonId}
            media={media}
            onSeek={requestSeek}
          />
        </div>

        <fieldset className="mt-4">
          <legend className="text-sm font-semibold">Adjust cuts</legend>
          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label htmlFor="cut-start" className="text-xs font-medium text-muted">Start (mm:ss.s or seconds)</label>
              <input
                id="cut-start"
                value={startText}
                onChange={(e) => setStartText(e.target.value)}
                inputMode="decimal"
                className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 font-mono text-sm text-mist"
              />
              <p className="mt-0.5 font-mono text-xs text-muted">{start !== null ? `= ${start.toFixed(1)}s` : "unparseable"}</p>
            </div>
            <div>
              <label htmlFor="cut-end" className="text-xs font-medium text-muted">End (mm:ss.s or seconds)</label>
              <input
                id="cut-end"
                value={endText}
                onChange={(e) => setEndText(e.target.value)}
                inputMode="decimal"
                className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 font-mono text-sm text-mist"
              />
              <p className="mt-0.5 font-mono text-xs text-muted">{end !== null ? `= ${end.toFixed(1)}s` : "unparseable"}</p>
            </div>
            <div>
              <label htmlFor="cut-offset" className="text-xs font-medium text-muted">Audio offset, s (±5, 0.1 steps)</label>
              <input
                id="cut-offset"
                value={offsetText}
                onChange={(e) => setOffsetText(e.target.value)}
                inputMode="decimal"
                step={0.1}
                className="mt-1 min-h-[44px] w-full min-w-0 rounded-md border border-line bg-ink px-3 font-mono text-sm text-mist"
              />
              <p className="mt-0.5 font-mono text-xs text-muted">{offset !== null ? `= ${formatCut(offset)}` : "unparseable"}</p>
            </div>
          </div>
          <p className="mt-2 font-mono text-xs text-muted" aria-live="polite">
            Computed duration: {duration !== null ? formatCut(duration) : "—"}
          </p>
          {errors.length > 0 ? (
            <ul className="mt-2 flex flex-col gap-1" role="alert">
              {errors.map((e) => (
                <li key={e} className="text-xs text-danger">{e}</li>
              ))}
            </ul>
          ) : null}
        </fieldset>

        <fieldset className="mt-4">
          <legend className="text-sm font-semibold">Render target</legend>
          <div className="mt-2 flex flex-col gap-2">
            <label className="flex min-h-[44px] cursor-pointer items-start gap-2 rounded-md border border-line p-3">
              <input
                type="radio"
                name="render-target"
                value="render"
                checked={target === "render"}
                onChange={() => setTarget("render")}
                className="mt-1"
              />
              <span className="text-sm">
                <span className="font-semibold">Render-only (default).</span>{" "}
                <span className="text-muted">Produces a local file for review. Nothing is uploaded.</span>
              </span>
            </label>
            <label className="flex min-h-[44px] cursor-pointer items-start gap-2 rounded-md border border-line p-3">
              <input
                type="radio"
                name="render-target"
                value="upload"
                checked={target === "upload"}
                onChange={() => setTarget("upload")}
                className="mt-1"
              />
              <span className="text-sm">
                <span className="font-semibold">Render + upload.</span>{" "}
                <span className="text-muted">Renders, then pushes the result to SermonAudio.</span>
              </span>
            </label>
          </div>
        </fieldset>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={approve} disabled={errors.length > 0 || applying} aria-busy={applying}>
            {applying ? "Queueing…" : "Approve & queue render"}
          </Button>
          <Button onClick={reset} disabled={!dirty || applying}>
            Reset to plan values
          </Button>
        </div>
      </Card>

      <Card>
        <p className="text-sm font-semibold">Restore original</p>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Discards every applied cut for this teaching and keeps the unedited source. This cannot be undone.
        </p>
        <div className="mt-3">
          <Button variant="danger" onClick={() => setConfirmRestore(true)}>
            Restore original
          </Button>
        </div>
      </Card>

      <ConfirmDialog
        open={confirmRestore}
        title={`Restore original for “${sermonTitle}”?`}
        body="All applied cuts are discarded and the unedited source is kept. This cannot be undone."
        confirmLabel="Restore original"
        onClose={() => setConfirmRestore(false)}
        onConfirm={() => {
          setPlan((p) => ({ ...p, status: "draft", revision: 1 }));
          setHistory([]);
          onToast("Original restored (mock). Plan reset to draft.");
        }}
      />
    </section>
  );
}
