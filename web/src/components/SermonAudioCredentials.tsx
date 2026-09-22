import { useEffect, useState } from "react";
import { isLive } from "../api/client";
import { fieldSource, fieldValue, useConfigSection } from "../api/useConfigSection";
import { Button, EnvSourceBadge, Field, SectionCard, inputCls } from "./ui";

const FALLBACK: Record<string, unknown> = { api_key: "", broadcaster_id: "" };

/**
 * Human-readable source for one credential. A saved value reads as the
 * database, "default" reads as not configured, and anything else is the
 * winning environment variable.
 */
export function sourceCopy(source: string): string {
  if (source === "db") return "saved in the database";
  if (source === "default") return "not configured";
  return `set by environment: ${source}`;
}

function SourceLine({ label, source }: { label: string; source: string }) {
  return (
    <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted" role="status">
      <span>
        {label}: {sourceCopy(source)}
      </span>
      <EnvSourceBadge source={source} />
    </p>
  );
}

export function SermonAudioCredentialsSection({ show }: { show: (m: string) => void }) {
  const { fields, save } = useConfigSection("sermonaudio", FALLBACK);
  const savedBroadcaster = String(fieldValue(fields, "broadcaster_id", ""));
  const [broadcasterId, setBroadcasterId] = useState(savedBroadcaster);
  const [apiKey, setApiKey] = useState("");

  useEffect(() => {
    setBroadcasterId(savedBroadcaster);
  }, [savedBroadcaster]);

  const apiField = fields["api_key"];
  const apiSource = fieldSource(fields, "api_key");
  const broadcasterSource = fieldSource(fields, "broadcaster_id");
  const dirty = broadcasterId !== savedBroadcaster || apiKey !== "";

  const onSave = () => {
    const values: Record<string, unknown> = { broadcaster_id: broadcasterId };
    if (apiKey.trim()) values["api_key"] = apiKey;
    void save(values)
      .then(() => {
        setApiKey("");
        show(isLive ? "SermonAudio credentials saved." : "SermonAudio credentials saved (mock).");
      })
      .catch((e) => show(`Could not save: ${(e as Error).message}`));
  };

  return (
    <SectionCard
      title="Single-account fallback"
      sub="The credentials used when no per-broadcaster account is selected. The environment can supply them; the database keeps them once seeded, and an exported variable wins while it is set."
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          label="Broadcaster ID"
          htmlFor="sa-cred-bid"
          hint="The broadcaster ID from the database or the SERMONAUDIO_BROADCASTER_ID environment variable."
        >
          <input
            id="sa-cred-bid"
            value={broadcasterId}
            onChange={(e) => setBroadcasterId(e.target.value)}
            className={`${inputCls} font-mono`}
            autoComplete="off"
          />
          <SourceLine label="Broadcaster ID source" source={broadcasterSource} />
        </Field>
        <Field
          label="API key"
          htmlFor="sa-cred-key"
          hint="Write-only. Only the last 4 characters ever display. Leave blank to keep the stored key."
        >
          <input
            id="sa-cred-key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className={`${inputCls} font-mono`}
            autoComplete="new-password"
            placeholder="••••••••"
          />
          {apiField?.has_value ? (
            <p className="mt-1 text-xs text-muted">
              A key is saved{apiField.masked ? ` (${apiField.masked})` : ""}. Leave blank to keep it.
            </p>
          ) : (
            <p className="mt-1 text-xs text-muted">No key saved yet.</p>
          )}
          <SourceLine label="API key source" source={apiSource} />
        </Field>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={!dirty} onClick={onSave}>
          Save fallback credentials
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
