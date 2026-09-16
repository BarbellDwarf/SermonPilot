import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { editPlans, librarySermons } from "../mock/data";
import { ReviewPanel } from "../components/ReviewPanel";
import { sermonStatusLabel, sermonStatusTone } from "./Library";
import { Button, Card, Chip, ConfirmDialog, EmptyState, Toast } from "../components/ui";

export function LibraryDetail() {
  const { id } = useParams();
  const [toast, setToast] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [pushing, setPushing] = useState(false);

  const sermon = librarySermons.find((s) => s.id === id);
  const plan = id ? editPlans[id] : undefined;

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  };

  if (!sermon) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          title="Teaching not found"
          body="This mock library has only a handful of sample teachings. The link may be stale."
          action={
            <Link to="/library">
              <Button variant="primary">Back to Library</Button>
            </Link>
          }
        />
      </div>
    );
  }

  if (deleted) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          title="Teaching deleted"
          body={`“${sermon.title}” was removed from this mock list. Nothing was uploaded or lost.`}
          action={
            <Link to="/library">
              <Button variant="primary">Back to Library</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const push = () => {
    setPushing(true);
    window.setTimeout(() => {
      setPushing(false);
      showToast("Push to SermonAudio queued (mock).");
    }, 1200);
  };

  return (
    <div className="flex flex-col gap-4">
      <Link to="/library" className="inline-flex min-h-[44px] w-fit items-center rounded-md px-2 text-sm font-medium text-accent hover:underline">
        ← Library
      </Link>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={sermonStatusTone[sermon.status]}>{sermonStatusLabel[sermon.status]}</Chip>
          <span className="rounded border border-line px-1.5 py-0.5 font-mono text-xs text-muted">
            {sermon.series}
          </span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight [overflow-wrap:anywhere]">{sermon.title}</h1>
        <p className="text-sm text-muted">
          {sermon.speaker} · {sermon.date} · {sermon.duration}
        </p>
      </div>

      <section aria-label="Sermon actions" className="flex flex-col gap-2">
        {sermon.status !== "draft" ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={push} disabled={pushing} aria-busy={pushing}>
              {pushing ? "Pushing…" : sermon.status === "rendered" ? "Push to SermonAudio" : "Push update to SermonAudio"}
            </Button>
            {sermon.status === "rendered" ? (
              <Button onClick={() => showToast("Re-render queued (mock).")}>Re-render render-only</Button>
            ) : null}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button variant="danger" onClick={() => setConfirmDelete(true)}>
            Delete
          </Button>
        </div>
      </section>

      <section aria-labelledby="info-h">
        <h2 id="info-h" className="mb-2 text-lg font-semibold">Information</h2>
        <Card>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            {[
              ["Title", sermon.title],
              ["Speaker", sermon.speaker],
              ["Date", sermon.date],
              ["Duration", sermon.duration],
              ["Series", sermon.series],
              ["Status", sermonStatusLabel[sermon.status]],
            ].map(([term, value]) => (
              <div key={term} className="min-w-0">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted">{term}</dt>
                <dd className="mt-0.5 [overflow-wrap:anywhere]">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </section>

      {plan ? (
        <ReviewPanel plan={plan} sermonTitle={sermon.title} onToast={showToast} />
      ) : (
        <section aria-labelledby="review-none-h">
          <h2 id="review-none-h" className="mb-2 text-lg font-semibold">Review auto-edit plan</h2>
          <EmptyState
            title="No auto-edit plan"
            body="This teaching has no proposed cuts to review. Plans appear here after analysis runs."
          />
        </section>
      )}

      <section aria-labelledby="files-h">
        <h2 id="files-h" className="mb-2 text-lg font-semibold">Files & transcript</h2>
        <EmptyState
          title="Nothing attached yet"
          body="Rendered audio, source media, and the transcript will be listed here in a later phase."
        />
      </section>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete “${sermon.title}”?`}
        body={`“${sermon.title}” by ${sermon.speaker} will be removed from this mock list. This cannot be undone.`}
        confirmLabel="Delete"
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => setDeleted(true)}
      />
      <Toast message={toast} />
    </div>
  );
}
