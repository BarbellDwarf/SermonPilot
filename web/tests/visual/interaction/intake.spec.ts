import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/new");
  await expect(page.getByRole("heading", { level: 1, name: "New teaching" })).toBeVisible();
});

test("shows the three intake sections and the event type default", async ({ page }) => {
  await expect(page.getByRole("region", { name: "Source" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Metadata" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Processing options" })).toBeVisible();
  await expect(page.getByLabel("Event type")).toHaveValue("Sunday Service");
  await expect(page.getByLabel("Selection summary")).toContainText("Sunday Service");
});

test("lists only the formats accepted by the file input", async ({ page }) => {
  const input = page.getByLabel("Choose a teaching file");
  const accept = (await input.getAttribute("accept")) ?? "";
  const expected = accept
    .split(",")
    .map((format) => format.trim().replace(/^\./, "").toUpperCase());

  const chips = page.getByLabel("Supported formats").getByText(/^[A-Z0-9]+$/);
  await expect(chips).toHaveText(expected);
});

test("run summary shows human choices and dry run", async ({ page }) => {
  await page.getByRole("button", { name: "Choose file" }).click();
  await page.getByLabel("Title (required)").fill("Sample Title");
  await page.getByRole("combobox", { name: "Speaker" }).fill("Sample Speaker");
  await page.getByLabel("Date (required)").fill("2026-09-22");
  await page.getByRole("switch", { name: "Dry run" }).click();

  const summary = page.getByLabel("Selection summary");
  await expect(summary).toContainText("Upload · sample-sermon-upload.mp3");
  await expect(summary).toContainText("Sample Title");
  await expect(summary).toContainText("Sample Speaker");
  await expect(summary).toContainText("2026-09-22");
  await expect(summary).toContainText("Local · processed_sermons");
  await expect(summary).toContainText("Dry run");
  await expect(summary).toContainText("Audio enhancement");
  await expect(summary).toContainText("Transcription");
  await expect(summary).toContainText("Metadata generated");
  await expect(page.getByRole("button", { name: "Save as my default" })).toBeVisible();
});

test("shows the readiness hint on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const readiness = page.locator("#ns-readiness");
  await expect(readiness).toBeVisible();
  await expect(readiness).not.toBeEmpty();
});
