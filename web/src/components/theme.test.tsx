import { afterEach, describe, expect, it } from "vitest";
import { Shell } from "./Shell";
import { readTheme, themeIsDark, THEME_KEY, writeTheme } from "./theme";
import { withProviders } from "../test/harness";

afterEach(() => {
  window.localStorage.removeItem(THEME_KEY);
  document.documentElement.className = "";
});

/**
 * The theme is one fact with three readers, and the visual pass found the header
 * toggle and the Settings > Appearance radios able to disagree, with the choice
 * lost on every reload. These pin the single source all three read from.
 */
describe("one theme, one source", () => {
  it("reads back what it wrote, so a reload keeps the choice", () => {
    writeTheme("light");
    expect(readTheme()).toBe("light");
    writeTheme("dark");
    expect(readTheme()).toBe("dark");
  });

  it("puts exactly one of the two classes on the document", () => {
    writeTheme("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    writeTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("light")).toBe(false);
  });

  it("treats an unrecognised stored value as dark rather than rendering nothing", () => {
    window.localStorage.setItem(THEME_KEY, "chartreuse");
    expect(readTheme()).toBe("dark");
  });

  it("resolves system against the media query and reports it consistently", () => {
    expect(themeIsDark("system")).toBe(!themeIsDark("light"));
    writeTheme("system");
    expect(document.documentElement.classList.contains("dark")).toBe(themeIsDark("system"));
  });

  it("labels the toggle with the theme it will switch to", () => {
    const light = withProviders(
      <Shell dark={false} theme="light" onToggleTheme={() => {}}>
        <p>body</p>
      </Shell>,
    );
    expect(toggleLabel()).toBe("Switch to dark theme");
    light.unmount();

    withProviders(
      <Shell dark theme="dark" onToggleTheme={() => {}}>
        <p>body</p>
      </Shell>,
    );
    expect(toggleLabel()).toBe("Switch to light theme");
  });
});

function toggleLabel(): string {
  return (
    document.querySelector('button[aria-label^="Switch to"]')?.getAttribute("aria-label") ?? ""
  );
}