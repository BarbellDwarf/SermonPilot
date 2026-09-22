import { useEffect, useState } from "react";
import { cloudApi, isLive, outputDirApi, type ApiCloudRemote, type ApiConfigField } from "../api/client";
import { fieldSource, useConfigForm } from "../api/useConfigSection";
import { Button, Chip, EnvSourceBadge, Field, SectionCard, Toggle, inputCls } from "./ui";
import { FileExplorerDialog } from "./FileExplorer";

interface GeneralState {
  dryRun: boolean;
  debug: boolean;
  hashtagVerification: boolean;
  saveOriginal: boolean;
  saveTranscript: boolean;
}

const DEFAULTS: GeneralState = {
  dryRun: false,
  debug: false,
  hashtagVerification: true,
  saveOriginal: true,
  saveTranscript: true,
};

const PATHS = {
  dryRun: "dry_run",
  debug: "debug",
  hashtagVerification: "hashtag_verification",
  saveOriginal: "save_original_audio",
  saveTranscript: "save_transcript",
} as const;

function overrideList(fields: Record<string, ApiConfigField>): { label: string; source: string }[] {
  const labels: Record<string, string> = {
    dry_run: "Dry run",
    debug: "Debug",
    hashtag_verification: "Hashtag verification",
    save_original_audio: "Save original audio",
    save_transcript: "Save transcript",
  };
  return Object.entries(labels)
    .map(([path, label]) => ({ label, source: fieldSource(fields, path) }))
    .filter((item) => item.source !== "db" && item.source !== "default");
}

