import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ApiError } from "./client";
import { QueryError, describeLoadError } from "./hooks";

const NOT_FOUND = "This teaching is no longer in the library (it may have been applied or removed).";

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
