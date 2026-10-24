import { useEffect, useState } from "react";
import { isLive, settingsApi } from "../api/client";

export function useUserSettings<T>(key: string, fallback: T): [T, (v: T) => Promise<void>, boolean] {
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

  const save = (v: T): Promise<void> => {
    if (!isLive) {
      setValue(v);
      return Promise.resolve();
    }
    return settingsApi.put(key, v).then(() => {
      setValue(v);
    });
  };

  return [value, save, loaded];
}
