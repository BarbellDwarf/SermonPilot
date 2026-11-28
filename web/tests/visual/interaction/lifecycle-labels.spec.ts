import { test, expect } from "@playwright/test";

test("the same teaching keeps its lifecycle label across Inbox, Library, and workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("inbox-section-needs_review").getByText("Needs review", { exact: true }).first()).toBeVisible();

  await page.goto("/library");
  await expect(page.getByTestId("library-row-s-01").getByText("Needs review", { exact: true })).toBeVisible();

  await page.goto("/teaching/s-01");
  await expect(page.getByTestId("mobile-status-trigger")).toContainText("Needs review");
  await expect(page.getByTestId("approve-primary")).toHaveText("Approve & upload");
});
