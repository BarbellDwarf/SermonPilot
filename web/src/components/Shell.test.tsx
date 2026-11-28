import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  isLive: true,
  mediaApi: { waveform: async () => ({ peaks: [], duration: 0 }) },
}));

import { Shell } from "./Shell";

const user = {
  id: "u-1",
  username: "sample-admin",
  display_name: "Sample Admin",
  role: "admin",
  is_active: true,
};

function renderShell({
  initialEntries = ["/"],
  onToggleTheme = vi.fn(),
  onLogout = vi.fn(),
} = {}) {
  const result = render(
    <MemoryRouter initialEntries={initialEntries}>
      <Shell dark onToggleTheme={onToggleTheme} user={user} onLogout={onLogout}>
        <Routes>
          <Route path="/" element={<p>inbox page</p>} />
          <Route path="/new" element={<p>new page</p>} />
          <Route path="/library" element={<p>library page</p>} />
          <Route path="/teaching/:id" element={<p>detail page</p>} />
          <Route path="/activity" element={<p>activity page</p>} />
          <Route path="/settings" element={<p>settings page</p>} />
          <Route path="/settings/:section" element={<p>settings page</p>} />
          <Route path="*" element={<p>unknown page</p>} />
        </Routes>
      </Shell>
    </MemoryRouter>,
  );
  return { ...result, onToggleTheme, onLogout };
}

describe("Shell chrome", () => {
  it("renders one brand block, the live pill, and one account trigger", () => {
    renderShell();

    expect(screen.getByRole("link", { name: "SermonPilot live" })).toBeTruthy();
    expect(screen.getByText("live")).toBeTruthy();
    expect(screen.getByTestId("account-menu-trigger")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Logout" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Open navigation" })).toBeNull();
    expect(screen.queryByText("admin")).toBeNull();
  });

  it("keeps role, settings, theme, and logout in the account menu", async () => {
    const userEvents = userEvent.setup();
    const { onToggleTheme, onLogout } = renderShell();

    await userEvents.click(screen.getByTestId("account-menu-trigger"));
    const menu = screen.getByRole("menu", { name: "Account menu for SA Sample Admin" });
    expect(screen.getByText("admin")).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Settings" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Switch to light theme" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Sign out" })).toBeTruthy();

    await userEvents.click(within(menu).getByRole("menuitem", { name: "Switch to light theme" }));
    expect(onToggleTheme).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();

    await userEvents.click(screen.getByTestId("account-menu-trigger"));
    await userEvents.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("navigates from the account menu and closes on Escape", async () => {
    const userEvents = userEvent.setup();
    renderShell();

    await userEvents.click(screen.getByTestId("account-menu-trigger"));
    await userEvents.click(screen.getByRole("menuitem", { name: "Settings" }));
    expect(screen.getByText("settings page")).toBeTruthy();

    await userEvents.click(screen.getByTestId("account-menu-trigger"));
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Settings" }));
    await userEvents.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(
      screen.getByRole("menuitem", { name: "Switch to light theme" }),
    );
    await userEvents.keyboard("{ArrowUp}");
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Settings" }));
    await userEvents.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(screen.getByTestId("account-menu-trigger"));
  });

  it("keeps five nav items in Inbox, Library, New teaching, Activity, Settings order", () => {
    renderShell();
    const labels = within(screen.getByRole("navigation", { name: "Sections" }))
      .getAllByRole("link")
      .map((link) => link.textContent?.trim());
    expect(labels).toEqual(["Inbox", "Library", "New teaching", "Activity", "Settings"]);
  });

  it("keeps the same nav membership and hrefs in both breakpoint treatments", () => {
    renderShell();
    const hrefs = (name: string) =>
      [...screen.getByRole("navigation", { name }).querySelectorAll("a")].map((a) =>
        a.getAttribute("href"),
      );
    expect(hrefs("Primary")).toEqual(hrefs("Sections"));
    expect(hrefs("Sections")).toEqual(["/", "/library", "/new", "/activity", "/settings"]);
  });

  it("centres New on mobile with a New teaching accessible name", () => {
    renderShell();
    const links = within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link");

    expect(links.map((link) => link.textContent?.trim())).toEqual([
      "Inbox",
      "Library",
      "New",
      "Activity",
      "Settings",
    ]);
    expect(links[Math.floor(links.length / 2)].getAttribute("aria-label")).toBe("New teaching");
  });

  it("uses one mobile nav treatment with no drawer and no header nav", () => {
    renderShell();

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Sections" })).toBeNull();
    expect(screen.getAllByText("New teaching")).toHaveLength(1);
    expect(screen.getAllByText("New")).toHaveLength(1);
  });
});

describe("Shell route metadata", () => {
  it.each([
    ["/", "Inbox · SermonPilot"],
    ["/new", "New teaching · SermonPilot"],
    ["/library", "Library · SermonPilot"],
    ["/library/s-01", "Teaching review · SermonPilot"],
    ["/teaching/s-01", "Teaching review · SermonPilot"],
    ["/activity", "Activity · SermonPilot"],
    ["/activity/job-1", "Activity · SermonPilot"],
    ["/settings", "Settings · SermonPilot"],
    ["/settings/preferences", "Settings · SermonPilot"],
    ["/missing", "Not found · SermonPilot"],
  ])("titles %s as %s", (path, title) => {
    renderShell({ initialEntries: [path] });
    expect(document.title).toBe(title);
  });

  it("moves focus to main on navigation and leaves it alone on first render", async () => {
    const userEvents = userEvent.setup();
    renderShell();
    const main = screen.getByRole("main");
    expect(main.getAttribute("tabindex")).toBe("-1");
    expect(document.activeElement).not.toBe(main);

    await userEvents.click(screen.getAllByRole("link", { name: "Library" })[0]);
    expect(screen.getByText("library page")).toBeTruthy();
    expect(document.activeElement).toBe(main);
  });

  it("does not move focus when only the query string changes", async () => {
    const userEvents = userEvent.setup();
    renderShell({ initialEntries: ["/?tab=one"] });
    const main = screen.getByRole("main");

    await userEvents.click(screen.getAllByRole("link", { name: "Inbox" })[0]);
    expect(screen.getByText("inbox page")).toBeTruthy();
    expect(document.activeElement).not.toBe(main);
  });
});
