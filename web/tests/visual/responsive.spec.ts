import { test, expect } from "@playwright/test";

const PAGES = [
  { name: "home", path: "/" },
  { name: "library", path: "/library" },
  { name: "jobs", path: "/jobs" },
  { name: "settings", path: "/settings" },
  { name: "new-teaching", path: "/new" },
  { name: "review", path: "/library/s-01" },
] as const;

const WIDTHS = [390, 768, 1024, 1440] as const;

for (const width of WIDTHS) {
  for (const target of PAGES) {
    test(`${target.name} holds at ${width}px with one section nav`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(target.path);
      await page.waitForLoadState("networkidle");
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();

      const measured = await page.evaluate(() => {
        const visible = (el: Element) => {
          const s = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return s.display !== "none" && s.visibility !== "hidden" && r.width > 0 && r.height > 0;
        };
        return {
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          navs: [...document.querySelectorAll("nav")]
            .filter(visible)
            .map((n) => n.getAttribute("aria-label"))
            .filter((name) => name === "Primary" || name === "Sections"),
        };
      });

      expect(measured.overflow).toBeLessThanOrEqual(0);
      expect(measured.navs).toHaveLength(1);
      expect(measured.navs[0]).toBe(width < 768 ? "Primary" : "Sections");
    });
  }
}
