import { expect, test } from "@playwright/test";

test("inbox groups lifecycle states and keeps one primary action", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Inbox" })).toBeVisible();

  for (const state of ["needs_review", "ready", "processing", "failed", "draft"]) {
    await expect(page.getByTestId(`inbox-section-${state}`)).toBeVisible();
  }
  await expect(page.getByTestId("inbox-section-published")).toHaveCount(0);

  const badge = page.getByTestId("nav-badge-inbox").filter({ visible: true });
  await expect(badge).toHaveText("1");
  await expect(page.getByTestId("inbox-section-needs_review").getByText("1", { exact: true })).toBeVisible();

  const width = page.viewportSize()?.width ?? 1440;
  const primaries = page.locator("main a.bg-accent, main button.bg-accent");
  await expect(primaries).toHaveCount(width >= 768 ? 1 : 0);
});

test("inbox row opens the teaching workspace", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("inbox-action-s-01").click();
  await expect(page).toHaveURL(/\/teaching\/s-01$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sample Teaching");
});

test("inbox and library use the same lifecycle label", async ({ page }) => {
  await page.goto("/");
  const inboxRow = page.getByTestId("inbox-section-needs_review");
  await expect(inboxRow.getByText("Needs review", { exact: true }).first()).toBeVisible();

  await page.goto("/library");
  const libraryRow = page.getByTestId("library-row-s-01");
  await expect(libraryRow.getByText("Needs review", { exact: true })).toBeVisible();
});

test("inbox holds its width on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Inbox" })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBe(0);
});
