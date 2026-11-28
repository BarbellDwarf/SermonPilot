import { useEffect } from "react";
import { useBlocker } from "react-router-dom";

export function useUnsavedChanges(when: boolean) {
  const blocker = useBlocker(when);

  useEffect(() => {
    if (!when) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [when]);

  return blocker;
}
