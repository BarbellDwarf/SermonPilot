import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Home } from "./Home";
import { Library } from "./Library";
import { Shell } from "../components/Shell";
import { librarySermons, recentSermons } from "../mock/data";
import { toLibrarySermon, toSermonStatus } from "../api/hooks";
import type { ApiSermonListItem } from "../api/client";
import { withProviders } from "../test/harness";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, isLive: false };
});

function row(overrides: Partial<ApiSermonListItem>): ApiSermonListItem {
  return {
    id: "s-1",
    title: "Sample Teaching 1",
    speaker: "Speaker A",
    date: "2026-09-06",
    duration: "42:10",
    series: "Sample Series A",
    status: "processed",
    ...overrides,
  };
}

/**
 * Fixture titles keep their placeholder names on purpose, so they are removed
 * before the scan: they are data, not chrome, and they would otherwise satisfy
 * the check on their own. What is left is the console's own wording, which
 * names the thing a teaching and never a sermon. The app processes classes as
 * well as pulpit messages, so the narrower word would misdescribe half of it.
 *
 * The markup is flattened to spaced text rather than read through
 * `textContent`, because `textContent` runs neighbouring elements together
 * with no separator. Two labels side by side, "Search sermons" then "Sort
 * teachings", collapse into the single token "sermonsSort", and a word-boundary
 * pattern then matches nothing. That is the shape most of this console's chrome
 * takes, so the scan would pass on the very wording it exists to catch.
 *
 * The boundary in the negative pattern still matters. "SermonAudio" and
 * "SermonPilot" are proper nouns, and a bare /sermon/i would fail on the vendor
 * name the operator has to recognise.
 */
function consoleWording(): string {
  return document.body.innerHTML
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z]+;|&#\d+;/gi, " ")
    .replace(/\s+/g, " ")
    .replace(/Sample Teaching \d+/g, " ");
}

/**
 * The vocabulary is product surface, not a naming preference. A record that
 * reads "Ready" on one page and "Processed" on another makes the operator
 * translate between screens in their head, so it is asserted rather than
 * reviewed.
 */
describe("one noun and one status vocabulary", () => {
  it("maps every database status to a word the operator uses", () => {
    expect(toSermonStatus("processed")).toBe("uploaded");
    expect(toSermonStatus("draft")).toBe("draft");
    expect(toSermonStatus("error")).toBe("failed");
    expect(toSermonStatus("pending")).toBe("queued");
  });

  it("has no invented record state left over", () => {
    const words = new Set(librarySermons.map((s) => s.status));
    expect(words).toEqual(new Set(["uploaded", "draft", "queued", "failed"]));
  });

  it("falls back to queued for a status the database does not have", () => {
    expect(toSermonStatus("half-done")).toBe("queued");
    expect(toSermonStatus(undefined)).toBe("queued");
  });

  it("labels an uploaded record as uploaded, not as processed or ready", () => {
    expect(toLibrarySermon(row({ status: "processed" })).status).toBe("uploaded");
  });

  it("does not call a queued record rendered", () => {
    expect(toLibrarySermon(row({ status: "pending" })).status).toBe("queued");
  });

  it("keeps each Library card's status and duration on one line", async () => {
    withProviders(<Library />);
    await screen.findAllByText("Uploaded");
    for (const card of Array.from(document.querySelectorAll("ol > li"))) {
      const row = card.querySelector("li > a > div");
      expect(row?.className ?? "").toContain("flex-nowrap");
      // The status chip must not wrap: a two-line chip pushed the duration out
      // of line with every other card in the grid.
      const chip = row?.querySelector("span.rounded-full");
      expect(chip?.className ?? "").not.toContain("flex-wrap");
      expect(chip?.getBoundingClientRect().height ?? 0).toBeLessThan(40);
    }
  });

  it("uses one word for the thing on every page, and never says sermon", async () => {
    const home = withProviders(<Home />);
    await screen.findAllByText("Uploaded");
    expect(consoleWording()).toMatch(/teachings?/i);
    expect(consoleWording()).not.toMatch(/\bsermons?\b/i);
    home.unmount();

    withProviders(<Library />);
    await screen.findAllByText("Uploaded");
    expect(consoleWording()).toMatch(/teachings?/i);
    expect(consoleWording()).not.toMatch(/\bsermons?\b/i);
    expect(screen.getByRole("heading", { name: "Library" })).toBeTruthy();
  });

  it("shows the same status word for the same record on Home and in the Library", async () => {
    const uploaded = recentSermons.filter((s) => s.status === "uploaded");
    expect(uploaded.length).toBeGreaterThan(0);

    const home = withProviders(<Home />);
    await screen.findAllByText("Uploaded");
    expect(screen.getAllByText("Uploaded").length).toBe(uploaded.length);
    home.unmount();

    withProviders(<Library />);
    await screen.findAllByText("Uploaded");
    expect(screen.getAllByText("Uploaded").length).toBeGreaterThan(0);
    expect(screen.queryByText("Processed")).toBeNull();
    expect(screen.queryByText("Rendered — not uploaded")).toBeNull();
  });
});

