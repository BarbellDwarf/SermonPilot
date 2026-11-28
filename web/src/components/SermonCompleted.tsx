import type { SermonMediaData } from "../api/hooks";
import type { LibrarySermon } from "../mock/data";
import { MediaPlayer } from "./MediaPlayer";
import { Button } from "./ui";
import { DetailsForm } from "./review/DetailsForm";
import { PublicationRows } from "./review/WorkspacePanels";
import { preferredKind } from "./review/media";
import type { DetailsPatch } from "./review/types";

export interface SermonCompletedProps {
  sermon: LibrarySermon;
  media: SermonMediaData;
  isLive: boolean;
}

export function SermonCompleted({ sermon, media, isLive }: SermonCompletedProps) {
  const activeKind = preferredKind(media);
  const activeItem = media.byKind[activeKind];
  return (
    <div data-testid="sermon-completed" className="flex flex-col gap-4">
      <section data-testid="completed-player" aria-label="Playback" className="rounded-lg border border-line bg-surface p-4">
        {isLive && media.error ? (
          <div role="alert" className="mb-2 flex flex-wrap items-center gap-2 rounded-md border border-danger bg-ink p-3 text-sm text-danger">
            <span className="min-w-0 flex-1">{media.error}</span>
            <Button onClick={media.retry}>Retry media</Button>
          </div>
        ) : null}
        {isLive && !media.error ? (
          <MediaPlayer
            sermonId={sermon.id}
            kind={activeKind}
            contentType={activeItem?.content_type}
            available={!!activeItem?.available}
            emptyMessage="No playable media for this teaching yet."
          />
        ) : isLive ? null : (
          <p className="rounded-md border border-dashed border-line bg-ink px-3 py-6 text-center text-sm text-muted">Preview available in the live console.</p>
        )}
      </section>
    </div>
  );
}

export interface CompletedDetailsProps {
  sermon: LibrarySermon;
  description: string | null;
  descriptionNeedsReview?: boolean;
  hashtags?: string | null;
  isLive: boolean;
  sermonaudioId?: string | null;
  uploadedAt?: string | null;
  bibleText?: string | null;
  scriptureReference?: string | null;
  onSaveDetails?: (patch: DetailsPatch) => Promise<void> | void;
  onRegenerateDescription?: () => Promise<void> | void;
  onToast: (message: string, variant?: "success" | "error" | "info") => void;
}

export function CompletedDetails({
  sermon,
  description,
  descriptionNeedsReview,
  hashtags,
  isLive,
  sermonaudioId,
  uploadedAt,
  bibleText,
  scriptureReference,
  onSaveDetails,
  onRegenerateDescription,
  onToast,
}: CompletedDetailsProps) {
  return (
    <section data-testid="completed-details" aria-labelledby="completed-details-h" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="completed-details-h" className="text-lg font-semibold">Details</h2>
      <p className="mt-1 text-xs text-muted">Changes stay local until you press Save details.</p>
      <div className="mt-3">
        <DetailsForm
          key={sermon.id}
          sermon={sermon}
          description={description}
          descriptionNeedsReview={descriptionNeedsReview}
          hashtags={hashtags}
          isLive={isLive}
          onSaveDetails={onSaveDetails}
          onRegenerateDescription={onRegenerateDescription}
          onToast={onToast}
        />
      </div>
      <PublicationRows
        sermonaudioId={sermonaudioId}
        uploadedAt={uploadedAt}
        bibleText={bibleText}
        scriptureReference={scriptureReference}
      />
    </section>
  );
}
