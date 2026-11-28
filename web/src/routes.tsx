import {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
} from "react";
import { Link, Navigate, Outlet, useLocation, useParams, type RouteObject } from "react-router-dom";
import { AuthGate } from "./components/AuthGate";
import { Shell } from "./components/Shell";
import { ToastHost, useToast } from "./components/toast";
import { EmptyState, PageHeader, buttonClass } from "./components/ui";
import type { AuthUser } from "./api/client";
import { useInboxCount } from "./api/hooks";
import { useThemePreference, type ThemePreference } from "./api/useUserSettings";
import { legacySettingsPath } from "./pages/settingsSections";

const Inbox = lazy(() => import("./pages/Inbox").then((m) => ({ default: m.Inbox })));
const NewSermon = lazy(() => import("./pages/NewSermon").then((m) => ({ default: m.NewSermon })));
const Library = lazy(() => import("./pages/Library").then((m) => ({ default: m.Library })));
const Teaching = lazy(() =>
  import("./pages/Teaching").then((m) => ({ default: m.Teaching })),
);
const Activity = lazy(() => import("./pages/Activity").then((m) => ({ default: m.Activity })));
const Settings = lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })));

interface Chrome {
  user: AuthUser;
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => Promise<void>;
  previewTheme: (theme: ThemePreference | null) => void;
}

const ChromeContext = createContext<Chrome | null>(null);

function useChrome(): Chrome {
  const chrome = useContext(ChromeContext);
  if (!chrome) throw new Error("Chrome context is unavailable outside the app shell.");
  return chrome;
}

function useSystemDark(): boolean {
  const [dark, setDark] = useState(() =>
    typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : true,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setDark(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return dark;
}

function AppChrome({
  user,
  logout,
  inboxCount,
}: {
  user: AuthUser;
  logout: () => void;
  inboxCount: number;
}) {
  const [theme, saveTheme] = useThemePreference();
  const [preview, setPreview] = useState<ThemePreference | null>(null);
  const systemDark = useSystemDark();
  const notify = useToast();
  const preference = preview ?? theme;
  const dark =
    preference === "system" ? systemDark : preference === "dark";

  useLayoutEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.classList.toggle("light", !dark);
  }, [dark]);

  const setTheme = useCallback(
    async (next: ThemePreference) => {
      setPreview(null);
      await saveTheme(next);
    },
    [saveTheme],
  );

  return (
    <ChromeContext.Provider value={{ user, theme, setTheme, previewTheme: setPreview }}>
      <Shell
        dark={dark}
        onToggleTheme={() => {
          const next = dark ? "light" : "dark";
          void setTheme(next).catch((error) =>
            notify.error(`Could not save theme: ${(error as Error).message}`),
          );
        }}
        user={user}
        onLogout={logout}
        badges={{ Inbox: inboxCount || undefined }}
      >
        <Suspense fallback={<p role="status" className="text-sm text-muted">Loading…</p>}>
          <Outlet />
        </Suspense>
      </Shell>
      <ToastHost />
    </ChromeContext.Provider>
  );
}

function RootLayout() {
  const inboxCount = useInboxCount();

  return (
    <AuthGate>
      {({ user, logout }) => (
        <AppChrome user={user} logout={logout} inboxCount={inboxCount} />
      )}
    </AuthGate>
  );
}

function SettingsRoute() {
  const { user, theme, setTheme, previewTheme } = useChrome();
  return <Settings user={user} theme={theme} setTheme={setTheme} previewTheme={previewTheme} />;
}

function LegacyTeachingRedirect() {
  const { id } = useParams();
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: `/teaching/${id}`, search, hash }} replace />;
}

function LegacyActivityRedirect() {
  const { id } = useParams();
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: id ? `/activity/${id}` : "/activity", search, hash }} replace />;
}

function SettingsRedirect() {
  const { search, hash } = useLocation();
  return <Navigate to={legacySettingsPath(search, hash)} replace />;
}

function NotFound() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Page not found" />
      <EmptyState
        title="This page does not exist"
        body="The link may be old or mistyped. The Inbox has everything waiting on you."
        action={
          <Link to="/" className={buttonClass("primary")}>
            Go to Inbox
          </Link>
        }
      />
    </div>
  );
}

export const routes: RouteObject[] = [
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <Inbox /> },
      { path: "new", element: <NewSermon /> },
      { path: "teaching/:id", element: <Teaching /> },
      { path: "library", element: <Library /> },
      { path: "library/:id", element: <LegacyTeachingRedirect /> },
      { path: "activity", element: <Activity /> },
      { path: "activity/:id", element: <Activity /> },
      { path: "jobs", element: <LegacyActivityRedirect /> },
      { path: "jobs/:id", element: <LegacyActivityRedirect /> },
      { path: "settings", element: <SettingsRedirect /> },
      { path: "settings/:section", element: <SettingsRoute /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];
