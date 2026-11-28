import { createContext, lazy, Suspense, useContext, useEffect, useState } from "react";
import { Link, Navigate, Outlet, useLocation, useParams, type RouteObject } from "react-router-dom";
import { AuthGate } from "./components/AuthGate";
import { Shell } from "./components/Shell";
import { ToastHost } from "./components/toast";
import { EmptyState, PageHeader, buttonClass } from "./components/ui";
import type { AuthUser } from "./api/client";
import { useInboxCount } from "./api/hooks";

const Inbox = lazy(() => import("./pages/Inbox").then((m) => ({ default: m.Inbox })));
const NewSermon = lazy(() => import("./pages/NewSermon").then((m) => ({ default: m.NewSermon })));
const Library = lazy(() => import("./pages/Library").then((m) => ({ default: m.Library })));
const LibraryDetail = lazy(() =>
  import("./pages/LibraryDetail").then((m) => ({ default: m.LibraryDetail })),
);
const Activity = lazy(() => import("./pages/Activity").then((m) => ({ default: m.Activity })));
const Settings = lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })));

interface Chrome {
  user: AuthUser;
}

const ChromeContext = createContext<Chrome | null>(null);

function useChrome(): Chrome {
  const chrome = useContext(ChromeContext);
  if (!chrome) throw new Error("Chrome context is unavailable outside the app shell.");
  return chrome;
}

function RootLayout() {
  const [dark, setDark] = useState(true);
  const inboxCount = useInboxCount();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.classList.toggle("light", !dark);
  }, [dark]);

  return (
    <AuthGate>
      {({ user, logout }) => (
        <ChromeContext.Provider value={{ user }}>
          <Shell
            dark={dark}
            onToggleTheme={() => setDark((d) => !d)}
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
      )}
    </AuthGate>
  );
}

function SettingsRoute() {
  const { user } = useChrome();
  return <Settings user={user} />;
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
  return <Navigate to={{ pathname: "/settings/preferences", search, hash }} replace />;
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
      { path: "teaching/:id", element: <LibraryDetail /> },
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
