import { useId, useState } from "react";
import { Button, Chip, ConfirmDialog, Field, SectionCard, inputCls } from "./ui";

const MASKED_YAML = `audio_amplify: true
audio_enhancement_method: deepfilternet
audio_gain_db: 0.5
audio_normalize: true
audio_noise_reduction: true
audio_target_level_db: -22.0
debug: false
dry_run: false
hashtag_verification: true
llm:
  primary:
    provider: ollama
output_directory: processed_sermons
save_original_audio: true
save_transcript: true
sermonaudio:
  api_key: '***'
  broadcaster_id: sample-broadcaster
transcription:
  backend: faster_whisper_local
  faster_whisper_local:
    compute_type: float16
    device: auto
    language: en
    model: base
`;

interface HistoryEntry {
  id: string;
  when: string;
  note: string;
}

const INITIAL_HISTORY: HistoryEntry[] = [
  { id: "cfg-3", when: "2026-09-14 09:12", note: "Audio method -> deepfilternet (mock)" },
  { id: "cfg-2", when: "2026-09-12 18:40", note: "Transcription backend -> local (mock)" },
  { id: "cfg-1", when: "2026-09-10 11:05", note: "Initial sample configuration (mock)" },
];

export function ConfigBackupSection({ show }: { show: (m: string) => void }) {
  const [history, setHistory] = useState<HistoryEntry[]>(INITIAL_HISTORY);
  const [restoreText, setRestoreText] = useState("");
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [pendingApply, setPendingApply] = useState(false);
  const [pendingReset, setPendingReset] = useState(false);
  const [copied, setCopied] = useState(false);
  const uid = useId();

  const maskedInUpload =
    restoreText.includes("'***'") || restoreText.includes('"***"') || /(^|\s)\*\*\*(\s|$)/m.test(restoreText);

  const requestApply = () => {
    const text = restoreText.trim();
    if (!text) {
      setRestoreError("Paste YAML configuration first.");
      return;
    }
    if (maskedInUpload) {
      setRestoreError(
        "This backup contains masked secrets ('***'). Applying it would overwrite stored keys with the mask, so the restore was rejected (mock). Remove masked values or paste the real keys first.",
      );
      return;
    }
    if (!/^[\w-]+:/m.test(text)) {
      setRestoreError("Configuration must contain a YAML mapping at the top level (mock check).");
      return;
    }
    setRestoreError(null);
    setPendingApply(true);
  };

  const downloadMock = () => {
    const blob = new Blob([MASKED_YAML], { type: "text/yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "config_backup.yaml";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    show("Config downloaded (mock): secrets masked as ***.");
  };

  return (
    <SectionCard
      title="Config Backup & Restore"
      sub="YAML backup and restore plus history (mock). Secrets display masked and masked values can never be applied."
    >
      <details open className="rounded-md border border-line p-3">
        <summary className="min-h-[44px] cursor-pointer text-sm font-semibold">
          Current configuration <span className="font-normal text-muted">(masked)</span>
        </summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-ink p-3 font-mono text-xs text-mist">
          {MASKED_YAML}
        </pre>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button onClick={downloadMock} aria-label="Download masked config backup">
            Download config
          </Button>
          <Button
            onClick={() => {
              void navigator.clipboard?.writeText(MASKED_YAML).catch(() => undefined);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 2000);
              show("Masked config copied (mock).");
            }}
            aria-label="Copy masked config"
          >
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </details>

      <div className="mt-4">
        <h3 className="text-sm font-semibold">Restore configuration</h3>
        <p className="mt-0.5 text-xs text-muted">
          Paste YAML from a backup. Masked secrets ('***') are rejected, matching the legacy
          uploader.
        </p>
        <div className="mt-2">
          <Field label="Configuration YAML" htmlFor={`${uid}-restore`}>
            <textarea
              id={`${uid}-restore`}
              value={restoreText}
              onChange={(e) => {
                setRestoreText(e.target.value);
                setRestoreError(null);
              }}
              className={`${inputCls} min-h-[120px] py-2 font-mono`}
              rows={6}
              placeholder={"dry_run: false\noutput_directory: processed_sermons"}
            />
          </Field>
        </div>
        {restoreError ? (
          <p className="mt-2 text-xs text-danger" role="alert">
            {restoreError}
          </p>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="primary" onClick={requestApply} aria-label="Apply pasted configuration">
            Apply configuration
          </Button>
          <Button
            onClick={() => {
              setRestoreText("");
              setRestoreError(null);
            }}
            aria-label="Clear pasted configuration"
          >
            Clear
          </Button>
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-sm font-semibold">Config history</h3>
        <p className="mt-0.5 text-xs text-muted">Mock snapshot list. Restoring adds a new entry.</p>
        <ul className="mt-2 flex flex-col gap-2" aria-label="Config history">
          {history.map((h) => (
            <li
              key={h.id}
              className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{h.note}</p>
                <p className="font-mono text-xs text-muted">
                  {h.id} · {h.when}
                </p>
              </div>
              <Chip tone="neutral">snapshot</Chip>
              <Button
                onClick={() => {
                  setHistory((hs) => [
                    { id: `cfg-${Date.now() % 100000}`, when: "just now", note: `Restored ${h.id} (mock)` },
                    ...hs,
                  ]);
                  show(`Config restored (mock): ${h.id}.`);
                }}
                aria-label={`Restore snapshot ${h.id}`}
              >
                Restore
              </Button>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4 rounded-md border border-danger p-3">
        <h3 className="text-sm font-semibold">Reset to defaults</h3>
        <p className="mt-0.5 text-xs text-muted">
          Resets every section above to sample defaults (mock). This cannot be undone.
        </p>
        <div className="mt-2">
          <Button variant="danger" onClick={() => setPendingReset(true)} aria-label="Reset all settings to defaults">
            Reset to defaults
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingApply}
        title="Apply configuration?"
        body="Replace the current mock settings with the pasted YAML? This cannot be undone."
        confirmLabel="Apply"
        onConfirm={() => {
          setHistory((hs) => [
            { id: `cfg-${Date.now() % 100000}`, when: "just now", note: "Pasted YAML applied (mock)" },
            ...hs,
          ]);
          setRestoreText("");
          show("Configuration applied (mock).");
          setPendingApply(false);
        }}
        onClose={() => setPendingApply(false)}
      />
      <ConfirmDialog
        open={pendingReset}
        title="Reset all settings?"
        body="Reset every settings section to sample defaults (mock)? This cannot be undone."
        confirmLabel="Reset"
        onConfirm={() => {
          setHistory((hs) => [
            { id: `cfg-${Date.now() % 100000}`, when: "just now", note: "Reset to defaults (mock)" },
            ...hs,
          ]);
          show("Settings reset to defaults (mock).");
          setPendingReset(false);
        }}
        onClose={() => setPendingReset(false)}
      />
    </SectionCard>
  );
}
