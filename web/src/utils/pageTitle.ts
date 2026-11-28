const titles: Record<string, string> = {
  "/": "Inbox · SermonPilot",
  "/new": "New teaching · SermonPilot",
  "/library": "Library · SermonPilot",
  "/activity": "Activity · SermonPilot",
  "/settings": "Settings · SermonPilot",
};

export function pageTitle(pathname: string): string {
  const path = pathname === "/" ? pathname : pathname.replace(/\/+$/, "");
  const exact = titles[path];
  if (exact) return exact;
  if (/^\/(teaching|library)\/[^/]+$/.test(path)) return "Teaching review · SermonPilot";
  if (/^\/activity\/[^/]+$/.test(path)) return "Activity · SermonPilot";
  if (/^\/settings\/[^/]+$/.test(path)) return "Settings · SermonPilot";
  return "Not found · SermonPilot";
}
