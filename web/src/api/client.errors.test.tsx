import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.stubEnv("VITE_API_MODE", "live");

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

async function loadError(fetchImpl: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(fetchImpl));
  const client = await import("./client");
  const hooks = await import("./hooks");
  let error: unknown = null;
  try {
    await client.api.sermon("does-not-exist-123");
  } catch (err) {
    error = err;
  }
  return { client, hooks, error };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("live GET failures", () => {
  it("throws an ApiError carrying the response status", async () => {
    const { client, error } = await loadError(() =>
      Promise.resolve(jsonResponse({ detail: "not found" }, 404)),
    );
    expect(error).toBeInstanceOf(client.ApiError);
    expect((error as { status: number }).status).toBe(404);
  });

  it("renders the not-found copy for a 404 GET", async () => {
    const { hooks, error } = await loadError(() =>
      Promise.resolve(jsonResponse({ detail: "not found" }, 404)),
    );
    render(
      <hooks.QueryError
        message={hooks.describeLoadError(error, "This teaching", NOT_FOUND) ?? ""}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByText(NOT_FOUND)).toBeTruthy();
    expect(screen.queryByText(/API bridge/)).toBeNull();
  });

  it("renders the server-error copy for a 500 GET and keeps the parsed detail", async () => {
    const { hooks, error } = await loadError(() =>
      Promise.resolve(jsonResponse({ detail: { message: "boom" } }, 500)),
    );
    expect((error as Error).message).toBe("boom");
    render(
      <hooks.QueryError
        message={hooks.describeLoadError(error, "This teaching", NOT_FOUND) ?? ""}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByText("Server error (500). Try again in a moment.")).toBeTruthy();
    expect(screen.queryByText(/API bridge/)).toBeNull();
  });

  it("renders the API bridge copy when fetch rejects", async () => {
    const { hooks, error } = await loadError(() =>
      Promise.reject(new TypeError("Failed to fetch")),
    );
    render(
      <hooks.QueryError
        message={hooks.describeLoadError(error, "This teaching", NOT_FOUND) ?? ""}
        onRetry={() => {}}
      />,
    );
    expect(
      screen.getByText(
        "This teaching could not be loaded. Check the API bridge and try again. (Failed to fetch)",
      ),
    ).toBeTruthy();
  });
});
