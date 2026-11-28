export const SETTINGS_GROUPS = [
  "Pipeline",
  "Connections",
  "Automation",
  "Advanced",
  "Access",
  "Preferences",
] as const;

export const SETTINGS_SECTIONS = [
  { id: "audio", label: "Audio", group: "Pipeline" },
  { id: "transcription", label: "Transcription", group: "Pipeline" },
  { id: "validation", label: "Validation", group: "Pipeline" },
  { id: "resources", label: "Resources", group: "Pipeline" },
  { id: "llm", label: "LLM providers", group: "Connections" },
  { id: "sermonaudio", label: "SermonAudio accounts", group: "Connections" },
  { id: "cloud", label: "Cloud mounts", group: "Connections" },
  { id: "automation", label: "Automation", group: "Automation" },
  { id: "storage", label: "Storage", group: "Advanced" },
  { id: "backup", label: "Backup & restore", group: "Advanced" },
  { id: "access", label: "Users", group: "Access" },
  { id: "preferences", label: "Preferences", group: "Preferences" },
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];
export type SettingsSectionId = SettingsSection["id"];

export function isSettingsSection(value: string | null | undefined): value is SettingsSectionId {
  return SETTINGS_SECTIONS.some((section) => section.id === value);
}

export function settingsSectionsForRole(role: string | undefined): SettingsSection[] {
  return SETTINGS_SECTIONS.filter((section) => section.id !== "access" || role === "admin");
}

export function legacySettingsPath(search: string, hash: string): string {
  const params = new URLSearchParams(search);
  const requested = params.get("section");
  const section = requested === "prompts" ? "automation" : requested;
  const target =
    params.get("cloud") === "connected"
      ? "cloud"
      : isSettingsSection(section)
        ? section
        : "preferences";
  params.delete("section");
  const query = params.toString();
  return `/settings/${target}${query ? `?${query}` : ""}${hash}`;
}
