import { useState } from "react";
import { Button, ConfirmDialog, Field, SectionCard, Toggle, inputCls } from "./ui";

interface TemplateDraft {
  enabled: boolean;
  system: string;
  user: string;
}

const TASKS = [
  { key: "title", label: "Title Generation", vars: "{context}, {transcript}" },
  { key: "short_title", label: "Short Title Generation", vars: "{full_title}" },
  {
    key: "description",
    label: "Description Generation",
    vars: "{role_desc}, {body_desc}, {transcript}, {speaker_instruction}",
  },
  { key: "hashtags", label: "Hashtag Generation", vars: "{text}" },
  {
    key: "hashtag_verification",
    label: "Hashtag Verification",
    vars: "{initial_hashtags}, {original_text}",
  },
  {
    key: "description_validation",
    label: "Description Validation",
    vars: "{context_info}, {criteria_text}, {description}",
  },
] as const;

type TaskKey = (typeof TASKS)[number]["key"];

const SAMPLE_USER: Record<TaskKey, string> = {
  title: "Generate a sermon title from this transcript:\n{transcript}",
  short_title: "Shorten this sermon title:\n{full_title}",
  description: "Write a description for this sermon:\n{transcript}",
  hashtags: "Generate hashtags for:\n{text}",
  hashtag_verification: "Verify these hashtags:\n{initial_hashtags}\n\nSource:\n{original_text}",
  description_validation: "Validate this description:\n{description}\n\nCriteria:\n{criteria_text}",
};

function defaults(): Record<TaskKey, TemplateDraft> {
  const d = {} as Record<TaskKey, TemplateDraft>;
  for (const t of TASKS) d[t.key] = { enabled: true, system: "", user: SAMPLE_USER[t.key] };
  return d;
}

export function PromptTemplatesSection({ show }: { show: (m: string) => void }) {
  const [cur, setCur] = useState<Record<TaskKey, TemplateDraft>>(defaults);
  const [saved, setSaved] = useState<Record<TaskKey, TemplateDraft>>(defaults);
  const [everSaved, setEverSaved] = useState(false);
  const [pendingReset, setPendingReset] = useState<TaskKey | null>(null);
  const dirty = JSON.stringify(cur) !== JSON.stringify(saved);
  const setTask = (k: TaskKey, patch: Partial<TemplateDraft>) =>
    setCur((c) => ({ ...c, [k]: { ...c[k], ...patch } }));

  return (
    <SectionCard
      title="Prompt Templates"
      sub="Per-task instructions sent to the LLM (mock). Use {variable} placeholders for dynamic content."
    >
      <div className="flex flex-col gap-2">
        {TASKS.map((t) => {
          const d = cur[t.key];
          return (
            <details key={t.key} className="rounded-md border border-line p-3">
              <summary className="flex min-h-[44px] cursor-pointer flex-wrap items-center gap-2 text-sm font-semibold">
                <span className="min-w-0 flex-1">{t.label}</span>
                <span
                  className={`rounded-full border px-2.5 py-0.5 font-mono text-xs uppercase tracking-wide ${
                    d.enabled ? "border-ok text-ok" : "border-line text-muted"
                  }`}
                >
                  {d.enabled ? "enabled" : "disabled"}
                </span>
              </summary>
              <div className="mt-3 flex flex-col gap-3">
                <Toggle
                  checked={d.enabled}
                  onChange={(v) => setTask(t.key, { enabled: v })}
                  label={`Enable ${t.label}`}
                />
                <Field label="System prompt" htmlFor={`pt-${t.key}-sys`}>
                  <textarea
                    id={`pt-${t.key}-sys`}
                    value={d.system}
                    onChange={(e) => setTask(t.key, { system: e.target.value })}
                    className={`${inputCls} min-h-[60px] py-2`}
                    rows={2}
                    placeholder="System-level instruction. Empty means omit."
                  />
                </Field>
                <Field label="User prompt" htmlFor={`pt-${t.key}-user`}>
                  <textarea
                    id={`pt-${t.key}-user`}
                    value={d.user}
                    onChange={(e) => setTask(t.key, { user: e.target.value })}
                    className={`${inputCls} min-h-[120px] py-2 font-mono`}
                    rows={5}
                  />
                </Field>
                <p className="text-xs text-muted">Available variables: {t.vars}</p>
                <div>
                  <Button
                    variant="danger"
                    onClick={() => setPendingReset(t.key)}
                    aria-label={`Reset ${t.label} to sample`}
                  >
                    Reset task
                  </Button>
                </div>
              </div>
            </details>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={!dirty}
          onClick={() => {
            setSaved(cur);
            setEverSaved(true);
            show("Prompt templates saved (mock).");
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

      <ConfirmDialog
        open={pendingReset !== null}
        title="Reset task template?"
        body={
          pendingReset
            ? `Restore the sample prompts for "${TASKS.find((t) => t.key === pendingReset)?.label}"? Your edits to this task will be lost.`
            : ""
        }
        confirmLabel="Reset"
        onConfirm={() => {
          if (pendingReset) {
            const fresh = defaults()[pendingReset];
            setTask(pendingReset, fresh);
            show(`Template reset (mock): ${pendingReset}.`);
          }
          setPendingReset(null);
        }}
        onClose={() => setPendingReset(null)}
      />
    </SectionCard>
  );
}
