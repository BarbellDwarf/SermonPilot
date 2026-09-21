import { useState } from "react";
import { isLive } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { Button, Field, SectionCard, inputCls } from "./ui";

const BACKENDS = [
  { id: "faster_whisper_local", label: "Local Whisper (Faster Whisper)" },
  { id: "whisper_openai", label: "OpenAI Whisper API" },
  { id: "whisper_openrouter", label: "OpenRouter Whisper API" },
];

const LOCAL_MODELS = [
  "tiny",
  "tiny.en",
  "base",
  "base.en",
  "small",
  "small.en",
  "medium",
  "medium.en",
  "large",
  "large-v2",
  "large-v3",
  "large-v3-turbo",
];
const DEVICES = [
  { id: "auto", label: "Auto (auto-detect)" },
  { id: "cpu", label: "cpu" },
  { id: "cuda", label: "cuda" },
];
const COMPUTE_TYPES = ["auto", "float16", "float32", "int8_float16", "int8"];

const MANAGEABLE_MODELS = [
  { id: "tiny", size: "75 MB" },
  { id: "base", size: "142 MB" },
  { id: "small", size: "244 MB" },
  { id: "medium", size: "769 MB" },
  { id: "large-v3-turbo", size: "809 MB" },
  { id: "large-v3", size: "2.9 GB" },
];

