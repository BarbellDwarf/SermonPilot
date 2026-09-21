import { useTranscriptSegments } from "../api/hooks";
import { formatCut } from "../utils/time";

interface TranscriptViewerProps {
  id: string;
  plainText: string;
  timestampsAvailable: boolean;
  onSeek?: (sec: number) => void;
  className?: string;
}

export function TranscriptViewer({
  id,
  plainText,
  timestampsAvailable,
  onSeek,
  className = "",
}: TranscriptViewerProps) {
  const { segments, isLoading } = useTranscriptSegments(id, timestampsAvailable);

  if (timestampsAvailable && isLoading) {
    return <p className="font-mono text-xs text-muted">Loading timestamps…</p>;
  }

  if (segments.length > 0) {
    return (
      <ol
        data-testid="transcript-segments"
        className={`flex max-h-96 flex-col gap-0.5 overflow-auto rounded-md border border-line bg-ink p-2 ${className}`}
      >
        {segments.map((segment, index) => (
          <li key={`${segment.start}-${index}`}>
            <button
              type="button"
              onClick={() => onSeek?.(segment.start)}
              className="flex w-full items-start gap-2 rounded px-1 py-1 text-left text-sm text-mist transition-colors hover:bg-raised"
            >
              <span className="shrink-0 font-mono text-xs text-accent">
                {formatCut(segment.start)}
              </span>
              <span className="min-w-0 [overflow-wrap:anywhere]">{segment.text}</span>
            </button>
          </li>
        ))}
      </ol>
    );
  }

  if (plainText) {
    return (
      <pre className={`max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-ink p-3 font-mono text-xs text-mist [overflow-wrap:anywhere] ${className}`}>
        {plainText}
      </pre>
    );
  }

  return <p className="text-sm text-muted">No transcript recorded for this teaching.</p>;
}
