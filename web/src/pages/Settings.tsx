import { useRef, useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { adminApi, api, isLive, meApi, metaApi, type AdminUser } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { AudioSettingsSection } from "../components/AudioSettings";
import { CloudMountsSection } from "../components/CloudMounts";
import { ConfigBackupSection } from "../components/ConfigBackup";
import { GeneralSettingsSection } from "../components/GeneralSettings";
import { LlmConnectionsSection } from "../components/LlmConnections";
import { PromptTemplatesSection } from "../components/PromptTemplates";
import { SermonAudioAccountsSection } from "../components/SermonAudioAccounts";
import { SermonAudioCredentialsSection } from "../components/SermonAudioCredentials";
import { TranscriptionSettingsSection } from "../components/TranscriptionSettings";
import { ValidationSettingsSection } from "../components/ValidationSettings";
import {
  Button,
  Chip,
  Field,
  PageHeader,
  SectionCard,
  Toast,
  inputCls,
} from "../components/ui";

const ENV_NOTE =
  "Environment variables override saved settings for the variables they map to. A field shows the variable name when the environment is winning.";

/**
 * Nine tabs, none of them a long scroll. Every documented capability keeps an
 * addressable home, and `?tab=` names one so any page can send the operator
 * straight to the setting that is blocking them.
 */
const TABS = [
  { id: "general", label: "General" },
  { id: "processing", label: "Audio & Transcription" },
  { id: "llm", label: "LLM Providers" },
  { id: "sermonaudio", label: "SermonAudio" },
  { id: "cloud", label: "Cloud Mounts" },
  { id: "content", label: "Descriptions & Prompts" },
  { id: "backup", label: "Backup & Restore" },
  { id: "account", label: "Appearance & Account" },
  { id: "users", label: "Users" },
  { id: "system", label: "System" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const TAB_IDS = TABS.map((t) => t.id) as readonly string[];

function tabFromParams(params: URLSearchParams): TabId {
  const asked = params.get("tab");
  if (asked && TAB_IDS.includes(asked)) return asked as TabId;
  if (params.get("cloud") === "connected") return "cloud";
  return "general";
}

function useSectionToast() {
  const [toast, setToast] = useState<string | null>(null);
  const show = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  };
  return { toast, show };
}

function SaveRow({ dirty, saved, onSave }: { dirty: boolean; saved: boolean; onSave: () => void }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <Button variant="primary" onClick={onSave} disabled={!dirty}>
        Save
      </Button>
      {!dirty ? (
        <span className="text-xs text-muted">{saved ? "Saved." : "No unsaved changes."}</span>
      ) : (
        <span className="text-xs text-warn" role="status">
          Unsaved changes.
        </span>
      )}
    </div>
  );
}

function AppearanceSection({ show }: { show: (m: string) => void }) {
  const [savedTheme, setSavedTheme] = useUserSettings<string>("settings.theme", "dark");
  const [theme, setTheme] = useState(savedTheme);
  const isDirty = isLive ? theme !== savedTheme : theme !== savedTheme;
  return (
    <SectionCard title="Appearance" sub="Theme applies instantly in this mock and persists on save.">
      <fieldset>
        <legend className="text-sm font-semibold">Theme</legend>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {["dark", "light", "system"].map((t) => (
            <label key={t} className="flex min-h-[44px] cursor-pointer items-center gap-2 rounded-md border border-line p-3 text-sm">
              <input type="radio" name="theme" value={t} checked={theme === t} onChange={() => setTheme(t)} />
              <span className="font-semibold capitalize">{t}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <SaveRow
        dirty={isDirty}
        saved={!isDirty}
        onSave={() => {
          setSavedTheme(theme);
          setTheme(theme);
          show(`Appearance saved: theme ${theme}${isLive ? "" : " (mock)"}.`);
        }}
      />
    </SectionCard>
  );
}

function AccountSection({ show, user }: { show: (m: string) => void; user: { display_name: string } }) {
  const [savedName, setSavedName] = useState(user.display_name);
  const [name, setName] = useState(user.display_name);
  const [sent, setSent] = useState(false);
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
            >
              {sent ? "Resend reset link" : "Send reset link"}
            </Button>
          </div>
          <p className="mt-1 text-xs text-muted">A reset link goes to the account email. No passwords are stored here.</p>
        </div>
      </div>
      <SaveRow
        dirty={dirty}
        saved={!dirty}
        onSave={() => {
          if (isLive) {
            void meApi
              .patch({ display_name: name })
              .then(() => {
                setSavedName(name);
                show("Account saved.");
              })
              .catch((e) => show(`Could not save: ${(e as Error).message}`));
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
    if (!newUser.trim() || !newPass) return;
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
      .catch((e) => show(`Could not create user: ${(e as Error).message}`));
  };

  const patch = (id: string, body: { is_active?: boolean; new_password?: string }) => {
    void adminApi
      .patchUser(id, body)
      .then(() => {
        show(body.new_password ? "Password reset." : body.is_active === false ? "User deactivated." : "User enabled.");
        load();
      })
      .catch((e) => show(`Could not update user: ${(e as Error).message}`));
  };

  return (
    <SectionCard title="Users" sub={isLive ? "Admins manage access. Deactivating blocks sign-in without deleting history." : "Admins manage access. Disabling a row blocks sign-in without deleting history. (mock)"}>
      {error ? <p className="text-xs text-danger" role="alert">{error}</p> : null}
      <ul className="flex flex-col gap-2">
        {users.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{u.display_name}</p>
              <p className="font-mono text-xs text-muted">{u.username} · {u.role}</p>
            </div>
            <Chip tone={u.is_active ? "ok" : "neutral"}>{u.is_active ? "enabled" : "disabled"}</Chip>
            <Button onClick={() => patch(u.id, { is_active: !u.is_active })} aria-pressed={!u.is_active}>
              {u.is_active ? "Deactivate" : "Enable"}
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
            <Button variant="primary" onClick={create} disabled={!newUser.trim() || !newPass}>
              Create user
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
  const cur = { a: audioBitrate, v: videoBitrate, o: offset };
  const isDirty = isLive && (cur.a !== saved.a || cur.v !== saved.v || cur.o !== saved.o);
  const offsetOk = /^-?\d+(\.\d+)?$/.test(offset.trim());
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
      <SaveRow
        dirty={isDirty && offsetOk}
        saved={saved !== null && !isDirty}
        onSave={() => {
          setSaved(cur);
          show(`Processing defaults saved${isLive ? "" : " (mock)"}.`);
        }}
      />
    </SectionCard>
  );
}

const SERVICE_CARDS: { id: string; label: string }[] = [
  { id: "sermonaudio_api", label: "SermonAudio" },
  { id: "database", label: "Database" },
  { id: "llm_primary", label: "AI provider" },
  { id: "local_storage", label: "Output folder" },
  { id: "processing_queue", label: "Job queue" },
  { id: "system_resources", label: "Machine load" },
];

const SERVICE_TONE: Record<string, string> = {
  ok: "ok",
  warning: "warn",
  error: "error",
};

function SystemSection({ show, isAdmin }: { show: (m: string) => void; isAdmin: boolean }) {
  const [savedLevel, setSavedLevel] = useUserSettings<string>("settings.logLevel", "info");
  const [logLevel, setLogLevel] = useState(savedLevel);
  const [retired, setRetired] = useState<boolean | null>(isLive ? null : false);
  const dirty = logLevel !== savedLevel;
  const status = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    enabled: isLive,
    staleTime: 15_000,
  });

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
    <SectionCard title="System" sub="What the server reports about itself, and how much it logs.">
      {isAdmin ? (
        <div
          role="status"
          aria-live="polite"
          className="mb-3 rounded-md border border-line bg-ink px-4 py-3 text-xs text-muted"
        >
          <p className="font-semibold text-mist">
            This console is the only interface.{" "}
            {retired === null
              ? "The front-door setting could not be read."
              : retired
                ? "Your domain has been pointed here."
                : "If your domain still loads the old interface, the reverse proxy is still pointing at port 8501. Move it to 8504 and reload it."}
          </p>
        </div>
      ) : null}

      {isLive ? (
        status.isPending ? (
          <p className="text-sm text-muted" role="status">
            Reading the server's own report…
          </p>
        ) : status.isError ? (
          <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-muted">The server's own report could not be read.</p>
            <Button onClick={() => void status.refetch()}>Try again</Button>
          </div>
        ) : (
          <ul className="flex flex-col gap-2" aria-label="Server report">
            {SERVICE_CARDS.map(({ id, label }) => {
              const entry = status.data?.status?.[id];
              if (!entry) return null;
              const raw = String(entry.status);
              const tone = SERVICE_TONE[raw] ?? "neutral";
              return (
                <li
                  key={id}
                  className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-ink p-3 sm:flex-row sm:items-center sm:gap-3"
                >
                  <Chip tone={tone}>
                    {tone === "warn" ? "Warning" : tone === "error" ? "Problem" : tone === "ok" ? "OK" : "Not measured"}
                  </Chip>
                  <span className="min-w-0 flex-1 text-sm font-semibold">{label}</span>
                  <span className="min-w-0 text-xs text-muted [overflow-wrap:anywhere]">
                    {entry.details || entry.message || ""}
                  </span>
                </li>
              );
            })}
          </ul>
        )
      ) : (
        <p className="text-sm text-muted">
          The server report appears here once the console is connected to one.
        </p>
      )}

      <div className="mt-4 max-w-xs">
        <Field label="Log level" htmlFor="set-loglevel" hint="Debug records everything, including each pipeline stage.">
          <select id="set-loglevel" value={logLevel} onChange={(e) => setLogLevel(e.target.value)} className={inputCls}>
            {["debug", "info", "warn", "error"].map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <SaveRow
        dirty={dirty}
        saved={!dirty}
        onSave={() => {
          setSavedLevel(logLevel);
          show(`System saved: log level ${logLevel}${isLive ? "" : " (mock)"}.`);
        }}
      />
    </SectionCard>
  );
}

export function Settings({ user }: { user: { display_name: string; role?: string } }) {
  const { toast, show } = useSectionToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [active, setActive] = useState<TabId>(() => tabFromParams(searchParams));
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const select = (id: TabId) => {
    setActive(id);
    setSearchParams({ tab: id }, { replace: true });
  };

  const focusTab = (id: TabId) => {
    select(id);
    tabRefs.current[id]?.focus();
  };

  const onTabKeyDown = (e: React.KeyboardEvent, id: TabId) => {
    const ids = TABS.map((t) => t.id);
    const i = ids.indexOf(id);
    if (e.key === "ArrowRight") {
      e.preventDefault();
      focusTab(ids[(i + 1) % ids.length] as TabId);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      focusTab(ids[(i - 1 + ids.length) % ids.length] as TabId);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusTab(ids[0] as TabId);
    } else if (e.key === "End") {
      e.preventDefault();
      focusTab(ids[ids.length - 1] as TabId);
    }
  };

  const panel = (id: TabId, children: React.ReactNode) => (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="flex flex-col gap-4">
      {children}
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Settings" sub="Each section saves on its own. Nothing here needs a restart." />
      <p className="rounded-lg border border-line bg-surface px-4 py-3 text-xs text-muted">{ENV_NOTE}</p>
      <div
        role="tablist"
        aria-label="Settings sections"
        className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1"
      >
        {TABS.map((t) => {
          const selected = active === t.id;
          return (
            <button
              key={t.id}
              ref={(el) => {
                tabRefs.current[t.id] = el;
              }}
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={selected}
              aria-controls={`panel-${t.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => select(t.id)}
              onKeyDown={(e) => onTabKeyDown(e, t.id)}
              className={`min-h-[44px] shrink-0 rounded-md border px-4 text-sm font-semibold transition-colors ${
                selected
                  ? "border-accent bg-raised text-mist"
                  : "border-line bg-surface text-muted hover:border-muted hover:text-mist"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      {active === "general" &&
        panel(
          "general",
          <>
            <GeneralSettingsSection show={show} />
            <ProcessingSection show={show} />
          </>,
        )}
      {active === "processing" &&
        panel(
          "processing",
          <>
            <AudioSettingsSection show={show} />
            <TranscriptionSettingsSection show={show} />
          </>,
        )}
      {active === "llm" && panel("llm", <LlmConnectionsSection show={show} />)}
      {active === "sermonaudio" &&
        panel(
          "sermonaudio",
          <>
            <SermonAudioAccountsSection show={show} />
            <SermonAudioCredentialsSection show={show} />
          </>,
        )}
      {active === "cloud" && panel("cloud", <CloudMountsSection show={show} isAdmin={user.role === "admin"} />)}
      {active === "content" &&
        panel(
          "content",
          <>
            <ValidationSettingsSection show={show} />
            <PromptTemplatesSection show={show} />
          </>,
        )}
      {active === "backup" && panel("backup", <ConfigBackupSection show={show} />)}
      {active === "account" &&
        panel(
          "account",
          <>
            <AccountSection show={show} user={user} />
            <AppearanceSection show={show} />
          </>,
        )}
      {active === "users" && panel("users", <UsersSection show={show} />)}
      {active === "system" && panel("system", <SystemSection show={show} isAdmin={user.role === "admin"} />)}
      <Toast message={toast} />
    </div>
  );
}
