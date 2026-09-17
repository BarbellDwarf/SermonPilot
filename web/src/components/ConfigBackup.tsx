import { useId, useState } from "react";
import { backupApi, isLive, type UserBackup } from "../api/client";
import { Button, Chip, ConfirmDialog, Field, SectionCard, inputCls } from "./ui";

const MASKED_BACKUP = `{
  "app": "sermonpilot",
  "backup_kind": "full-data",
  "tables": {
    "sermons": 5,
    "accounts": 2,
    "connections": 3,
    "templates": 6
  },
  "preview": {
    "theme": "dark",
    "transcription_backend": "faster_whisper_local",
    "sermons": ["Sample Teaching 1", "Sample Teaching 2"]
  },
  "secrets": "***"
}`;

interface HistoryEntry {
  id: string;
  when: string;
  note: string;
}

const INITIAL_HISTORY: HistoryEntry[] = [
  { id: "bkp-3", when: "2026-09-14 09:12", note: "Audio method -> deepfilternet (mock)" },
  { id: "bkp-2", when: "2026-09-12 18:40", note: "Transcription backend -> local (mock)" },
  { id: "bkp-1", when: "2026-09-10 11:05", note: "Initial sample data (mock)" },
];

export function ConfigBackupSection({ show }: { show: (m: string) => void }) {
  const [backup, setBackup] = useState<UserBackup | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(INITIAL_HISTORY);
  const [restoreText, setRestoreText] = useState("");
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [pendingApply, setPendingApply] = useState(false);
  const [pendingReset, setPendingReset] = useState(false);
  const [copied, setCopied] = useState(false);
  const uid = useId();

  const maskedInUpload =
    restoreText.includes("'***'") || restoreText.includes('"***"') || /(^|\s)\*\*\*(\s|$)/m.test(restoreText);

  const applyLive = (text: string) => {
    try {
      const parsed = JSON.parse(text) as { settings?: Record<string, unknown> };
      void backupApi
        .restore({ settings: parsed.settings ?? {} })
        .then((r) => {
          setHistory((hs) => [
            { id: `bkp-${Date.now() % 100000}`, when: "just now", note: `Restored ${r.restored} setting group(s)` },
            ...hs,
          ]);
          setRestoreText("");
          show("Backup applied.");
          setPendingApply(false);
        })
        .catch((e) => {
          setRestoreError((e as Error).message);
          setPendingApply(false);
        });
    } catch {
      setRestoreError("Backup data must be the JSON downloaded from this page.");
      setPendingApply(false);
    }
  };

  const requestApply = () => {
    const text = restoreText.trim();
    if (!text) {
      setRestoreError("Paste backup data first, or choose a backup file below.");
      return;
    }
    if (maskedInUpload) {
      setRestoreError(
        "This backup contains masked secrets ('***'). Applying it would overwrite stored keys with the mask, so the restore was rejected (mock). Paste a backup with real values first.",
      );
      return;
    }
    if (!text.startsWith("{")) {
      setRestoreError("Backup data must be the JSON downloaded from this page.");
      return;
    }
    if (isLive) {
      applyLive(text);
      return;
    }
    setRestoreError(null);
    setPendingApply(true);
  };

  const pickFile = (f: File | undefined) => {
    if (!f) return;
    void f.text().then((t) => {
      setRestoreText(t);
      setRestoreError(null);
      show(`Backup file loaded (mock): ${f.name}.`);
    }).catch(() => {
      setRestoreError("Could not read that file in this browser (mock).");
    });
  };

  const download = () => {
    if (isLive) {
      void backupApi
        .download()
        .then((data) => {
          setBackup(data);
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "sermonpilot-backup.json";
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
          show("Backup downloaded: secrets masked.");
        })
        .catch((e) => show(`Could not download backup: ${(e as Error).message}`));
      return;
    }
    const blob = new Blob([MASKED_BACKUP], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sermonpilot-backup.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    show("Backup downloaded (mock): secrets masked as ***.");
  };

  return (
    <SectionCard
      title="Backup & Restore"
      sub="Everything lives in the app database. Download is a full data backup; upload restores it (mock). Secrets stay masked and masked values can never be applied."
    >
      <details open className="rounded-md border border-line p-3">
        <summary className="min-h-[44px] cursor-pointer text-sm font-semibold">
          Current data <span className="font-normal text-muted">(masked preview)</span>
        </summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-ink p-3 font-mono text-xs text-mist">
          {backup ? JSON.stringify(backup, null, 2) : MASKED_BACKUP}
        </pre>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button onClick={download} aria-label="Download full data backup">
            Download backup
          </Button>
          <Button
            onClick={() => {
              const text = backup ? JSON.stringify(backup, null, 2) : MASKED_BACKUP;
              void navigator.clipboard?.writeText(text).catch(() => undefined);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 2000);
              show(`Backup copied${isLive ? "" : " (mock)"}.`);
            }}
            aria-label="Copy masked backup"
          >
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </details>

      <div className="mt-4">
        <h3 className="text-sm font-semibold">Restore from backup</h3>
        <p className="mt-0.5 text-xs text-muted">
          Paste backup data from a download, or choose a backup file. Masked secrets ('***')
          are rejected.
        </p>
        <div className="mt-2">
          <Field label="Backup data" htmlFor={`${uid}-restore`}>
            <textarea
              id={`${uid}-restore`}
              value={restoreText}
              onChange={(e) => {
                setRestoreText(e.target.value);
                setRestoreError(null);
              }}
              className={`${inputCls} min-h-[120px] py-2 font-mono`}
              rows={6}
              placeholder={'{\n  "app": "sermonpilot",\n  "backup_kind": "full-data"\n}'}
            />
          </Field>
        </div>
        <div className="mt-2">
          <label htmlFor={`${uid}-file`} className="text-xs font-medium text-muted">
            Or choose a backup file
          </label>
          <input
            id={`${uid}-file`}
            type="file"
            accept="application/json,.json"
            onChange={(e) => pickFile(e.target.files?.[0])}
            className="mt-1 block min-h-[44px] w-full min-w-0 text-sm text-mist"
          />
        </div>
        {restoreError ? (
          <p className="mt-2 text-xs text-danger" role="alert">
            {restoreError}
          </p>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="primary" onClick={requestApply} aria-label="Apply pasted backup">
            Apply backup
          </Button>
          <Button
            onClick={() => {
              setRestoreText("");
              setRestoreError(null);
            }}
            aria-label="Clear pasted backup"
          >
            Clear
          </Button>
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-sm font-semibold">Backup history</h3>
        <p className="mt-0.5 text-xs text-muted">Mock snapshot list. Restoring adds a new entry.</p>
        <ul className="mt-2 flex flex-col gap-2" aria-label="Backup history">
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
                    { id: `bkp-${Date.now() % 100000}`, when: "just now", note: `Restored ${h.id} (mock)` },
                    ...hs,
                  ]);
                  show(`Backup restored (mock): ${h.id}.`);
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
          Resets every settings tab to sample defaults (mock). Stored data is replaced. This cannot be undone.
        </p>
        <div className="mt-2">
          <Button variant="danger" onClick={() => setPendingReset(true)} aria-label="Reset all settings to defaults">
            Reset to defaults
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingApply}
        title="Apply backup?"
        body="Replace the current data with the pasted backup? This cannot be undone."
        confirmLabel="Apply"
        onConfirm={() => {
          setHistory((hs) => [
            { id: `bkp-${Date.now() % 100000}`, when: "just now", note: "Pasted backup applied (mock)" },
            ...hs,
          ]);
          setRestoreText("");
          show("Backup applied (mock).");
          setPendingApply(false);
        }}
        onClose={() => setPendingApply(false)}
      />
      <ConfirmDialog
        open={pendingReset}
        title="Reset all settings?"
        body="Reset every settings tab to sample defaults (mock)? This cannot be undone."
        confirmLabel="Reset"
        onConfirm={() => {
          setHistory((hs) => [
            { id: `bkp-${Date.now() % 100000}`, when: "just now", note: "Reset to defaults (mock)" },
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

export const BackupRestoreSection = ConfigBackupSection;
