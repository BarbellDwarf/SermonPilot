import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { configApi, isLive, type ApiConfigField } from "./client";

type ConfigFields = Record<string, ApiConfigField>;

function fallbackFields(fallback: Record<string, unknown>): ConfigFields {
  const fields: ConfigFields = {};
  for (const [path, value] of Object.entries(fallback)) {
    fields[path] = { value, source: "default", secret: false };
  }
  return fields;
}

function optimisticFields(fields: ConfigFields, values: Record<string, unknown>): ConfigFields {
  const next = { ...fields };
  for (const [path, value] of Object.entries(values)) {
    const current = next[path];
    const environmentSource =
      current?.source && current.source !== "db" && current.source !== "default"
        ? current.source
        : "db";
    next[path] = current?.secret
      ? { ...current, source: environmentSource, has_value: true }
      : { ...current, value, source: environmentSource, secret: false };
  }
  return next;
}

export interface ConfigSection {
  fields: ConfigFields;
  loaded: boolean;
  error: string | null;
  save: (values: Record<string, unknown>) => Promise<void>;
}

export function useConfigSection(
  section: string,
  fallback: Record<string, unknown> = {},
): ConfigSection {
  const queryClient = useQueryClient();
  const queryKey = useMemo(() => ["config-section", section] as const, [section]);
  const query = useQuery({
    queryKey,
    queryFn: async () => (await configApi.section(section)).fields,
    enabled: isLive,
    initialData: isLive ? undefined : fallbackFields(fallback),
    staleTime: isLive ? 0 : Infinity,
  });
  const fields = query.data ?? fallbackFields(fallback);

  const saveMutation = useMutation({
    mutationFn: async (values: Record<string, unknown>) =>
      isLive ? configApi.save(section, values) : null,
    onMutate: (values) => {
      void queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<ConfigFields>(queryKey) ?? fields;
      queryClient.setQueryData(queryKey, optimisticFields(previous, values));
      return { previous };
    },
    onError: (_error, _values, context) => {
      if (context) queryClient.setQueryData(queryKey, context.previous);
    },
    onSuccess: (result) => {
      if (result) queryClient.setQueryData(queryKey, result.fields);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey }),
  });

  const save = useCallback(
    async (values: Record<string, unknown>) => {
      await saveMutation.mutateAsync(values);
    },
    [saveMutation],
  );

  return {
    fields,
    loaded: !isLive || !query.isPending,
    error: query.error ? (query.error as Error).message : null,
    save,
  };
}

export function fieldValue<T>(fields: ConfigFields, path: string, fallback: T): T {
  const field = fields[path];
  if (!field || field.value === undefined || field.value === null) return fallback;
  return field.value as T;
}

export function fieldSource(fields: ConfigFields, path: string): string {
  return fields[path]?.source ?? "default";
}

export interface ConfigForm<T extends object> {
  cur: T;
  saved: T;
  fields: ConfigFields;
  loaded: boolean;
  dirty: boolean;
  set: <K extends keyof T & string>(key: K, value: T[K]) => void;
  save: (serialize: (cur: T) => Record<string, unknown>) => Promise<void>;
}

export function useConfigForm<T extends object>(
  section: string,
  defaults: T,
  paths: Record<keyof T & string, string>,
  normalize?: (values: T) => T,
): ConfigForm<T> {
  const fallback = useMemo(() => {
    const map: Record<string, unknown> = {};
    for (const [key, path] of Object.entries(paths) as [string, string][]) {
      map[path] = (defaults as Record<string, unknown>)[key];
    }
    return map;
  }, [defaults, paths]);
  const { fields, loaded, save: apiSave } = useConfigSection(section, fallback);

  const saved = useMemo(() => {
    const next = { ...defaults };
    for (const [key, path] of Object.entries(paths) as [string, string][]) {
      (next as Record<string, unknown>)[key] = fieldValue(
        fields,
        path,
        (defaults as Record<string, unknown>)[key],
      );
    }
    return normalize ? normalize(next) : next;
  }, [fields, defaults, paths, normalize]);

  const [cur, setCur] = useState<T>(saved);
  const saving = useRef(false);
  const saveFailed = useRef(false);
  const savedKey = JSON.stringify(saved);
  useEffect(() => {
    if (!saving.current && !saveFailed.current) setCur(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, savedKey]);

  const set = useCallback(<K extends keyof T & string>(key: K, value: T[K]) => {
    setCur((c) => ({ ...c, [key]: value }));
  }, []);

  const save = useCallback(
    async (serialize: (cur: T) => Record<string, unknown>) => {
      saving.current = true;
      saveFailed.current = false;
      try {
        await apiSave(serialize(cur));
      } catch (error) {
        saveFailed.current = true;
        throw error;
      } finally {
        saving.current = false;
      }
    },
    [cur, apiSave],
  );

  return { cur, saved, fields, loaded, dirty: JSON.stringify(cur) !== savedKey, set, save };
}
