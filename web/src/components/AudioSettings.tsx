import { useMemo } from "react";
import { isLive } from "../api/client";
import { fieldSource, useConfigForm } from "../api/useConfigSection";
import { Button, EnvSourceBadge, Field, SectionCard, Toggle, inputCls } from "./ui";

const METHODS = [
  { id: "deepfilternet", label: "DeepFilterNet (standard)", hint: "Standard speech enhancement." },
  { id: "clear-natural", label: "Clear-Natural", hint: "Gentler noise suppression." },
  { id: "clear-studio", label: "Clear-Studio", hint: "Aggressive, podcast-ready." },
  { id: "custom", label: "Custom ONNX", hint: "Point to any ONNX model on HuggingFace." },
  { id: "none", label: "None", hint: "Skip enhancement." },
];

const DEVICES = [
  { id: "auto", label: "Auto", hint: "Use the GPU unless VRAM is below the threshold, then CPU." },
  { id: "cpu", label: "CPU", hint: "Slower, but always leaves the GPU free for whisper." },
  { id: "cuda", label: "GPU (CUDA)", hint: "Fastest; needs room for enhancement and whisper." },
];

interface AudioState {
  method: string;
  device: string;
  customRepo: string;
  customFile: string;
  noiseReduction: boolean;
  amplify: boolean;
  normalize: boolean;
  gainDb: string;
  targetLevelDb: string;
}

const DEFAULTS: AudioState = {
  method: "deepfilternet",
  device: "auto",
  customRepo: "",
  customFile: "",
  noiseReduction: true,
  amplify: true,
  normalize: true,
  gainDb: "0.5",
  targetLevelDb: "-22",
};

const PATHS = {
  method: "audio_enhancement_method",
  device: "enhancement.device",
  customRepo: "clear_custom_repo",
  customFile: "clear_custom_file",
  noiseReduction: "audio_noise_reduction",
  amplify: "audio_amplify",
  normalize: "audio_normalize",
  gainDb: "audio_gain_db",
  targetLevelDb: "audio_target_level_db",
} as const;

function numError(v: string, min: number, max: number): string | null {
  if (!/^-?\d+(\.\d+)?$/.test(v.trim())) return "Must be a number.";
  const n = Number(v);
  if (n < min || n > max) return `Must be between ${min} and ${max}.`;
  return null;
}

