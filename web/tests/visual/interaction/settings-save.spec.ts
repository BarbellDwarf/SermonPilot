import { expect, test } from "@playwright/test";

test("a clean Settings section has no save bar", async ({ page }) => {
  await page.goto("/settings/audio");

  await expect(page.getByRole("heading", { name: "Audio processing" })).toBeVisible();
  await expect(page.getByTestId("settings-save-bar")).toHaveCount(0);
  await expect(page.getByText("Saved.")).toHaveCount(0);
});

test("one named secondary bar stays visible while its section is dirty", async ({ page }) => {
  await page.goto("/settings/audio");
  await page.getByLabel("Audio enhancement method").selectOption("none");

  const save = page.getByRole("button", { name: "Save audio settings" });
  await expect(save).toBeVisible();
  await expect(save).toHaveClass(/bg-raised/);
  await expect(save).not.toHaveClass(/bg-accent/);
  await expect(page.getByTestId("settings-save-bar")).toHaveCount(1);

  for (const y of [0, 400, 1200]) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await expect(page.getByTestId("settings-save-bar")).toHaveCount(1);
    await expect(page.getByTestId("settings-save-bar")).toBeVisible();
    const clickable = await save.evaluate((button) => {
      const rect = button.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return Boolean(hit && (button === hit || button.contains(hit)));
    });
    expect(clickable).toBe(true);
  }

  await save.click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(page.getByTestId("settings-save-bar")).toHaveCount(0, { timeout: 5000 });
});

test("two dirty Preference cards share one visible save surface", async ({ page }) => {
  await page.goto("/settings/preferences");
  await page.getByRole("radio", { name: "light", exact: true }).check();
  await page.getByLabel("Display name").fill("River");

  await expect(page.getByTestId("settings-save-bar")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Save account" })).toBeVisible();

  await page.getByRole("button", { name: "Save account" }).click();
  await expect(page.getByRole("button", { name: "Save appearance" })).toBeVisible();
  await expect(page.getByTestId("settings-save-bar")).toHaveCount(1);
});

test("the section rail appears only at desktop width", async ({ page }) => {
  await page.goto("/settings/preferences");
  const rail = page.getByRole("navigation", { name: "Settings sections" });
  const select = page.getByTestId("settings-section-select");

  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(rail).toBeHidden();
  await expect(select).toBeVisible();

  await page.setViewportSize({ width: 1024, height: 900 });
  await expect(rail).toBeVisible();
  await expect(select).toBeHidden();
});
