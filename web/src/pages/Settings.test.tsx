import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import { withProviders } from "../test/harness";

const mocks = vi.hoisted(() => ({
  listUsers: vi.fn(),
  retirement: vi.fn(),
  status: vi.fn(),
  patchMe: vi.fn(),
}));

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    isLive: true,
    api: { ...actual.api, status: mocks.status },
    metaApi: { ...actual.metaApi, retirement: mocks.retirement },
    adminApi: { ...actual.adminApi, listUsers: mocks.listUsers },
    meApi: { ...actual.meApi, patch: mocks.patchMe },
  };
});

const TABS = [
  "General",
  "Audio & Transcription",
  "LLM Providers",
  "SermonAudio",
  "Cloud Mounts",
  "Descriptions & Prompts",
  "Backup & Restore",
  "Appearance & Account",
  "Users",
  "System",
];

function renderSettings(route = "/settings") {
  return withProviders(<Settings user={{ display_name: "Operator", role: "admin" }} />, route);
}

function sectionCards(): string[] {
  const panel = screen.getByRole("tabpanel");
  return Array.from(panel.querySelectorAll("section")).map((s) =>
    (s.querySelector("h2")?.textContent ?? "").trim(),
  );
}

beforeEach(() => {
  mocks.listUsers.mockResolvedValue({ users: [] });
  mocks.retirement.mockResolvedValue({ streamlit_ready: false });
  mocks.status.mockResolvedValue({
    checked_at: "2026-09-06T12:00:00",
    status: {
      sermonaudio_api: { status: "ok", message: "Connected", details: "12 teachings available" },
      database: { status: "ok", message: "Healthy", details: "small" },
      llm_primary: { status: "ok", message: "Configured", details: "gpt-4o-mini" },
      local_storage: { status: "warning", message: "Low disk space", details: "0.4GB free" },
      processing_queue: { status: "ok", message: "No active processing", details: "0 queued" },
      system_resources: { status: "unknown", message: "State not determined", details: "psutil missing" },
    },
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Settings is a short tab list, not one long scroll", () => {
  it("offers every section by name", () => {
    renderSettings();
    for (const label of TABS) {
      expect(screen.getByRole("tab", { name: label })).toBeTruthy();
    }
    expect(screen.getAllByRole("tab")).toHaveLength(TABS.length);
  });

  it("keeps each tab to at most two cards", async () => {
    const user = userEvent.setup();
    renderSettings();
    for (const label of TABS) {
      await user.click(screen.getByRole("tab", { name: label }));
      expect(sectionCards().length, `${label} should not be a long scroll`).toBeLessThanOrEqual(2);
    }
  });

  it("opens on General and does not stack account, users, and system under it", async () => {
    renderSettings();
    expect(screen.getByRole("tab", { name: "General" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("heading", { name: "Users" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "System" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Account" })).toBeNull();
  });

  it("keeps the theme control, which used to live inside the General stack", async () => {
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByRole("tab", { name: "Appearance & Account" }));
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /dark/i })).toBeTruthy();
  });
});

describe("Settings deep links", () => {
  it("opens the tab named in the query string", () => {
    renderSettings("/settings?tab=sermonaudio");
    expect(screen.getByRole("tab", { name: "SermonAudio" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("heading", { name: /SermonAudio/ })).toBeTruthy();
  });

  it("keeps the old cloud=connected link working", () => {
    renderSettings("/settings?cloud=connected");
    expect(screen.getByRole("tab", { name: "Cloud Mounts" }).getAttribute("aria-selected")).toBe("true");
  });

  it("falls back to General for a tab that does not exist", () => {
    renderSettings("/settings?tab=nope");
    expect(screen.getByRole("tab", { name: "General" }).getAttribute("aria-selected")).toBe("true");
  });

  it("writes the chosen tab into the address so the link can be shared", async () => {
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByRole("tab", { name: "LLM Providers" }));
    await waitFor(() => expect(screen.getByTestId("location-search").textContent).toContain("tab=llm"));
  });
});

describe("Settings System tab reports the server's own account", () => {
  async function openSystem(user: ReturnType<typeof userEvent.setup>) {
    renderSettings("/settings?tab=system");
    await user.click(screen.getByRole("tab", { name: "System" }));
    return screen.getByRole("tabpanel");
  }

  it("shows what the server says rather than invented storage bars", async () => {
    const user = userEvent.setup();
    const panel = await openSystem(user);
    await within(panel).findByText("Output folder");
    expect(within(panel).getByText("12 teachings available")).toBeTruthy();
    expect(within(panel).getByText("0.4GB free")).toBeTruthy();
    expect(panel.textContent ?? "").not.toContain("61 GB free of 120 GB");
    expect(panel.textContent ?? "").not.toContain("mock");
  });

  it("distinguishes not measured from a warning", async () => {
    const user = userEvent.setup();
    const panel = await openSystem(user);
    await within(panel).findByText("Machine load");
    expect(within(panel).getByText("Not measured")).toBeTruthy();
    expect(within(panel).getByText("Warning")).toBeTruthy();
  });

  it("offers a retry when the server report cannot be read", async () => {
    mocks.status.mockRejectedValue(new Error("bridge down"));
    const user = userEvent.setup();
    const panel = await openSystem(user);
    const retry = within(panel).getByRole("button", { name: "Try again" });
    retry.click();
    await waitFor(() => expect(mocks.status.mock.calls.length).toBeGreaterThan(1));
  });

  it("tells the operator how to point their domain at this console", async () => {
    const user = userEvent.setup();
    const panel = await openSystem(user);
    expect(within(panel).getByText(/only interface/)).toBeTruthy();
    expect(panel.textContent ?? "").toContain("8504");
  });

  it("says the domain is pointed here once the operator confirms it", async () => {
    mocks.retirement.mockResolvedValue({ console_ready: true });
    const user = userEvent.setup();
    const panel = await openSystem(user);
    expect(await within(panel).findByText(/pointed here/)).toBeTruthy();
  });
});