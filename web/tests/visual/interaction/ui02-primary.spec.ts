import { test, expect } from "@playwright/test";

test.describe("UI-02 review primary action", () => {
  test("approve stays in view at scrollY 0 as the only accent control", async ({ page }) => {
    await page.goto("/library/s-01");
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-testid="approve-primary"]')).toBeVisible();

    const geometry = await page.evaluate(() => {
      const visible = (el: Element) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          rect.width > 0 &&
          rect.height > 0
        );
      };
      const review = document.querySelector('[data-testid="sermon-review"]');
      const bar = document.querySelector('[data-testid="approval-bar"]');
      const approve = document.querySelector('[data-testid="approve-primary"]');
      const nav = [...document.querySelectorAll('nav[aria-label="Primary"]')].find(visible);
      const accents = review
        ? [...review.querySelectorAll("button.bg-accent, a.bg-accent")].filter(visible)
        : [];
      const approveRect = approve?.getBoundingClientRect();
      return {
        scrollY: window.scrollY,
        innerHeight: window.innerHeight,
        barPosition: bar ? getComputedStyle(bar).position : null,
        approveTop: approveRect?.top ?? null,
        approveBottom: approveRect?.bottom ?? null,
        navTop: nav?.getBoundingClientRect().top ?? null,
        accentCount: accents.length,
        accentTestIds: accents.map((el) => el.getAttribute("data-testid")),
      };
    });

    expect(geometry.scrollY).toBe(0);
    expect(geometry.barPosition).toBe((page.viewportSize()?.width ?? 0) >= 1024 ? "sticky" : "fixed");
    expect(geometry.approveTop).not.toBeNull();
    expect(geometry.approveTop as number).toBeGreaterThanOrEqual(0);
    expect(geometry.approveBottom as number).toBeLessThanOrEqual(geometry.innerHeight);
    if (geometry.navTop !== null) {
      expect(geometry.approveBottom as number).toBeLessThanOrEqual(geometry.navTop);
    }
    expect(geometry.accentCount).toBe(1);
    expect(geometry.accentTestIds).toEqual(["approve-primary"]);
  });
});
