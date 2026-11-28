import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Navigate, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  mediaApi: { waveform: async () => ({ peaks: [], duration: 0 }) },
  isLive: false,
  adminApi: { listUsers: vi.fn().mockResolvedValue({ users: [] }) },
  meApi: {
    patch: vi.fn().mockResolvedValue({
      id: "mock-admin",
      username: "admin",
      display_name: "Sample Admin",
      role: "admin",
      is_active: true,
    }),
  },
}));

vi.mock("../components/GeneralSettings", () => ({
  GeneralSettingsSection: () => <p>Automation defaults panel</p>,
}));
vi.mock("../components/AudioSettings", async () => {
  const React = await import("react");
  const { SaveBar } = await import("../components/ui");
  return {
    AudioSettingsSection: () => {
      const [dirty, setDirty] = React.useState(false);
      return (
        <div>
          <p>Audio panel</p>
          <button type="button" onClick={() => setDirty(true)}>
            Make audio dirty
          </button>
          <SaveBar
            dirty={dirty}
            onSave={() => setDirty(false)}
            label="Save audio settings"
          />
        </div>
      );
    },
  };
});
vi.mock("../components/TranscriptionSettings", () => ({
  TranscriptionSettingsSection: () => <p>Transcription panel</p>,
}));
vi.mock("../components/ValidationSettings", () => ({
  ValidationSettingsSection: () => <p>Validation panel</p>,
}));
vi.mock("../components/LlmConnections", () => ({
  LlmConnectionsSection: () => <p>LLM panel</p>,
}));
vi.mock("../components/SermonAudioAccounts", () => ({
  SermonAudioAccountsSection: () => <p>SermonAudio panel</p>,
}));
vi.mock("../components/SermonAudioCredentials", () => ({
  SermonAudioCredentialsSection: () => <p>Fallback credentials panel</p>,
}));
vi.mock("../components/CloudMounts", () => ({
  CloudMountsSection: () => <p>Cloud panel</p>,
}));
vi.mock("../components/PromptTemplates", () => ({
  PromptTemplatesSection: () => <p>Prompts panel</p>,
}));
vi.mock("../components/ConfigBackup", () => ({
  ConfigBackupSection: () => <p>Backup panel</p>,
}));
vi.mock("../components/ResourceSettings", () => ({
  ResourceSettingsSection: () => <p>Resources panel</p>,
}));
vi.mock("../components/StorageSettings", () => ({
  StorageSettingsSection: () => <p>Storage panel</p>,
}));

import { Settings } from "./Settings";

function renderSettings(entry = "/settings/preferences", role = "admin") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      {
        path: "/settings/:section",
        element: (
          <Settings
            user={{ display_name: "Sample Admin", role }}
            theme="dark"
            previewTheme={vi.fn()}
            setTheme={vi.fn().mockResolvedValue(undefined)}
          />
        ),
      },
      { path: "/settings", element: <Navigate to="/settings/preferences" replace /> },
      { path: "*", element: <Navigate to="/settings/preferences" replace /> },
    ],
    { initialEntries: [entry] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("Settings shell", () => {
  it("shows Appearance and Account under Preferences", () => {
    renderSettings();

    expect(screen.getByRole("region", { name: "Appearance" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Account" })).toBeTruthy();
    expect(screen.queryByText("Automation defaults panel")).toBeNull();
    expect(screen.getAllByText("Preferences").length).toBeGreaterThan(0);
  });

  it("moves Users into the admin-only Access section", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Users" }));
    expect(screen.getByRole("region", { name: "Users" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Appearance" })).toBeNull();
  });

  it("redirects Access for a non-admin", async () => {
    const router = renderSettings("/settings/access", "user");

    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/preferences"));
    expect(screen.getByRole("region", { name: "Appearance" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Users" })).toBeNull();
  });

  it("folds processing defaults and prompt templates into Automation", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Automation" }));
    expect(screen.getByText("Automation defaults panel")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Processing defaults" })).toBeTruthy();
    expect(screen.getByText("Prompts panel")).toBeTruthy();
    expect(screen.queryByText("System")).toBeNull();
    expect(screen.queryByText("Prompts", { selector: "p" })).toBeNull();
  });

  it("switches sections with URL updates", async () => {
    const user = userEvent.setup();
    const router = renderSettings();

    await user.click(screen.getByRole("button", { name: "Audio" }));
    expect(router.state.location.pathname).toBe("/settings/audio");
    expect(router.state.location.search).toBe("");
    expect(screen.getByText("Audio panel")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Backup & restore" }));
    expect(router.state.location.pathname).toBe("/settings/backup");
    expect(screen.getByText("Backup panel")).toBeTruthy();
  });

  it("names the active section in the compact select", async () => {
    const user = userEvent.setup();
    const router = renderSettings();

    const select = screen.getByTestId("settings-section-select") as HTMLSelectElement;
    expect(select.value).toBe("preferences");

    await user.selectOptions(select, "transcription");
    expect(router.state.location.pathname).toBe("/settings/transcription");
    expect(screen.getByText("Transcription panel")).toBeTruthy();
  });

  it.each(["/settings/general", "/settings/unknown"])(
    "redirects %s to Preferences",
    async (entry) => {
      const router = renderSettings(entry);
      await waitFor(() => expect(router.state.location.pathname).toBe("/settings/preferences"));
      expect(screen.getByRole("region", { name: "Appearance" })).toBeTruthy();
    },
  );

  it("asks before discarding a dirty section and stays when declined", async () => {
    const user = userEvent.setup();
    const router = renderSettings("/settings/audio");

    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));
    expect(screen.getByText("Unsaved changes.")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Automation" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(
      screen.getByText("This section has unsaved changes. Leave and discard them?"),
    ).toBeTruthy();
    expect(screen.getByText("Audio panel")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.state.location.pathname).toBe("/settings/audio");
  });

  it("treats Escape as Stay", async () => {
    const user = userEvent.setup();
    renderSettings("/settings/audio");

    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));
    await user.click(screen.getByRole("button", { name: "Automation" }));
    expect(screen.getByRole("dialog")).toBeTruthy();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Audio panel")).toBeTruthy();
  });

  it("leaves after Discard and clears the named save surface after save", async () => {
    const user = userEvent.setup();
    const router = renderSettings("/settings/audio");

    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));
    await user.click(screen.getByRole("button", { name: "Automation" }));
    await user.click(screen.getByRole("button", { name: "Discard" }));
    expect(router.state.location.pathname).toBe("/settings/automation");
    expect(screen.getByText("Prompts panel")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Audio" }));
    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));
    await user.click(screen.getByRole("button", { name: "Save audio settings" }));
    expect(screen.getByText("Saved.")).toBeTruthy();
    expect(screen.queryByText("Unsaved changes.")).toBeNull();
  });

  it("shows one save surface when two Preference cards are dirty", async () => {
    const user = userEvent.setup();
    renderSettings();

    await user.click(screen.getByRole("radio", { name: "light" }));
    await user.clear(screen.getByLabelText("Display name"));
    await user.type(screen.getByLabelText("Display name"), "River");

    expect(screen.getAllByTestId("settings-save-bar")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Save account" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Save account" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save appearance" })).toBeTruthy(),
    );
    expect(screen.getAllByTestId("settings-save-bar")).toHaveLength(1);
  });

  it("blocks a route leave until the operator discards changes", async () => {
    const user = userEvent.setup();
    const router = renderSettings("/settings/audio");
    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));

    act(() => {
      void router.navigate("/settings/backup");
    });
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/settings/audio");

    await user.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/backup"));
    expect(screen.getByText("Backup panel")).toBeTruthy();
  });
});
