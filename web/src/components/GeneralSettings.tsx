import { useEffect, useState } from "react";
import { cloudApi, isLive, outputDirApi, type ApiCloudRemote } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { Button, Chip, Field, SectionCard, Toggle, inputCls } from "./ui";
import { FileExplorerDialog } from "./FileExplorer";

interface GeneralState {
  dryRun: boolean;
  debug: boolean;
  hashtagVerification: boolean;
  outputDir: string;
  saveOriginal: boolean;
  saveTranscript: boolean;
}

const DEFAULTS: GeneralState = {
  dryRun: false,
  debug: false,
  hashtagVerification: true,
  outputDir: "processed_sermons",
  saveOriginal: true,
  saveTranscript: true,
};

export function GeneralSettingsSection({ show }: { show: (m: string) => void }) {
  const [saved, setSaved] = useUserSettings<GeneralState>("settings.general", DEFAULTS);
  const [cur, setCur] = useState<GeneralState>(saved);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [cloudOpen, setCloudOpen] = useState(false);
  const [remotes, setRemotes] = useState<ApiCloudRemote[]>([]);
  const remoteMatch = /^remote:([A-Za-z0-9._-]{1,64}):(.*)$/.exec(cur.outputDir.trim());
  const [cloudRemote, setCloudRemote] = useState(remoteMatch?.[1] ?? "");
  const dirty = isLive && JSON.stringify(cur) !== JSON.stringify(saved);
  const set = <K extends keyof GeneralState>(k: K, v: GeneralState[K]) =>
    setCur((c) => ({ ...c, [k]: v }));

  useEffect(() => {
    if (!isLive) return;
    void cloudApi
      .list()
      .then((r) => setRemotes(r.items))
      .catch(() => setRemotes([]));
  }, []);

  const chooseRemote = (name: string) => {
    setCloudRemote(name);
    if (name) set("outputDir", `remote:${name}:`);
  };

  const pickCloudFolder = (path: string) => {
    const sub = path.replace(/^\/+/, "");
    set("outputDir", `remote:${cloudRemote}:${sub}`);
  };

  const save = () => {
    const commit = () => {
      setSaved(cur);
      setCur(cur);
      show(isLive ? "General settings saved." : "General settings saved (mock).");
    };
    if (isLive && cur.outputDir !== saved.outputDir) {
      void outputDirApi
        .put(cur.outputDir)
        .then(commit)
        .catch((e) => show(`Output directory rejected: ${(e as Error).message}`));
      return;
    }
    commit();
  };

  return (
    <SectionCard
      title="General"
      sub="Processing options and output settings (mock). Mirrors the legacy General tab minus SermonAudio credentials, which live under SermonAudio Accounts."
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

      <h3 className="mt-4 text-sm font-semibold">Output settings</h3>
      <div className="mt-2 grid grid-cols-1 gap-2">
        <Field label="Output directory" htmlFor="gen-outdir" hint="Local directory or a cloud remote (remote:<name>:<folder>) for processed sermon files. This is your default for new sermons.">
          <div className="flex flex-wrap items-center gap-2">
            <input
              id="gen-outdir"
              value={cur.outputDir}
              onChange={(e) => set("outputDir", e.target.value)}
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
              <Chip tone="info">{cur.outputDir || "no path"}</Chip>
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
        <Button variant="primary" disabled={!dirty} onClick={save}>
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

      <FileExplorerDialog
        open={browseOpen}
        title="Choose an output directory"
        pick="folder"
        onPickFolder={(p) => set("outputDir", p)}
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
