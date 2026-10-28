const LOCALE = "en-US";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

function parseDateValue(value: string): Date | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    const [year, month, day] = trimmed.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, day));
  }
  const iso = trimmed.includes(" ") ? trimmed.replace(" ", "T") : trimmed;
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`;
  const parsed = new Date(zoned);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function zonedParts(date: Date, timeZone?: string) {
  const formatter = new Intl.DateTimeFormat(LOCALE, {
    timeZone,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
    minute: get("minute"),
  };
}

export function formatDate(
  value: string | number | Date | null | undefined,
  options: { timeZone?: string } = {},
): string {
  if (value === null || value === undefined) return "—";
  const date = value instanceof Date ? value : parseDateValue(String(value));
  if (!date || Number.isNaN(date.getTime())) return "—";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value.trim())) {
    const [year, month, day] = value.trim().split("-").map(Number);
    return `${MONTHS[month - 1]} ${day}, ${year}`;
  }
  const parts = zonedParts(date, options.timeZone);
  return `${parts.month} ${Number(parts.day)}, ${parts.year}`;
}

export function formatDateTime(
  value: string | number | Date | null | undefined,
  options: { timeZone?: string; year?: "auto" | "always" | "never" } = {},
): string {
  if (value === null || value === undefined) return "—";
  const raw = typeof value === "string" ? value.trim() : value;
  if (typeof raw === "string" && /^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    return formatDate(raw, options);
  }
  const date = raw instanceof Date ? raw : parseDateValue(String(raw));
  if (!date || Number.isNaN(date.getTime())) {
    return typeof raw === "string" ? raw : "—";
  }
  const parts = zonedParts(date, options.timeZone);
  const mode = options.year ?? "auto";
  const includeYear =
    mode === "always" ||
    (mode === "auto" && parts.year !== String(new Date().getFullYear()));
  const day = `${parts.month} ${Number(parts.day)}`;
  return `${day}${includeYear ? `, ${parts.year}` : ""}, ${parts.hour}:${parts.minute}`;
}

export function formatRelativeTime(
  value: string | number | Date | null | undefined,
  now: number = Date.now(),
): string {
  if (value === null || value === undefined) return "—";
  const date = value instanceof Date ? value : parseDateValue(String(value));
  if (!date || Number.isNaN(date.getTime())) return "—";
  const total = Math.round((now - date.getTime()) / 1000);
  const past = total >= 0;
  const abs = Math.abs(total);
  const phrase =
    abs < 45
      ? "just now"
      : abs < 3600
        ? `${Math.floor(abs / 60)}m`
        : abs < 86_400
          ? `${Math.floor(abs / 3600)}h`
          : `${Math.floor(abs / 86_400)}d`;
  if (abs < 45) return phrase;
  if (abs >= 7 * 86_400) return formatDate(date);
  return past ? `${phrase} ago` : `in ${phrase}`;
}

export function parseDuration(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) && value >= 0 ? value : null;
  const trimmed = value.trim();
  if (!trimmed || ["running", "waiting", "--:--", "—"].includes(trimmed.toLowerCase())) {
    return null;
  }
  const clock = trimmed.match(/^(?:(\d+):)?(\d+):(\d{2})$/);
  if (clock) {
    const [, hours, minutes, seconds] = clock;
    return Number(hours ?? 0) * 3600 + Number(minutes) * 60 + Number(seconds);
  }
  const prose = trimmed.match(/^(?:(\d+(?:\.\d+)?)h)?\s*(?:(\d+(?:\.\d+)?)m)?\s*(?:(\d+(?:\.\d+)?)s)?$/i);
  if (prose && (prose[1] || prose[2] || prose[3])) {
    return Number(prose[1] ?? 0) * 3600 + Number(prose[2] ?? 0) * 60 + Number(prose[3] ?? 0);
  }
  const seconds = Number(trimmed);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "—";
  }
  const total = Math.round(seconds);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) {
    const rest = total % 60;
    return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

export function formatDurationValue(value: string | number | null | undefined): string {
  return formatDuration(parseDuration(value));
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return "size unknown";
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatCount(
  count: number,
  singular: string,
  plural: string = `${singular}s`,
): string {
  const safe = Number.isFinite(count) ? count : 0;
  return `${safe.toLocaleString(LOCALE)} ${safe === 1 ? singular : plural}`;
}
