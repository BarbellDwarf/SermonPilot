import { useRef, useState } from "react";
import { isLive, meApi } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { AudioSettingsSection } from "../components/AudioSettings";
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
  Toggle,
  inputCls,
} from "../components/ui";

const ENV_NOTE = "Environment variables only seed defaults — saved user settings always win.";

const TABS = [
  { id: "general", label: "General" },
  { id: "llm", label: "LLM Providers" },
  { id: "sermonaudio", label: "SermonAudio Accounts" },
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
  { id: "u-1", name: "Sample Admin", role: "Admin" },
  { id: "u-2", name: "Sample Editor", role: "Editor" },
  { id: "u-3", name: "Sample Viewer", role: "Viewer" },
];

function UsersSection({ show }: { show: (m: string) => void }) {
  const [disabled, setDisabled] = useState<string[]>([]);
  const [multi, setMulti] = useState(true);
  const [savedKey, setSavedKey] = useState("");
  const [savedMulti, setSavedMulti] = useState(true);
  const [everSaved, setEverSaved] = useState(false);
  const isDirty = disabled.join() !== savedKey || multi !== savedMulti;
  return (
    <SectionCard title="Users" sub="Admins manage access. Disabling a row blocks sign-in without deleting history.">
      <ul className="flex flex-col gap-2">
        {mockUsers.map((u) => {
          const off = disabled.includes(u.id);
          return (
            <li key={u.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{u.name}</p>
                <p className="font-mono text-xs text-muted">{u.role}</p>
              </div>
              <Chip tone={off ? "neutral" : "ok"}>{off ? "disabled" : "enabled"}</Chip>
              <Button
                onClick={() => setDisabled((d) => (off ? d.filter((x) => x !== u.id) : [...d, u.id]))}
                aria-pressed={off}
              >
                {off ? "Enable" : "Disable"}
              </Button>
            </li>
          );
        })}
      </ul>
      <div className="mt-3">
        <Toggle
          checked={multi}
          onChange={setMulti}
          label="Multi-user sign-in"
          hint="Off means a single shared operator account. On means each person signs in separately."
        />
      </div>
      <SaveRow
        dirty={isDirty}
        saved={!isDirty && everSaved}
        onSave={() => {
          setSavedKey(disabled.join());
          setSavedMulti(multi);
          setEverSaved(true);
          show("User settings saved (mock).");
        }}
      />
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

function SystemSection({ show }: { show: (m: string) => void }) {
  const [savedLevel, setSavedLevel] = useUserSettings<string>("settings.logLevel", "info");
  const [logLevel, setLogLevel] = useState(savedLevel);
  const dirty = isLive ? logLevel !== savedLevel : logLevel !== savedLevel;
  const bars = [
    { label: "Processed media", pct: 62 },
    { label: "Source uploads", pct: 24 },
    { label: "Database", pct: 8 },
  ];
  return (
    <SectionCard title="System" sub="Mock usage and log verbosity.">
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

export function Settings({ user }: { user: { display_name: string } }) {
  const { toast, show } = useSectionToast();
  const [active, setActive] = useState<TabId>("general");
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
      <PageHeader title="Settings" sub={isLive ? "Each section saves to your account on save." : "Mock forms. Each section saves on its own."} />
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
        <SystemSection show={show} />
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
