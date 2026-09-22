import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewSermon } from "./NewSermon";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/new"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <NewSermon />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NewSermon demo mode", () => {
  it("browses the mock cloud fallback without a live API", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("tab", { name: "Cloud file" }));
    await user.selectOptions(screen.getByLabelText("Cloud remote"), "sermons-drive");
    expect(await screen.findByText("sample-sermon.mp3")).toBeTruthy();
  });

  it("never reports a queued job when the console is not live", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Choose file" }));
    await user.type(screen.getByLabelText("Title (required)"), "Sample Title");
    await user.type(screen.getByRole("combobox", { name: "Speaker" }), "Sample Speaker");
    fireEvent.change(screen.getByLabelText("Date (required)"), {
      target: { value: "2026-09-22" },
    });

    const submit = screen.getByRole("button", { name: "Start Processing" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
    await user.click(submit);

    const toast = await screen.findByText(/nothing was sent/);
    expect(toast.textContent).not.toContain("queued");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
