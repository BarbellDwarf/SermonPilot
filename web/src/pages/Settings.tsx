import { useState, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { adminApi, isLive, meApi, metaApi, type AdminUser } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { AudioSettingsSection } from "../components/AudioSettings";
import { CloudMountsSection } from "../components/CloudMounts";
import { ConfigBackupSection } from "../components/ConfigBackup";
import { GeneralSettingsSection } from "../components/GeneralSettings";
import { LlmConnectionsSection } from "../components/LlmConnections";
import { PromptTemplatesSection } from "../components/PromptTemplates";
import { ResourceSettingsSection } from "../components/ResourceSettings";
import { SermonAudioAccountsSection } from "../components/SermonAudioAccounts";
import { SermonAudioCredentialsSection } from "../components/SermonAudioCredentials";
import { StorageSettingsSection } from "../components/StorageSettings";
import { TranscriptionSettingsSection } from "../components/TranscriptionSettings";
import { ValidationSettingsSection } from "../components/ValidationSettings";
import {
  Advanced,
  Button,
  Chip,
  ConfirmDialog,
  DirtyRegistryContext,
  Field,
  PageHeader,
  SaveBar,
  SectionCard,
  Toast,
  inputCls,
  type DirtyRegistry,
} from "../components/ui";

const SECTIONS = [
  { id: "audio", label: "Audio", group: "Pipeline" },
  { id: "transcription", label: "Transcription", group: "Pipeline" },
  { id: "validation", label: "Validation", group: "Pipeline" },
  { id: "resources", label: "Resources", group: "Pipeline" },
  { id: "llm", label: "LLM providers", group: "Connections" },
  { id: "sermonaudio", label: "SermonAudio accounts", group: "Connections" },
  { id: "cloud", label: "Cloud mounts", group: "Connections" },
  { id: "prompts", label: "Prompt templates", group: "Prompts" },
  { id: "general", label: "General", group: "System" },
  { id: "storage", label: "Storage", group: "System" },
  { id: "backup", label: "Backup & restore", group: "System" },
] as const;

const GROUPS = ["Pipeline", "Connections", "Prompts", "System"] as const;

type TabId = (typeof SECTIONS)[number]["id"];

function isSection(value: string | null): value is TabId {
  return SECTIONS.some((s) => s.id === value);
}

function useSectionToast() {
  const [toast, setToast] = useState<string | null>(null);
  const show = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  };
  return { toast, show };
}

