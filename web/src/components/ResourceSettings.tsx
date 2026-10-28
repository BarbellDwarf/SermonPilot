import { useMemo, useState } from "react";
import { isLive } from "../api/client";
import { fieldSource, useConfigForm } from "../api/useConfigSection";
import { EnvSourceBadge, Field, Fieldset, SaveBar, SectionCard, inputCls } from "./ui";

interface ResourceState {
  minFreeRamGb: string;
  minFreeVramGb: string;
  minGpuVramGb: string;
}

const DEFAULTS: ResourceState = {
  minFreeRamGb: "3",
  minFreeVramGb: "1.5",
  minGpuVramGb: "12",
};

const PATHS = {
  minFreeRamGb: "job_queue.min_free_ram_gb",
  minFreeVramGb: "job_queue.min_free_vram_gb",
  minGpuVramGb: "enhancement.min_gpu_vram_gb",
} as const;

function numberError(v: string, min: number): string | null {
  if (!/^\d+(\.\d+)?$/.test(v.trim())) return "Must be a number.";
  if (Number(v) < min) return `Must be at least ${min}.`;
  return null;
}

export function ResourceSettingsSection({
  show,
  isAdmin,
}: {
  show: (m: string) => void;
  isAdmin: boolean;
}) {
  const normalize = useMemo(
    () => (values: ResourceState): ResourceState => ({
      minFreeRamGb: String(values.minFreeRamGb),
      minFreeVramGb: String(values.minFreeVramGb),
      minGpuVramGb: String(values.minGpuVramGb),
    }),
    [],
  );
  const { cur, fields, dirty, set, save } = useConfigForm<ResourceState>(
    "resources",
    DEFAULTS,
    PATHS,
    normalize,
  );
  const [saving, setSaving] = useState(false);

  const ramErr = numberError(cur.minFreeRamGb, 0);
  const vramErr = numberError(cur.minFreeVramGb, 0);
  const gpuErr = numberError(cur.minGpuVramGb, 0);
  const valid = !ramErr && !vramErr && !gpuErr;

  return (
    <SectionCard
      title="Resources"
      sub="Queue and GPU thresholds the worker checks before it starts a job."
    >
      <Fieldset
        legend="Job queue"
        help="A queued job waits while the host has less free memory than these floors."
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Minimum free RAM (GB)" htmlFor="res-ram">
            <input
              id="res-ram"
              value={cur.minFreeRamGb}
              disabled={!isAdmin}
              onChange={(e) => set("minFreeRamGb", e.target.value)}
              inputMode="decimal"
              className={`${inputCls} font-mono`}
              autoComplete="off"
            />
            <div className="mt-1">
              <EnvSourceBadge source={fieldSource(fields, PATHS.minFreeRamGb)} />
            </div>
            {ramErr ? <p className="mt-1 text-xs text-danger" role="alert">{ramErr}</p> : null}
          </Field>
          <Field label="Minimum free VRAM (GB)" htmlFor="res-vram">
            <input
              id="res-vram"
              value={cur.minFreeVramGb}
              disabled={!isAdmin}
              onChange={(e) => set("minFreeVramGb", e.target.value)}
              inputMode="decimal"
              className={`${inputCls} font-mono`}
              autoComplete="off"
            />
            <div className="mt-1">
              <EnvSourceBadge source={fieldSource(fields, PATHS.minFreeVramGb)} />
            </div>
            {vramErr ? <p className="mt-1 text-xs text-danger" role="alert">{vramErr}</p> : null}
          </Field>
        </div>
      </Fieldset>

      <Fieldset
        legend="Enhancement placement"
        help="With enhancement device set to Auto, a GPU below this total VRAM runs enhancement on the CPU so whisper keeps the card."
      >
        <Field label="GPU VRAM floor (GB)" htmlFor="res-gpu">
          <input
            id="res-gpu"
            value={cur.minGpuVramGb}
            disabled={!isAdmin}
            onChange={(e) => set("minGpuVramGb", e.target.value)}
            inputMode="decimal"
            className={`${inputCls} font-mono`}
            autoComplete="off"
          />
          <div className="mt-1">
            <EnvSourceBadge source={fieldSource(fields, PATHS.minGpuVramGb)} />
          </div>
          {gpuErr ? <p className="mt-1 text-xs text-danger" role="alert">{gpuErr}</p> : null}
        </Field>
      </Fieldset>

      {!isAdmin ? (
        <p className="text-xs text-muted" role="status">
          Read-only for your role. Ask an admin to change a resource floor.
        </p>
      ) : null}

      <SaveBar
        dirty={isAdmin && dirty && valid}
        saved={!isAdmin || !dirty}
        busy={saving}
        onSave={() => {
          if (!isAdmin || saving) return;
          setSaving(true);
          void save((c) => ({
            [PATHS.minFreeRamGb]: Number(c.minFreeRamGb),
            [PATHS.minFreeVramGb]: Number(c.minFreeVramGb),
            [PATHS.minGpuVramGb]: Number(c.minGpuVramGb),
          }))
            .then(() => show(isLive ? "Resource settings saved." : "Resource settings saved (mock)."))
            .catch((e) => show(`Could not save: ${(e as Error).message}`))
            .finally(() => setSaving(false));
        }}
      />
    </SectionCard>
  );
}
