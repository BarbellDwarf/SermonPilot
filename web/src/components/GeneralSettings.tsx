import { useEffect, useState } from "react";
import { cloudApi, isLive, outputDirApi, type ApiCloudRemote } from "../api/client";
import { fieldSource, useConfigForm } from "../api/useConfigSection";
import { Button, Chip, Field, Fieldset, SaveBar, SectionCard, Toggle, inputCls } from "./ui";
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
  const [saving, setSaving] = useState(false);
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
  const dirtyAll = dirty || outputDirty;

  const chooseRemote = (name: string) => {
    setCloudRemote(name);
    if (name) setOutputDir(`remote:${name}:`);
  };

  const pickCloudFolder = (path: string) => {
    const sub = path.replace(/^\/+/, "");
    setOutputDir(`remote:${cloudRemote}:${sub}`);
  };

  const onSave = () => {
    if (saving) return;
    setSaving(true);
    const persistOutput = outputDirty
      ? isLive
        ? outputDirApi.put(outputDir).then(() => setSavedOutputDir(outputDir))
        : Promise.resolve().then(() => setSavedOutputDir(outputDir))
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
      .then(() => show(isLive ? "General settings saved." : "General settings saved (demo)."))
      .catch((e) => show(`Could not save: ${(e as Error).message}`))
      .finally(() => setSaving(false));
  };

  return (
    <SectionCard
      title="General"
      sub={
        isLive
          ? "Processing options and output settings. Saved here is what the pipeline resolves."
          : "Processing options and output settings (demo)."
      }
    >
      <div className="flex flex-col gap-3">
        <Fieldset
          legend="Processing options"
          help="Defaults for every new teaching run. A badge marks a value the environment currently wins."
        >
          <Toggle
            checked={cur.dryRun}
            onChange={(v) => set("dryRun", v)}
            label="Dry run mode (default)"
            hint="Preview changes without uploading by default."
            source={fieldSource(fields, PATHS.dryRun)}
          />
          <Toggle
            checked={cur.debug}
            onChange={(v) => set("debug", v)}
            label="Debug mode"
            hint="Verbose debug output during processing."
            source={fieldSource(fields, PATHS.debug)}
          />
          <Toggle
            checked={cur.hashtagVerification}
            onChange={(v) => set("hashtagVerification", v)}
            label="Hashtag verification"
            hint="Verify hashtags through a second LLM pass."
            source={fieldSource(fields, PATHS.hashtagVerification)}
          />
        </Fieldset>

        <Fieldset legend="Output settings" help="Where processed teaching files land, and what is kept beside them.">
          <Field
            label="Output directory"
            htmlFor="gen-outdir"
            hint="Local directory or a cloud remote (remote:<name>:<folder>) for processed teaching files. This is your default for new teachings."
          >
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
          <div className="flex flex-wrap items-center gap-2">
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
            <Button variant="secondary" disabled={!cloudRemote} onClick={() => setCloudOpen(true)}>
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
            label="Save original audio"
            hint="Keep a copy of the original audio file."
            source={fieldSource(fields, PATHS.saveOriginal)}
          />
          <Toggle
            checked={cur.saveTranscript}
            onChange={(v) => set("saveTranscript", v)}
            label="Save transcript"
            hint="Save the sermon transcript as a text file."
            source={fieldSource(fields, PATHS.saveTranscript)}
          />
        </Fieldset>
      </div>

      <SaveBar dirty={dirtyAll} saved={!dirtyAll} busy={saving} onSave={onSave} />

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
