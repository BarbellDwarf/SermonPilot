import { useEffect, useState } from "react";
import {
  isLive,
  promptsApi,
  type ApiPromptsConfig,
  type ApiPromptsUpdate,
} from "../api/client";
import { Advanced, Button, ConfirmDialog, Field, SaveBar, SectionCard, Toggle, inputCls } from "./ui";

interface TemplateDraft {
  enabled: boolean;
  system: string;
  user: string;
}

const TASKS = [
  { key: "title", label: "Title generation", vars: "{context}, {transcript}" },
  { key: "short_title", label: "Short title generation", vars: "{full_title}" },
  {
    key: "description",
    label: "Description generation",
    vars: "{role_desc}, {body_desc}, {transcript}, {speaker_instruction}",
  },
  { key: "hashtags", label: "Hashtag generation", vars: "{text}" },
  {
    key: "hashtag_verification",
    label: "Hashtag verification",
    vars: "{initial_hashtags}, {original_text}",
  },
  {
    key: "description_validation",
    label: "Description validation",
    vars: "{context_info}, {criteria_text}, {description}",
  },
  {
    key: "cut_detection",
    label: "Cut detection",
    vars: "{transcript}, {elision_note}, {refinement}, {qa_margin_seconds}",
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
  cut_detection:
    "Identify the start of the teaching and the transition into Q&A.\n{transcript}\n{refinement}",
};

function defaults(): Record<TaskKey, TemplateDraft> {
  const d = {} as Record<TaskKey, TemplateDraft>;
  for (const t of TASKS) d[t.key] = { enabled: true, system: "", user: SAMPLE_USER[t.key] };
  return d;
}

function applyPromptsConfig(cfg: ApiPromptsConfig): {
  tasks: Record<TaskKey, TemplateDraft>;
  builtin: Record<TaskKey, TemplateDraft>;
} {
  const samples = defaults();
  const tasks = {} as Record<TaskKey, TemplateDraft>;
  const builtin = {} as Record<TaskKey, TemplateDraft>;
  for (const t of TASKS) {
    const b = cfg.defaults?.[t.key];
    builtin[t.key] = b
      ? { enabled: b.enabled, system: b.system, user: b.user }
      : samples[t.key];
    const eff = cfg.templates?.[t.key];
    tasks[t.key] = eff
      ? { enabled: eff.enabled, system: eff.system, user: eff.user }
      : builtin[t.key];
  }
  return { tasks, builtin };
}

function toUpdate(tasks: Record<TaskKey, TemplateDraft>): ApiPromptsUpdate {
  const templates: ApiPromptsUpdate["templates"] = {};
  for (const t of TASKS) {
    templates[t.key] = {
      enabled: tasks[t.key].enabled,
      system: tasks[t.key].system,
      user: tasks[t.key].user,
    };
  }
  return { templates };
}

export function PromptTemplatesSection({ show }: { show: (m: string) => void }) {
  const [saved, setSaved] = useState<Record<TaskKey, TemplateDraft>>(defaults());
  const [cur, setCur] = useState<Record<TaskKey, TemplateDraft>>(defaults());
  const [builtin, setBuiltin] = useState<Record<TaskKey, TemplateDraft>>(defaults());
  const [loaded, setLoaded] = useState(!isLive);
  const [busy, setBusy] = useState(false);
  const [pendingReset, setPendingReset] = useState<TaskKey | null>(null);
  const [activeTask, setActiveTask] = useState<TaskKey>("title");
  const dirty = JSON.stringify(cur) !== JSON.stringify(saved);
  const activeDef = TASKS.find((t) => t.key === activeTask) ?? TASKS[0];
  const activeDraft = cur[activeTask];

  useEffect(() => {
    if (!isLive || loaded) return;
    let alive = true;
    promptsApi
      .get()
      .then((cfg) => {
        if (!alive) return;
        const next = applyPromptsConfig(cfg);
        setCur(next.tasks);
        setSaved(next.tasks);
        setBuiltin(next.builtin);
      })
      .catch(() => undefined)
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [loaded]);

  const setTask = (k: TaskKey, patch: Partial<TemplateDraft>) =>
    setCur((c) => ({ ...c, [k]: { ...c[k], ...patch } }));

  const save = () => {
    setSaved(cur);
    if (!isLive) {
      show("Prompt templates saved (demo).");
      return;
    }
    setBusy(true);
    void promptsApi
      .put(toUpdate(cur))
      .then((cfg) => {
        const next = applyPromptsConfig(cfg);
        setCur(next.tasks);
        setSaved(next.tasks);
        setBuiltin(next.builtin);
        setBusy(false);
        show("Prompt templates saved.");
      })
      .catch(() => {
        setBusy(false);
        show("Could not save prompt templates.");
      });
  };

  return (
    <SectionCard
      title="Prompt templates"
      sub={
        isLive
          ? "Per-task instructions sent to the LLM. Saved to the settings database; what is saved here is what the pipeline resolves on the next run. Use {variable} placeholders for dynamic content."
          : "Per-task instructions sent to the LLM (demo). Use {variable} placeholders for dynamic content."
      }
    >
      <ul className="flex flex-col gap-2" aria-label="Prompt tasks">
        {TASKS.map((t) => {
          const d = cur[t.key];
          const selected = activeTask === t.key;
          return (
            <li key={t.key}>
              <button
                type="button"
                onClick={() => setActiveTask(t.key)}
                aria-expanded={selected}
                aria-controls="prompt-editor"
                className={`flex min-h-[44px] w-full flex-wrap items-center gap-2 rounded-md border p-3 text-left transition-colors ${
                  selected ? "border-accent bg-raised" : "border-line hover:border-muted"
                }`}
              >
                <span className="min-w-0 flex-1 text-sm font-semibold">{t.label}</span>
                <span
                  className={`rounded-sm border px-2 py-0.5 font-mono text-xs uppercase leading-4 tracking-wide ${
                    d.enabled ? "border-ok text-ok" : "border-line text-muted"
                  }`}
                >
                  {d.enabled ? "enabled" : "disabled"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <div
        id="prompt-editor"
        role="region"
        aria-label={`${activeDef.label} template`}
        className="mt-3 flex flex-col gap-3 rounded-md border border-line bg-ink p-3"
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 flex-1 text-sm font-semibold">{activeDef.label}</p>
          <span className="font-mono text-xs text-muted">{activeTask}</span>
        </div>
        <Toggle
          checked={activeDraft.enabled}
          onChange={(v) => setTask(activeTask, { enabled: v })}
          label={`Enable ${activeDef.label}`}
        />
        <Field label="User prompt" htmlFor={`pt-${activeTask}-user`}>
          <textarea
            id={`pt-${activeTask}-user`}
            value={activeDraft.user}
            onChange={(e) => setTask(activeTask, { user: e.target.value })}
            className={`${inputCls} min-h-[120px] py-2 font-mono`}
            rows={5}
          />
        </Field>
        <p className="text-xs text-muted">Available variables: {activeDef.vars}</p>
        <Advanced label="Advanced: system prompt">
          <Field label="System prompt" htmlFor={`pt-${activeTask}-sys`}>
            <textarea
              id={`pt-${activeTask}-sys`}
              value={activeDraft.system}
              onChange={(e) => setTask(activeTask, { system: e.target.value })}
              className={`${inputCls} min-h-[60px] py-2`}
              rows={2}
              placeholder="System-level instruction. Empty means omit."
            />
          </Field>
        </Advanced>
        <div>
          <Button
            variant="danger"
            onClick={() => setPendingReset(activeTask)}
            aria-label={`Reset ${activeDef.label} to default`}
          >
            Reset task
          </Button>
        </div>
      </div>

      <SaveBar dirty={dirty} saved={!dirty} busy={busy} onSave={save} />

      <ConfirmDialog
        open={pendingReset !== null}
        title="Reset task template?"
        body={
          pendingReset
            ? `Restore the default prompts for "${TASKS.find((t) => t.key === pendingReset)?.label}"? Your edits to this task will be lost.`
            : ""
        }
        confirmLabel="Reset"
        onConfirm={() => {
          if (pendingReset) {
            setTask(pendingReset, builtin[pendingReset]);
            show(`Template reset to default: ${pendingReset}.`);
          }
          setPendingReset(null);
        }}
        onClose={() => setPendingReset(null)}
      />
    </SectionCard>
  );
}
