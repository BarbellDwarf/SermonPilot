import { describe, expect, it } from "vitest";
import {
  isSettingsSection,
  legacySettingsPath,
  settingsSectionsForRole,
} from "./settingsSections";

describe("Settings sections", () => {
  it("splits preferences and access out of the old General section", () => {
    expect(settingsSectionsForRole("admin").filter((section) => section.group === "Preferences"))
      .toEqual([
        { id: "preferences", label: "Preferences", group: "Preferences" },
      ]);
    expect(settingsSectionsForRole("admin").filter((section) => section.group === "Access"))
      .toEqual([{ id: "access", label: "Users", group: "Access" }]);
    expect(settingsSectionsForRole("admin").map((section) => section.group)).not.toContain("System");
  });

  it("folds General processing and prompt templates into Automation", () => {
    const automation = settingsSectionsForRole("admin").filter(
      (section) => section.group === "Automation",
    );
    expect(automation).toEqual([{ id: "automation", label: "Automation", group: "Automation" }]);
  });

  it("keeps Users admin-only", () => {
    expect(isSettingsSection("access")).toBe(true);
    expect(settingsSectionsForRole("user").some((section) => section.id === "access")).toBe(false);
  });

  it("rejects the retired General route and unknown sections", () => {
    expect(isSettingsSection("general")).toBe(false);
    expect(isSettingsSection("unknown")).toBe(false);
  });
});

describe("legacy Settings links", () => {
  it.each([
    ["/settings", "/settings/preferences"],
    ["/settings?section=general", "/settings/preferences"],
    ["/settings?section=unknown", "/settings/preferences"],
    ["/settings?section=backup", "/settings/backup"],
    ["/settings?section=prompts", "/settings/automation"],
  ])("maps %s to %s", (from, to) => {
    const url = new URL(from, "https://example.test");
    expect(legacySettingsPath(url.search, url.hash)).toBe(to);
  });

  it("keeps the cloud OAuth return on the Cloud section", () => {
    expect(legacySettingsPath("?cloud=connected&name=shared", "#files")).toBe(
      "/settings/cloud?cloud=connected&name=shared#files",
    );
  });

  it("preserves unrelated query and hash values", () => {
    expect(legacySettingsPath("?section=audio&focus=gain", "#levels")).toBe(
      "/settings/audio?focus=gain#levels",
    );
  });
});
