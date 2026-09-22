import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import componentSource from "./LlmConnections.tsx?raw";
import { LlmConnectionsSection } from "./LlmConnections";
import type { ApiLlmConfig } from "../api/client";

const CONFIG: ApiLlmConfig = {
  primary: {
    role: "primary",
    enabled: true,
    provider: "ollama",
    preset: "ollama-cloud",
    model: "glm-5.3-flash:cloud",
    endpoint: "http://host.docker.internal:11434",
    numCtx: "32768",
    maxTokens: "16000",
    temperature: "0.7",
    hasKey: true,
    maskedKey: "********9f2a",
  },
  fallback: {
    role: "fallback",
    enabled: false,
    provider: "openai",
    preset: "openai",
    model: "gpt-4o-mini",
    endpoint: "https://api.openai.com/v1",
    numCtx: "",
    maxTokens: "",
    temperature: "",
    hasKey: false,
    maskedKey: "",
  },
  validator: {
    role: "validator",
    enabled: false,
    provider: "ollama",
    preset: "ollama",
    model: "gemma2:2b",
    endpoint: "http://localhost:11434",
    numCtx: "8192",
    maxTokens: "4000",
    temperature: "0.3",
    hasKey: false,
    maskedKey: "",
  },
  routing: {
    metadata: "primary",
    validation: "validator",
    transcription_assist: "primary",
    fallback: "fallback",
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
    if (url.includes("/api/llm/test-connection")) {
      return Promise.resolve(
        mockResponse({ ok: true, latency_ms: 250, model_echo: "glm-5.3-flash:cloud", error: null }),
      );
    }
    if (url.includes("/api/llm/config")) {
      return Promise.resolve(mockResponse(CONFIG));
    }
    return Promise.resolve(mockResponse({ detail: "unexpected request" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LlmConnectionsSection", () => {
  it("renders provider slots from the config API with the masked key", async () => {
    stubApi();
    render(<LlmConnectionsSection show={() => {}} />);

    expect(await screen.findByDisplayValue("glm-5.3-flash:cloud")).toBeTruthy();
    expect(screen.getByDisplayValue("http://host.docker.internal:11434")).toBeTruthy();
    expect(screen.getByDisplayValue("gpt-4o-mini")).toBeTruthy();
    expect(screen.getByDisplayValue("gemma2:2b")).toBeTruthy();
    expect(screen.getByText("********9f2a")).toBeTruthy();
  });

  it("shows the measured latency and echoed model after a connection test", async () => {
    const user = userEvent.setup();
    stubApi();
    render(<LlmConnectionsSection show={() => {}} />);

    const testButton = await screen.findByRole("button", { name: "Test Primary connection" });
    await user.click(testButton);

    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toContain("250 ms");
    });
    expect(screen.getByRole("status").textContent).toContain("glm-5.3-flash:cloud");
  });

  it("persists an edited slot through the config API", async () => {
    const user = userEvent.setup();
    const { calls } = stubApi();
    render(<LlmConnectionsSection show={() => {}} />);

    const modelInput = await screen.findByDisplayValue("glm-5.3-flash:cloud");
    await user.clear(modelInput);
    await user.type(modelInput, "glm-5.3-pro:cloud");
    await user.click(screen.getByRole("button", { name: "Save Primary provider" }));

    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT" && c.url.includes("/api/llm/config"));
      expect(put).toBeTruthy();
      expect(JSON.stringify(put?.body)).toContain("glm-5.3-pro:cloud");
    });
  });

  it("contains no mock copy", () => {
    expect(componentSource.toLowerCase()).not.toContain("mock");
  });
});
