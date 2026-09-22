import { useCallback, useEffect, useMemo, useState } from "react";
import { configApi, isLive, type ApiConfigField } from "./client";

function fallbackFields(fallback: Record<string, unknown>): Record<string, ApiConfigField> {
  const fields: Record<string, ApiConfigField> = {};
  for (const [path, value] of Object.entries(fallback)) {
    fields[path] = { value, source: "default", secret: false };
  }
  return fields;
}

export interface ConfigSection {
  fields: Record<string, ApiConfigField>;
  loaded: boolean;
  error: string | null;
  save: (values: Record<string, unknown>) => Promise<void>;
}

/**
 * Read and write one config section through the console API. The section
 * fields are keyed by dotted config path; ``source`` names the environment
 * variable that is overriding a saved value, or ``db``/``default``.
 */
export function useConfigSection(
  section: string,
  fallback: Record<string, unknown> = {},
): ConfigSection {
  const [fields, setFields] = useState<Record<string, ApiConfigField>>(() => fallbackFields(fallback));
  const [loaded, setLoaded] = useState(!isLive);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLive) return;
    let alive = true;
    configApi
      .section(section)
      .then((r) => {
        if (!alive) return;
        setFields(r.fields);
        setError(null);
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      })
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [section]);

  const save = useCallback(
    async (values: Record<string, unknown>) => {
      if (!isLive) {
        setFields((f) => {
          const next = { ...f };
          for (const [path, value] of Object.entries(values)) {
            next[path] = { ...next[path], value, source: "db", secret: false };
          }
          return next;
        });
        return;
      }
      const r = await configApi.save(section, values);
      setFields(r.fields);
    },
    [section],
  );

  return { fields, loaded, error, save };
}

export function fieldValue<T>(fields: Record<string, ApiConfigField>, path: string, fallback: T): T {
  const field = fields[path];
  if (!field || field.value === undefined || field.value === null) return fallback;
  return field.value as T;
}

export function fieldSource(fields: Record<string, ApiConfigField>, path: string): string {
  return fields[path]?.source ?? "default";
}

export interface ConfigForm<T extends object> {
  cur: T;
  saved: T;
  fields: Record<string, ApiConfigField>;
  loaded: boolean;
  dirty: boolean;
  set: <K extends keyof T & string>(key: K, value: T[K]) => void;
  save: (serialize: (cur: T) => Record<string, unknown>) => Promise<void>;
}

/**
 * A section form: maps a flat form-key object onto dotted config paths,
 * tracks a saved baseline loaded from the API, and writes through on save.
 * ``serialize`` turns the form state into the path -> value map to send.
 */
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
  const savedKey = JSON.stringify(saved);
  useEffect(() => {
    setCur(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedKey]);

  const set = useCallback(<K extends keyof T & string>(key: K, value: T[K]) => {
    setCur((c) => ({ ...c, [key]: value }));
  }, []);

  const save = useCallback(
    async (serialize: (cur: T) => Record<string, unknown>) => {
      await apiSave(serialize(cur));
    },
    [cur, apiSave],
  );

  return { cur, saved, fields, loaded, dirty: JSON.stringify(cur) !== savedKey, set, save };
}
