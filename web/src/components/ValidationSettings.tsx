import { useId, useState } from "react";
import { isLive } from "../api/client";
import { useUserSettings } from "../api/useUserSettings";
import { Button, Field, SectionCard, Toggle, inputCls } from "./ui";

interface ValidationState {
  enabled: boolean;
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
  criteria: ["Contains a scripture reference", "Mentions the main sermon topic"],
  descMissing: true,
  descMinimal: true,
  descMinLength: "50",
  hashMissing: true,
  hashMinimal: true,
  hashMinLength: "10",
};

function intError(v: string, min: number, max: number): string | null {
  if (!/^\d+$/.test(v.trim())) return "Must be a whole number.";
  const n = Number(v);
  if (n < min || n > max) return `Must be between ${min} and ${max}.`;
  return null;
}

export function ValidationSettingsSection({ show }: { show: (m: string) => void }) {
  const [saved, setSaved] = useUserSettings<ValidationState>("settings.validation", DEFAULTS);
  const [cur, setCur] = useState<ValidationState>(saved);
  const [newCriterion, setNewCriterion] = useState("");
  const uid = useId();
  const dirty = isLive && JSON.stringify(cur) !== JSON.stringify(saved);

  const descErr = intError(cur.descMinLength, 10, 200);
  const hashErr = intError(cur.hashMinLength, 5, 50);
  const valid = !descErr && !hashErr;

  const removeCriterion = (i: number) => {
    const removed = cur.criteria[i];
    setCur((c) => ({ ...c, criteria: c.criteria.filter((_, j) => j !== i) }));
    show(`Criterion removed (mock): ${removed}. Save to keep it.`);
  };

  const addCriterion = () => {
    const v = newCriterion.trim();
    if (!v) return;
    setCur((c) => ({ ...c, criteria: [...c.criteria, v] }));
    setNewCriterion("");
  };

  return (
    <SectionCard
      title="Validation"
      sub="Description validation criteria and metadata processing thresholds (mock). Mirrors the legacy Validation tab."
    >
      <Toggle
        checked={cur.enabled}
        onChange={(v) => setCur((c) => ({ ...c, enabled: v }))}
        label="Enable Description Validation"
        hint="Use AI to validate description quality."
      />

      {cur.enabled ? (
        <div className="mt-3">
          <h3 className="text-sm font-semibold">Validation criteria</h3>
          {cur.criteria.length === 0 ? (
            <p className="mt-1 text-xs text-muted">No criteria yet. Add one below.</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-2" aria-label="Validation criteria">
              {cur.criteria.map((c, i) => (
                <li
                  key={`${i}-${c}`}
                  className="flex flex-wrap items-center gap-2 rounded-md border border-line p-2"
                >
                  <input
                    value={c}
                    onChange={(e) =>
                      setCur((s) => ({
                        ...s,
                        criteria: s.criteria.map((x, j) => (j === i ? e.target.value : x)),
                      }))
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

      <h3 className="mt-4 text-sm font-semibold">Processing settings</h3>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="min-w-0 rounded-md border border-line p-3">
          <h4 className="text-sm font-semibold">Description settings</h4>
          <div className="mt-2 flex flex-col gap-2">
            <Toggle
              checked={cur.descMissing}
              onChange={(v) => setCur((c) => ({ ...c, descMissing: v }))}
              label="Update if Missing"
            />
            <Toggle
              checked={cur.descMinimal}
              onChange={(v) => setCur((c) => ({ ...c, descMinimal: v }))}
              label="Update if Minimal"
            />
            <Field label="Min length threshold" htmlFor={`${uid}-desc-min`} hint="10 to 200.">
              <input
                id={`${uid}-desc-min`}
                value={cur.descMinLength}
                onChange={(e) => setCur((c) => ({ ...c, descMinLength: e.target.value }))}
                className={`${inputCls} font-mono`}
                inputMode="numeric"
                autoComplete="off"
              />
              {descErr ? (
                <p className="mt-1 text-xs text-danger" role="alert">
                  {descErr}
                </p>
              ) : null}
            </Field>
          </div>
        </div>
        <div className="min-w-0 rounded-md border border-line p-3">
          <h4 className="text-sm font-semibold">Hashtag settings</h4>
          <div className="mt-2 flex flex-col gap-2">
            <Toggle
              checked={cur.hashMissing}
              onChange={(v) => setCur((c) => ({ ...c, hashMissing: v }))}
              label="Update if Missing"
            />
            <Toggle
              checked={cur.hashMinimal}
              onChange={(v) => setCur((c) => ({ ...c, hashMinimal: v }))}
              label="Update if Minimal"
            />
            <Field label="Min length threshold" htmlFor={`${uid}-hash-min`} hint="5 to 50.">
              <input
                id={`${uid}-hash-min`}
                value={cur.hashMinLength}
                onChange={(e) => setCur((c) => ({ ...c, hashMinLength: e.target.value }))}
                className={`${inputCls} font-mono`}
                inputMode="numeric"
                autoComplete="off"
              />
              {hashErr ? (
                <p className="mt-1 text-xs text-danger" role="alert">
                  {hashErr}
                </p>
              ) : null}
            </Field>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={!dirty || !valid}
          onClick={() => {
            setSaved(cur);
            setCur(cur);
            show(isLive ? "Validation settings saved." : "Validation settings saved (mock).");
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
