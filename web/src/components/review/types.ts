export interface DetailsPatch {
  title?: string;
  speaker?: string;
  series_title?: string;
  recorded_date?: string;
  description?: string;
  hashtags?: string;
}

export interface TranscriptState {
  open: boolean;
  onToggle: () => void;
  loading: boolean;
  error: string | null;
  plainText: string;
  totalLength: number;
  truncated: boolean;
  timestampsAvailable: boolean;
  copied: boolean;
  onCopy: () => void;
}
