import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useBlocker, useNavigate, useParams } from "react-router-dom";
import { adminApi, isLive, meApi, type AdminUser } from "../api/client";
import { useUserSettings, type ThemePreference } from "../api/useUserSettings";
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
  Button,
  Chip,
  ConfirmDialog,
  DirtyRegistryContext,
  Field,
  Icon,
  PageHeader,
  SaveBar,
  SectionCard,
  inputCls,
  type DirtyRegistry,
} from "../components/ui";
import { useToast } from "../components/toast";
import {
  SETTINGS_GROUPS,
  isSettingsSection,
  settingsSectionsForRole,
  type SettingsSectionId,
} from "./settingsSections";

type ShowMessage = (message: string, variant?: "success" | "error") => void;

function useSectionToast() {
  const notify = useToast();
  return {
    show: ((message, variant) => notify[variant ?? "success"](message)) as ShowMessage,
  };
}

function AppearanceSection({
  show,
  savedTheme,
  setTheme,
  previewTheme,
}: {
  show: ShowMessage;
  savedTheme: ThemePreference;
  setTheme: (theme: ThemePreference) => Promise<void>;
  previewTheme: (theme: ThemePreference | null) => void;
}) {
  const [draft, setDraft] = useState<ThemePreference | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const theme = draft ?? savedTheme;
  const isDirty = draft !== null;

  useEffect(() => () => previewTheme(null), [previewTheme]);

  const choose = (next: ThemePreference) => {
    setDraft(next === savedTheme ? null : next);
    setSaveError(null);
    previewTheme(next === savedTheme ? null : next);
  };

  return (
    <SectionCard
      title="Appearance"
      sub="The theme applies here immediately. Save to keep it on your account. The account menu switch changes the same preference."
    >
      <fieldset>
        <legend className="text-sm font-semibold">Preferred theme</legend>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {(["dark", "light", "system"] as const).map((value) => (
            <label
              key={value}
              className="flex min-h-[44px] cursor-pointer items-center gap-2 rounded-md border border-line p-3 text-sm"
            >
              <input
                type="radio"
                name="theme"
                value={value}
                checked={theme === value}
                onChange={() => choose(value)}
              />
              <span className="font-semibold capitalize">{value}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <SaveBar
        dirty={isDirty}
        busy={saving}
        error={saveError}
        label="Save appearance"
        onSave={async () => {
          setSaving(true);
          setSaveError(null);
          try {
            await setTheme(theme);
            setDraft(null);
            previewTheme(null);
            show(`Appearance saved: theme ${theme}${isLive ? "" : " (demo)"}.`);
          } catch (error) {
            setDraft(null);
            setSaveError(`Could not save: ${(error as Error).message}`);
            previewTheme(null);
          } finally {
            setSaving(false);
          }
        }}
      />
    </SectionCard>
  );
}

function AccountSection({ show, user }: { show: ShowMessage; user: { display_name: string } }) {
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
          <input
            id="set-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={inputCls}
            autoComplete="off"
          />
        </Field>
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">Password</p>
          <div className="mt-1">
            <Button
              onClick={() => {
                setSent(true);
                show("Password reset link sent (demo).");
              }}
              disabled={isLive}
              title={isLive ? "Password reset is not available in this console." : undefined}
            >
              {sent ? "Resend reset link" : "Send reset link"}
            </Button>
          </div>
          <p className="mt-1 text-xs text-muted">
            {isLive
              ? "An admin resets passwords from the Users section."
              : "A reset link goes to the account email. No passwords are stored here."}
          </p>
        </div>
      </div>
      <SaveBar
        dirty={dirty}
        busy={saving}
        error={saveError}
        label="Save account"
        onSave={async () => {
          if (!isLive) {
            setSavedName(name);
            show("Account saved (demo).");
            return;
          }
          setSaving(true);
          setSaveError(null);
          try {
            await meApi.patch({ display_name: name });
            setSavedName(name);
            show("Account saved.");
          } catch (error) {
            setSaveError(`Could not save: ${(error as Error).message}`);
          } finally {
            setSaving(false);
          }
        }}
      />
    </SectionCard>
  );
}

const mockUsers = [
  { id: "mock-admin", name: "Admin", role: "admin" },
  { id: "mock-user", name: "User", role: "user" },
];

function UsersSection({ show }: { show: ShowMessage }) {
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
      .then((response) => {
        setUsers(response.users);
        setError(null);
      })
      .catch((reason) => setError((reason as Error).message))
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
      .createUser({
        username: newUser.trim(),
        display_name: newName.trim() || newUser.trim(),
        password: newPass,
        role: newRole,
      })
      .then(() => {
        setNewName("");
        setNewUser("");
        setNewPass("");
        setNewRole("user");
        show("User created.");
        load();
      })
      .catch((reason) => show(`Could not create user: ${(reason as Error).message}`, "error"))
      .finally(() => setCreating(false));
  };

  const patch = (id: string, body: { is_active?: boolean; new_password?: string }) => {
    if (busyId) return;
    setBusyId(id);
    void adminApi
      .patchUser(id, body)
      .then(() => {
        show(
          body.new_password
            ? "Password reset."
            : body.is_active === false
              ? "User deactivated."
              : "User enabled.",
        );
        load();
      })
      .catch((reason) => show(`Could not update user: ${(reason as Error).message}`, "error"))
      .finally(() => setBusyId(null));
  };

  return (
    <SectionCard
      title="Users"
      sub={
        isLive
          ? "Admins manage access. Deactivating blocks sign-in without deleting history."
          : "Admins manage access. Disabling a row blocks sign-in without deleting history. (demo)"
      }
    >
      {error ? (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <p className="text-xs text-danger" role="alert">
            {error}
          </p>
          <Button onClick={load}>Retry</Button>
        </div>
      ) : null}
      <ul className="flex flex-col gap-2">
        {users.map((account) => (
          <li
            key={account.id}
            className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{account.display_name}</p>
              <p className="font-mono text-xs text-muted">
                {account.username} · {account.role}
              </p>
            </div>
            <Chip tone={account.is_active ? "ok" : "neutral"}>
              {account.is_active ? "enabled" : "disabled"}
            </Chip>
            <Button
              onClick={() => patch(account.id, { is_active: !account.is_active })}
              aria-pressed={!account.is_active}
              disabled={busyId !== null}
              aria-busy={busyId === account.id}
            >
              {busyId === account.id ? "Saving…" : account.is_active ? "Deactivate" : "Enable"}
            </Button>
          </li>
        ))}
        {isLive && loaded && users.length === 0 ? (
          <li className="text-xs text-muted">No users found.</li>
        ) : null}
        {!isLive
          ? mockUsers.map((account) => (
              <li
                key={account.id}
                className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{account.name}</p>
                  <p className="font-mono text-xs text-muted">{account.role}</p>
                </div>
                <Chip tone="ok">enabled</Chip>
              </li>
            ))
          : null}
      </ul>
      {isLive ? (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Field label="Username" htmlFor="adm-user">
            <input
              id="adm-user"
              value={newUser}
              onChange={(event) => setNewUser(event.target.value)}
              className={inputCls}
              autoComplete="off"
            />
          </Field>
          <Field label="Display name" htmlFor="adm-name">
            <input
              id="adm-name"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              className={inputCls}
              autoComplete="off"
            />
          </Field>
          <Field label="Password" htmlFor="adm-pass">
            <input
              id="adm-pass"
              type="password"
              value={newPass}
              onChange={(event) => setNewPass(event.target.value)}
              className={inputCls}
              autoComplete="new-password"
            />
          </Field>
          <Field label="Role" htmlFor="adm-role">
            <select
              id="adm-role"
              value={newRole}
              onChange={(event) => setNewRole(event.target.value)}
              className={inputCls}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Button
              variant="primary"
              onClick={create}
              disabled={!newUser.trim() || !newPass || creating}
              aria-busy={creating}
            >
              {creating ? "Creating…" : "Create user"}
            </Button>
          </div>
        </div>
      ) : null}
    </SectionCard>
  );
}

function ProcessingSection({ show }: { show: ShowMessage }) {
  const [saved, setSaved] = useUserSettings<{ a: string; v: string; o: string }>(
    "settings.processing",
    { a: "128k", v: "2500k", o: "0.0" },
  );
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
    <SectionCard
      title="Processing defaults"
      sub="Keeper bitrates and the default audio offset for new runs."
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Audio bitrate" htmlFor="set-abit" hint="Keeper file, e.g. 128k">
          <input
            id="set-abit"
            value={audioBitrate}
            onChange={(event) => setAudioBitrate(event.target.value)}
            className={inputCls}
            autoComplete="off"
          />
        </Field>
        <Field label="Video bitrate" htmlFor="set-vbit" hint="Keeper file, e.g. 2500k">
          <input
            id="set-vbit"
            value={videoBitrate}
            onChange={(event) => setVideoBitrate(event.target.value)}
            className={inputCls}
            autoComplete="off"
          />
        </Field>
        <Field
          label="Audio offset default (s)"
          htmlFor="set-offset"
          hint="Applied to new auto-edit plans"
        >
          <input
            id="set-offset"
            value={offset}
            onChange={(event) => setOffset(event.target.value)}
            inputMode="decimal"
            className={inputCls}
            autoComplete="off"
          />
        </Field>
      </div>
      {!offsetOk ? (
        <p className="mt-2 text-xs text-danger" role="alert">
          Offset must be a number in seconds.
        </p>
      ) : null}
      <SaveBar
        dirty={isDirty && offsetOk}
        busy={saving}
        error={saveError}
        label="Save processing defaults"
        onSave={async () => {
          setSaving(true);
          setSaveError(null);
          try {
            await setSaved(cur);
            show(`Processing defaults saved${isLive ? "" : " (demo)"}.`);
          } catch (error) {
            setSaveError(`Could not save: ${(error as Error).message}`);
          } finally {
            setSaving(false);
          }
        }}
      />
    </SectionCard>
  );
}