function ModelManager({ show }: { show: (m: string) => void }) {
  const [downloaded, setDownloaded] = useState<string[]>(["tiny", "base"]);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const downloading = Object.keys(progress).length > 0 ? Object.keys(progress)[0] : null;

  const startDownload = (id: string) => {
    if (downloaded.includes(id) || progress[id] !== undefined) return;
    setProgress({ [id]: 0 });
    const t = window.setInterval(() => {
      setProgress((p) => {
        const cur = (p[id] ?? 0) + 20;
        if (cur >= 100) {
          window.clearInterval(t);
          window.setTimeout(() => {
            setProgress({});
            setDownloaded((d) => (d.includes(id) ? d : [...d, id]));
            show(`Model downloaded (mock): ${id}.`);
          }, 250);
          return { [id]: 100 };
        }
        return { [id]: cur };
      });
    }, 300);
  };

  return (
    <div className="mt-3 rounded-md border border-line p-3" aria-label="Manage models">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Manage models</h3>
        <p className="text-xs text-muted">Mock downloads. Nothing leaves the browser.</p>
      </div>
      <ul className="mt-2 flex flex-col gap-2">
        {MANAGEABLE_MODELS.map((m) => {
          const done = downloaded.includes(m.id);
          const pct = progress[m.id];
          const busy = downloading !== null && downloading !== m.id;
          return (
            <li key={m.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm font-semibold">{m.id}</p>
                <p className="font-mono text-xs text-muted">{m.size}{done ? " · downloaded" : ""}</p>
                {pct !== undefined ? (
                  <div className="mt-2 h-2 overflow-hidden rounded bg-raised" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Downloading ${m.id}`}>
                    <div className="h-full rounded bg-accent" style={{ width: `${pct}%` }} />
                  </div>
                ) : null}
              </div>
              {done ? (
                <span className="text-xs text-muted" role="status">Ready</span>
              ) : pct !== undefined ? (
                <span className="font-mono text-xs text-muted" role="status">{pct}%</span>
              ) : (
                <Button onClick={() => startDownload(m.id)} disabled={busy} aria-label={`Download model ${m.id}`}>
                  Download
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface TranscriptionState {
  backend: string;
  localModel: string;
  device: string;
  computeType: string;
  language: string;
  openaiBaseUrl: string;
  openaiModel: string;
  openrouterBaseUrl: string;
  openrouterModel: string;
}

const DEFAULTS: TranscriptionState = {
  backend: "faster_whisper_local",
  localModel: "base",
  device: "auto",
  computeType: "auto",
  language: "en",
  openaiBaseUrl: "https://api.openai.com/v1",
  openaiModel: "whisper-1",
  openrouterBaseUrl: "https://openrouter.ai/api/v1",
  openrouterModel: "openai/whisper-large-v3",
};

export function TranscriptionSettingsSection({ show }: { show: (m: string) => void }) {
  const [saved, setSaved] = useUserSettings<TranscriptionState>("settings.transcription", DEFAULTS);
  const [cur, setCur] = useState<TranscriptionState>(saved);
  const [openaiKey, setOpenaiKey] = useState("");
  const [savedOpenaiKey, setSavedOpenaiKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [savedOpenrouterKey, setSavedOpenrouterKey] = useState("");
  const dirty =
    (isLive && JSON.stringify(cur) !== JSON.stringify(saved)) ||
    openaiKey !== savedOpenaiKey ||
    openrouterKey !== savedOpenrouterKey;
  const set = <K extends keyof TranscriptionState>(k: K, v: TranscriptionState[K]) =>
    setCur((c) => ({ ...c, [k]: v }));

  const urlOk = (u: string) => u.trim() === "" || /^https?:\/\/.{3,}/.test(u.trim());
  const valid =
    urlOk(cur.openaiBaseUrl) && urlOk(cur.openrouterBaseUrl) && cur.language.trim() !== "";

  return (
    <SectionCard
      title="Transcription"
      sub="Backend and per-backend options (mock). API keys are placeholders only and never leave the browser."
    >
      <Field label="Transcription backend" htmlFor="tr-backend">
        <select
          id="tr-backend"
          value={cur.backend}
          onChange={(e) => set("backend", e.target.value)}
          className={inputCls}
        >
          {BACKENDS.map((b) => (
            <option key={b.id} value={b.id}>
              {b.label}
            </option>
          ))}
        </select>
      </Field>

      {cur.backend === "faster_whisper_local" ? (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Local model" htmlFor="tr-model" hint="Larger is more accurate but slower.">
            <select
              id="tr-model"
              value={cur.localModel}
              onChange={(e) => set("localModel", e.target.value)}
              className={`${inputCls} font-mono`}
            >
              {LOCAL_MODELS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Device" htmlFor="tr-device" hint="Auto detects cuda when available, otherwise cpu.">
            <select
              id="tr-device"
              value={cur.device}
              onChange={(e) => set("device", e.target.value)}
              className={`${inputCls} font-mono`}
            >
              {DEVICES.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Compute type"
            htmlFor="tr-compute"
            hint="auto: int8 on cpu, float16 on cuda. Pin one to override the fallback."
          >
            <select
              id="tr-compute"
              value={cur.computeType}
              onChange={(e) => set("computeType", e.target.value)}
              className={`${inputCls} font-mono`}
            >
              {COMPUTE_TYPES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Language" htmlFor="tr-lang" hint="Language code, e.g. en.">
            <input
              id="tr-lang"
              value={cur.language}
              onChange={(e) => set("language", e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="off"
            />
          </Field>
        </div>
      ) : null}

      {cur.backend === "faster_whisper_local" ? <ModelManager show={show} /> : null}

      {cur.backend === "whisper_openai" ? (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="OpenAI API key"
            htmlFor="tr-oai-key"
            hint="Placeholder only. Only the last 4 characters ever display."
          >
            <input
              id="tr-oai-key"
              type="password"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="new-password"
              placeholder="••••••••"
            />
          </Field>
          <Field label="Base URL" htmlFor="tr-oai-url" hint="OpenAI-compatible endpoint.">
            <input
              id="tr-oai-url"
              value={cur.openaiBaseUrl}
              onChange={(e) => set("openaiBaseUrl", e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="off"
              inputMode="url"
            />
          </Field>
          <Field label="Model" htmlFor="tr-oai-model" hint="API model name, e.g. whisper-1.">
            <input
              id="tr-oai-model"
              value={cur.openaiModel}
              onChange={(e) => set("openaiModel", e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="off"
            />
          </Field>
        </div>
      ) : null}

      {cur.backend === "whisper_openrouter" ? (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="OpenRouter API key"
            htmlFor="tr-or-key"
            hint="Placeholder only. Only the last 4 characters ever display."
          >
            <input
              id="tr-or-key"
              type="password"
              value={openrouterKey}
              onChange={(e) => setOpenrouterKey(e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="new-password"
              placeholder="••••••••"
            />
          </Field>
          <Field label="Base URL" htmlFor="tr-or-url" hint="OpenRouter API endpoint.">
            <input
              id="tr-or-url"
              value={cur.openrouterBaseUrl}
              onChange={(e) => set("openrouterBaseUrl", e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="off"
              inputMode="url"
            />
          </Field>
          <Field label="Model" htmlFor="tr-or-model" hint="API model name.">
            <input
              id="tr-or-model"
              value={cur.openrouterModel}
              onChange={(e) => set("openrouterModel", e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="off"
            />
          </Field>
        </div>
      ) : null}

      {!valid ? (
        <p className="mt-2 text-xs text-danger" role="alert">
          Check base URLs (must start with http(s)://) and the language code.
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={!dirty || !valid}
          onClick={() => {
            const next = { ...cur, openaiKey, openrouterKey };
            setSaved(next);
            setSavedOpenaiKey(openaiKey);
            setSavedOpenrouterKey(openrouterKey);
            setCur(cur);
            show(isLive ? "Transcription settings saved." : "Transcription settings saved (mock).");
          }}
        >
          Save
        </Button>
        {!dirty ? (
          <span className="text-xs text-muted">{isLive ? "Saved." : "No unsaved changes."}</span>
        ) : (
          <span className="text-xs text-warn" role="status">
            Unsaved changes.
          </span>
        )}
      </div>
    </SectionCard>
  );
}
