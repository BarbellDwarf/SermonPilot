import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { AuthError, auth, isLive, type AuthUser } from "../api/client";
import { Button, Card, Field, inputCls } from "./ui";

export interface AuthState {
  user: AuthUser;
  logout: () => void;
}

type GateStatus = "loading" | "authed" | "login" | "bootstrap";

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-4 py-8 text-mist">
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}

function Brand() {
  return (
    <div className="mb-4 flex items-center gap-2">
      <span
        className="flex h-8 w-8 items-center justify-center rounded-md bg-accent font-mono text-sm font-bold text-[var(--accent-ink)]"
        aria-hidden="true"
      >
        SP
      </span>
      <span className="text-base font-bold tracking-tight">SermonPilot</span>
    </div>
  );
}

function LoginScreen({ onAuthed }: { onAuthed: (user: AuthUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { user } = await auth.login(username.trim(), password);
      onAuthed(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Centered>
      <Brand />
      <Card>
        <h1 className="text-lg font-semibold">Sign in</h1>
        <p className="mt-0.5 text-sm text-muted">Use your SermonPilot account.</p>
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <Field label="Username" htmlFor="sp-username">
            <input
              id="sp-username"
              className={inputCls}
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. admin"
            />
          </Field>
          <Field label="Password" htmlFor="sp-password">
            <input
              id="sp-password"
              type="password"
              className={inputCls}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </Field>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}
          <Button type="submit" variant="primary" disabled={busy || !username || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </Centered>
  );
}

function BootstrapScreen({ onRechecked }: { onRechecked: (next: GateStatus, user?: AuthUser) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function recheck() {
    setBusy(true);
    setError(null);
    try {
      try {
        await auth.bootstrap();
      } catch {
      }
      const user = await auth.me();
      onRechecked("authed", user);
    } catch (err) {
      if (err instanceof AuthError && err.needsBootstrap) return;
      if (err instanceof Error && /failed with 401/.test(err.message)) {
        onRechecked("login");
        return;
      }
      setError(err instanceof Error ? err.message : "Recheck failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Centered>
      <Brand />
      <Card>
        <h1 className="text-lg font-semibold">First-time setup</h1>
        <p className="mt-2 text-sm text-muted">
          Instance bootstrap happens server-side; set SERMONPILOT_ADMIN_USER/PASSWORD in the
          deployment env, then click Check again.
        </p>
        {error ? (
          <p role="alert" className="mt-2 text-sm text-danger">
            {error}
          </p>
        ) : null}
        <div className="mt-4">
          <Button variant="primary" onClick={() => void recheck()} disabled={busy}>
            {busy ? "Checking…" : "Check again"}
          </Button>
        </div>
      </Card>
    </Centered>
  );
}

export function AuthGate({ children }: { children: (auth: AuthState) => ReactNode }) {
  const [status, setStatus] = useState<GateStatus>(isLive ? "loading" : "authed");
  const [user, setUser] = useState<AuthUser | null>(
    isLive ? null : { id: "mock-admin", username: "admin", display_name: "Admin", role: "admin", is_active: true },
  );

  const check = useCallback(async () => {
    setStatus("loading");
    try {
      const me = await auth.me();
      setUser(me);
      setStatus("authed");
    } catch (err) {
      if (err instanceof AuthError && err.needsBootstrap) {
        setStatus("bootstrap");
      } else {
        setStatus("login");
      }
    }
  }, []);

  useEffect(() => {
    if (isLive) void check();
  }, [check]);

  const logout = useCallback(() => {
    void auth.logout().finally(() => {
      setUser(null);
      if (isLive) setStatus("login");
    });
  }, []);

  if (!isLive && user) return <>{children({ user, logout })}</>;

  if (status === "loading") {
    return (
      <Centered>
        <p role="status" className="text-sm text-muted">
          Checking session…
        </p>
      </Centered>
    );
  }

  if (status === "bootstrap") {
    return (
      <BootstrapScreen
        onRechecked={(next, nextUser) => {
          if (next === "authed" && nextUser) {
            setUser(nextUser);
            setStatus("authed");
          } else {
            setStatus(next);
          }
        }}
      />
    );
  }

  if (status === "login" || !user) {
    return (
      <LoginScreen
        onAuthed={(u) => {
          setUser(u);
          setStatus("authed");
        }}
      />
    );
  }

  return <>{children({ user, logout })}</>;
}
