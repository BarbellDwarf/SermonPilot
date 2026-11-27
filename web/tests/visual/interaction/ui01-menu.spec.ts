import { test, expect, type Locator, type Page } from "@playwright/test";

async function openMenu(page: Page, id: string) {
  const trigger = page.getByTestId(`library-actions-${id}`);
  await trigger.scrollIntoViewIfNeeded();
  await trigger.click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  return { trigger, menu };
}

async function expectEveryItemHitTestable(menu: Locator) {
  const items = menu.getByRole("menuitem");
  const count = await items.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const item = items.nth(index);
    await expect(item).toBeVisible();
    const hit = await item.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      const target = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return target === el || el.contains(target);
    });
    expect(hit, `menuitem ${index} is covered`).toBe(true);
  }
}

test.describe("UI-01 library row menu", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "both viewports are set per test");
  });

  test("first row preview stays on Sample Teaching 1 at 1440x900", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/library");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Library");

    const { menu } = await openMenu(page, "s-01");
    await expectEveryItemHitTestable(menu);

    await menu.getByRole("menuitem", { name: "Preview" }).click();

    await expect(page).toHaveURL(/\/library$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Library");
    await expect(page.locator("#library-preview-s-01")).toBeVisible();
    await expect(page.locator("#library-preview-s-03")).toHaveCount(0);
  });

  test("last row menu stays inside the viewport at 390x568", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 568 });
    await page.goto("/library");

    const { menu } = await openMenu(page, "s-06");
    const box = await menu.locator("..").boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(568);
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);

    await expectEveryItemHitTestable(menu);
  });

  test("Tab closes the menu and returns focus to the trigger", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/library");

    const { trigger, menu } = await openMenu(page, "s-01");
    await expect(menu.getByRole("menuitem").first()).toBeFocused();

    await page.keyboard.press("Tab");

    await expect(menu).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test("Escape closes the menu and returns focus to the trigger", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/library");

    const { trigger, menu } = await openMenu(page, "s-01");
    await expect(menu.getByRole("menuitem").first()).toBeFocused();

    await page.keyboard.press("Escape");

    await expect(menu).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});
