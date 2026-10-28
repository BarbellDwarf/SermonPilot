import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("../api/client", () => {
  class AuthError extends Error {
    needsBootstrap: boolean;
    constructor(message: string, needsBootstrap: boolean) {
      super(message);
      this.needsBootstrap = needsBootstrap;
    }
  }
  return {
    isLive: true,
    AuthError,
    auth: {
      me: mocks.me,
      login: mocks.login,
      logout: mocks.logout,
    },
  };
});

import { AuthGate } from "./AuthGate";

const USER = {
  id: "u-1",
  username: "operator",
  display_name: "Operator",
  role: "admin",
  is_active: true,
};

describe("AuthGate deep links", () => {
  it("returns to the requested page after signing in", async () => {
    const user = userEvent.setup();
    mocks.me.mockRejectedValue(new Error("authentication required"));
    mocks.login.mockResolvedValue({ token: "t", user: USER });

    render(
      <MemoryRouter initialEntries={["/library/s-1"]}>
        <AuthGate>
          {() => (
            <Routes>
              <Route path="/" element={<p>Home page</p>} />
              <Route path="/library/:id" element={<p>Requested library record</p>} />
            </Routes>
          )}
        </AuthGate>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeTruthy();
    await user.type(screen.getByLabelText("Username"), "operator");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Requested library record")).toBeTruthy();
    expect(screen.queryByText("Home page")).toBeNull();
  });
});
