import { useId, useMemo, useState } from "react";
import { isLive } from "../api/client";
import { fieldSource, useConfigForm } from "../api/useConfigSection";
import { Advanced, Button, Field, Fieldset, SaveBar, SectionCard, Toggle, inputCls } from "./ui";

interface ValidationState {
  enabled: boolean;
  metadataEnabled: boolean;
  criteria: string[];
  descMissing: boolean;
  descMinimal: boolean;
  descMinLength: string;
  hashMissing: boolean;
  hashMinimal: boolean;
  hashMinLength: string;
}

const DEFAULTS: ValidationState = {
  enabled: true,
  metadataEnabled: true,
  criteria: ["Contains a scripture reference", "Mentions the main sermon topic"],
  descMissing: true,
  descMinimal: true,
  descMinLength: "50",
  hashMissing: true,
  hashMinimal: true,
  hashMinLength: "10",
};

const PATHS = {
  enabled: "metadata_processing.description.validation.enabled",
  metadataEnabled: "metadata_processing.enabled",
  criteria: "metadata_processing.description.validation.criteria",
  descMissing: "metadata_processing.description.update_if_missing",
  descMinimal: "metadata_processing.description.update_if_minimal",
  descMinLength: "metadata_processing.description.min_length_threshold",
  hashMissing: "metadata_processing.hashtags.update_if_missing",
  hashMinimal: "metadata_processing.hashtags.update_if_minimal",
  hashMinLength: "metadata_processing.hashtags.min_length_threshold",
} as const;

function intError(v: string, min: number, max: number): string | null {
  if (!/^\d+$/.test(v.trim())) return "Enter a whole number.";
  const n = Number(v);
  if (n < min || n > max) return `Enter a value between ${min} and ${max}.`;
  return null;
}

