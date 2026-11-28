import { test, expect, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/new");
  await expect(page.getByRole("heading", { level: 1, name: "New teaching" })).toBeVisible();
});

const libraryLink = (page: Page) => page.getByRole("link", { name: "Library" }).first();

test("asks before leaving a draft and Discard continues to Library", async ({ page }) => {
  await page.getByLabel("Title (required)").fill("Draft title");
  await libraryLink(page).click();

  const dialog = page.getByRole("dialog", { name: "Unsaved changes" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Stay" })).toBeVisible();
  await expect(page).toHaveURL(/\/new$/);

  await dialog.getByRole("button", { name: "Discard" }).click();
  await expect(page).toHaveURL(/\/library$/);
});

test("reset clears the navigation guard", async ({ page }) => {
  await page.getByLabel("Title (required)").fill("Draft title");
  await page.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Reset form" }).click();
  await page
    .getByRole("dialog", { name: "Reset this form?" })
    .getByRole("button", { name: "Reset form" })
    .click();

  await libraryLink(page).click();
  await expect(page).toHaveURL(/\/library$/);
  await expect(page.getByRole("dialog", { name: "Unsaved changes" })).toHaveCount(0);
});