function AppearanceSection({ show }: { show: (m: string) => void }) {
  const [savedTheme, setSavedTheme] = useUserSettings<string>("settings.theme", "dark");
  const [theme, setTheme] = useState(savedTheme);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const isDirty = theme !== savedTheme;

  useEffect(() => {
    setTheme(savedTheme);
  }, [savedTheme]);

  return (
    <SectionCard title="Appearance" sub="Theme preference is stored with your account. The header toggle changes the current view.">
      <fieldset>
        <legend className="text-sm font-semibold">Preferred theme</legend>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {["dark", "light", "system"].map((t) => (
            <label key={t} className="flex min-h-[44px] cursor-pointer items-center gap-2 rounded-md border border-line p-3 text-sm">
              <input type="radio" name="theme" value={t} checked={theme === t} onChange={() => setTheme(t)} />
              <span className="font-semibold capitalize">{t}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <SaveBar
        dirty={isDirty}
        saved={!isDirty}
        busy={saving}
        error={saveError}
        onSave={() => {
          setSaving(true);
          setSaveError(null);
          void setSavedTheme(theme)
            .then(() => {
              setTheme(theme);
              show(`Appearance saved: theme ${theme}${isLive ? "" : " (mock)"}.`);
            })
            .catch((e) => setSaveError(`Could not save: ${(e as Error).message}`))
            .finally(() => setSaving(false));
        }}
      />
    </SectionCard>
  );
}

function AccountSection({ show, user }: { show: (m: string) => void; user: { display_name: string } }) {
  const [savedName, setSavedName] = useState(user.display_name);
  const [name, setName] = useState(user.display_name);
  const [sent, setSent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dirty = name !== savedName;
  return (
    <SectionCard title="Account" sub="Display name shows in the header. Passwords are never displayed.">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Display name" htmlFor="set-name">
          <input id="set-name" value={name} onChange={(e) => setName(e.target.value)} className={inputCls} autoComplete="off" />
        </Field>
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">Password</p>
          <div className="mt-1">
            <Button
              onClick={() => {
                setSent(true);
                show("Password reset link sent (mock).");
              }}
              disabled={isLive}
              title={isLive ? "Password reset is not available in this console." : undefined}
            >
              {sent ? "Resend reset link" : "Send reset link"}
            </Button>
          </div>
          <p className="mt-1 text-xs text-muted">
            {isLive
              ? "An admin resets passwords from the Users section below."
              : "A reset link goes to the account email. No passwords are stored here."}
          </p>
        </div>
      </div>
      <SaveBar
        dirty={dirty}
        saved={!dirty}
        busy={saving}
        error={saveError}
        onSave={() => {
          if (isLive) {
            setSaving(true);
            setSaveError(null);
            void meApi
              .patch({ display_name: name })
              .then(() => {
                setSavedName(name);
                show("Account saved.");
              })
              .catch((e) => setSaveError(`Could not save: ${(e as Error).message}`))
              .finally(() => setSaving(false));
            return;
          }
          setSavedName(name);
          show("Account saved (mock).");
        }}
      />
    </SectionCard>
  );
}

const mockUsers = [
  { id: "mock-admin", name: "Admin", role: "admin" },
  { id: "mock-user", name: "User", role: "user" },
];

function UsersSection({ show }: { show: (m: string) => void }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loaded, setLoaded] = useState(!isLive);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newUser, setNewUser] = useState("");
  const [newPass, setNewPass] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    if (!isLive) return;
    void adminApi
      .listUsers()
      .then((r) => {
        setUsers(r.users);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoaded(true));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = () => {
    if (!newUser.trim() || !newPass || creating) return;
    setCreating(true);
    void adminApi
      .createUser({ username: newUser.trim(), display_name: newName.trim() || newUser.trim(), password: newPass, role: newRole })
      .then(() => {
        setNewName("");
        setNewUser("");
        setNewPass("");
        setNewRole("user");
        show("User created.");
        load();
      })
      .catch((e) => show(`Could not create user: ${(e as Error).message}`))
      .finally(() => setCreating(false));
  };

  const patch = (id: string, body: { is_active?: boolean; new_password?: string }) => {
    if (busyId) return;
    setBusyId(id);
    void adminApi
      .patchUser(id, body)
      .then(() => {
        show(body.new_password ? "Password reset." : body.is_active === false ? "User deactivated." : "User enabled.");
        load();
      })
      .catch((e) => show(`Could not update user: ${(e as Error).message}`))
      .finally(() => setBusyId(null));
  };

  return (
    <SectionCard title="Users" sub={isLive ? "Admins manage access. Deactivating blocks sign-in without deleting history." : "Admins manage access. Disabling a row blocks sign-in without deleting history. (mock)"}>
      {error ? (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <p className="text-xs text-danger" role="alert">{error}</p>
          <Button onClick={load}>Retry</Button>
        </div>
      ) : null}
      <ul className="flex flex-col gap-2">
        {users.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{u.display_name}</p>
              <p className="font-mono text-xs text-muted">{u.username} · {u.role}</p>
            </div>
            <Chip tone={u.is_active ? "ok" : "neutral"}>{u.is_active ? "enabled" : "disabled"}</Chip>
            <Button
              onClick={() => patch(u.id, { is_active: !u.is_active })}
              aria-pressed={!u.is_active}
              disabled={busyId !== null}
              aria-busy={busyId === u.id}
            >
              {busyId === u.id ? "Saving…" : u.is_active ? "Deactivate" : "Enable"}
            </Button>
          </li>
        ))}
        {isLive && loaded && users.length === 0 ? <li className="text-xs text-muted">No users found.</li> : null}
        {!isLive ? (
          <>
            {mockUsers.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{u.name}</p>
                  <p className="font-mono text-xs text-muted">{u.role}</p>
                </div>
                <Chip tone="ok">enabled</Chip>
              </li>
            ))}
          </>
        ) : null}
      </ul>
      {isLive ? (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Field label="Username" htmlFor="adm-user">
            <input id="adm-user" value={newUser} onChange={(e) => setNewUser(e.target.value)} className={inputCls} autoComplete="off" />
          </Field>
          <Field label="Display name" htmlFor="adm-name">
            <input id="adm-name" value={newName} onChange={(e) => setNewName(e.target.value)} className={inputCls} autoComplete="off" />
          </Field>
          <Field label="Password" htmlFor="adm-pass">
            <input id="adm-pass" type="password" value={newPass} onChange={(e) => setNewPass(e.target.value)} className={inputCls} autoComplete="new-password" />
          </Field>
          <Field label="Role" htmlFor="adm-role">
            <select id="adm-role" value={newRole} onChange={(e) => setNewRole(e.target.value)} className={inputCls}>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Button variant="primary" onClick={create} disabled={!newUser.trim() || !newPass || creating} aria-busy={creating}>
              {creating ? "Creating…" : "Create user"}
            </Button>
          </div>
        </div>
      ) : null}
    </SectionCard>
  );
}

