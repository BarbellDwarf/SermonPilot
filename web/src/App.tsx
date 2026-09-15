import { useEffect, useState } from "react";
import { Shell, type Section } from "./components/Shell";
import { Home } from "./pages/Home";
import { Jobs } from "./pages/Jobs";
import { Placeholder } from "./pages/Placeholder";

export function App() {
  const [section, setSection] = useState<Section>("home");
  const [dark, setDark] = useState(true);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.classList.toggle("light", !dark);
  }, [dark ]);

  return (
    <Shell section={section} onNavigate={setSection} dark={dark} onToggleTheme={() => setDark((d) => !d)}>
      {section === "home" ? <Home onNavigate={setSection} /> : null}
      {section === "jobs" ? <Jobs /> : null}
      {section === "new" || section === "library" || section === "settings" ? (
        <Placeholder section={section} onNavigate={setSection} />
      ) : null}
    </Shell>
  );
}
