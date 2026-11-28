import { test, expect } from "@playwright/test";

test.describe("library filters sheet", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "mobile only");
  });

  test("opens as a dialog, applies a lifecycle, and returns focus", async ({ page }) => {
    await page.goto("/library");
    const trigger = page.getByTestId("library-filters-trigger");
    await trigger.click();

    const sheet = page.getByRole("dialog", { name: "Filters" });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Close Filters" })).toBeFocused();

    await expect
      .poll(async () => {
        const box = await sheet.boundingBox();
        return box ? Math.round(box.y + box.height) : 0;
      })
      .toBeLessThanOrEqual(844);
    const box = await sheet.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.height).toBeLessThanOrEqual(844 * 0.9 + 1);

    await sheet.getByLabel("Lifecycle").selectOption("failed");
    await expect(page).toHaveURL(/state=failed/);

    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});
