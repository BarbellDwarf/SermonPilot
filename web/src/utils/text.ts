export function truncateText(value: string | null | undefined, max: number): string {
  const clean = (value ?? "").replace(/\s+/g, " ").trim();
  if (max <= 0) return "";
  if (clean.length <= max) return clean;
  const room = Math.max(0, max - 1);
  const cut = clean.slice(0, room);
  const boundary = cut.lastIndexOf(" ");
  const body = boundary > room * 0.5 ? cut.slice(0, boundary) : cut;
  return `${body.trimEnd()}…`;
}
