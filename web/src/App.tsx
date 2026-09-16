import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Home } from "./pages/Home";
import { Jobs } from "./pages/Jobs";
import { Library } from "./pages/Library";
import { LibraryDetail } from "./pages/LibraryDetail";
import { NewSermon } from "./pages/NewSermon";
import { Settings } from "./pages/Settings";

export function App() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.classList.toggle("light", !dark);
  }, [dark]);

  return (
    <BrowserRouter>
      <Shell dark={dark} onToggleTheme={() => setDark((d) => !d)}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/new" element={<NewSermon />} />
          <Route path="/library" element={<Library />} />
          <Route path="/library/:id" element={<LibraryDetail />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
