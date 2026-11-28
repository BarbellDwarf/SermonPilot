import { test, expect } from "@playwright/test";

const PAGES = [
  { name: "inbox", path: "/" },
  { name: "library", path: "/library" },
  { name: "activity", path: "/activity" },
  { name: "settings", path: "/settings/preferences" },
  { name: "new-teaching", path: "/new" },
  { name: "review", path: "/teaching/s-01" },
] as const;

test.describe("touch targets at 390", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "mobile only");
  });

  for (const target of PAGES) {
    test(`${target.name} controls are at least 44x44`, async ({ page }) => {
      await page.goto(target.path);
      await page.waitForLoadState("networkidle");
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();

      const small = await page.evaluate(() => {
        const selector =
          'button, a, summary, [role="tab"], [role="switch"], [role="slider"]';
        const controls = Array.from(document.querySelectorAll<HTMLElement>(selector)).filter(
          (element) => {
            if (!element.closest("main")) return false;
            const style = getComputedStyle(element);
            return (
              style.display !== "none" &&
              style.visibility !== "hidden" &&
              element.getClientRects().length > 0
            );
          },
        );
        return controls
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              name:
                element.getAttribute("aria-label") ||
                element.textContent?.trim().slice(0, 48) ||
                element.tagName,
              width: Math.round(rect.width),
              height: Math.round(rect.height),
            };
          })
          .filter((control) => control.width < 44 || control.height < 44);
      });

      expect(small).toEqual([]);
    });
  }
});