describe("Home leads with what needs a decision", () => {
  it("lists the drafts and failures that need the operator, each one a link", async () => {
    withProviders(<Home />);
    const heading = await screen.findByRole("heading", { name: "Needs you" });
    await waitFor(() =>
      expect(
        within(heading.closest("section") as HTMLElement).queryByLabelText("Loading"),
      ).toBeNull(),
    );
    const scope = within(heading.closest("section") as HTMLElement);
    const links = scope.getAllByRole("link").filter((l) =>
      (l.getAttribute("href") ?? "").startsWith("/library/"),
    );
    const needsMe = recentSermons.filter((s) => s.status === "draft" || s.status === "failed");
    expect(needsMe.length).toBeGreaterThan(0);
    expect(links).toHaveLength(needsMe.length);
    for (const link of links) {
      expect(link.textContent ?? "").toMatch(/Review and publish|Retry or re-run/);
    }
  });

  it("puts Needs you above the system status, because it is the actionable one", async () => {
    withProviders(<Home />);
    const needs = await screen.findByRole("heading", { name: "Needs you" });
    const status = screen.getByRole("heading", { name: "System status" });
    expect(needs.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("counts every waiting record in the summary, not just the drafts", async () => {
    withProviders(<Home />);
    const heading = await screen.findByRole("heading", { name: "Needs you" });
    const scope = within(heading.closest("section") as HTMLElement);
    await waitFor(() =>
      expect(scope.queryByLabelText("Loading")).toBeNull(),
    );
    const rows = scope.getAllByRole("link").filter((l) =>
      (l.getAttribute("href") ?? "").startsWith("/library/"),
    );
    const stat = screen
      .getAllByText("Waiting for you")
      .map((label) => label.parentElement?.textContent ?? "")
      .find((text) => /\d/.test(text));
    expect(stat).toBeTruthy();
    expect(Number(stat?.replace(/\D/g, ""))).toBe(rows.length);
  });

  it("never truncates a title in Needs you, because the title is the whole point", async () => {
    withProviders(<Home />);
    const heading = await screen.findByRole("heading", { name: "Needs you" });
    const scope = within(heading.closest("section") as HTMLElement);
    await waitFor(() => expect(scope.queryByLabelText("Loading")).toBeNull());
    const rows = scope
      .getAllByRole("link")
      .filter((l) => (l.getAttribute("href") ?? "").startsWith("/library/"));
    expect(rows.length).toBeGreaterThan(0);
    for (const link of rows) {
      const title = link.querySelector("span.line-clamp-2");
      expect(title).toBeTruthy();
      expect(title?.className).not.toMatch(/\btruncate\b/);
    }
  });

  it("lists a queued job once, not in both Active jobs and Up next", () => {
    withProviders(<Home />);
    const titles = Array.from(
      document.querySelectorAll("main section li p.font-semibold"),
    ).map((p) => p.textContent?.trim() ?? "");
    const repeats = titles.filter((t, i) => titles.indexOf(t) !== i);
    expect(repeats).toEqual([]);
  });
});

describe("service health states", () => {
  afterEach(() => {
    vi.resetModules();
    vi.doUnmock("../api/client");
    vi.doMock("../api/client", async (importOriginal) => {
      const actual = await importOriginal<typeof import("../api/client")>();
      return { ...actual, isLive: false };
    });
  });

  it("shows an unmeasurable check as not measured rather than as a warning", async () => {
    vi.resetModules();
    vi.doMock("../api/client", async (importOriginal) => {
      const actual = await importOriginal<typeof import("../api/client")>();
      return {
        ...actual,
        isLive: true,
        api: {
          ...actual.api,
          status: async () => ({
            checked_at: "2026-09-06T12:00:00",
            status: {
              sermonaudio_api: {
                status: "ok",
                message: "API connected and authenticated",
                details: "1 teaching available",
              },
              database: { status: "ok", message: "Database healthy", details: "small" },
              llm_primary: {
                status: "unknown",
                message: "State not determined",
                details: "Settings could not be read, so this check did not run.",
              },
              local_storage: {
                status: "warning",
                message: "Low disk space",
                details: "0.4GB free. Open Settings, then the General tab, to change it.",
              },
            },
          }),
          jobs: async () => ({ items: [], total: 0 }),
          sermons: async () => ({ items: [], total: 0 }),
        },
      };
    });
    const { Home: LiveHome } = await import("./Home");
    withProviders(<LiveHome />);

    const heading = await screen.findByRole("heading", { name: "System status" });
    const scope = within(heading.closest("section") as HTMLElement);
    expect(await scope.findByText("Not measured")).toBeTruthy();
    expect(scope.getByText("Warning")).toBeTruthy();
    expect(scope.getAllByText("OK")).toHaveLength(2);
    expect(scope.getByText(/1 of 4 could not be measured/)).toBeTruthy();
    expect(scope.queryByText("ok")).toBeNull();
    expect(scope.queryByText("warn")).toBeNull();
    expect(scope.queryByText("error")).toBeNull();
    expect(scope.getByText("SermonAudio")).toBeTruthy();
    expect(scope.getByText("AI provider")).toBeTruthy();
    expect(screen.getByText("2/4")).toBeTruthy();
  });
});

describe("the header carries no developer scaffolding", () => {
  it("does not tell the operator which data mode the build is in", () => {
    withProviders(
      <Shell dark={false} theme="light" onToggleTheme={() => {}}>
        <p>body</p>
      </Shell>,
    );
    expect(screen.queryByText("mock")).toBeNull();
    expect(screen.queryByText("live")).toBeNull();
    expect(screen.getByRole("banner").textContent ?? "").not.toMatch(/\b(mock|live)\b/);
  });
});