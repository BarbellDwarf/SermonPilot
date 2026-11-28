import { test, expect } from "@playwright/test";

test("approve is visible at scrollY 0 and queues one linked job", async ({ page }) => {
  await page.goto("/teaching/s-01");
  const approve = page.getByTestId("approve-primary");
  await expect(approve).toBeVisible();
  await expect(approve).toHaveText("Approve & upload");

  const geometry = await approve.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const nav = document.querySelector('nav[aria-label="Primary"]');
    const navRect = nav?.getBoundingClientRect();
    const review = document.querySelector('[data-testid="sermon-review"]');
    const visible = (candidate: Element) => {
      const style = getComputedStyle(candidate);
      const bounds = candidate.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && bounds.width > 0 && bounds.height > 0;
    };
    return {
      scrollY: window.scrollY,
      top: rect.top,
      bottom: rect.bottom,
      viewportHeight: window.innerHeight,
      navTop: navRect && navRect.height > 0 ? navRect.top : null,
      barPosition: getComputedStyle(document.querySelector('[data-testid="approval-bar"]') as Element).position,
      accentCount: review ? [...review.querySelectorAll("button.bg-accent, a.bg-accent")].filter(visible).length : 0,
    };
  });
  expect(geometry.scrollY).toBe(0);
  expect(geometry.barPosition).toBe((page.viewportSize()?.width ?? 0) >= 1024 ? "sticky" : "fixed");
  expect(geometry.accentCount).toBe(1);
  expect(geometry.top).toBeGreaterThanOrEqual(0);
  expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewportHeight);
  if (geometry.navTop !== null) expect(geometry.bottom).toBeLessThanOrEqual(geometry.navTop);

  await approve.click();
  await expect(page.getByTestId("queued-state")).toContainText("Queued as job");
  await expect(page.getByTestId("queued-state")).toContainText("Rendering, then upload");
  const jobLink = page.getByTestId("queued-job-link");
  await expect(jobLink).toHaveAttribute("href", /^\/activity\/.+/);
  await expect(page.getByTestId("approve-primary")).toHaveCount(0);
});

test("a draft without a plan can queue detection", async ({ page }) => {
  await page.goto("/teaching/s-05");
  const detect = page.getByTestId("approve-primary");
  await expect(detect).toHaveText("Run cut detection");
  await detect.click();
  await expect(page.getByTestId("queued-state")).toContainText("Cut detection queued");
  await expect(page.getByTestId("queued-job-link")).toHaveAttribute("href", /^\/activity\/.+/);
});

test("a published teaching has no primary action", async ({ page }) => {
  await page.goto("/teaching/s-03");
  await expect(page.getByTestId("sermon-completed")).toBeVisible();
  await expect(page.getByTestId("approve-primary")).toHaveCount(0);
  await expect(page.getByTestId("more-actions-trigger")).toBeVisible();
});
