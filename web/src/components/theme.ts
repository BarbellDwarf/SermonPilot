/**
 * One theme, three readers.
 *
 * The console's theme lives on `<html>` as the `dark` and `light` classes. The
 * header toggle, the Settings > Appearance radios, and the class list all have
 * to agree, and the choice has to survive a reload, so it is kept in one place
 * and written to local storage rather than to the settings database.
 */

export type Theme = "dark" | "light" | "system";

export const THEME_KEY = "sp.theme";

export function isTheme(value: unknown): value is Theme {
  return value === "dark" || value === "light" || value === "system";
}

export function prefersLight(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: light)").matches
  );
}

export function readTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return isTheme(stored) ? stored : "dark";
  } catch {
    return "dark";
  }
}

/** Put the theme on the document. A storage failure costs persistence, not the theme. */
export function writeTheme(theme: Theme): void {
  const dark = themeIsDark(theme);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.classList.toggle("light", !dark);
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* a browser without storage still shows the theme for this visit */
  }
}

export function themeIsDark(theme: Theme): boolean {
  return theme === "system" ? !prefersLight() : theme === "dark";
}