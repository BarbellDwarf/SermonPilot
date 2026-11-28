import { test, expect } from "@playwright/test";

test.describe("route titles, focus and redirects", () => {
  test("direct loads use the new page titles", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Inbox · SermonPilot");

    await page.goto("/new");
    await expect(page).toHaveTitle("New teaching · SermonPilot");

    await page.goto("/library");
    await expect(page).toHaveTitle("Library · SermonPilot");

    await page.goto("/activity");
    await expect(page).toHaveTitle("Activity · SermonPilot");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Activity");

    await page.goto("/settings/preferences");
    await expect(page).toHaveTitle("Settings · SermonPilot");
  });

  test("client navigation moves focus to main", async ({ page }) => {
    await page.goto("/library");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Library");

    const primary = page.getByRole("navigation", { name: "Primary" });
    const nav = (await primary.isVisible())
      ? primary
      : page.getByRole("navigation", { name: "Sections" });
    await nav.getByRole("link", { name: "Activity" }).click();

    await expect(page).toHaveURL(/\/activity$/);
    await expect(page.locator("main")).toBeFocused();
  });

  test("/jobs redirects to /activity", async ({ page }) => {
    await page.goto("/jobs");

    await expect(page).toHaveURL(/\/activity$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Activity");
  });

  test("/library/s-01 redirects to /teaching/s-01", async ({ page }) => {
    await page.goto("/library/s-01");

    await expect(page).toHaveURL(/\/teaching\/s-01$/);
    await expect(page).toHaveTitle("Teaching review · SermonPilot");
  });

  test("catch-all shows NotFound with a route back to the Inbox", async ({ page }) => {
    await page.goto("/this-page-does-not-exist");

    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found");
    await expect(page).toHaveTitle("Not found · SermonPilot");
    await page.getByRole("link", { name: "Go to Inbox" }).click();
    await expect(page).toHaveURL(/\/$/);
  });
});

test.describe("route overflow at 390", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "mobile only");
  });

  for (const path of ["/", "/library", "/activity", "/settings/preferences"]) {
    test(`${path} has no horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const overflow = await page.evaluate(() => ({
        document: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      }));
      expect(overflow.document).toBeLessThanOrEqual(overflow.viewport + 1);
    });
  }
});
