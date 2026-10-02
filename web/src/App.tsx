import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthGate } from "./components/AuthGate";
import { Shell } from "./components/Shell";
import { Home } from "./pages/Home";
import { Jobs } from "./pages/Jobs";
import { Library } from "./pages/Library";
import { LibraryDetail } from "./pages/LibraryDetail";
import { NewSermon } from "./pages/NewSermon";
import { Settings } from "./pages/Settings";
import { readTheme, themeIsDark, writeTheme } from "./components/theme";

export function App() {
  // The theme is one fact with three readers: the <html> class list, the header
  // toggle's icon and label, and the Settings > Appearance radios. Keeping it
  // here means the header and the radios can never disagree, and writing it to
  // local storage means a reload keeps the choice.
  const [theme, setTheme] = useState(readTheme);
  const dark = themeIsDark(theme);

  useEffect(() => {
    writeTheme(theme);
    if (!themeIsDark(theme)) return;
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const onChange = () => setTheme(readTheme());
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  return (
    <BrowserRouter>
      <AuthGate>
        {({ user, logout }) => (
          <Shell
            dark={dark}
            theme={theme}
            onToggleTheme={() => setTheme(theme === "light" ? "dark" : "light")}
            user={user}
            onLogout={logout}
          >
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/new" element={<NewSermon />} />
              <Route path="/library" element={<Library />} />
              <Route path="/library/:id" element={<LibraryDetail />} />
              <Route path="/jobs" element={<Jobs />} />
              <Route path="/settings" element={<Settings user={user} theme={theme} onTheme={setTheme} />} />
            </Routes>
          </Shell>
        )}
      </AuthGate>
    </BrowserRouter>
  );
}