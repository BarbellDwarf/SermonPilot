import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiConfigField, ApiConnection } from "../api/client";
import componentSource from "./SermonAudioAccounts.tsx?raw";

const configState = vi.hoisted(() => ({ fields: {} as Record<string, ApiConfigField> }));

vi.mock("../api/useConfigSection", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/useConfigSection")>();
  return {
    ...actual,
    useConfigSection: () => ({
      fields: configState.fields,
      loaded: true,
      error: null,
      save: async () => {},
    }),
  };
});

import { SermonAudioAccountsSection } from "./SermonAudioAccounts";
import { SermonAudioCredentialsSection } from "./SermonAudioCredentials";

const BASE = "/api/me/connections/sermonaudio";

function json(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function noContent(): Response {
  return {
    ok: true,
    status: 204,
    json: async () => ({}),
    text: async () => "",
  } as unknown as Response;
}

function stubApi(initial: ApiConnection[], defaultId: string | null = null) {
  const rows = initial.map((r) => ({ ...r }));
  let def = defaultId;
  const calls: { url: string; method: string; body: Record<string, unknown> | undefined }[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const body = init?.body
      ? (JSON.parse(String(init.body)) as Record<string, unknown>)
      : undefined;
    calls.push({ url, method, body });

    if (method === "GET") {
      return Promise.resolve(json({ items: rows, total: rows.length, default_id: def }));
    }
    if (method === "PUT" && url.endsWith(`${BASE}/default`)) {
      def = body?.id as string;
      return Promise.resolve(json({ default_id: def }));
    }
    if (method === "POST") {
      const id = `sa-${rows.length + 1}`;
      const key = typeof body?.apiKey === "string" ? body.apiKey : "";
      const created: ApiConnection = {
        id,
        name: String(body?.name ?? ""),
        broadcasterId: String(body?.broadcasterId ?? ""),
        notes: String(body?.notes ?? ""),
        has_key: Boolean(key),
        masked_key: key ? `********${key.slice(-4)}` : "",
      };
      rows.push(created);
      if (def === null && key) def = id;
      return Promise.resolve(json(created, 201));
    }
    const match = url.match(new RegExp(`${BASE}/([^/?]+)$`));
    const id = match ? decodeURIComponent(match[1]) : "";
    const row = rows.find((r) => r.id === id);
    if (method === "PUT" && row) {
      if (typeof body?.name === "string") row.name = body.name;
      if (typeof body?.broadcasterId === "string") row.broadcasterId = body.broadcasterId;
      if (typeof body?.notes === "string") row.notes = body.notes;
      if (typeof body?.apiKey === "string" && body.apiKey) {
        row.has_key = true;
        row.masked_key = `********${body.apiKey.slice(-4)}`;
      }
      return Promise.resolve(json(row));
    }
    if (method === "DELETE" && row) {
      rows.splice(rows.indexOf(row), 1);
      if (def === id) def = null;
      return Promise.resolve(noContent());
    }
    return Promise.resolve(json({ detail: "unexpected request" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, rows };
}

function sampleRow(overrides: Partial<ApiConnection> = {}): ApiConnection {
  return {
    id: "sa-1",
    name: "Sample Chapel",
    broadcasterId: "sample-chapel",
    notes: "",
    has_key: true,
    masked_key: "********7890",
    ...overrides,
  };
}

beforeEach(() => {
  configState.fields = {};
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SermonAudioAccountsSection", () => {
  it("lists accounts from the connections API", async () => {
    const { calls } = stubApi([sampleRow()], "sa-1");
    render(<SermonAudioAccountsSection show={() => {}} />);

    expect(await screen.findByText("Sample Chapel")).toBeTruthy();
    expect(screen.getByText("sample-chapel")).toBeTruthy();
    expect(screen.getByText("********7890")).toBeTruthy();
    expect(screen.getByText(/API key saved in the database/)).toBeTruthy();
    expect(calls.some((c) => c.method === "GET" && c.url.includes(BASE))).toBe(true);
  });

  it("adds an account through the API and re-reads the list", async () => {
    const user = userEvent.setup();
    const { calls } = stubApi([]);
    render(<SermonAudioAccountsSection show={() => {}} />);

    expect(await screen.findByText(/No SermonAudio accounts configured/i)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Add SermonAudio account" }));
    await screen.findByRole("form", { name: "Account editor" });
    await user.type(screen.getByLabelText("Broadcaster display name"), "Sample Chapel");
    await user.type(screen.getByLabelText("Broadcaster ID"), "sample-chapel");
    await user.type(screen.getByLabelText("API key"), "sa-key-4321");
    await user.click(screen.getByRole("button", { name: "Add account to list" }));

    await waitFor(
      () => {
        const post = calls.find((c) => c.method === "POST" && c.url.includes(BASE));
        expect(post?.body).toMatchObject({
          name: "Sample Chapel",
          broadcasterId: "sample-chapel",
          apiKey: "sa-key-4321",
        });
      },
      { timeout: 3000 },
    );
    expect(await screen.findByText("Sample Chapel")).toBeTruthy();
    const reads = calls.filter((c) => c.method === "GET" && c.url.includes(BASE));
    expect(reads.length).toBeGreaterThanOrEqual(2);
  });

  it("edits an account through the API without sending the stored key", async () => {
    const user = userEvent.setup();
    const { calls } = stubApi([sampleRow()], "sa-1");
    render(<SermonAudioAccountsSection show={() => {}} />);

    await user.click(await screen.findByRole("button", { name: "Edit Sample Chapel" }));
    const nameInput = screen.getByLabelText("Broadcaster display name");
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Chapel");
    await user.click(screen.getByRole("button", { name: "Save account" }));

    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT" && c.url.endsWith("/sa-1"));
      expect(put?.body).toMatchObject({ name: "Renamed Chapel" });
      expect(put?.body).not.toHaveProperty("apiKey");
    });
    expect(await screen.findByText("Renamed Chapel")).toBeTruthy();
  });

  it("marks the default account through the API", async () => {
    const user = userEvent.setup();
    const { calls } = stubApi([sampleRow()]);
    render(<SermonAudioAccountsSection show={() => {}} />);

    await user.click(await screen.findByRole("button", { name: "Set Sample Chapel as default account" }));

    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT" && c.url.endsWith(`${BASE}/default`));
      expect(put?.body).toEqual({ id: "sa-1" });
    });
    expect(await screen.findByText("★ default")).toBeTruthy();
  });

  it("deletes an account through the API", async () => {
    const user = userEvent.setup();
    const { calls } = stubApi([sampleRow()], "sa-1");
    render(<SermonAudioAccountsSection show={() => {}} />);

    await user.click(await screen.findByRole("button", { name: "Delete Sample Chapel" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/sa-1"))).toBe(true);
    });
    expect(await screen.findByText(/No SermonAudio accounts configured/i)).toBeTruthy();
  });

  it("never renders a stored secret in full", async () => {
    const user = userEvent.setup();
    const full = "sa-live-secret-7890";
    stubApi([sampleRow({ masked_key: "********7890" })]);
    render(<SermonAudioAccountsSection show={() => {}} />);

    expect(await screen.findByText("********7890")).toBeTruthy();
    expect(screen.queryByText(full)).toBeNull();
    expect(document.body.textContent).not.toContain(full);

    await user.click(screen.getByRole("button", { name: "Edit Sample Chapel" }));
    const keyInput = screen.getByLabelText("API key") as HTMLInputElement;
    expect(keyInput.value).toBe("");
    expect(keyInput.type).toBe("password");
  });

  it("contains no mock copy", () => {
    expect(componentSource.toLowerCase()).not.toContain("mock");
    expect(componentSource).not.toContain("Nothing here calls the network");
  });
});

describe("SermonAudio accounts and fallback together", () => {
  it("shows the environment-sourced fallback credential when the store is empty", async () => {
    configState.fields = {
      api_key: {
        source: "SERMONAUDIO_API_KEY",
        secret: true,
        has_value: true,
        masked: "********1234",
      },
      broadcaster_id: {
        source: "SERMONAUDIO_BROADCASTER_ID",
        secret: false,
        value: "env-broadcaster",
      },
    };
    stubApi([]);
    render(
      <>
        <SermonAudioAccountsSection show={() => {}} />
        <SermonAudioCredentialsSection show={() => {}} />
      </>,
    );

    expect(await screen.findByText(/No SermonAudio accounts configured/i)).toBeTruthy();
    expect(screen.getByText(/set by environment: SERMONAUDIO_API_KEY/)).toBeTruthy();
    expect(screen.getByDisplayValue("env-broadcaster")).toBeTruthy();
  });
});
