import { useState } from "react";
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
  const [theme, setTheme] = useState("dark");
  const [savedTheme, setSavedTheme] = useState("dark");
  const isDirty = theme !== savedTheme;
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
          show(`Appearance saved (mock): theme ${theme}.`);
        }}
      />
    </SectionCard>
  );
}

function AccountSection({ show }: { show: (m: string) => void }) {
  const [name, setName] = useState("Sample Operator");
  const [savedName, setSavedName] = useState("Sample Operator");
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
  const [audioBitrate, setAudioBitrate] = useState("128k");
  const [videoBitrate, setVideoBitrate] = useState("2500k");
  const [offset, setOffset] = useState("0.0");
  const [saved, setSaved] = useState<{ a: string; v: string; o: string } | null>(null);
  const base = { a: "128k", v: "2500k", o: "0.0" };
  const cur = { a: audioBitrate, v: videoBitrate, o: offset };
  const ref = saved ?? base;
  const isDirty = cur.a !== ref.a || cur.v !== ref.v || cur.o !== ref.o;
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
          show("Processing defaults saved (mock).");
        }}
      />
    </SectionCard>
  );
}

function SecretField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  const [showKey, setShowKey] = useState(false);
  return (
    <Field label={label} htmlFor={id} hint="Stored masked. Only the last 4 characters ever display.">
      <div className="flex gap-2">
        <input
          id={id}
          type={showKey ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="••••••••"
          autoComplete="new-password"
          className={`${inputCls} font-mono`}
        />
        <Button onClick={() => setShowKey((s) => !s)} aria-pressed={showKey} aria-label={showKey ? `Hide ${label}` : `Show ${label}`}>
          {showKey ? "Hide" : "Show"}
        </Button>
      </div>
    </Field>
  );
}

function IntegrationsSection({ show }: { show: (m: string) => void }) {
  const [saKey, setSaKey] = useState("");
  const [llmKey, setLlmKey] = useState("");
  const [llmModel, setLlmModel] = useState("mock-model-a");
  const [saved, setSaved] = useState(false);
  const dirty = saKey !== "" || llmKey !== "" || llmModel !== "mock-model-a";
  return (
    <SectionCard title="Integrations" sub="Keys are typed blind and stored masked. Nothing here calls the network.">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <SecretField id="set-sakey" label="SermonAudio API key" value={saKey} onChange={setSaKey} />
        <SecretField id="set-llmkey" label="LLM provider key" value={llmKey} onChange={setLlmKey} />
        <Field label="LLM model" htmlFor="set-llmmodel">
          <select id="set-llmmodel" value={llmModel} onChange={(e) => setLlmModel(e.target.value)} className={inputCls}>
            {["mock-model-a", "mock-model-b", "mock-model-c"].map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <SaveRow
        dirty={dirty}
        saved={saved}
        onSave={() => {
          setSaved(true);
          show("Integration settings saved (mock). Keys stored masked.");
        }}
      />
    </SectionCard>
  );
}

function SystemSection({ show }: { show: (m: string) => void }) {
  const [logLevel, setLogLevel] = useState("info");
  const [savedLevel, setSavedLevel] = useState("info");
  const dirty = logLevel !== savedLevel;
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
          show(`System saved (mock): log level ${logLevel}.`);
        }}
      />
    </SectionCard>
  );
}

export function Settings() {
  const { toast, show } = useSectionToast();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Settings" sub="Mock forms. Each section saves on its own." />
      <p className="rounded-lg border border-line bg-surface px-4 py-3 text-xs text-muted">{ENV_NOTE}</p>
      <AppearanceSection show={show} />
      <AccountSection show={show} />
      <UsersSection show={show} />
      <ProcessingSection show={show} />
      <IntegrationsSection show={show} />
      <SystemSection show={show} />
      <Toast message={toast} />
    </div>
  );
}
