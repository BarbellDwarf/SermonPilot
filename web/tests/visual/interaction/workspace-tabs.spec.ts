import { test, expect } from "@playwright/test";

test("desktop tabs use roving focus and keep every panel mounted", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "desktop and tablet tabs");
  await page.goto("/teaching/s-01");
  const details = page.getByRole("tab", { name: "Details" });
  await expect(details).toHaveAttribute("aria-selected", "true");
  await expect(details).toHaveAttribute("tabindex", "0");
  await details.focus();
  await page.keyboard.press("ArrowRight");
  const transcript = page.getByRole("tab", { name: "Transcript" });
  await expect(transcript).toBeFocused();
  await expect(transcript).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("End");
  const history = page.getByRole("tab", { name: "History" });
  await expect(history).toBeFocused();
  await expect(history).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await expect(details).toBeFocused();
  await expect(page.locator('[role="tabpanel"]')).toHaveCount(4);
  for (const tab of await page.getByRole("tab").all()) {
    const controls = await tab.getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    await expect(page.locator(`#${controls}`)).toHaveCount(1);
  }
});

test("mobile accordion rows remain keyboard accessible", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile only");
  await page.goto("/teaching/s-01");
  await expect(page.getByRole("tablist")).toHaveCount(0);
  const transcript = page.locator("summary").filter({ hasText: "Transcript" }).first();
  await transcript.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("workspace-accordion-transcript")).toHaveAttribute("open", "");
});
