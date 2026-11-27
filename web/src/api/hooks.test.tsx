import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ApiError } from "./client";
import { QueryError, describeLoadError } from "./hooks";

const NOT_FOUND = "This teaching is no longer in the library (it may have been applied or removed).";

function jsonResponse(body: unknown, status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    clone() {
      return this;
    },
  } as unknown as Response;
}

describe("mediaApi.waveform", () => {
  async function loadClient(mode: "mock" | "live") {
    vi.stubEnv("VITE_API_MODE", mode);
    vi.resetModules();
    return await import("./client");
  }

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("does not request the waveform in demo mode", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { mediaApi } = await loadClient("mock");
    await expect(mediaApi.waveform("s-01")).resolves.toEqual({ peaks: [], duration: 0 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requests the waveform endpoint in live mode", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ peaks: [0.2, 0.6], duration: 30 }, 200),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { mediaApi } = await loadClient("live");
    await expect(mediaApi.waveform("s-01")).resolves.toEqual({ peaks: [0.2, 0.6], duration: 30 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/media/sermons/s-01/waveform");
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("GET");
  });
});

describe("describeLoadError", () => {
  it("returns null when there is no error", () => {
    expect(describeLoadError(null, "This teaching")).toBeNull();
  });

  it("shows the not-found copy for a 404", () => {
    expect(describeLoadError(new ApiError("missing", 404), "This teaching", NOT_FOUND)).toBe(
      NOT_FOUND,
    );
  });

  it("shows the status for a 5xx", () => {
    expect(describeLoadError(new ApiError("boom", 500), "Jobs")).toBe(
      "Server error (500). Try again in a moment.",
    );
  });

  it("keeps the API bridge hint for a network failure and includes the reason", () => {
    expect(describeLoadError(new TypeError("Failed to fetch"), "Jobs")).toBe(
      "Jobs could not be loaded. Check the API bridge and try again. (Failed to fetch)",
    );
  });

  it("reports the status and reason for other API errors", () => {
    expect(describeLoadError(new ApiError("forbidden", 403), "Jobs")).toBe(
      "Jobs could not be loaded (403: forbidden).",
    );
  });

  it("uses the numeric status even when the error is not an ApiError instance", () => {
    const error = Object.assign(new Error("missing"), { status: 404 });
    expect(describeLoadError(error, "This teaching", NOT_FOUND)).toBe(NOT_FOUND);
    expect(describeLoadError(Object.assign(new Error("boom"), { status: 500 }), "Jobs")).toBe(
      "Server error (500). Try again in a moment.",
    );
  });
});

describe("QueryError", () => {
  it("renders the not-found message instead of the API bridge hint", () => {
    render(
      <QueryError
        message={describeLoadError(new ApiError("missing", 404), "This teaching", NOT_FOUND) ?? ""}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText(/no longer in the library/)).toBeTruthy();
    expect(screen.queryByText(/API bridge/)).toBeNull();
  });

  it("renders the server error copy for a 500", () => {
    render(
      <QueryError
        message={describeLoadError(new ApiError("boom", 500), "Home data") ?? ""}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText("Server error (500). Try again in a moment.")).toBeTruthy();
    expect(screen.queryByText(/API bridge/)).toBeNull();
  });
});
