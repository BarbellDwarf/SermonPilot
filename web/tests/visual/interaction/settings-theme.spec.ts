import { expect, test } from "@playwright/test";

test("stored light theme applies before the app mounts", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("sp_theme", "light"));
  await page.goto("/settings/preferences", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveClass(/light/);
});

test("Light applies immediately and survives reload", async ({ page }) => {
  await page.goto("/settings/preferences");
  await expect(page.locator("html")).toHaveClass(/dark/);

  await page.getByRole("radio", { name: "light", exact: true }).check();
  await expect(page.locator("html")).toHaveClass(/light/);
  await expect(page.getByRole("button", { name: "Save appearance" })).toBeVisible();
  await page.getByRole("button", { name: "Save appearance" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.reload();
  await expect(page.locator("html")).toHaveClass(/light/);
  await expect(page.getByRole("radio", { name: "light", exact: true })).toBeChecked();

  await page.getByTestId("account-menu-trigger").click();
  await expect(page.getByRole("menuitem", { name: "Switch to dark theme" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.getByTestId("settings-save-bar")).toHaveCount(0);

  await page.goto("/settings/preferences");
  await expect(page.getByRole("radio", { name: "dark", exact: true })).toBeChecked();
  await expect(page.getByTestId("settings-save-bar")).toHaveCount(0);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
