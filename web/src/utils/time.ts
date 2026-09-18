export function formatCut(sec: number): string {
  const sign = sec < 0 ? "-" : "";
  const abs = Math.abs(sec);
  const m = Math.floor(abs / 60);
  const s = abs - m * 60;
  const whole = Math.floor(s);
  const tenth = Math.floor((s - whole) * 10);
  return `${sign}${String(m).padStart(2, "0")}:${String(whole).padStart(2, "0")}.${tenth}`;
}

export function parseCut(input: string): number | null {
  const t = input.trim();
  if (t === "") return null;
  if (t.includes(":")) {
    const neg = t.startsWith("-");
    const body = neg ? t.slice(1) : t;
    const parts = body.split(":");
    if (parts.length !== 2) return null;
    const m = Number(parts[0]);
    const s = Number(parts[1]);
    if (!Number.isFinite(m) || !Number.isFinite(s) || m < 0 || s < 0 || s >= 60) return null;
    return (neg ? -1 : 1) * (m * 60 + s);
  }
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}
