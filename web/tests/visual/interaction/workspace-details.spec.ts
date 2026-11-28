import { test, expect } from "@playwright/test";

test("desktop details open first with title and speaker fields", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "desktop only");
  await page.goto("/teaching/s-01");
  const details = page.getByRole("tabpanel", { name: "Details" });
  await expect(details).toBeVisible();
  await expect(details.getByRole("textbox", { name: "Title", exact: true })).toBeVisible();
  await expect(details.getByLabel("Speaker")).toBeVisible();
  await expect(details.getByRole("button", { name: "Save details" })).toBeVisible();
});

test("mobile details stay read-only and send-back traps focus", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile only");
  await page.goto("/teaching/s-01");
  const details = page.locator("details").filter({ hasText: "Details" }).first();
  if (!(await details.evaluate((element) => element.open))) await details.locator("summary").click();
  await expect(details.getByText("Speaker A")).toBeVisible();
  await expect(details.getByRole("textbox")).toHaveCount(0);
  const sendBack = details.getByRole("button", { name: "Send back with note" });
  await sendBack.click();
  const dialog = page.getByRole("dialog", { name: "Send back with note" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Note")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(sendBack).toBeFocused();
});
