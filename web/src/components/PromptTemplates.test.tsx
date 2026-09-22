import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.stubEnv("VITE_API_MODE", "live");

const CONFIG = {
  templates: {
    title: { enabled: false, system: "", user: "title {transcript}" },
    cut_detection: { enabled: true, system: "custom system", user: "detect {transcript}" },
  },
  defaults: {
    title: { enabled: false, system: "", user: "builtin title {transcript}" },
    cut_detection: { enabled: true, system: "builtin system", user: "builtin {transcript}" },
  },
};

function mockResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function stubApi() {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(String(init.body)) as unknown) : undefined;
    calls.push({ url, method, body });
    if (url.includes("/api/prompts/config")) return Promise.resolve(mockResponse(CONFIG));
    return Promise.resolve(mockResponse({ detail: "unexpected request" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

async function renderSection() {
  const { PromptTemplatesSection } = await import("./PromptTemplates");
  render(<PromptTemplatesSection show={() => {}} />);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PromptTemplatesSection live wiring", () => {
  it("lists the Cut Detection task", async () => {
    stubApi();
    await renderSection();
    expect(await screen.findByText("Cut Detection")).toBeTruthy();
  });

  it("loads the effective cut-detection template from the prompts API", async () => {
    stubApi();
    await renderSection();
    expect(await screen.findByDisplayValue("detect {transcript}")).toBeTruthy();
    expect(screen.getByDisplayValue("custom system")).toBeTruthy();
  });

  it("saves edited templates back to the prompts API", async () => {
    const user = userEvent.setup();
    const { calls } = stubApi();
    await renderSection();

    const box = (await screen.findByDisplayValue("detect {transcript}")) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "next {transcript}" } });
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT" && c.url.includes("/api/prompts/config"));
      expect(put).toBeTruthy();
      expect(JSON.stringify(put?.body)).toContain("next {transcript}");
      expect(JSON.stringify(put?.body)).toContain('"enabled":true');
    });
  });
});
