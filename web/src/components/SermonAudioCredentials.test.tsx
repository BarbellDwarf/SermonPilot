import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiConfigField } from "../api/client";

const state = vi.hoisted(() => ({ fields: {} as Record<string, ApiConfigField> }));

vi.mock("../api/useConfigSection", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/useConfigSection")>();
  return {
    ...actual,
    useConfigSection: () => ({
      fields: state.fields,
      loaded: true,
      error: null,
      save: async () => {},
    }),
  };
});

import { SermonAudioCredentialsSection, sourceCopy } from "./SermonAudioCredentials";

describe("sourceCopy", () => {
  it("names the database, the default, and the environment", () => {
    expect(sourceCopy("db")).toBe("saved in the database");
    expect(sourceCopy("default")).toBe("not configured");
    expect(sourceCopy("SERMONAUDIO_API_KEY")).toBe(
      "set by environment: SERMONAUDIO_API_KEY",
    );
  });
});

describe("SermonAudioCredentialsSection", () => {
  beforeEach(() => {
    state.fields = {};
  });

  it("reports the environment as the source while it is winning", () => {
    state.fields = {
      api_key: {
        source: "SERMONAUDIO_API_KEY",
        secret: true,
        has_value: true,
        masked: "********1234",
      },
      broadcaster_id: {
        source: "SERMONAUDIO_BROADCASTER_ID",
        secret: false,
        value: "env-broadcaster",
      },
    };

    render(<SermonAudioCredentialsSection show={() => {}} />);

    expect(screen.getByText(/set by environment: SERMONAUDIO_API_KEY/)).toBeTruthy();
    expect(screen.getByText(/set by environment: SERMONAUDIO_BROADCASTER_ID/)).toBeTruthy();
    expect(screen.getByDisplayValue("env-broadcaster")).toBeTruthy();
  });

  it("reports a database value without naming the environment", () => {
    state.fields = {
      api_key: { source: "db", secret: true, has_value: true, masked: "********1234" },
      broadcaster_id: { source: "db", secret: false, value: "db-broadcaster" },
    };

    render(<SermonAudioCredentialsSection show={() => {}} />);

    expect(screen.getByText(/Broadcaster ID source: saved in the database/)).toBeTruthy();
    expect(screen.getByText(/API key source: saved in the database/)).toBeTruthy();
    expect(screen.getByDisplayValue("db-broadcaster")).toBeTruthy();
  });

  it("reports an unconfigured credential as not configured", () => {
    render(<SermonAudioCredentialsSection show={() => {}} />);

    expect(screen.getAllByText(/not configured/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/No key saved yet/)).toBeTruthy();
  });
});
