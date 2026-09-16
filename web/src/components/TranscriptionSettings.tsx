import { useState } from "react";
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
const DEVICES = ["auto", "cpu", "cuda"];
const COMPUTE_TYPES = ["float16", "float32", "int8_float16", "int8"];

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
  computeType: "float16",
  language: "en",
  openaiBaseUrl: "https://api.openai.com/v1",
  openaiModel: "whisper-1",
  openrouterBaseUrl: "https://openrouter.ai/api/v1",
  openrouterModel: "openai/whisper-large-v3",
};

export function TranscriptionSettingsSection({ show }: { show: (m: string) => void }) {
  const [cur, setCur] = useState<TranscriptionState>(DEFAULTS);
  const [saved, setSaved] = useState<TranscriptionState>(DEFAULTS);
  const [everSaved, setEverSaved] = useState(false);
  const [openaiKey, setOpenaiKey] = useState("");
  const [savedOpenaiKey, setSavedOpenaiKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [savedOpenrouterKey, setSavedOpenrouterKey] = useState("");
  const dirty =
    JSON.stringify(cur) !== JSON.stringify(saved) ||
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
          <Field label="Device" htmlFor="tr-device" hint="Compute device.">
            <select
              id="tr-device"
              value={cur.device}
              onChange={(e) => set("device", e.target.value)}
              className={`${inputCls} font-mono`}
            >
              {DEVICES.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Compute type" htmlFor="tr-compute" hint="Floating point precision.">
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
            setSaved(cur);
            setSavedOpenaiKey(openaiKey);
            setSavedOpenrouterKey(openrouterKey);
            setEverSaved(true);
            show("Transcription settings saved (mock).");
          }}
        >
          Save
        </Button>
        {!dirty ? (
          <span className="text-xs text-muted">{everSaved ? "Saved." : "No unsaved changes."}</span>
        ) : (
          <span className="text-xs text-warn" role="status">
            Unsaved changes.
          </span>
        )}
      </div>
    </SectionCard>
  );
}
