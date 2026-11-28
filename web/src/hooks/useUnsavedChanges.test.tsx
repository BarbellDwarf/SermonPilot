import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { useUnsavedChanges } from "./useUnsavedChanges";

function Form({ when }: { when: boolean }) {
  const blocker = useUnsavedChanges(when);
  return (
    <div>
      <p>form</p>
      <p>blocker: {blocker.state}</p>
      <Link to="/other">other</Link>
    </div>
  );
}

function renderForm(when: boolean) {
  const router = createMemoryRouter(
    [
      { path: "/", element: <Form when={when} /> },
      { path: "/other", element: <p>other page</p> },
    ],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe("useUnsavedChanges", () => {
  it("blocks client navigation and warns on unload while dirty", async () => {
    const user = userEvent.setup();
    renderForm(true);

    await user.click(screen.getByRole("link", { name: "other" }));
    await waitFor(() => expect(screen.getByText("blocker: blocked")).toBeTruthy());
    expect(screen.getByText("form")).toBeTruthy();
    expect(screen.queryByText("other page")).toBeNull();

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("does nothing while clean", async () => {
    const user = userEvent.setup();
    renderForm(false);

    await user.click(screen.getByRole("link", { name: "other" }));
    expect(screen.getByText("other page")).toBeTruthy();

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});
