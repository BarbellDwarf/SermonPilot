import type { SermonMediaData } from "../../api/hooks";

export function artifactLabel(kind: string): string {
  switch (kind) {
    case "source":
      return "Source media";
    case "processed":
      return "Final recording";
    case "keeper":
      return "Keeper";
    case "enhanced":
      return "Enhanced audio";
    case "transcript":
      return "Transcript";
    case "transcript_timestamps":
      return "Transcript timestamps";
    case "snippet_start":
      return "Start cut";
    case "snippet_end":
      return "End cut";
    case "snippet_ending":
      return "Proposed ending";
    default:
      return kind;
  }
}

export function preferredKind(media: SermonMediaData): string {
  const order = [media.primary, "processed", "keeper", "source", media.audio, ...media.items.map((item) => item.kind)];
  for (const kind of order) {
    if (kind && media.byKind[kind]?.available) return kind;
  }
  return media.primary ?? "processed";
}
