import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiConfigField } from "./client";

const api = vi.hoisted(() => ({
  configSection: vi.fn(),
  configSave: vi.fn(),
  settingsGet: vi.fn(),
  settingsPut: vi.fn(),
}));

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return {
    ...actual,
    isLive: true,
    configApi: { section: api.configSection, save: api.configSave },
    settingsApi: { get: api.settingsGet, put: api.settingsPut },
  };
});

import { useConfigForm, useConfigSection } from "./useConfigSection";
import { useUserSettings } from "./useUserSettings";

const clients: QueryClient[] = [];

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function configFields(value: number): Record<string, ApiConfigField> {
  return { gain: { value, source: "db", secret: false } };
}

afterEach(() => {
  for (const client of clients.splice(0)) client.clear();
  vi.clearAllMocks();
});

describe("useConfigSection", () => {
  it("updates the cache optimistically and rolls back through one invalidation", async () => {
    api.configSection.mockResolvedValue({ section: "audio", fields: configFields(1) });
    const request = deferred<{ section: string; fields: Record<string, ApiConfigField> }>();
    api.configSave.mockReturnValue(request.promise);
    const { result } = renderHook(() => useConfigSection("audio", { gain: 0 }), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.loaded).toBe(true));

    let save!: Promise<void>;
    act(() => {
      save = result.current.save({ gain: 2 });
    });
    await waitFor(() => expect(result.current.fields.gain.value).toBe(2));

    await act(async () => {
      request.reject(new Error("save failed"));
      await expect(save).rejects.toThrow("save failed");
    });

    await waitFor(() => expect(result.current.fields.gain.value).toBe(1));
    expect(api.configSection).toHaveBeenCalledTimes(2);
    expect(api.configSave).toHaveBeenCalledTimes(1);
  });

  it("keeps a failed form draft dirty so the operator can retry", async () => {
    api.configSection.mockResolvedValue({ section: "audio", fields: configFields(1) });
    const request = deferred<{ section: string; fields: Record<string, ApiConfigField> }>();
    api.configSave.mockReturnValue(request.promise);
    const { result } = renderHook(
      () =>
        useConfigForm(
          "audio",
          { gain: "0" },
          { gain: "gain" },
          (values) => ({ gain: String(values.gain) }),
        ),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.loaded).toBe(true));
    act(() => result.current.set("gain", "2"));
    expect(result.current.dirty).toBe(true);

    let save!: Promise<void>;
    act(() => {
      save = result.current.save((values) => ({ gain: Number(values.gain) }));
    });
    await waitFor(() => expect(result.current.dirty).toBe(false));

    await act(async () => {
      request.reject(new Error("save failed"));
      await expect(save).rejects.toThrow("save failed");
    });

    await waitFor(() => expect(result.current.dirty).toBe(true));
    expect(result.current.cur.gain).toBe("2");
    expect(result.current.saved.gain).toBe("1");
  });
});

describe("useUserSettings", () => {
  it("applies a setting optimistically and refetches once after saving", async () => {
    api.settingsGet.mockResolvedValue({ key: "settings.theme", value: "dark" });
    const request = deferred<{ key: string; value: string }>();
    api.settingsPut.mockReturnValue(request.promise);
    const { result } = renderHook(() => useUserSettings("settings.theme", "dark"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current[2]).toBe(true));

    let save!: Promise<void>;
    act(() => {
      save = result.current[1]("light");
    });
    await waitFor(() => expect(result.current[0]).toBe("light"));

    await act(async () => {
      request.resolve({ key: "settings.theme", value: "light" });
      await save;
    });

    await waitFor(() => expect(api.settingsGet).toHaveBeenCalledTimes(2));
    expect(api.settingsPut).toHaveBeenCalledWith("settings.theme", "light");
  });

  it("restores the previous setting when the write fails", async () => {
    api.settingsGet.mockResolvedValue({ key: "settings.theme", value: "dark" });
    const request = deferred<{ key: string; value: string }>();
    api.settingsPut.mockReturnValue(request.promise);
    const { result } = renderHook(() => useUserSettings("settings.theme", "dark"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current[2]).toBe(true));

    let save!: Promise<void>;
    act(() => {
      save = result.current[1]("light");
    });
    await waitFor(() => expect(result.current[0]).toBe("light"));

    await act(async () => {
      request.reject(new Error("save failed"));
      await expect(save).rejects.toThrow("save failed");
    });

    await waitFor(() => expect(result.current[0]).toBe("dark"));
    expect(api.settingsGet).toHaveBeenCalledTimes(2);
  });
});
