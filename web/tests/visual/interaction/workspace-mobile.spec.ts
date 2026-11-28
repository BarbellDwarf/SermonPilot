import { test, expect } from "@playwright/test";

test.describe("mobile teaching review", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "mobile only");
  });

  test("keeps the plan read-only and the action bar above navigation", async ({ page }) => {
    await page.goto("/teaching/s-01");
    await expect(page.getByTestId("approve-primary")).toBeVisible();
    await expect(page.getByTestId("approval-bar").getByRole("button", { name: "Send back with note" })).toBeVisible();
    await expect(page.getByTestId("timeline")).toHaveCount(0);
    await expect(page.getByTestId("cut-toggle-start")).toHaveCount(0);
    await expect(page.getByTestId("cut-menu-interior-0")).toHaveCount(0);

    const geometry = await page.getByTestId("approval-bar").evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const nav = document.querySelector('nav[aria-label="Primary"]');
      return {
        position: getComputedStyle(element).position,
        bottom: rect.bottom,
        height: rect.height,
        navTop: nav?.getBoundingClientRect().top ?? null,
      };
    });
    expect(geometry.position).toBe("fixed");
    expect(geometry.height).toBeLessThanOrEqual(58);
    expect(geometry.navTop).not.toBeNull();
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.navTop ?? 0);
  });

  test("opens the one-line status as a named dialog and returns focus", async ({ page }) => {
    await page.goto("/teaching/s-01");
    const trigger = page.getByTestId("mobile-status-trigger");
    await expect(trigger).toContainText("%");
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Review status" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});
