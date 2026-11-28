import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/new");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("fresh page announces no failure", async ({ page }) => {
  await expect(page.locator("[role=alert]")).toHaveCount(0);
  await expect(page.locator("[aria-invalid]")).toHaveCount(0);

  const start = page.getByTestId("start-processing");
  await expect(start).toBeDisabled();
  await expect(start).toHaveAttribute("aria-describedby", "ns-readiness");
  await expect(page.locator("#ns-readiness")).toHaveText(
    "Still needed: source file, title, speaker, date.",
  );
});

test("blurred required fields show linked inline errors", async ({ page }) => {
  const title = page.getByLabel("Title (required)");
  await title.focus();
  await page.keyboard.press("Tab");
  await expect(page.locator("#ns-title-error")).toBeVisible();
  await expect(title).toHaveAttribute("aria-invalid", "true");
  await expect(title).toHaveAttribute("aria-describedby", "ns-title-error");

  const speaker = page.getByRole("combobox", { name: "Speaker" });
  await speaker.focus();
  await page.keyboard.press("Tab");
  await expect(page.locator("#ns-speaker-error")).toBeVisible();
  await expect(speaker).toHaveAttribute("aria-invalid", "true");
  await expect(speaker).toHaveAttribute("aria-describedby", "ns-speaker-error");

  const date = page.getByLabel("Date (required)");
  await date.focus();
  await date.evaluate((element: HTMLInputElement) => element.blur());
  await expect(page.locator("#ns-date-error")).toBeVisible();
  await expect(date).toHaveAttribute("aria-invalid", "true");
  await expect(date).toHaveAttribute("aria-describedby", "ns-date-error");
});

test("submit attempt focuses the first invalid field", async ({ page }) => {
  await page.locator("form").evaluate((form: HTMLFormElement) => form.requestSubmit());
  await expect(page.getByRole("button", { name: "Choose file" })).toBeFocused();
  await expect(page.locator("#ns-source-error")).toBeVisible();
  await expect(page.locator("#ns-title-error")).toBeVisible();
  await expect(page.locator("#ns-speaker-error")).toBeVisible();
  await expect(page.locator("#ns-date-error")).toBeVisible();
});

test("dropzone has one control and the file input is not a tab stop", async ({ page }) => {
  const panel = page.locator("#source-panel-browser");
  await expect(panel.locator('[role="button"]')).toHaveCount(0);

  const choose = panel.getByRole("button", { name: "Choose file" });
  await expect(choose).toBeVisible();
  await expect(choose.locator("button, [role=button], input")).toHaveCount(0);
  await expect(choose).toHaveClass(/bg-raised/);

  await expect(page.getByLabel("Choose a teaching file")).toHaveAttribute("tabindex", "-1");
});

test("Start processing is the only accent control", async ({ page }) => {
  const accents = page.locator("main button.bg-accent");
  await expect(accents).toHaveCount(1);

  const start = page.getByTestId("start-processing");
  await expect(start).toHaveClass(/bg-accent/);
  await expect(start).toHaveText("Start processing");
});