function SettingsSectionContent({
  active,
  show,
  user,
  savedTheme,
  setTheme,
  previewTheme,
}: {
  active: SettingsSectionId;
  show: ShowMessage;
  user: { display_name: string; role?: string };
  savedTheme: ThemePreference;
  setTheme: (theme: ThemePreference) => Promise<void>;
  previewTheme: (theme: ThemePreference | null) => void;
}) {
  switch (active) {
    case "preferences":
      return (
        <>
          <AppearanceSection
            show={show}
            savedTheme={savedTheme}
            setTheme={setTheme}
            previewTheme={previewTheme}
          />
          <AccountSection show={show} user={user} />
        </>
      );
    case "access":
      return <UsersSection show={show} />;
    case "automation":
      return (
        <>
          <GeneralSettingsSection show={show} />
          <ProcessingSection show={show} />
          <PromptTemplatesSection show={show} />
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
    case "backup":
      return <ConfigBackupSection show={show} isAdmin={user.role === "admin"} />;
  }
}

export function Settings({
  user,
  theme,
  setTheme,
  previewTheme,
}: {
  user: { display_name: string; role?: string };
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => Promise<void>;
  previewTheme: (theme: ThemePreference | null) => void;
}) {
  const { show } = useSectionToast();
  const { section } = useParams();
  const navigate = useNavigate();
  const sections = useMemo(() => settingsSectionsForRole(user.role), [user.role]);
  const accessAllowed = user.role === "admin";
  const requested =
    isSettingsSection(section) && (section !== "access" || accessAllowed) ? section : null;
  const active = requested ?? "preferences";

  const [pendingSection, setPendingSection] = useState<SettingsSectionId | null>(null);
  const [dirtySections, setDirtySections] = useState<Set<string>>(() => new Set());
  const dirtyIds = useRef<Set<string>>(new Set());
  const [activeSave, setActiveSave] = useState<string | null>(null);

  const dirtyRegistry = useMemo<DirtyRegistry>(
    () => ({
      set: (id, dirty) => {
        const wasDirty = dirtyIds.current.has(id);
        if (wasDirty === dirty) return;
        if (dirty) dirtyIds.current.add(id);
        else dirtyIds.current.delete(id);
        setDirtySections(new Set(dirtyIds.current));
        if (dirty) setActiveSave(id);
        else
          setActiveSave((current) =>
            current === id ? (dirtyIds.current.values().next().value ?? null) : current,
          );
      },
      remove: (id) => {
        if (!dirtyIds.current.has(id)) return;
        dirtyIds.current.delete(id);
        setDirtySections(new Set(dirtyIds.current));
        setActiveSave((current) =>
          current === id ? (dirtyIds.current.values().next().value ?? null) : current,
        );
      },
      activeSave,
    }),
    [activeSave],
  );

  useEffect(() => {
    if (dirtySections.size === 0) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirtySections]);

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      pendingSection === null &&
      dirtySections.size > 0 &&
      currentLocation.pathname !== nextLocation.pathname,
  );

  if (!requested) return <Navigate to="/settings/preferences" replace />;

  const activeSection = sections.find((item) => item.id === active) ?? sections[0];

  const choose = (id: SettingsSectionId) => {
    if (id === active) return;
    if (dirtySections.size > 0) {
      setPendingSection(id);
      return;
    }
    navigate(`/settings/${id}`, { replace: true });
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

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <div className="min-w-0 lg:sticky lg:top-24 lg:self-start">
            <div className="lg:hidden">
              <label htmlFor="settings-section" className="text-xs font-medium text-muted">
                Section
              </label>
              <div className="relative mt-1">
                <select
                  id="settings-section"
                  value={active}
                  onChange={(event) => choose(event.target.value as SettingsSectionId)}
                  className={`${inputCls} appearance-none pr-10 font-semibold`}
                  data-testid="settings-section-select"
                >
                  {SETTINGS_GROUPS.map((group) => {
                    const grouped = sections.filter((item) => item.group === group);
                    return grouped.length > 0 ? (
                      <optgroup key={group} label={group}>
                        {grouped.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.label}
                          </option>
                        ))}
                      </optgroup>
                    ) : null;
                  })}
                </select>
                <Icon
                  name="chevron"
                  className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
                />
              </div>
            </div>

            <nav aria-label="Settings sections" className="hidden flex-col gap-3 lg:flex">
              {SETTINGS_GROUPS.map((group) => {
                const grouped = sections.filter((item) => item.group === group);
                return grouped.length > 0 ? (
                  <div key={group}>
                    {grouped.length === 1 && grouped[0].label === group ? null : (
                      <p className="px-3 font-mono text-xs uppercase tracking-wide text-muted">
                        {group}
                      </p>
                    )}
                    <div className="mt-1 flex flex-col gap-1">
                      {grouped.map((item) => {
                        const selected = active === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => choose(item.id)}
                            aria-current={selected ? "page" : undefined}
                            className={`relative flex min-h-[44px] w-full items-center rounded-md px-3 text-left text-sm font-medium transition-colors duration-150 ${
                              selected
                                ? "bg-raised text-mist before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-full before:bg-accent"
                                : "text-muted hover:bg-raised hover:text-mist"
                            }`}
                          >
                            {item.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ) : null;
              })}
            </nav>
          </div>

          <div
            role="region"
            aria-label={`${activeSection.label} settings`}
            className="flex min-w-0 flex-col gap-4"
          >
            <SettingsSectionContent
              active={active}
              show={show}
              user={user}
              savedTheme={theme}
              setTheme={setTheme}
              previewTheme={previewTheme}
            />
          </div>
        </div>
        <ConfirmDialog
          open={pendingSection !== null || blocker.state === "blocked"}
          title="Unsaved changes"
          body="This section has unsaved changes. Leave and discard them?"
          confirmLabel="Discard"
          cancelLabel="Stay"
          onConfirm={() => {
            if (pendingSection) {
              const next = pendingSection;
              setPendingSection(null);
              navigate(`/settings/${next}`, { replace: true });
            } else if (blocker.state === "blocked") {
              blocker.proceed();
            }
          }}
          onClose={() => {
            setPendingSection(null);
            if (blocker.state === "blocked") blocker.reset();
          }}
        />
      </div>
    </DirtyRegistryContext.Provider>
  );
}