export function ValidationSettingsSection({ show }: { show: (m: string) => void }) {
  const normalize = useMemo(
    () => (values: ValidationState): ValidationState => ({
      ...values,
      criteria: Array.isArray(values.criteria) ? values.criteria.map(String) : DEFAULTS.criteria,
      descMinLength: String(values.descMinLength),
      hashMinLength: String(values.hashMinLength),
    }),
    [],
  );
  const { cur, fields, dirty, set, save } = useConfigForm<ValidationState>(
    "validation",
    DEFAULTS,
    PATHS,
    normalize,
  );
  const [newCriterion, setNewCriterion] = useState("");
  const [saving, setSaving] = useState(false);
  const uid = useId();

  const descErr = intError(cur.descMinLength, 10, 200);
  const hashErr = intError(cur.hashMinLength, 5, 50);
  const valid = !descErr && !hashErr;

  const removeCriterion = (i: number) => {
    const removed = cur.criteria[i];
    set(
      "criteria",
      cur.criteria.filter((_, j) => j !== i),
    );
    show(`Criterion removed: ${removed}. Save to keep it.`);
  };

  const addCriterion = () => {
    const v = newCriterion.trim();
    if (!v) return;
    set("criteria", [...cur.criteria, v]);
    setNewCriterion("");
  };

  const onSave = () => {
    if (saving) return;
    setSaving(true);
    void save((c) => ({
      [PATHS.enabled]: c.enabled,
      [PATHS.metadataEnabled]: c.metadataEnabled,
      [PATHS.criteria]: c.criteria,
      [PATHS.descMissing]: c.descMissing,
      [PATHS.descMinimal]: c.descMinimal,
      [PATHS.descMinLength]: Number(c.descMinLength),
      [PATHS.hashMissing]: c.hashMissing,
      [PATHS.hashMinimal]: c.hashMinimal,
      [PATHS.hashMinLength]: Number(c.hashMinLength),
    }))
      .then(() => show(isLive ? "Validation settings saved." : "Validation settings saved (demo)."))
      .catch((e) => show(`Could not save: ${(e as Error).message}`))
      .finally(() => setSaving(false));
  };

  return (
    <SectionCard
      title="Validation"
      sub={
        isLive
          ? "Description validation criteria and metadata processing thresholds."
          : "Description validation criteria and metadata processing thresholds (demo)."
      }
    >
      <div className="flex flex-col gap-3">
        <Fieldset
          legend="Metadata generation"
          help="Turn the title, description, and hashtag pass off for runs that should publish only what the operator entered."
        >
          <Toggle
            checked={cur.metadataEnabled}
            onChange={(v) => set("metadataEnabled", v)}
            label="Generate metadata"
            hint="When off, the pipeline keeps the metadata already on the record."
            source={fieldSource(fields, PATHS.metadataEnabled)}
          />
        </Fieldset>
        <Fieldset
          legend="Description validation"
          help="A second LLM pass checks each draft against these criteria before publishing."
        >
          <Toggle
            checked={cur.enabled}
            onChange={(v) => set("enabled", v)}
            label="Enable description validation"
            hint="Use AI to validate description quality."
          />

          {cur.enabled ? (
            <div>
              {cur.criteria.length === 0 ? (
                <p className="text-xs text-muted">No criteria yet. Add one below.</p>
              ) : (
                <ul className="flex flex-col gap-2" aria-label="Validation criteria">
                  {cur.criteria.map((c, i) => (
                    <li
                      key={i}
                      className="flex flex-wrap items-center gap-2 rounded-md border border-line p-2"
                    >
                      <input
                        value={c}
                        onChange={(e) =>
                          set(
                            "criteria",
                            cur.criteria.map((x, j) => (j === i ? e.target.value : x)),
                          )
                        }
                        aria-label={`Criterion ${i + 1}`}
                        className={`${inputCls} min-w-0 flex-1`}
                        autoComplete="off"
                      />
                      <Button
                        variant="danger"
                        onClick={() => removeCriterion(i)}
                        aria-label={`Remove criterion ${i + 1}`}
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-2 flex flex-wrap items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Field label="Add new criterion" htmlFor={`${uid}-new-crit`}>
                    <input
                      id={`${uid}-new-crit`}
                      value={newCriterion}
                      onChange={(e) => setNewCriterion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addCriterion();
                        }
                      }}
                      className={inputCls}
                      autoComplete="off"
                      placeholder="e.g. Contains a scripture reference"
                    />
                  </Field>
                </div>
                <Button onClick={addCriterion} disabled={!newCriterion.trim()} aria-label="Add criterion">
                  Add
                </Button>
              </div>
            </div>
          ) : null}
        </Fieldset>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Fieldset legend="Description refresh" help="When the pipeline replaces an existing description.">
            <Toggle
              checked={cur.descMissing}
              onChange={(v) => set("descMissing", v)}
              label="Update if missing"
            />
            <Toggle
              checked={cur.descMinimal}
              onChange={(v) => set("descMinimal", v)}
              label="Update if minimal"
            />
            <Advanced label="Minimum length" open={Boolean(descErr)}>
              <Field label="Min length threshold" htmlFor={`${uid}-desc-min`} hint="10 to 200 characters.">
                <input
                  id={`${uid}-desc-min`}
                  type="number"
                  min={10}
                  max={200}
                  step={1}
                  value={cur.descMinLength}
                  onChange={(e) => set("descMinLength", e.target.value)}
                  className={`${inputCls} font-mono`}
                  autoComplete="off"
                />
                {descErr ? (
                  <p className="mt-1 text-xs text-danger" role="alert">
                    {descErr}
                  </p>
                ) : null}
              </Field>
            </Advanced>
          </Fieldset>
          <Fieldset legend="Hashtag refresh" help="When the pipeline replaces existing hashtags.">
            <Toggle
              checked={cur.hashMissing}
              onChange={(v) => set("hashMissing", v)}
              label="Update if missing"
            />
            <Toggle
              checked={cur.hashMinimal}
              onChange={(v) => set("hashMinimal", v)}
              label="Update if minimal"
            />
            <Advanced label="Minimum length" open={Boolean(hashErr)}>
              <Field label="Min length threshold" htmlFor={`${uid}-hash-min`} hint="5 to 50 characters.">
                <input
                  id={`${uid}-hash-min`}
                  type="number"
                  min={5}
                  max={50}
                  step={1}
                  value={cur.hashMinLength}
                  onChange={(e) => set("hashMinLength", e.target.value)}
                  className={`${inputCls} font-mono`}
                  autoComplete="off"
                />
                {hashErr ? (
                  <p className="mt-1 text-xs text-danger" role="alert">
                    {hashErr}
                  </p>
                ) : null}
              </Field>
            </Advanced>
          </Fieldset>
        </div>
      </div>

      <SaveBar dirty={dirty && valid} saved={!dirty} busy={saving} onSave={onSave} />
    </SectionCard>
  );
}
