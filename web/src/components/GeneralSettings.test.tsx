import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.stubEnv("VITE_API_MODE", "live");

function mockResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function stubApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/config/sections/general")) {
        return Promise.resolve(
          mockResponse({
            section: "general",
            fields: {
              dry_run: { value: true, source: "SA_DRY_RUN", secret: false },
              debug: { value: false, source: "db", secret: false },
              hashtag_verification: { value: true, source: "default", secret: false },
              save_original_audio: { value: true, source: "SA_KEEP_ORIGINAL", secret: false },
              save_transcript: { value: true, source: "db", secret: false },
            },
          }),
        );
      }
      if (url.includes("/api/me/output-dir")) {
        return Promise.resolve(mockResponse({ output_dir: "processed_sermons" }));
      }
      if (url.includes("/api/cloud/remotes")) {
        return Promise.resolve(mockResponse({ items: [], total: 0 }));
      }
      return Promise.resolve(mockResponse({ detail: "unexpected request" }));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("GeneralSettingsSection environment overrides", () => {
  it("shows the override on the control row instead of a page-level callout", async () => {
    stubApi();
    const { GeneralSettingsSection } = await import("./GeneralSettings");
    render(<GeneralSettingsSection show={() => {}} />);

    const toggle = await screen.findByRole("switch", { name: "Dry Run Mode (default)" });
    const row = toggle.closest("label");
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText("SA_DRY_RUN")).toBeTruthy();

    const keepRow = screen.getByRole("switch", { name: "Save Original Audio" }).closest("label");
    expect(within(keepRow as HTMLElement).getByText("SA_KEEP_ORIGINAL")).toBeTruthy();

    expect(screen.queryByText(/Overridden by the environment:/)).toBeNull();
  });
});
