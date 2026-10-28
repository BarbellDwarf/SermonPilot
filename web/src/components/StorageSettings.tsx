import { useMemo, useState } from "react";
import { isLive } from "../api/client";
import { fieldSource, useConfigForm } from "../api/useConfigSection";
import { EnvSourceBadge, Field, Fieldset, SaveBar, SectionCard, inputCls } from "./ui";

interface StorageState {
  inputDirectory: string;
  outputDirectory: string;
  uploadDir: string;
  processingTempDir: string;
  reviewMediaDirectory: string;
  trashDirectory: string;
  trashRetentionDays: string;
}

const DEFAULTS: StorageState = {
  inputDirectory: "",
  outputDirectory: "",
  uploadDir: "",
  processingTempDir: "",
  reviewMediaDirectory: "",
  trashDirectory: "",
  trashRetentionDays: "30",
};

const PATHS = {
  inputDirectory: "input_directory",
  outputDirectory: "output_directory",
  uploadDir: "upload_dir",
  processingTempDir: "processing_temp_dir",
  reviewMediaDirectory: "review_media_directory",
  trashDirectory: "trash_directory",
  trashRetentionDays: "trash_retention_days",
} as const;

export function StorageSettingsSection({
  show,
  isAdmin,
}: {
  show: (m: string) => void;
  isAdmin: boolean;
}) {
  const normalize = useMemo(
    () => (values: StorageState): StorageState => ({
      ...values,
      trashRetentionDays: String(values.trashRetentionDays),
    }),
    [],
  );
  const { cur, fields, dirty, set, save } = useConfigForm<StorageState>(
    "storage",
    DEFAULTS,
    PATHS,
    normalize,
  );
  const [saving, setSaving] = useState(false);
  const retentionError =
    !/^\d+(\.\d+)?$/.test(cur.trashRetentionDays.trim()) ||
    Number(cur.trashRetentionDays) < 0
      ? "Enter zero or more days."
      : null;

  const field = (
    key: keyof StorageState,
    id: string,
    label: string,
    hint: string,
  ) => (
    <Field label={label} htmlFor={id} hint={hint}>
      <input
        id={id}
        value={cur[key]}
        onChange={(e) => set(key, e.target.value)}
        className={`${inputCls} font-mono`}
        autoComplete="off"
        disabled={!isAdmin}
        placeholder="Built-in default"
      />
      <div className="mt-1">
        <EnvSourceBadge source={fieldSource(fields, PATHS[key])} />
      </div>
    </Field>
  );

  return (
    <SectionCard
      title="Storage"
      sub={
        isAdmin
          ? "Roots the pipeline reads and writes. Only an admin can change these."
          : "Roots the pipeline reads and writes. An admin can change these."
      }
    >
      <Fieldset legend="Source roots" help="Server-path sources must live under the input or per-user ingest directory.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {field("inputDirectory", "sto-in", "Input directory", "Shared operator source folder.")}
          {field("outputDirectory", "sto-out", "Default output directory", "Used when a run has no per-user output.")}
          {field("uploadDir", "sto-uploads", "Upload directory", "Browser uploads stage here. Blank uses the cache root.")}
          {field("processingTempDir", "sto-temp", "Processing temp directory", "Scratch space for renders. Blank uses the cache root.")}
        </div>
      </Fieldset>

      <Fieldset legend="Review media" help="Where streamable copies live for the console player.">
        {field("reviewMediaDirectory", "sto-review", "Review media directory", "Blank uses the cache root.")}
      </Fieldset>

      <Fieldset legend="Deletion safety" help="Every media delete moves the item here before it can be swept.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {field("trashDirectory", "sto-trash", "Trash directory", "Blank uses the cache root.")}
          <Field label="Trash retention (days)" htmlFor="sto-retention" hint="0 or less keeps items forever.">
            <input
              id="sto-retention"
              value={cur.trashRetentionDays}
              onChange={(e) => set("trashRetentionDays", e.target.value)}
              className={`${inputCls} font-mono`}
              inputMode="decimal"
              autoComplete="off"
              disabled={!isAdmin}
            />
            <div className="mt-1">
              <EnvSourceBadge source={fieldSource(fields, PATHS.trashRetentionDays)} />
            </div>
            {retentionError ? (
              <p className="mt-1 text-xs text-danger" role="alert">
                {retentionError}
              </p>
            ) : null}
          </Field>
        </div>
      </Fieldset>

      {!isAdmin ? (
        <p className="text-xs text-muted" role="status">
          Read-only for your role. Ask an admin to change a storage root.
        </p>
      ) : null}

      <SaveBar
        dirty={isAdmin && dirty && !retentionError}
        saved={!isAdmin || !dirty}
        busy={saving}
        onSave={() => {
          if (!isAdmin || saving) return;
          setSaving(true);
          void save((c) => ({
            [PATHS.inputDirectory]: c.inputDirectory,
            [PATHS.outputDirectory]: c.outputDirectory,
            [PATHS.uploadDir]: c.uploadDir,
            [PATHS.processingTempDir]: c.processingTempDir,
            [PATHS.reviewMediaDirectory]: c.reviewMediaDirectory,
            [PATHS.trashDirectory]: c.trashDirectory,
            [PATHS.trashRetentionDays]: Number(c.trashRetentionDays),
          }))
            .then(() => show(isLive ? "Storage settings saved." : "Storage settings saved (demo)."))
            .catch((e) => show(`Could not save: ${(e as Error).message}`))
            .finally(() => setSaving(false));
        }}
      />
    </SectionCard>
  );
}
