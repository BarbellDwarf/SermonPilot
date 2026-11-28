import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

const AXE_SOURCE = readFileSync(
  new URL("../../../node_modules/axe-core/axe.min.js", import.meta.url),
  "utf8",
);

test("filter chips expose pressed state and keep the filter in the URL", async ({ page }) => {
  await page.goto("/activity");

  await expect(page.getByRole("tablist")).toHaveCount(0);
  const all = page.getByRole("button", { name: /^All/ });
  const failed = page.getByRole("button", { name: /^Failed/ });
  await expect(all).toHaveAttribute("aria-pressed", "true");

  await failed.click();

  await expect(page).toHaveURL(/\/activity\?state=failed$/);
  await expect(failed).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("job-row-job-1037")).toBeVisible();
  await expect(page.getByTestId("job-row-job-1042")).toHaveCount(0);
});

test("a failed row deep link opens expanded and back restores the filtered list", async ({ page }) => {
  await page.goto("/activity?state=failed");
  await page.getByTestId("job-row-job-1037").click();

  await expect(page).toHaveURL(/\/activity\/job-1037\?state=failed$/);
  await expect(page.getByTestId("job-row-job-1037")).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("job-detail-job-1037")).toBeVisible();

  await page.goBack();

  await expect(page).toHaveURL(/\/activity\?state=failed$/);
  await expect(page.getByTestId("job-row-job-1037")).toHaveAttribute("aria-expanded", "false");
});

test("the interrupted filter shows only interrupted work", async ({ page }) => {
  await page.goto("/activity");
  await page.getByRole("button", { name: /^Interrupted/ }).click();

  await expect(page).toHaveURL(/\/activity\?state=interrupted$/);
  await expect(page.getByTestId("job-row-job-1036")).toBeVisible();
  await expect(page.getByTestId("job-row-job-1036")).toContainText("INTERRUPTED");
  await expect(page.getByTestId("job-row-job-1037")).toHaveCount(0);
});

test("the job query parameter opens the matching row expanded", async ({ page }) => {
  await page.goto("/activity?state=failed&job=job-1037");

  await expect(page.getByTestId("job-row-job-1037")).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("job-detail-job-1037")).toBeVisible();
});

test("the expanded failed detail has no serious or critical axe findings", async ({ page }) => {
  await page.addInitScript({ content: AXE_SOURCE });
  await page.goto("/activity/job-1037?state=failed");
  await expect(page.getByTestId("job-detail-job-1037")).toBeVisible();

  const violations = await page.evaluate(async () => {
    const results = await (
      window as unknown as {
        axe: { run: (target: Document, options: unknown) => Promise<{ violations: unknown[] }> };
      }
    ).axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    });
    return results.violations as {
      id: string;
      impact: string | null;
      nodes: { target: string[] }[];
    }[];
  });
  const blocking = violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  expect(blocking.map((violation) => `${violation.id}: ${violation.nodes[0]?.target}`)).toEqual([]);
});
