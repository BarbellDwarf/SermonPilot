import { useEffect, useState } from "react";
import { isLive, settingsApi } from "../api/client";

export function useUserSettings<T>(key: string, fallback: T): [T, (v: T) => void, boolean] {
  const [value, setValue] = useState<T>(fallback);
  const [loaded, setLoaded] = useState(!isLive);

  useEffect(() => {
    if (!isLive || loaded) return;
    let alive = true;
    settingsApi
      .get(key)
      .then((r) => {
        if (alive && r.value !== null && r.value !== undefined) setValue(r.value as T);
      })
      .catch(() => undefined)
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [key, loaded]);

  const save = (v: T) => {
    setValue(v);
    if (!isLive) return;
    void settingsApi.put(key, v).catch(() => undefined);
  };

  return [value, save, loaded];
}
