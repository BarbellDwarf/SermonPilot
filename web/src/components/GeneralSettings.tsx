import { useState } from "react";
import { isLive } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { Button, Field, SectionCard, Toggle, inputCls } from "./ui";

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
  const dirty = isLive && JSON.stringify(cur) !== JSON.stringify(saved);
  const set = <K extends keyof GeneralState>(k: K, v: GeneralState[K]) =>
    setCur((c) => ({ ...c, [k]: v }));

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
        <Field label="Output directory" htmlFor="gen-outdir" hint="Directory for processed sermon files.">
          <input
            id="gen-outdir"
            value={cur.outputDir}
            onChange={(e) => set("outputDir", e.target.value)}
            className={`${inputCls} font-mono`}
            autoComplete="off"
          />
        </Field>
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
        <Button
          variant="primary"
          disabled={!dirty}
          onClick={() => {
            setSaved(cur);
            setCur(cur);
            show(isLive ? "General settings saved." : "General settings saved (mock).");
          }}
        >
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
