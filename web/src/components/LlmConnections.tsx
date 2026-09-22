import { useEffect, useId, useState } from "react";
import {
  llmConfigApi,
  type ApiLlmConfig,
  type ApiLlmConfigUpdate,
  type ApiLlmRouting,
  type ApiLlmSlot,
  type ApiLlmSlotUpdate,
  type ApiLlmTestResult,
  type LlmRole,
  type LlmRouteRole,
} from "../api/client";
import { Button, Chip, Field, SectionCard, Toggle, inputCls } from "./ui";

const SLOT_ORDER: LlmRole[] = ["primary", "fallback", "validator"];

const SLOT_LABEL: Record<LlmRole, string> = {
  primary: "Primary",
  fallback: "Fallback",
  validator: "Validator",
};

const SLOT_HINT: Record<LlmRole, string> = {
  primary: "Generates metadata and runs by default.",
  fallback: "Catches failures when the primary cannot answer.",
  validator: "Reviews drafts before they reach SermonAudio.",
};

const SLOT_TONE: Record<LlmRole, string> = {
  primary: "accent",
  fallback: "info",
  validator: "ok",
};

const PROVIDERS = [
  { id: "ollama", label: "Ollama (local or cloud)" },
  { id: "openai", label: "OpenAI-compatible" },
  { id: "xai", label: "xAI Grok" },
  { id: "groq", label: "Groq" },
  { id: "openrouter", label: "OpenRouter" },
] as const;

const DEFAULT_ENDPOINTS: Record<string, string> = {
  ollama: "http://localhost:11434",
  openai: "https://api.openai.com/v1",
  xai: "https://api.x.ai/v1",
  groq: "https://api.groq.com/openai/v1",
  openrouter: "https://openrouter.ai/api/v1",
};

const ROUTE_ORDER: LlmRouteRole[] = [
  "metadata",
  "validation",
  "transcription_assist",
  "fallback",
];

const ROUTE_LABEL: Record<LlmRouteRole, string> = {
  metadata: "Metadata generation",
  validation: "Validation",
  transcription_assist: "Transcription assist",
  fallback: "Fallback",
};

interface SlotDraft {
  enabled: boolean;
  provider: string;
  model: string;
  endpoint: string;
  numCtx: string;
  maxTokens: string;
  temperature: string;
  apiKey: string;
}

function draftFromSlot(slot: ApiLlmSlot): SlotDraft {
  return {
    enabled: slot.role === "primary" ? true : slot.enabled,
    provider: slot.provider || "ollama",
    model: slot.model,
    endpoint: slot.endpoint,
    numCtx: slot.numCtx,
    maxTokens: slot.maxTokens,
    temperature: slot.temperature,
    apiKey: "",
  };
}

function endpointLabel(provider: string): string {
  return provider === "ollama" ? "Host" : "Base URL";
}

function endpointHint(provider: string): string {
  if (provider === "ollama") return "Host of the Ollama server, without a trailing /api.";
  if (provider === "openrouter") return "Base URL ending in /api/v1.";
  return "Base URL ending in /v1.";
}

function testSummary(role: LlmRole, result: ApiLlmTestResult): string {
  const label = SLOT_LABEL[role];
  if (result.ok) {
    const model = result.model_echo ? `, model ${result.model_echo}` : "";
    return `${label} connected in ${result.latency_ms} ms${model}.`;
  }
  const detail = result.error ?? "no error detail returned.";
  return `${label} failed: ${detail}`;
}

