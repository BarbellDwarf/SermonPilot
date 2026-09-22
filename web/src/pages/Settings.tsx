import { useRef, useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { adminApi, isLive, meApi, metaApi, type AdminUser } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { AudioSettingsSection } from "../components/AudioSettings";
import { CloudMountsSection } from "../components/CloudMounts";
import { ConfigBackupSection } from "../components/ConfigBackup";
import { GeneralSettingsSection } from "../components/GeneralSettings";
import { LlmConnectionsSection } from "../components/LlmConnections";
import { PromptTemplatesSection } from "../components/PromptTemplates";
import { SermonAudioAccountsSection } from "../components/SermonAudioAccounts";
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

const TABS = [
  { id: "general", label: "General" },
  { id: "llm", label: "LLM Providers" },
  { id: "sermonaudio", label: "SermonAudio Accounts" },
  { id: "cloud", label: "Cloud Mounts" },
  { id: "audio", label: "Audio" },
  { id: "transcription", label: "Transcription" },
  { id: "validation", label: "Validation" },
  { id: "prompts", label: "Prompt Templates" },
  { id: "backup", label: "Backup & Restore" },
] as const;

type TabId = (typeof TABS)[number]["id"];

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

function SystemSection({ show, isAdmin }: { show: (m: string) => void; isAdmin: boolean }) {
  const [savedLevel, setSavedLevel] = useUserSettings<string>("settings.logLevel", "info");
  const [logLevel, setLogLevel] = useState(savedLevel);
  const [retired, setRetired] = useState<boolean | null>(isLive ? null : false);
  const dirty = isLive ? logLevel !== savedLevel : logLevel !== savedLevel;
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
            {retired === null ? "state unknown (bridge unreachable)" : retired ? "console is live — Streamlit may retire" : "Streamlit still serves sermon.example.com"}
          </p>
          <p className="mt-1 font-mono">
            web_console_ready lives in the settings database; the Streamlit System settings page
            flips it, then the operator moves the nginx vhost sermon.example.com.conf upstream
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
  const [searchParams] = useSearchParams();
  const [active, setActive] = useState<TabId>(
    searchParams.get("cloud") === "connected" ? "cloud" : "general",
  );
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const focusTab = (id: TabId) => {
    setActive(id);
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

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Settings" sub={isLive ? "Each section saves to your account on save." : "Sections save on their own. Placeholder sections are labelled as such."} />
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
              onClick={() => setActive(t.id)}
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
      {active === "general" && (
        <div role="tabpanel" id="panel-general" aria-labelledby="tab-general" className="flex flex-col gap-4">
        <GeneralSettingsSection show={show} />
        <ProcessingSection show={show} />
        <AppearanceSection show={show} />
        <AccountSection show={show} user={user} />
        <UsersSection show={show} />
        <SystemSection show={show} isAdmin={user.role === "admin"} />
        </div>
      )}
      {active === "llm" && (
        <div role="tabpanel" id="panel-llm" aria-labelledby="tab-llm" className="flex flex-col gap-4">
        <LlmConnectionsSection show={show} />
        </div>
      )}
      {active === "sermonaudio" && (
        <div role="tabpanel" id="panel-sermonaudio" aria-labelledby="tab-sermonaudio" className="flex flex-col gap-4">
        <SermonAudioAccountsSection show={show} />
        </div>
      )}
      {active === "cloud" && (
        <div role="tabpanel" id="panel-cloud" aria-labelledby="tab-cloud" className="flex flex-col gap-4">
        <CloudMountsSection show={show} isAdmin={user.role === "admin"} />
        </div>
      )}
      {active === "audio" && (
        <div role="tabpanel" id="panel-audio" aria-labelledby="tab-audio" className="flex flex-col gap-4">
        <AudioSettingsSection show={show} />
        </div>
      )}
      {active === "transcription" && (
        <div role="tabpanel" id="panel-transcription" aria-labelledby="tab-transcription" className="flex flex-col gap-4">
        <TranscriptionSettingsSection show={show} />
        </div>
      )}
      {active === "validation" && (
        <div role="tabpanel" id="panel-validation" aria-labelledby="tab-validation" className="flex flex-col gap-4">
        <ValidationSettingsSection show={show} />
        </div>
      )}
      {active === "prompts" && (
        <div role="tabpanel" id="panel-prompts" aria-labelledby="tab-prompts" className="flex flex-col gap-4">
        <PromptTemplatesSection show={show} />
        </div>
      )}
      {active === "backup" && (
        <div role="tabpanel" id="panel-backup" aria-labelledby="tab-backup" className="flex flex-col gap-4">
        <ConfigBackupSection show={show} />
        </div>
      )}
      <Toast message={toast} />
    </div>
  );
}
