import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  isLive: false,
  adminApi: { listUsers: vi.fn().mockResolvedValue({ users: [] }) },
  meApi: { patch: vi.fn() },
  metaApi: { retirement: vi.fn().mockResolvedValue({ streamlit_ready: false }) },
}));

vi.mock("../api/useUserSettings", () => ({
  useUserSettings: (_key: string, initial: unknown) => [
    initial,
    vi.fn().mockResolvedValue(undefined),
  ],
}));

vi.mock("../components/GeneralSettings", () => ({
  GeneralSettingsSection: () => <p>General panel</p>,
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
          <SaveBar dirty={dirty} saved={!dirty} onSave={() => setDirty(false)} />
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

import { Settings } from "./Settings";

function renderSettings(entry = "/settings") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Settings user={{ display_name: "Sample Admin", role: "admin" }} />
    </MemoryRouter>,
  );
}

describe("Settings shell", () => {
  it("switches sections from the desktop section list", async () => {
    const user = userEvent.setup();
    renderSettings();

    expect(screen.getByText("General panel")).toBeTruthy();
    for (const group of ["Pipeline", "Connections", "Prompts", "System"]) {
      expect(screen.getAllByText(group).length).toBeGreaterThan(0);
    }

    await user.click(screen.getByRole("button", { name: "Audio" }));
    expect(screen.getByText("Audio panel")).toBeTruthy();
    expect(screen.queryByText("General panel")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Prompt templates" }));
    expect(screen.getByText("Prompts panel")).toBeTruthy();
  });

  it("names the active section in the mobile select and switches with it", async () => {
    const user = userEvent.setup();
    renderSettings();

    const select = screen.getByTestId("settings-section-select") as HTMLSelectElement;
    expect(select.value).toBe("general");

    await user.selectOptions(select, "transcription");
    expect(select.value).toBe("transcription");
    expect(screen.getByText("Transcription panel")).toBeTruthy();
  });

  it("opens the section named in the URL", () => {
    renderSettings("/settings?section=backup");
    expect(screen.getByText("Backup panel")).toBeTruthy();
  });

  it("confirms before discarding a dirty section and keeps it when declined", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Audio" }));
    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));
    expect(screen.getByText("Unsaved changes.")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Prompt templates" }));
    expect(confirm).toHaveBeenCalled();
    expect(screen.getByText("Audio panel")).toBeTruthy();
    expect(screen.queryByText("Prompts panel")).toBeNull();
    confirm.mockRestore();
  });

  it("leaves a dirty section once the user confirms, and clears dirty after save", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderSettings();

    await user.click(screen.getByRole("button", { name: "Audio" }));
    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));
    await user.click(screen.getByRole("button", { name: "Prompt templates" }));
    expect(screen.getByText("Prompts panel")).toBeTruthy();
    expect(confirm).toHaveBeenCalled();
    confirm.mockRestore();

    await user.click(screen.getByRole("button", { name: "Audio" }));
    await user.click(screen.getByRole("button", { name: "Make audio dirty" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("Saved.")).toBeTruthy();
    expect(screen.queryByText("Unsaved changes.")).toBeNull();
  });
});