function SlotCard({
  role,
  slot,
  draft,
  uid,
  saving,
  testing,
  result,
  keyHidden,
  onChange,
  onSave,
  onTest,
  onToggleKey,
}: {
  role: LlmRole;
  slot: ApiLlmSlot;
  draft: SlotDraft;
  uid: string;
  saving: boolean;
  testing: boolean;
  result: ApiLlmTestResult | null;
  keyHidden: boolean;
  onChange: (patch: Partial<SlotDraft>) => void;
  onSave: () => void;
  onTest: () => void;
  onToggleKey: () => void;
}) {
  const label = SLOT_LABEL[role];
  const masked = slot.hasKey ? (keyHidden ? "••••••••" : slot.maskedKey) : "no key set";
  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold">{label}</p>
        <Chip tone={SLOT_TONE[role]}>{role}</Chip>
        <span className="min-w-0 flex-1 text-xs text-muted">{SLOT_HINT[role]}</span>
      </div>

      {role !== "primary" ? (
        <div className="mt-3">
          <Toggle
            checked={draft.enabled}
            onChange={(v) => onChange({ enabled: v })}
            label={`${label} enabled`}
            hint={draft.enabled ? "Included in routing." : "Stored but skipped by routing."}
          />
        </div>
      ) : null}

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Provider" htmlFor={`${uid}-${role}-provider`}>
          <select
            id={`${uid}-${role}-provider`}
            value={draft.provider}
            onChange={(e) => {
              const id = e.target.value;
              const knownDefaults = Object.values(DEFAULT_ENDPOINTS);
              const current = draft.endpoint.trim();
              const replaceEndpoint = !current || knownDefaults.includes(current);
              onChange({
                provider: id,
                endpoint: replaceEndpoint ? DEFAULT_ENDPOINTS[id] ?? "" : draft.endpoint,
              });
            }}
            className={inputCls}
          >
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label={endpointLabel(draft.provider)}
          htmlFor={`${uid}-${role}-endpoint`}
          hint={endpointHint(draft.provider)}
        >
          <input
            id={`${uid}-${role}-endpoint`}
            value={draft.endpoint}
            onChange={(e) => onChange({ endpoint: e.target.value })}
            className={`${inputCls} font-mono`}
            autoComplete="off"
            inputMode="url"
            placeholder="https://..."
          />
        </Field>

        <Field label="Model id" htmlFor={`${uid}-${role}-model`}>
          <input
            id={`${uid}-${role}-model`}
            value={draft.model}
            onChange={(e) => onChange({ model: e.target.value })}
            className={`${inputCls} font-mono`}
            autoComplete="off"
            placeholder="model-id"
          />
        </Field>

        <Field
          label="API key"
          htmlFor={`${uid}-${role}-key`}
          hint="Stored on the server. Only the last four characters ever display. Leave blank to keep the stored key."
        >
          <input
            id={`${uid}-${role}-key`}
            type="password"
            value={draft.apiKey}
            onChange={(e) => onChange({ apiKey: e.target.value })}
            className={`${inputCls} font-mono`}
            autoComplete="new-password"
            placeholder={slot.hasKey ? "stored key unchanged" : "not set"}
          />
          <div className="mt-1 flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted" aria-label={`${label} stored key`}>
              {masked}
            </span>
            {slot.hasKey ? (
              <button
                type="button"
                onClick={onToggleKey}
                aria-pressed={keyHidden}
                aria-label={`${keyHidden ? "Show" : "Hide"} stored ${label} key`}
                className="min-h-[32px] shrink-0 rounded px-2 text-xs font-semibold text-muted hover:bg-raised hover:text-mist"
              >
                {keyHidden ? "Show" : "Hide"}
              </button>
            ) : null}
          </div>
        </Field>

        <Field label="Context window (num_ctx)" htmlFor={`${uid}-${role}-ctx`} hint="Blank uses the provider default.">
          <input
            id={`${uid}-${role}-ctx`}
            value={draft.numCtx}
            onChange={(e) => onChange({ numCtx: e.target.value })}
            className={`${inputCls} font-mono`}
            inputMode="numeric"
            autoComplete="off"
            placeholder="e.g. 32768"
          />
        </Field>

        <Field label="Max tokens" htmlFor={`${uid}-${role}-max`} hint="Blank uses the provider default.">
          <input
            id={`${uid}-${role}-max`}
            value={draft.maxTokens}
            onChange={(e) => onChange({ maxTokens: e.target.value })}
            className={`${inputCls} font-mono`}
            inputMode="numeric"
            autoComplete="off"
            placeholder="e.g. 16000"
          />
        </Field>

        <Field label="Temperature" htmlFor={`${uid}-${role}-temp`} hint="0 to 2. Blank uses the provider default.">
          <input
            id={`${uid}-${role}-temp`}
            value={draft.temperature}
            onChange={(e) => onChange({ temperature: e.target.value })}
            className={`${inputCls} font-mono`}
            inputMode="decimal"
            autoComplete="off"
            placeholder="e.g. 0.7"
          />
        </Field>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={onSave} disabled={saving} aria-label={`Save ${label} provider`}>
          {saving ? "Saving..." : "Save"}
        </Button>
        <Button onClick={onTest} disabled={testing} aria-label={`Test ${label} connection`}>
          {testing ? "Testing..." : "Test connection"}
        </Button>
        {result ? (
          result.ok ? (
            <p role="status" className="text-xs text-ok">
              {testSummary(role, result)}
            </p>
          ) : (
            <p role="alert" className="text-xs text-danger">
              {testSummary(role, result)}
            </p>
          )
        ) : null}
      </div>
    </li>
  );
}

