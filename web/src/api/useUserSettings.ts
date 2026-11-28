import { useCallback, useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isLive, settingsApi } from "../api/client";

export type ThemePreference = "dark" | "light" | "system";

const THEME_STORAGE_KEY = "sp_theme";

function readStoredTheme(): ThemePreference {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "system" ? value : "dark";
  } catch {
    return "dark";
  }
}

function storeTheme(value: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, value);
  } catch {
  }
}

function withFallback<T>(fallback: T, value: unknown): T {
  if (value === null || value === undefined) return fallback;
  if (
    typeof fallback === "object" &&
    fallback !== null &&
    !Array.isArray(fallback) &&
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  ) {
    return { ...fallback, ...value } as T;
  }
  return value as T;
}

export function useUserSettings<T>(
  key: string,
  fallback: T,
): [T, (v: T) => Promise<void>, boolean] {
  const queryClient = useQueryClient();
  const queryKey = useMemo(() => ["user-setting", key] as const, [key]);
  const query = useQuery({
    queryKey,
    queryFn: async () => {
      const result = await settingsApi.get(key);
      return withFallback(fallback, result.value);
    },
    enabled: isLive,
    initialData: isLive ? undefined : fallback,
    staleTime: isLive ? 0 : Infinity,
  });
  const value = query.data ?? fallback;

  const saveMutation = useMutation({
    mutationFn: async (next: T) => {
      if (!isLive) return next;
      const result = await settingsApi.put(key, next);
      return withFallback(next, result.value);
    },
    onMutate: (next: T) => {
      void queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<T>(queryKey) ?? value;
      queryClient.setQueryData(queryKey, next);
      return { previous };
    },
    onError: (_error, _next, context) => {
      if (context) queryClient.setQueryData(queryKey, context.previous);
    },
    onSuccess: (result) => queryClient.setQueryData(queryKey, result),
    onSettled: () => queryClient.invalidateQueries({ queryKey }),
  });

  const save = useCallback(
    async (next: T) => {
      await saveMutation.mutateAsync(next);
    },
    [saveMutation],
  );

  return [value, save, !isLive || !query.isPending];
}

export function useThemePreference(): [
  ThemePreference,
  (value: ThemePreference) => Promise<void>,
  boolean,
] {
  const fallback = useMemo(readStoredTheme, []);
  const [theme, save, loaded] = useUserSettings<ThemePreference>("settings.theme", fallback);

  useEffect(() => {
    storeTheme(theme);
  }, [theme]);

  return [theme, save, loaded];
}
