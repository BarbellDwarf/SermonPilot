import { test, expect, type Page } from "@playwright/test";

const PAGES = [
  { name: "home", path: "/" },
  { name: "library", path: "/library" },
  { name: "jobs", path: "/jobs" },
  { name: "settings", path: "/settings" },
  { name: "new-teaching", path: "/new" },
  { name: "review", path: "/library/s-01" },
] as const;

const THEMES = ["dark", "light"] as const;

const SCREENSHOT_STYLE = `
  header, nav[aria-label="Primary"], .sticky, [class*="sticky"] { position: static !important; }
`;

async function applyTheme(page: Page, theme: (typeof THEMES)[number]) {
  if (theme === "dark") return;
  const isLight = await page.locator("html").evaluate((el) => el.classList.contains("light"));
  if (isLight) return;
  await page.getByTestId("account-menu-trigger").click();
  await page.getByRole("menuitem", { name: "Switch to light theme" }).click();
}

for (const theme of THEMES) {
  for (const target of PAGES) {
    test(`${target.name} ${theme}`, async ({ page }) => {
      await page.clock.install({ time: new Date("2026-10-25T21:07:00Z") });
      await page.goto(target.path);
      await applyTheme(page, theme);
      await page.waitForLoadState("networkidle");
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
      await page.clock.fastForward(1200);
      await page.waitForTimeout(150);
      await page.addStyleTag({ content: SCREENSHOT_STYLE });
      await expect(page).toHaveScreenshot(`${target.name}-${theme}.png`, {
        fullPage: true,
      });
    });
  }
}