export function LlmConnectionsSection({ show }: { show: (m: string) => void }) {
  const [config, setConfig] = useState<ApiLlmConfig | null>(null);
  const [drafts, setDrafts] = useState<Record<LlmRole, SlotDraft> | null>(null);
  const [routing, setRouting] = useState<ApiLlmRouting | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [savingRole, setSavingRole] = useState<LlmRole | null>(null);
  const [savingRouting, setSavingRouting] = useState(false);
  const [testingRole, setTestingRole] = useState<LlmRole | null>(null);
  const [results, setResults] = useState<Partial<Record<LlmRole, ApiLlmTestResult>>>({});
  const [keyHidden, setKeyHidden] = useState<Partial<Record<LlmRole, boolean>>>({});
  const uid = useId();

  const applyConfig = (next: ApiLlmConfig) => {
    setConfig(next);
    setDrafts({
      primary: draftFromSlot(next.primary),
      fallback: draftFromSlot(next.fallback),
      validator: draftFromSlot(next.validator),
    });
    setRouting(next.routing);
  };

  const load = () => {
    setLoading(true);
    setLoadError(null);
    llmConfigApi
      .get()
      .then((next) => applyConfig(next))
      .catch((e) => setLoadError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    let cancelled = false;
    llmConfigApi
      .get()
      .then((next) => {
        if (!cancelled) applyConfig(next);
      })
      .catch((e) => {
        if (!cancelled) setLoadError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateDraft = (role: LlmRole, patch: Partial<SlotDraft>) => {
    setDrafts((d) => (d ? { ...d, [role]: { ...d[role], ...patch } } : d));
  };

  const saveSlot = (role: LlmRole) => {
    if (!drafts) return;
    const d = drafts[role];
    const update: ApiLlmSlotUpdate = {
      enabled: d.enabled,
      provider: d.provider,
      model: d.model,
      endpoint: d.endpoint,
      numCtx: d.numCtx,
      maxTokens: d.maxTokens,
      temperature: d.temperature,
    };
    if (d.apiKey.trim()) update.apiKey = d.apiKey;
    const body: ApiLlmConfigUpdate =
      role === "primary"
        ? { primary: update }
        : role === "fallback"
          ? { fallback: update }
          : { validator: update };
    setSavingRole(role);
    llmConfigApi
      .put(body)
      .then((next) => {
        applyConfig(next);
        show(`${SLOT_LABEL[role]} provider saved.`);
      })
      .catch((e) => show(`Could not save ${SLOT_LABEL[role]}: ${(e as Error).message}`))
      .finally(() => setSavingRole(null));
  };

  const testSlot = (role: LlmRole) => {
    setTestingRole(role);
    setResults((r) => {
      const next = { ...r };
      delete next[role];
      return next;
    });
    llmConfigApi
      .test(role)
      .then((result) => setResults((r) => ({ ...r, [role]: result })))
      .catch((e) =>
        setResults((r) => ({
          ...r,
          [role]: { ok: false, latency_ms: 0, model_echo: null, error: (e as Error).message },
        })),
      )
      .finally(() => setTestingRole(null));
  };

  const changeRouting = (route: LlmRouteRole, target: LlmRole) => {
    if (!routing) return;
    const next = { ...routing, [route]: target };
    setRouting(next);
    setSavingRouting(true);
    llmConfigApi
      .put({ routing: next })
      .then((saved) => {
        setConfig(saved);
        setRouting(saved.routing);
        show(`Routing saved: ${ROUTE_LABEL[route]} uses ${SLOT_LABEL[target]}.`);
      })
      .catch((e) => {
        setRouting(routing);
        show(`Could not save routing: ${(e as Error).message}`);
      })
      .finally(() => setSavingRouting(false));
  };

  return (
    <SectionCard
      title="LLM Providers"
      sub="These are the provider slots the processing pipeline resolves. Saving here changes what the next job uses. API keys stay on the server and only the last four characters ever display."
    >
      {loading ? <p className="text-sm text-muted">Loading providers...</p> : null}

      {!loading && loadError ? (
        <div className="rounded-md border border-danger p-3">
          <p className="text-sm font-semibold text-danger">Could not load providers</p>
          <p className="mt-1 text-xs text-muted">{loadError}</p>
          <div className="mt-2">
            <Button onClick={load}>Retry</Button>
          </div>
        </div>
      ) : null}

      {!loading && !loadError && config && drafts && routing ? (
        <>
          <ul className="flex flex-col gap-2" aria-label="Provider slots">
            {SLOT_ORDER.map((role) => (
              <SlotCard
                key={role}
                role={role}
                slot={config[role]}
                draft={drafts[role]}
                uid={uid}
                saving={savingRole === role}
                testing={testingRole === role}
                result={results[role] ?? null}
                keyHidden={keyHidden[role] ?? false}
                onChange={(patch) => updateDraft(role, patch)}
                onSave={() => saveSlot(role)}
                onTest={() => testSlot(role)}
                onToggleKey={() => setKeyHidden((k) => ({ ...k, [role]: !(k[role] ?? false) }))}
              />
            ))}
          </ul>

          <div className="mt-4 rounded-md border border-line p-3" aria-label="Routing">
            <h3 className="text-sm font-semibold">Routing</h3>
            <p className="mt-0.5 text-xs text-muted">
              Which slot handles each pipeline step. Each change saves immediately.
            </p>
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {ROUTE_ORDER.map((route) => (
                <Field key={route} label={ROUTE_LABEL[route]} htmlFor={`${uid}-route-${route}`}>
                  <select
                    id={`${uid}-route-${route}`}
                    value={routing[route]}
                    onChange={(e) => changeRouting(route, e.target.value as LlmRole)}
                    disabled={savingRouting}
                    className={inputCls}
                  >
                    {SLOT_ORDER.map((role) => (
                      <option key={role} value={role}>
                        {SLOT_LABEL[role]}
                      </option>
                    ))}
                  </select>
                </Field>
              ))}
            </div>
          </div>

          <p className="mt-3 text-xs text-muted">
            Tests run against the saved configuration with a fixed one-word prompt. Unsaved edits are not
            sent.
          </p>
        </>
      ) : null}
    </SectionCard>
  );
}