function ProcessingSection({ show }: { show: (m: string) => void }) {
  const [saved, setSaved] = useUserSettings<{ a: string; v: string; o: string }>("settings.processing", { a: "128k", v: "2500k", o: "0.0" });
  const [audioBitrate, setAudioBitrate] = useState(saved.a);
  const [videoBitrate, setVideoBitrate] = useState(saved.v);
  const [offset, setOffset] = useState(saved.o);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const cur = { a: audioBitrate, v: videoBitrate, o: offset };
  const isDirty = cur.a !== saved.a || cur.v !== saved.v || cur.o !== saved.o;
  const offsetOk = /^-?\d+(\.\d+)?$/.test(offset.trim());

  useEffect(() => {
    setAudioBitrate(saved.a);
    setVideoBitrate(saved.v);
    setOffset(saved.o);
  }, [saved.a, saved.v, saved.o]);
  return (
    <SectionCard title="Processing defaults" sub="Keeper bitrates and the default audio offset for new runs.">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Audio bitrate" htmlFor="set-abit" hint="Keeper file, e.g. 128k">
          <input id="set-abit" value={audioBitrate} onChange={(e) => setAudioBitrate(e.target.value)} className={inputCls} autoComplete="off" />
        </Field>
        <Field label="Video bitrate" htmlFor="set-vbit" hint="Keeper file, e.g. 2500k">
          <input id="set-vbit" value={videoBitrate} onChange={(e) => setVideoBitrate(e.target.value)} className={inputCls} autoComplete="off" />
        </Field>
        <Field label="Audio offset default (s)" htmlFor="set-offset" hint="Applied to new auto-edit plans">
          <input id="set-offset" value={offset} onChange={(e) => setOffset(e.target.value)} inputMode="decimal" className={inputCls} autoComplete="off" />
        </Field>
      </div>
      {!offsetOk ? <p className="mt-2 text-xs text-danger" role="alert">Offset must be a number in seconds.</p> : null}
      <SaveBar
        dirty={isDirty && offsetOk}
        saved={!isDirty}
        busy={saving}
        error={saveError}
        onSave={() => {
          setSaving(true);
          setSaveError(null);
          void setSaved(cur)
            .then(() => show(`Processing defaults saved${isLive ? "" : " (mock)"}.`))
            .catch((e) => setSaveError(`Could not save: ${(e as Error).message}`))
            .finally(() => setSaving(false));
        }}
      />
    </SectionCard>
  );
}

