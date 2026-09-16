import { useState } from "react";
import { Button, Field, SectionCard, Toggle, inputCls } from "./ui";

const METHODS = [
  { id: "deepfilternet", label: "DeepFilterNet (standard)", hint: "Standard speech enhancement." },
  { id: "clear-natural", label: "Clear-Natural", hint: "Gentler noise suppression." },
  { id: "clear-studio", label: "Clear-Studio", hint: "Aggressive, podcast-ready." },
  { id: "custom", label: "Custom ONNX", hint: "Point to any ONNX model on HuggingFace." },
  { id: "none", label: "None", hint: "Skip enhancement." },
];

interface AudioState {
  method: string;
  customRepo: string;
  customFile: string;
  useAudacity: boolean;
  noiseReduction: boolean;
  amplify: boolean;
  normalize: boolean;
  gainDb: string;
  targetLevelDb: string;
}

const DEFAULTS: AudioState = {
  method: "deepfilternet",
  customRepo: "",
  customFile: "",
  useAudacity: false,
  noiseReduction: true,
  amplify: true,
  normalize: true,
  gainDb: "0.5",
  targetLevelDb: "-22",
};

function numError(v: string, min: number, max: number): string | null {
  if (!/^-?\d+(\.\d+)?$/.test(v.trim())) return "Must be a number.";
  const n = Number(v);
  if (n < min || n > max) return `Must be between ${min} and ${max}.`;
  return null;
}

export function AudioSettingsSection({ show }: { show: (m: string) => void }) {
  const [cur, setCur] = useState<AudioState>(DEFAULTS);
  const [saved, setSaved] = useState<AudioState>(DEFAULTS);
  const [everSaved, setEverSaved] = useState(false);
  const dirty = JSON.stringify(cur) !== JSON.stringify(saved);
  const set = <K extends keyof AudioState>(k: K, v: AudioState[K]) =>
    setCur((c) => ({ ...c, [k]: v }));

  const gainErr = numError(cur.gainDb, -10, 10);
  const levelErr = numError(cur.targetLevelDb, -30, -10);
  const customOk =
    cur.method !== "custom" || (cur.customRepo.trim() !== "" && cur.customFile.trim() !== "");
  const valid = !gainErr && !levelErr && customOk;

  return (
    <SectionCard
      title="Audio Processing"
      sub="Enhancement method and processing options (mock). Mirrors the legacy Audio tab."
    >
      <Field
        label="Audio enhancement method"
        htmlFor="aud-method"
        hint={METHODS.find((m) => m.id === cur.method)?.hint}
      >
        <select
          id="aud-method"
          value={cur.method}
          onChange={(e) => set("method", e.target.value)}
          className={inputCls}
        >
          {METHODS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
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
      {cur.method === "custom" && customOk ? (
        <p className="mt-2 text-xs text-muted" role="status">
          Will use (mock): {cur.customRepo.trim()}/{cur.customFile.trim()}
        </p>
      ) : null}

      <h3 className="mt-4 text-sm font-semibold">Processing options</h3>
      <div className="mt-2 grid grid-cols-1 gap-2">
        <Toggle
          checked={cur.useAudacity}
          onChange={(v) => set("useAudacity", v)}
          label="Use Audacity Integration"
          hint="Use Audacity with mod-script-pipe if available."
        />
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
          {levelErr ? (
            <p className="mt-1 text-xs text-danger" role="alert">
              {levelErr}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={!dirty || !valid}
          onClick={() => {
            setSaved(cur);
            setEverSaved(true);
            show("Audio settings saved (mock).");
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
