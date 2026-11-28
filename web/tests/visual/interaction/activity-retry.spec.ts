import { test, expect, type Page } from "@playwright/test";

const failedJob = {
  id: "job-1037",
  type: "sermon_processing",
  title: "Process sermon · Midweek Class · Sample Speaker",
  description: 'Running the processing pipeline for "Midweek Class" (Sample Speaker, 2026-10-23).',
  status: "failed",
  progress: 68,
  created_at: "2026-10-23 15:03:00",
  completed_at: "2026-10-23 15:19:00",
  duration: "16m",
  error: "Upload rejected: gateway timeout",
};

const queuedJob = {
  ...failedJob,
  id: "job-9000",
  title: "(Retry) Process sermon · Midweek Class · Sample Speaker",
  status: "queued",
  progress: 0,
  created_at: "2026-10-27 21:07:00",
  completed_at: null,
  duration: "—",
  error: null,
};

function jobDetail(job: typeof failedJob) {
  return {
    ...job,
    logs: ["job accepted", "upload rejected: gateway timeout"],
    parameters: { sermon_id: "s-02", form_data: { whisper_model: "base" } },
    result: null,
  };
}

async function mockLiveJobs(page: Page) {
  let retried = false;
  let retryPosts = 0;
  let authRequests = 0;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/auth/me") {
      authRequests += 1;
      await route.fulfill({
        json: {
          id: "mock-admin",
          username: "admin",
          display_name: "Admin",
          role: "admin",
          is_active: true,
        },
      });
      return;
    }

    if (path === "/api/jobs/job-1037/retry" && request.method() === "POST") {
      retryPosts += 1;
      retried = true;
      await route.fulfill({ status: 202, json: { job_id: "job-9000", status: "queued" } });
      return;
    }

    if (path === "/api/jobs" && request.method() === "GET") {
      const status = url.searchParams.get("status");
      const items = status === "failed" ? [failedJob] : retried && status === "active" ? [queuedJob] : [];
      await route.fulfill({ json: { items, total: items.length } });
      return;
    }

    if (path === "/api/jobs/job-1037") {
      await route.fulfill({ json: jobDetail(failedJob) });
      return;
    }

    if (path === "/api/jobs/job-9000") {
      await route.fulfill({ json: jobDetail(queuedJob) });
      return;
    }

    await route.fulfill({ status: 404, json: { detail: "not found" } });
  });

  return {
    retryPosts: () => retryPosts,
    authRequests: () => authRequests,
  };
}

test("mock retry creates one queued row, names its id, and preserves failed history", async ({ page }) => {
  await page.goto("/activity?state=failed");
  const failedItem = page.getByTestId("job-row-job-1037").locator("xpath=ancestor::li");

  await expect(failedItem.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(failedItem.getByRole("link", { name: "View teaching" })).toHaveAttribute(
    "href",
    "/teaching/s-02",
  );
  await expect(failedItem.getByRole("button", { name: "Cancel", exact: true })).toHaveCount(0);

  await failedItem.getByRole("button", { name: "Retry" }).click();

  await expect(page).toHaveURL(/\/activity\/(job-\d+)\?state=active$/);
  const newId = new URL(page.url()).pathname.split("/").pop() as string;
  await expect(page.getByTestId(`job-row-${newId}`)).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId(`job-row-${newId}`)).toContainText("QUEUED");
  await expect(page.getByText(new RegExp(`Retry queued as job ${newId}`))).toBeVisible();

  await page.getByRole("button", { name: /^Failed/ }).click();
  await expect(page.getByTestId("job-row-job-1037")).toBeVisible();
  await expect(page.getByTestId(`job-row-${newId}`)).toHaveCount(0);

  await page.getByRole("button", { name: /^Active/ }).click();
  await page.getByTestId(`job-row-${newId}`).click();
  await page.getByTestId(`job-detail-${newId}`).getByRole("link", { name: "View teaching" }).click();
  await expect(page).toHaveURL(/\/teaching\/s-02$/);
  await page.goBack();
  await expect(page.getByTestId(`job-row-${newId}`)).toHaveAttribute("aria-expanded", "true");
});

test("live retry posts once and expands the returned job id", async ({ page }) => {
  const calls = await mockLiveJobs(page);
  await page.goto("/activity?state=failed");
  await expect(page.getByTestId("job-row-job-1037")).toBeVisible();
  test.skip(calls.authRequests() === 0, "Requires a VITE_API_MODE=live build with intercepted API responses.");

  const failedItem = page.getByTestId("job-row-job-1037").locator("xpath=ancestor::li");
  await expect(failedItem.getByRole("button", { name: "Cancel", exact: true })).toHaveCount(0);
  await expect(failedItem.getByRole("link", { name: "View teaching" })).toHaveAttribute(
    "href",
    "/teaching/s-02",
  );
  await failedItem.getByRole("button", { name: "Retry" }).click();

  await expect(page).toHaveURL(/\/activity\/job-9000\?state=active$/);
  await expect(page.getByTestId("job-row-job-9000")).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("job-row-job-9000")).toContainText("QUEUED");
  await expect(page.getByText(/Retry queued as job job-9000/)).toBeVisible();
  expect(calls.retryPosts()).toBe(1);

  await page.getByRole("button", { name: /^Failed/ }).click();
  await expect(page.getByTestId("job-row-job-1037")).toBeVisible();
});
