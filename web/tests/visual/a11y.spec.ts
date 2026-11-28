import { readFileSync } from "node:fs";
import { test, expect, type Page } from "@playwright/test";

const PAGES = [
  { name: "inbox", path: "/" },
  { name: "library", path: "/library" },
  { name: "activity", path: "/activity" },
  { name: "settings", path: "/settings" },
  { name: "new-teaching", path: "/new" },
  { name: "review", path: "/teaching/s-01" },
] as const;

const THEMES = ["dark", "light"] as const;

const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const FAILING_IMPACTS = new Set(["serious", "critical"]);

const BASELINE_RULES = [
  "aria-prohibited-attr",
  "label-content-name-mismatch",
  "nested-interactive",
];

const AXE_SOURCE = readFileSync(
  new URL("../../node_modules/axe-core/axe.min.js", import.meta.url),
  "utf8",
);

interface AxeNode {
  target: string[];
  html: string;
  failureSummary?: string;
}

interface AxeViolation {
  id: string;
  impact: string | null;
  help: string;
  nodes: AxeNode[];
}

async function applyTheme(page: Page, theme: (typeof THEMES)[number]) {
  if (theme === "dark") return;
  const isLight = await page.locator("html").evaluate((el) => el.classList.contains("light"));
  if (isLight) return;
  await page.getByTestId("account-menu-trigger").click();
  await page.getByRole("menuitem", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveClass(/light/);
}

async function scan(page: Page): Promise<AxeViolation[]> {
  return page.evaluate(async (tags) => {
    const results = await (window as unknown as { axe: { run: Function } }).axe.run(
      document,
      { runOnly: { type: "tag", values: tags } },
    );
    return results.violations as AxeViolation[];
  }, AXE_TAGS);
}

function describe(violations: AxeViolation[]): string[] {
  return violations.flatMap((violation) =>
    violation.nodes.map(
      (node) => `${violation.id} (${violation.impact}) ${node.target.join(" ")}: ${violation.help}`,
    ),
  );
}

for (const theme of THEMES) {
  for (const target of PAGES) {
    test(`${target.name} ${theme} has no serious or critical axe findings`, async ({ page }) => {
      await page.addInitScript({ content: AXE_SOURCE });
      await page.goto(target.path);
      await applyTheme(page, theme);
      await page.waitForLoadState("networkidle");
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();

      const violations = await scan(page);
      const blocking = violations.filter(
        (violation) => violation.impact && FAILING_IMPACTS.has(violation.impact),
      );
      expect(describe(blocking)).toEqual([]);

      const ids = violations.map((violation) => violation.id);
      for (const rule of BASELINE_RULES) {
        expect(ids, `baseline rule ${rule} reappeared`).not.toContain(rule);
      }
      if (target.name === "review" && theme === "dark") {
        expect(ids, "dark Review regressed to a color-contrast failure").not.toContain(
          "color-contrast",
        );
      }
    });
  }
}