function SystemSection({ show, isAdmin }: { show: (m: string) => void; isAdmin: boolean }) {
  const [savedLevel, setSavedLevel] = useUserSettings<string>("settings.logLevel", "info");
  const [logLevel, setLogLevel] = useState(savedLevel);
  const [retired, setRetired] = useState<boolean | null>(isLive ? null : false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dirty = logLevel !== savedLevel;

  useEffect(() => {
    setLogLevel(savedLevel);
  }, [savedLevel]);
  const bars = [
    { label: "Processed media", pct: 62 },
    { label: "Source uploads", pct: 24 },
    { label: "Database", pct: 8 },
  ];

  useEffect(() => {
    if (!isLive || !isAdmin) return;
    let cancelled = false;
    void metaApi
      .retirement()
      .then((r) => {
        if (!cancelled) setRetired(r.streamlit_ready);
      })
      .catch(() => {
        if (!cancelled) setRetired(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

  return (
    <SectionCard title="System" sub="Mock usage and log verbosity.">
      {isAdmin ? (
        <div
          role="status"
          aria-live="polite"
          className="mb-3 rounded-md border border-line bg-ink px-4 py-3 text-xs text-muted"
        >
          <p className="font-semibold text-mist">
            Front-door cutover:{" "}
            {retired === null ? "state unknown (bridge unreachable)" : retired ? "console is live; the legacy UI may retire" : "the legacy UI still serves your domain"}
          </p>
          <p className="mt-1 font-mono">
            web_console_ready lives in the settings database; the legacy UI System settings page
            flips it, then the operator moves the reverse proxy upstream
            8501 → 8504 (see web/README.md).
          </p>
        </div>
      ) : null}
      <div className="flex flex-col gap-2" aria-label="Storage usage">
        {bars.map((b) => (
          <div key={b.label}>
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="font-medium">{b.label}</span>
              <span className="font-mono text-muted">{b.pct}%</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded bg-raised" role="img" aria-label={`${b.label} ${b.pct} percent`}>
              <div className="h-full rounded bg-accent" style={{ width: `${b.pct}%` }} />
            </div>
          </div>
        ))}
        <p className="font-mono text-xs text-muted">61 GB free of 120 GB (mock)</p>
      </div>
      <div className="mt-3 max-w-xs">
        <Field label="Log level" htmlFor="set-loglevel">
          <select id="set-loglevel" value={logLevel} onChange={(e) => setLogLevel(e.target.value)} className={inputCls}>
            {["debug", "info", "warn", "error"].map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <SaveBar
        dirty={dirty}
        saved={!dirty}
        busy={saving}
        error={saveError}
        onSave={() => {
          setSaving(true);
          setSaveError(null);
          void setSavedLevel(logLevel)
            .then(() => show(`System saved: log level ${logLevel}${isLive ? "" : " (mock)"}.`))
            .catch((e) => setSaveError(`Could not save: ${(e as Error).message}`))
            .finally(() => setSaving(false));
        }}
      />
    </SectionCard>
  );
}

export function Settings({ user }: { user: { display_name: string; role?: string } }) {
  const { toast, show } = useSectionToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("section");
  const initial: TabId = isSection(requested)
    ? requested
    : searchParams.get("cloud") === "connected"
      ? "cloud"
      : "general";
  const [active, setActive] = useState<TabId>(initial);
  const [pendingSection, setPendingSection] = useState<TabId | null>(null);
  const [dirtySections, setDirtySections] = useState<Set<string>>(() => new Set());
  const dirtyRegistry = useMemo<DirtyRegistry>(
    () => ({
      set: (id, dirty) =>
        setDirtySections((prev) => {
          if (prev.has(id) === dirty) return prev;
          const next = new Set(prev);
          if (dirty) next.add(id);
          else next.delete(id);
          return next;
        }),
      remove: (id) =>
        setDirtySections((prev) => {
          if (!prev.has(id)) return prev;
          const next = new Set(prev);
          next.delete(id);
          return next;
        }),
    }),
    [],
  );

  useEffect(() => {
    const next = searchParams.get("section");
    if (isSection(next)) setActive(next);
  }, [searchParams]);

  const go = (id: TabId) => {
    setActive(id);
    const next = new URLSearchParams(searchParams);
    next.set("section", id);
    setSearchParams(next, { replace: true });
  };

  const choose = (id: TabId) => {
    if (id === active) return;
    if (dirtySections.size > 0) {
      setPendingSection(id);
      return;
    }
    go(id);
  };

  const activeSection = SECTIONS.find((s) => s.id === active) ?? SECTIONS[0];

  const renderSection = () => {
    switch (active) {
      case "general":
        return (
          <>
            <GeneralSettingsSection show={show} />
            <AppearanceSection show={show} />
            <AccountSection show={show} user={user} />
            {user.role === "admin" ? <UsersSection show={show} /> : null}
            <Advanced label="Advanced: processing defaults and system">
              <ProcessingSection show={show} />
              <SystemSection show={show} isAdmin={user.role === "admin"} />
            </Advanced>
          </>
        );
      case "llm":
        return <LlmConnectionsSection show={show} />;
      case "sermonaudio":
        return (
          <>
            <SermonAudioAccountsSection show={show} />
            <SermonAudioCredentialsSection show={show} />
          </>
        );
      case "cloud":
        return <CloudMountsSection show={show} isAdmin={user.role === "admin"} />;
      case "audio":
        return <AudioSettingsSection show={show} />;
      case "transcription":
        return <TranscriptionSettingsSection show={show} />;
      case "validation":
        return <ValidationSettingsSection show={show} />;
      case "resources":
        return <ResourceSettingsSection show={show} isAdmin={user.role === "admin"} />;
      case "storage":
        return <StorageSettingsSection show={show} isAdmin={user.role === "admin"} />;
      case "prompts":
        return <PromptTemplatesSection show={show} />;
      case "backup":
        return <ConfigBackupSection show={show} />;
    }
  };

  return (
    <DirtyRegistryContext.Provider value={dirtyRegistry}>
      <div className="flex flex-col gap-4">
      <PageHeader
        title="Settings"
        actions={
          <details className="w-fit max-w-[min(22rem,calc(100vw-2rem))] text-xs text-muted">
            <summary className="min-h-[44px] cursor-pointer content-center rounded-md border border-line px-3">
              Environment overrides
            </summary>
            <p className="mt-1 max-w-prose">
              An environment variable wins over a saved value. Each affected field shows the
              variable name on its own row.
            </p>
          </details>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[15rem_minmax(0,1fr)]">
        <div className="min-w-0 md:sticky md:top-24 md:self-start">
          <div className="md:hidden">
            <label htmlFor="settings-section" className="text-xs font-medium text-muted">
              Section
            </label>
            <div className="relative mt-1">
              <select
                id="settings-section"
                value={active}
                onChange={(e) => choose(e.target.value as TabId)}
                className={`${inputCls} appearance-none pr-10 font-semibold`}
                data-testid="settings-section-select"
              >
                {GROUPS.map((group) => (
                  <optgroup key={group} label={group}>
                    {SECTIONS.filter((s) => s.group === group).map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                aria-hidden="true"
                className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
              >
                <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <nav aria-label="Settings sections" className="hidden flex-col gap-3 md:flex">
            {GROUPS.map((group) => (
              <div key={group}>
                <p className="px-3 font-mono text-xs uppercase tracking-wide text-muted">{group}</p>
                <div className="mt-1 flex flex-col gap-1">
                  {SECTIONS.filter((s) => s.group === group).map((s) => {
                    const selected = active === s.id;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => choose(s.id)}
                        aria-current={selected ? "page" : undefined}
                        className={`relative flex min-h-[44px] w-full items-center rounded-md px-3 text-left text-sm font-medium transition-colors duration-150 ${
                          selected
                            ? "bg-raised text-mist before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-full before:bg-accent"
                            : "text-muted hover:bg-raised hover:text-mist"
                        }`}
                      >
                        {s.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>
        </div>

        <div
          role="region"
          aria-label={`${activeSection.label} settings`}
          className="flex min-w-0 flex-col gap-4"
        >
          {renderSection()}
        </div>
      </div>
      <ConfirmDialog
        open={pendingSection !== null}
        title="Unsaved changes"
        body="This section has unsaved changes. Leave and discard them?"
        confirmLabel="Discard"
        cancelLabel="Stay"
        onConfirm={() => {
          if (pendingSection) go(pendingSection);
        }}
        onClose={() => setPendingSection(null)}
      />
      <Toast message={toast} />
      </div>
    </DirtyRegistryContext.Provider>
  );
}
