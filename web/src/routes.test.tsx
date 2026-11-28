import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { routes } from "./routes";

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(routes, { initialEntries: [initialEntry] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("route table", () => {
  it.each([
    ["/jobs", "/activity"],
    ["/jobs/job-1", "/activity/job-1"],
    ["/library/s-01", "/teaching/s-01"],
    ["/settings", "/settings/preferences"],
  ])("redirects %s to %s", async (from, to) => {
    const router = renderRoute(from);

    await waitFor(() => expect(router.state.location.pathname).toBe(to));
  });

  it("keeps search and hash when redirecting a legacy teaching link", async () => {
    const router = renderRoute("/library/s-01?tab=plan#cuts");

    await waitFor(() => expect(router.state.location.pathname).toBe("/teaching/s-01"));
    expect(router.state.location.search).toBe("?tab=plan");
    expect(router.state.location.hash).toBe("#cuts");
  });

  it("renders NotFound with a link back to the Inbox", () => {
    renderRoute("/missing");

    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to Inbox" }).getAttribute("href")).toBe("/");
  });

  it("moves focus to main on client navigation but not on first render", async () => {
    const user = userEvent.setup();
    renderRoute("/library");
    const main = screen.getByRole("main");

    expect(document.activeElement).not.toBe(main);

    await user.click(
      within(screen.getByRole("navigation", { name: "Sections" })).getByRole("link", {
        name: "Activity",
      }),
    );

    await waitFor(() => expect(document.activeElement).toBe(main));
  });
});