export function GeneralSettingsSection({ show }: { show: (m: string) => void }) {
  const { cur, fields, dirty, set, save } = useConfigForm<GeneralState>(
    "general",
    DEFAULTS,
    PATHS,
  );
  const [outputDir, setOutputDir] = useState("processed_sermons");
  const [savedOutputDir, setSavedOutputDir] = useState<string | null>(null);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [cloudOpen, setCloudOpen] = useState(false);
  const [remotes, setRemotes] = useState<ApiCloudRemote[]>([]);
  const remoteMatch = /^remote:([A-Za-z0-9._-]{1,64}):(.*)$/.exec(outputDir.trim());
  const [cloudRemote, setCloudRemote] = useState(remoteMatch?.[1] ?? "");

  useEffect(() => {
    if (!isLive) {
      setSavedOutputDir("processed_sermons");
      return;
    }
    void outputDirApi
      .get()
      .then((r) => {
        setOutputDir(r.output_dir);
        setSavedOutputDir(r.output_dir);
      })
      .catch(() => setSavedOutputDir("processed_sermons"));
    void cloudApi
      .list()
      .then((r) => setRemotes(r.items))
      .catch(() => setRemotes([]));
  }, []);

  const outputDirty = savedOutputDir !== null && outputDir !== savedOutputDir;
  const dirtyAll = (isLive ? dirty : false) || outputDirty;

  const chooseRemote = (name: string) => {
    setCloudRemote(name);
    if (name) setOutputDir(`remote:${name}:`);
  };

  const pickCloudFolder = (path: string) => {
    const sub = path.replace(/^\/+/, "");
    setOutputDir(`remote:${cloudRemote}:${sub}`);
  };

  const onSave = () => {
    const persistOutput = outputDirty
      ? outputDirApi.put(outputDir).then(() => setSavedOutputDir(outputDir))
      : Promise.resolve();
    persistOutput
      .then(() =>
        save((c) => ({
          [PATHS.dryRun]: c.dryRun,
          [PATHS.debug]: c.debug,
          [PATHS.hashtagVerification]: c.hashtagVerification,
          [PATHS.saveOriginal]: c.saveOriginal,
          [PATHS.saveTranscript]: c.saveTranscript,
        })),
      )
      .then(() => show(isLive ? "General settings saved." : "General settings saved (mock)."))
      .catch((e) => show(`Could not save: ${(e as Error).message}`));
  };

  const overrides = overrideList(fields);

  return (
    <SectionCard
      title="General"
      sub={
        isLive
          ? "Processing options and output settings. Saved here is what the pipeline resolves."
          : "Processing options and output settings (mock)."
      }
    >
      <h3 className="text-sm font-semibold">Processing options</h3>
      <div className="mt-2 grid grid-cols-1 gap-2">
        <Toggle
          checked={cur.dryRun}
          onChange={(v) => set("dryRun", v)}
          label="Dry Run Mode (default)"
          hint="Preview changes without uploading by default."
        />
        <Toggle
          checked={cur.debug}
          onChange={(v) => set("debug", v)}
          label="Debug Mode"
          hint="Verbose debug output during processing."
        />
        <Toggle
          checked={cur.hashtagVerification}
          onChange={(v) => set("hashtagVerification", v)}
          label="Hashtag Verification"
          hint="Verify hashtags through a second LLM pass."
        />
      </div>

      {overrides.length > 0 ? (
        <div
          className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-line bg-ink px-3 py-2 text-xs text-muted"
          role="status"
        >
          <span>Overridden by the environment:</span>
          {overrides.map((item) => (
            <span key={item.source} className="flex items-center gap-1">
              <span>{item.label}</span>
              <EnvSourceBadge source={item.source} />
            </span>
          ))}
        </div>
      ) : null}

      <h3 className="mt-4 text-sm font-semibold">Output settings</h3>
      <div className="mt-2 grid grid-cols-1 gap-2">
        <Field label="Output directory" htmlFor="gen-outdir" hint="Local directory or a cloud remote (remote:<name>:<folder>) for processed sermon files. This is your default for new sermons.">
          <div className="flex flex-wrap items-center gap-2">
            <input
              id="gen-outdir"
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
              className={`${inputCls} min-w-0 flex-1 font-mono`}
              autoComplete="off"
            />
            <Button variant="secondary" onClick={() => setBrowseOpen(true)}>
              Browse local…
            </Button>
          </div>
        </Field>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <select
            aria-label="Cloud remote"
            value={cloudRemote}
            onChange={(e) => chooseRemote(e.target.value)}
            className={`${inputCls} min-w-0 flex-1`}
          >
            <option value="">Cloud remote…</option>
            {remotes.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name} · {r.provider}
              </option>
            ))}
          </select>
          <Button
            variant="secondary"
            disabled={!cloudRemote}
            onClick={() => setCloudOpen(true)}
          >
            Browse cloud…
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-live="polite" aria-label="Destination validation">
          {remoteMatch ? (
            <>
              <Chip tone="ok">cloud remote</Chip>
              <Chip tone="info">{remoteMatch[2] ? `folder: ${remoteMatch[2]}` : "remote root"}</Chip>
            </>
          ) : (
            <>
              <Chip tone="ok">local folder</Chip>
              <Chip tone="info">{outputDir || "no path"}</Chip>
            </>
          )}
        </div>
        <Toggle
          checked={cur.saveOriginal}
          onChange={(v) => set("saveOriginal", v)}
          label="Save Original Audio"
          hint="Keep a copy of the original audio file."
        />
        <Toggle
          checked={cur.saveTranscript}
          onChange={(v) => set("saveTranscript", v)}
          label="Save Transcript"
          hint="Save the sermon transcript as a text file."
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={!dirtyAll} onClick={onSave}>
          Save
        </Button>
        {!dirtyAll ? (
          <span className="text-xs text-muted">{isLive ? "Saved." : "No unsaved changes."}</span>
        ) : (
          <span className="text-xs text-warn" role="status">
            Unsaved changes.
          </span>
        )}
      </div>

      <FileExplorerDialog
        open={browseOpen}
        title="Choose an output directory"
        pick="folder"
        onPickFolder={(p) => setOutputDir(p)}
        onClose={() => setBrowseOpen(false)}
      />
      {cloudRemote ? (
        <FileExplorerDialog
          open={cloudOpen}
          title="Choose a cloud output folder"
          mode="cloud"
          name={cloudRemote}
          pick="folder"
          onPickFolder={pickCloudFolder}
          onClose={() => setCloudOpen(false)}
        />
      ) : null}
    </SectionCard>
  );
}
