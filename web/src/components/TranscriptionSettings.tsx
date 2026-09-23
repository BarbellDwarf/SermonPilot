import { useEffect, useMemo, useState } from "react";
import { isLive, type ApiConfigField } from "../api/client";
import { fieldSource, fieldValue, useConfigSection } from "../api/useConfigSection";
import { Button, EnvSourceBadge, Field, SectionCard, inputCls } from "./ui";

const BACKENDS = [
  { id: "whisper_local", label: "Local Whisper (openai-whisper)" },
  { id: "faster_whisper_local", label: "Local Whisper (Faster Whisper)" },
  { id: "whisper_openai", label: "OpenAI Whisper API" },
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

const LOCAL_BACKENDS = new Set(["whisper_local", "faster_whisper_local"]);

interface TranscriptionState {
  backend: string;
  localModel: string;
  device: string;
  computeType: string;
  language: string;
  openaiBaseUrl: string;
  openaiModel: string;
}

const FALLBACK: Record<string, unknown> = {
  "transcription.backend": "faster_whisper_local",
  "transcription.compute_type": "auto",
  "transcription.whisper_local.model": "base",
  "transcription.whisper_local.device": "auto",
  "transcription.whisper_local.language": "en",
  "transcription.faster_whisper_local.model": "base",
  "transcription.faster_whisper_local.device": "auto",
  "transcription.faster_whisper_local.language": "en",
  "transcription.whisper_openai.base_url": "https://api.openai.com/v1",
  "transcription.whisper_openai.model": "whisper-1",
};

function localPrefix(backend: string): string {
  return backend === "whisper_local" ? "whisper_local" : "faster_whisper_local";
}

function stateFromFields(fields: Record<string, ApiConfigField>): TranscriptionState {
  const backend = String(fieldValue(fields, "transcription.backend", "faster_whisper_local"));
  const prefix = localPrefix(backend);
  return {
    backend,
    localModel: String(fieldValue(fields, `transcription.${prefix}.model`, "base")),
    device: String(fieldValue(fields, `transcription.${prefix}.device`, "auto")),
    language: String(fieldValue(fields, `transcription.${prefix}.language`, "en")),
    computeType: String(fieldValue(fields, "transcription.compute_type", "auto")),
    openaiBaseUrl: String(
      fieldValue(fields, "transcription.whisper_openai.base_url", "https://api.openai.com/v1"),
    ),
    openaiModel: String(fieldValue(fields, "transcription.whisper_openai.model", "whisper-1")),
  };
}

function SecretStatus({ field }: { field: ApiConfigField | undefined }) {
  if (field?.has_value) {
    return (
      <p className="mt-1 text-xs text-muted" role="status">
        A key is saved{field.masked ? ` (${field.masked})` : ""}. Leave blank to keep it.
      </p>
    );
  }
  return <p className="mt-1 text-xs text-muted">No key saved yet.</p>;
}

export function TranscriptionSettingsSection({ show }: { show: (m: string) => void }) {
  const { fields, save } = useConfigSection("transcription", FALLBACK);
  const saved = useMemo(() => stateFromFields(fields), [fields]);
  const savedKey = JSON.stringify(saved);
  const [cur, setCur] = useState<TranscriptionState>(saved);
  const [openaiKey, setOpenaiKey] = useState("");

  useEffect(() => {
    setCur(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedKey]);

  const set = <K extends keyof TranscriptionState>(k: K, v: TranscriptionState[K]) =>
    setCur((c) => ({ ...c, [k]: v }));

  const dirty = JSON.stringify(cur) !== savedKey || openaiKey !== "";

  const urlOk = (u: string) => u.trim() === "" || /^https?:\/\/.{3,}/.test(u.trim());
  const valid = urlOk(cur.openaiBaseUrl) && cur.language.trim() !== "";

  const localKeyExpr = `transcription.${localPrefix(cur.backend)}`;
  const isLocal = LOCAL_BACKENDS.has(cur.backend);

  const onSave = () => {
    const values: Record<string, unknown> = {
      "transcription.backend": cur.backend,
      "transcription.compute_type": cur.computeType,
      "transcription.whisper_openai.base_url": cur.openaiBaseUrl,
      "transcription.whisper_openai.model": cur.openaiModel,
    };
    if (isLocal) {
      values[`${localKeyExpr}.model`] = cur.localModel;
      values[`${localKeyExpr}.device`] = cur.device;
      values[`${localKeyExpr}.language`] = cur.language;
    }
    if (openaiKey.trim()) values["transcription.whisper_openai.api_key"] = openaiKey;
    void save(values)
      .then(() => {
        setOpenaiKey("");
        show(isLive ? "Transcription settings saved." : "Transcription settings saved (mock).");
      })
      .catch((e) => show(`Could not save: ${(e as Error).message}`));
  };

  return (
    <SectionCard
      title="Transcription"
      sub={
        isLive
          ? "Backend and per-backend options. Saved here is what the pipeline resolves. API keys are write-only."
          : "Backend and per-backend options (mock). API keys are placeholders only and never leave the browser."
      }
    >
      <Field label="Transcription backend" htmlFor="tr-backend">
        <div className="flex flex-wrap items-center gap-2">
          <select
            id="tr-backend"
            value={cur.backend}
            onChange={(e) => set("backend", e.target.value)}
            className={`${inputCls} min-w-0 flex-1`}
          >
            {BACKENDS.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}
              </option>
            ))}
          </select>
          <EnvSourceBadge source={fieldSource(fields, "transcription.backend")} />
        </div>
      </Field>

      {isLocal ? (
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

      {cur.backend === "whisper_openai" ? (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="OpenAI API key"
            htmlFor="tr-oai-key"
            hint="Write-only. Only the last 4 characters ever display."
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
            <SecretStatus field={fields["transcription.whisper_openai.api_key"]} />
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

      {isLocal ? (
        <div className="mt-3 rounded-md border border-line p-3">
          <h3 className="text-sm font-semibold">Model downloads</h3>
          <p className="mt-1 text-xs text-muted">
            Whisper weights are fetched inside the processing container on first use. This console
            does not trigger or track downloads yet.
          </p>
        </div>
      ) : null}

      {!valid ? (
        <p className="mt-2 text-xs text-danger" role="alert">
          Check base URLs (must start with http(s)://) and the language code.
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={!dirty || !valid} onClick={onSave}>
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