export function AudioSettingsSection({ show }: { show: (m: string) => void }) {
  const normalize = useMemo(
    () => (values: AudioState): AudioState => ({
      ...values,
      gainDb: String(values.gainDb),
      targetLevelDb: String(values.targetLevelDb),
    }),
    [],
  );
  const { cur, fields, dirty, set, save } = useConfigForm<AudioState>(
    "audio",
    DEFAULTS,
    PATHS,
    normalize,
  );

  const gainErr = numError(cur.gainDb, -10, 10);
  const levelErr = numError(cur.targetLevelDb, -30, -10);
  const customOk =
    cur.method !== "custom" || (cur.customRepo.trim() !== "" && cur.customFile.trim() !== "");
  const valid = !gainErr && !levelErr && customOk;

  const onSave = () => {
    void save((c) => ({
      [PATHS.method]: c.method,
      [PATHS.device]: c.device,
      [PATHS.customRepo]: c.customRepo,
      [PATHS.customFile]: c.customFile,
      [PATHS.noiseReduction]: c.noiseReduction,
      [PATHS.amplify]: c.amplify,
      [PATHS.normalize]: c.normalize,
      [PATHS.gainDb]: Number(c.gainDb),
      [PATHS.targetLevelDb]: Number(c.targetLevelDb),
    }))
      .then(() => show(isLive ? "Audio settings saved." : "Audio settings saved (mock)."))
      .catch((e) => show(`Could not save: ${(e as Error).message}`));
  };

  return (
    <SectionCard
      title="Audio Processing"
      sub={
        isLive
          ? "Enhancement method and processing options. Saved here is what the pipeline resolves."
          : "Enhancement method and processing options (mock)."
      }
    >
      <Field
        label="Audio enhancement method"
        htmlFor="aud-method"
        hint={METHODS.find((m) => m.id === cur.method)?.hint}
      >
        <div className="flex flex-wrap items-center gap-2">
          <select
            id="aud-method"
            value={cur.method}
            onChange={(e) => set("method", e.target.value)}
            className={`${inputCls} min-w-0 flex-1`}
          >
            {METHODS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          <EnvSourceBadge source={fieldSource(fields, PATHS.method)} />
        </div>
      </Field>

      <Field
        label="Enhancement device"
        htmlFor="aud-device"
        hint={DEVICES.find((d) => d.id === cur.device)?.hint}
      >
        <div className="flex flex-wrap items-center gap-2">
          <select
            id="aud-device"
            value={cur.device}
            onChange={(e) => set("device", e.target.value)}
            className={`${inputCls} min-w-0 flex-1`}
          >
            {DEVICES.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
          <EnvSourceBadge source={fieldSource(fields, PATHS.device)} />
        </div>
      </Field>

      {cur.method === "custom" ? (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="HuggingFace repo" htmlFor="aud-repo" hint="e.g. sample-org/sample-model">
            <input
              id="aud-repo"
              value={cur.customRepo}
              onChange={(e) => set("customRepo", e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="off"
            />
          </Field>
          <Field label="ONNX filename" htmlFor="aud-file" hint="e.g. model.onnx">
            <input
              id="aud-file"
              value={cur.customFile}
              onChange={(e) => set("customFile", e.target.value)}
              className={`${inputCls} font-mono`}
              autoComplete="off"
            />
          </Field>
        </div>
      ) : null}
      {cur.method === "custom" && !customOk ? (
        <p className="mt-2 text-xs text-danger" role="alert">
          Enter both a HuggingFace repo and an ONNX filename.
        </p>
      ) : null}

      <h3 className="mt-4 text-sm font-semibold">Processing options</h3>
      <div className="mt-2 grid grid-cols-1 gap-2">
        <Toggle
          checked={cur.noiseReduction}
          onChange={(v) => set("noiseReduction", v)}
          label="Noise Reduction"
          hint="Apply noise reduction during processing."
        />
        <Toggle
          checked={cur.amplify}
          onChange={(v) => set("amplify", v)}
          label="Audio Amplification"
          hint="Apply audio amplification."
        />
        <Toggle
          checked={cur.normalize}
          onChange={(v) => set("normalize", v)}
          label="Audio Normalization"
          hint="Normalize audio levels."
        />
      </div>
      {fieldSource(fields, PATHS.noiseReduction) !== "db" &&
      fieldSource(fields, PATHS.noiseReduction) !== "default" ? (
        <p className="mt-1 text-xs text-muted" role="status">
          Noise reduction is overridden by the environment:{" "}
          <EnvSourceBadge source={fieldSource(fields, PATHS.noiseReduction)} />
        </p>
      ) : null}

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="min-w-0">
          <label htmlFor="aud-gain" className="text-xs font-medium text-muted">
            Gain (dB): <span className="font-mono text-mist">{cur.gainDb} dB</span>
          </label>
          <input
            id="aud-gain"
            type="range"
            min={-10}
            max={10}
            step={0.1}
            value={Number.isNaN(Number(cur.gainDb)) ? 0 : Number(cur.gainDb)}
            onChange={(e) => set("gainDb", e.target.value)}
            className="mt-1 min-h-[44px] w-full"
          />
          <input
            value={cur.gainDb}
            onChange={(e) => set("gainDb", e.target.value)}
            inputMode="decimal"
            aria-label="Gain in decibels, exact value"
            className={`${inputCls} mt-1 font-mono`}
            autoComplete="off"
          />
          <div className="mt-1">
            <EnvSourceBadge source={fieldSource(fields, PATHS.gainDb)} />
          </div>
          {gainErr ? (
            <p className="mt-1 text-xs text-danger" role="alert">
              {gainErr}
            </p>
          ) : null}
        </div>
        <div className="min-w-0">
          <label htmlFor="aud-level" className="text-xs font-medium text-muted">
            Target level (dB): <span className="font-mono text-mist">{cur.targetLevelDb} dB</span>
          </label>
          <input
            id="aud-level"
            type="range"
            min={-30}
            max={-10}
            step={1}
            value={Number.isNaN(Number(cur.targetLevelDb)) ? -22 : Number(cur.targetLevelDb)}
            onChange={(e) => set("targetLevelDb", e.target.value)}
            className="mt-1 min-h-[44px] w-full"
          />
          <input
            value={cur.targetLevelDb}
            onChange={(e) => set("targetLevelDb", e.target.value)}
            inputMode="decimal"
            aria-label="Target level in decibels, exact value"
            className={`${inputCls} mt-1 font-mono`}
            autoComplete="off"
          />
          <div className="mt-1">
            <EnvSourceBadge source={fieldSource(fields, PATHS.targetLevelDb)} />
          </div>
          {levelErr ? (
            <p className="mt-1 text-xs text-danger" role="alert">
              {levelErr}
            </p>
          ) : null}
        </div>
      </div>

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
