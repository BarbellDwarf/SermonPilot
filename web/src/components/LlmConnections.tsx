import { useId, useRef, useState } from "react";
import { Button, Chip, ConfirmDialog, Field, SectionCard, inputCls } from "./ui";

export type LlmRole = "Primary" | "Fallback" | "Validator" | "Unused";
export type LlmStatus = "ok" | "warn" | "error" | "unknown";

export interface LlmConnection {
  id: string;
  name: string;
  preset: string;
  provider: string;
  model: string;
  endpoint: string;
  apiKey: string;
  numCtx: string;
  maxTokens: string;
  temperature: string;
  role: LlmRole;
  status: LlmStatus;
}

interface Preset {
  id: string;
  label: string;
  provider: string;
  endpoint: string;
  docsHint: string;
  setupNote: string;
  needsKey: boolean;
  needsHostOnly: boolean;
}

const PRESETS: Preset[] = [
  { id: "ollama", label: "Ollama (local)", provider: "Ollama", endpoint: "http://localhost:11434", docsHint: "docs: ollama.com/library", setupNote: "Runs on this machine. Pull models first: ollama pull llama3.", needsKey: false, needsHostOnly: true },
  { id: "ollama-cloud", label: "Ollama Cloud", provider: "Ollama Cloud", endpoint: "https://ollama.com", docsHint: "docs: ollama.com/cloud", setupNote: "Cloud-hosted Ollama models behind one account key.", needsKey: true, needsHostOnly: false },
  { id: "openai", label: "OpenAI", provider: "OpenAI", endpoint: "https://api.openai.com/v1", docsHint: "docs: platform.openai.com", setupNote: "Standard API key from the OpenAI dashboard.", needsKey: true, needsHostOnly: false },
  { id: "anthropic", label: "Anthropic", provider: "Anthropic", endpoint: "https://api.anthropic.com", docsHint: "docs: docs.anthropic.com", setupNote: "API key from console.anthropic.com for Claude models.", needsKey: true, needsHostOnly: false },
  { id: "gemini", label: "Google Gemini", provider: "Google", endpoint: "https://generativelanguage.googleapis.com", docsHint: "docs: ai.google.dev", setupNote: "API key from Google AI Studio.", needsKey: true, needsHostOnly: false },
  { id: "grok", label: "xAI Grok", provider: "xAI", endpoint: "https://api.x.ai/v1", docsHint: "docs: docs.x.ai", setupNote: "API key from the xAI console.", needsKey: true, needsHostOnly: false },
  { id: "groq", label: "Groq", provider: "Groq", endpoint: "https://api.groq.com/openai/v1", docsHint: "docs: console.groq.com", setupNote: "Fast inference. One key, OpenAI-compatible endpoint.", needsKey: true, needsHostOnly: false },
  { id: "openrouter", label: "OpenRouter", provider: "OpenRouter", endpoint: "https://openrouter.ai/api/v1", docsHint: "docs: openrouter.ai/docs", setupNote: "One key for many models. Set model to e.g. openai/gpt-4o-mini.", needsKey: true, needsHostOnly: false },
  { id: "azure", label: "Azure OpenAI", provider: "Azure OpenAI", endpoint: "https://{resource}.openai.azure.com", docsHint: "docs: learn.microsoft.com/azure/ai-services/openai", setupNote: "Endpoint is your resource URL plus deployment model id.", needsKey: true, needsHostOnly: false },
  { id: "lmstudio", label: "LM Studio (local)", provider: "LM Studio", endpoint: "http://localhost:1234/v1", docsHint: "docs: lmstudio.ai/docs", setupNote: "Local server. Start the server in LM Studio first.", needsKey: false, needsHostOnly: false },
  { id: "vllm", label: "vLLM (self-hosted)", provider: "vLLM", endpoint: "http://localhost:8000/v1", docsHint: "docs: docs.vllm.ai", setupNote: "Self-hosted OpenAI-compatible server. Point at your host.", needsKey: false, needsHostOnly: false },
  { id: "custom", label: "Custom (OpenAI-compatible)", provider: "Custom", endpoint: "", docsHint: "Any OpenAI-compatible /v1 endpoint.", setupNote: "Any base URL that speaks the OpenAI chat API.", needsKey: true, needsHostOnly: false },
];

const PRESET_DEFAULT_MODEL: Record<string, string> = {
  ollama: "llama3",
  "ollama-cloud": "glm-5.3-flash:cloud",
  openai: "gpt-4o-mini",
  anthropic: "claude-3-5-sonnet-20241022",
  gemini: "gemini-1.5-flash",
  grok: "grok-beta",
  groq: "llama-3.1-8b-instant",
  openrouter: "openai/gpt-4o-mini",
  azure: "your-deployment",
  lmstudio: "local-model",
  vllm: "served-model",
  custom: "",
};

const ROLE_TONE: Record<LlmRole, string> = {
  Primary: "accent",
  Fallback: "info",
  Validator: "ok",
  Unused: "neutral",
};

const STATUS_DOT: Record<LlmStatus, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  error: "bg-danger",
  unknown: "bg-muted",
};

function maskKey(key: string): string {
  if (!key) return "not set";
  if (key.startsWith("oauth-")) return "oauth-••••" + key.slice(-4);
  if (key.length <= 8) return "••••••••";
  return "••••••••" + key.slice(-4);
}

function latencyFor(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 700;
  return 140 + h;
}

let seq = 100;
function nextId(): string {
  seq += 1;
  return `conn-${seq}`;
}

interface EditorDraft {
  name: string;
  preset: string;
  endpoint: string;
  apiKey: string;
  model: string;
  numCtx: string;
  maxTokens: string;
  temperature: string;
  role: LlmRole;
}

const EMPTY_DRAFT: EditorDraft = {
  name: "",
  preset: "openai",
  endpoint: "https://api.openai.com/v1",
  apiKey: "",
  model: "",
  numCtx: "32768",
  maxTokens: "16000",
  temperature: "0.7",
  role: "Unused",
};

type EditorErrors = Partial<Record<"name" | "endpoint" | "model" | "numCtx" | "maxTokens" | "temperature", string>>;

function validateDraft(d: EditorDraft): EditorErrors {
  const e: EditorErrors = {};
  if (!d.name.trim()) e.name = "Name is required.";
  if (d.endpoint && !/^https?:\/\/.{3,}/.test(d.endpoint.trim()) && !d.endpoint.includes("{resource}")) e.endpoint = "Base URL must start with http(s)://.";
  if (!d.model.trim()) e.model = "Model id is required.";
  if (d.numCtx.trim() && !/^\d+$/.test(d.numCtx.trim())) e.numCtx = "Context window must be a whole number.";
  if (d.maxTokens.trim() && !/^\d+$/.test(d.maxTokens.trim())) e.maxTokens = "Max tokens must be a whole number.";
  if (d.temperature.trim() && !/^\d+(\.\d+)?$/.test(d.temperature.trim())) e.temperature = "Temperature must be a number.";
  else if (d.temperature.trim()) {
    const t = Number(d.temperature);
    if (t < 0 || t > 2) e.temperature = "Temperature must be between 0 and 2.";
  }
  return e;
}

function draftFromConnection(c: LlmConnection): EditorDraft {
  return {
    name: c.name,
    preset: c.preset,
    endpoint: c.endpoint,
    apiKey: "",
    model: c.model,
    numCtx: c.numCtx,
    maxTokens: c.maxTokens,
    temperature: c.temperature,
    role: c.role,
  };
}

const INITIAL_CONNECTIONS: LlmConnection[] = [
  {
    id: "conn-1",
    name: "Local Ollama",
    preset: "ollama",
    provider: "Ollama",
    model: "llama3",
    endpoint: "http://localhost:11434",
    apiKey: "",
    numCtx: "32768",
    maxTokens: "16000",
    temperature: "0.7",
    role: "Primary",
    status: "ok",
  },
  {
    id: "conn-2",
    name: "OpenAI fallback",
    preset: "openai",
    provider: "OpenAI",
    model: "gpt-3.5-turbo",
    endpoint: "https://api.openai.com/v1",
    apiKey: "mock-sk-••••-9f2a",
    numCtx: "",
    maxTokens: "",
    temperature: "0.7",
    role: "Fallback",
    status: "warn",
  },
  {
    id: "conn-3",
    name: "Validator small",
    preset: "ollama",
    provider: "Ollama",
    model: "gemma2:2b",
    endpoint: "http://localhost:11434",
    apiKey: "",
    numCtx: "8192",
    maxTokens: "4000",
    temperature: "0.3",
    role: "Validator",
    status: "ok",
  },
];

type SubState = "idle" | "code" | "waiting" | "connected";

interface SubConnection {
  key: "claude" | "chatgpt";
  title: string;
  detail: string;
  state: SubState;
  code: string;
  token: string;
}

function ConnectionCard({
  conn,
  testing,
  testResult,
  onToggleKey,
  keyVisible,
  onTest,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  conn: LlmConnection;
  testing: boolean;
  testResult: string | null;
  keyVisible: boolean;
  onToggleKey: () => void;
  onTest: () => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span aria-label={`status ${conn.status}`} title={`status: ${conn.status}`} className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[conn.status]}`} />
        <p className="min-w-0 flex-1 truncate text-sm font-semibold">{conn.name}</p>
        <Chip tone={ROLE_TONE[conn.role]}>{conn.role}</Chip>
      </div>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        <div className="flex gap-1.5">
          <dt className="shrink-0 text-muted">Provider</dt>
          <dd className="min-w-0 truncate font-mono">{conn.provider}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="shrink-0 text-muted">Model</dt>
          <dd className="min-w-0 truncate font-mono">{conn.model || "—"}</dd>
        </div>
        <div className="flex gap-1.5 sm:col-span-2">
          <dt className="shrink-0 text-muted">Endpoint</dt>
          <dd className="min-w-0 truncate font-mono">{conn.endpoint || "—"}</dd>
        </div>
        <div className="flex items-center gap-1.5 sm:col-span-2">
          <dt className="shrink-0 text-muted">Key</dt>
          <dd className="min-w-0 flex-1 truncate font-mono">{keyVisible ? conn.apiKey || "(empty mock)" : maskKey(conn.apiKey)}</dd>
          <dd className="shrink-0">
            <button
              type="button"
              onClick={onToggleKey}
              aria-pressed={keyVisible}
              aria-label={keyVisible ? `Hide key for ${conn.name}` : `Show key for ${conn.name}`}
              className="min-h-[44px] rounded px-2 text-xs font-semibold text-muted hover:bg-raised hover:text-mist"
            >
              {keyVisible ? "Hide" : "Show"}
            </button>
          </dd>
        </div>
      </dl>
      {testResult ? (
        <p className="mt-2 text-xs text-muted" role="status">
          {testResult}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button onClick={onTest} disabled={testing} aria-label={`Test connection ${conn.name}`}>
          {testing ? "Testing…" : "Test connection"}
        </Button>
        <Button onClick={onEdit} aria-label={`Edit ${conn.name}`}>
          Edit
        </Button>
        <Button onClick={onDuplicate} aria-label={`Duplicate ${conn.name}`}>
          Duplicate
        </Button>
        <Button variant="danger" onClick={onDelete} aria-label={`Delete ${conn.name}`}>
          Delete
        </Button>
      </div>
    </li>
  );
}

export function LlmConnectionsSection({ show }: { show: (m: string) => void }) {
  const [connections, setConnections] = useState<LlmConnection[]>(INITIAL_CONNECTIONS);
  const [visibleKeys, setVisibleKeys] = useState<string[]>([]);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditorDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<EditorErrors>({});
  const [pendingDelete, setPendingDelete] = useState<LlmConnection | null>(null);
  const [routing, setRouting] = useState({ metadata: "conn-1", validation: "conn-3", assist: "conn-1", fallback: "conn-2" });
  const [subs, setSubs] = useState<SubConnection[]>([
    { key: "claude", title: "Claude Pro / Max", detail: "OAuth device login. Uses your subscription, no API key.", state: "idle", code: "", token: "" },
    { key: "chatgpt", title: "ChatGPT Plus / Pro", detail: "OAuth device login. Uses your subscription, no API key.", state: "idle", code: "", token: "" },
  ]);
  const editorRef = useRef<HTMLDivElement>(null);
  const uid = useId();
  const timers = useRef<number[]>([]);

  const openEditor = (d: EditorDraft, id: string | null) => {
    setDraft(d);
    setErrors({});
    setEditingId(id);
    setEditorOpen(true);
    window.setTimeout(() => {
      editorRef.current?.scrollIntoView({ block: "nearest" });
      const first = editorRef.current?.querySelector("input,select");
      if (first instanceof HTMLElement) first.focus();
    }, 50);
  };

  const applyPreset = (presetId: string) => {
    const p = PRESETS.find((x) => x.id === presetId);
    if (!p) return;
    setDraft((d) => ({
      ...d,
      preset: presetId,
      endpoint: p.endpoint,
      model: d.model || PRESET_DEFAULT_MODEL[presetId] || "",
    }));
  };

  const saveDraft = () => {
    const e = validateDraft(draft);
    setErrors(e);
    if (Object.keys(e).length > 0) return;
    const preset = PRESETS.find((x) => x.id === draft.preset);
    if (editingId) {
      setConnections((cs) =>
        cs.map((c) =>
          c.id === editingId
            ? {
                ...c,
                name: draft.name.trim(),
                preset: draft.preset,
                provider: preset?.provider ?? c.provider,
                model: draft.model.trim(),
                endpoint: draft.endpoint.trim(),
                apiKey: draft.apiKey ? `mock-••••-${draft.apiKey.slice(-4)}` : c.apiKey,
                numCtx: draft.numCtx.trim(),
                maxTokens: draft.maxTokens.trim(),
                temperature: draft.temperature.trim(),
                role: draft.role,
              }
            : c,
        ),
      );
      show(`Connection saved (mock): ${draft.name.trim()}.`);
    } else {
      const c: LlmConnection = {
        id: nextId(),
        name: draft.name.trim(),
        preset: draft.preset,
        provider: preset?.provider ?? "Custom",
        model: draft.model.trim(),
        endpoint: draft.endpoint.trim(),
        apiKey: draft.apiKey ? `mock-••••-${draft.apiKey.slice(-4)}` : "",
        numCtx: draft.numCtx.trim(),
        maxTokens: draft.maxTokens.trim(),
        temperature: draft.temperature.trim(),
        role: draft.role,
        status: "unknown",
      };
      setConnections((cs) => [...cs, c]);
      show(`Connection added (mock): ${c.name}.`);
    }
    setEditorOpen(false);
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
  };

  const testConnection = (id: string) => {
    const conn = connections.find((c) => c.id === id);
    if (!conn) return;
    setTesting(id);
    setTestResults((r) => ({ ...r, [id]: "" }));
    const t = window.setTimeout(() => {
      const ok = conn.endpoint.trim().length > 0;
      const ms = latencyFor(id);
      const msg = ok ? `Success (mock): ${ms} ms via ${conn.provider} / ${conn.model || "default model"}.` : "Failed (mock): endpoint is empty.";
      setTestResults((r) => ({ ...r, [id]: msg }));
      setConnections((cs) => cs.map((c) => (c.id === id ? { ...c, status: ok ? "ok" : "error" } : c)));
      setTesting(null);
      show(ok ? `Test passed (mock): ${conn.name}, ${ms} ms.` : `Test failed (mock): ${conn.name}.`);
    }, 900);
    timers.current.push(t);
  };

  const startOAuth = (key: "claude" | "chatgpt") => {
    const code = `${Math.random().toString(36).slice(2, 6).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
    setSubs((ss) => ss.map((s) => (s.key === key ? { ...s, state: "code", code } : s)));
    const t1 = window.setTimeout(() => {
      setSubs((ss) => ss.map((s) => (s.key === key && s.state === "code" ? { ...s, state: "waiting" } : s)));
      const t2 = window.setTimeout(() => {
        setSubs((ss) =>
          ss.map((s) => (s.key === key ? { ...s, state: "connected", token: `oauth-••••${code.slice(-4)}` } : s)),
        );
        show(`Subscription connected (mock): ${key === "claude" ? "Claude" : "ChatGPT"}.`);
      }, 2500);
      timers.current.push(t2);
    }, 1200);
    timers.current.push(t1);
  };

  const disconnectSub = (key: "claude" | "chatgpt") => {
    setSubs((ss) => ss.map((s) => (s.key === key ? { ...s, state: "idle", code: "", token: "" } : s)));
    show("Subscription disconnected (mock).");
  };

  const activePreset = PRESETS.find((x) => x.id === draft.preset);

  return (
    <SectionCard
      title="LLM Providers"
      sub="Connections manager (mock). Shape mirrors the app config llm block: primary / fallback / validator with provider, model, base URL, key, ollama host, num_ctx, max_tokens."
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">
          {connections.length} connection{connections.length === 1 ? "" : "s"} configured. Nothing here calls the network.
        </p>
        <Button
          variant="primary"
          onClick={() => openEditor({ ...EMPTY_DRAFT }, null)}
          aria-label="Add connection"
        >
          Add connection
        </Button>
      </div>

      <ul className="mt-3 flex flex-col gap-2" aria-label="Configured connections">
        {connections.map((c) => (
          <ConnectionCard
            key={c.id}
            conn={c}
            testing={testing === c.id}
            testResult={testResults[c.id] ?? null}
            keyVisible={visibleKeys.includes(c.id)}
            onToggleKey={() => setVisibleKeys((v) => (v.includes(c.id) ? v.filter((x) => x !== c.id) : [...v, c.id]))}
            onTest={() => testConnection(c.id)}
            onEdit={() => openEditor(draftFromConnection(c), c.id)}
            onDuplicate={() => {
              const copy: LlmConnection = { ...c, id: nextId(), name: `${c.name} copy`, role: "Unused", status: "unknown" };
              setConnections((cs) => [...cs, copy]);
              show(`Connection duplicated (mock): ${copy.name}.`);
            }}
            onDelete={() => setPendingDelete(c)}
          />
        ))}
      </ul>

      {editorOpen ? (
        <div ref={editorRef} className="mt-4 rounded-md border border-line bg-ink p-4" role="form" aria-label="Connection editor">
          <h3 className="text-sm font-semibold">{editingId ? "Edit connection" : "New connection"}</h3>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name" htmlFor={`${uid}-name`}>
              <input
                id={`${uid}-name`}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                onBlur={() => setErrors(validateDraft(draft))}
                className={inputCls}
                autoComplete="off"
                placeholder="e.g. OpenAI fallback"
              />
              {errors.name ? <p className="mt-1 text-xs text-danger" role="alert">{errors.name}</p> : null}
            </Field>
            <Field label="Type preset" htmlFor={`${uid}-preset`} hint={activePreset ? `${activePreset.setupNote} ${activePreset.docsHint}` : undefined}>
              <select
                id={`${uid}-preset`}
                value={draft.preset}
                onChange={(e) => applyPreset(e.target.value)}
                className={inputCls}
              >
                {PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={activePreset?.needsHostOnly ? "Host" : "Base URL"} htmlFor={`${uid}-endpoint`}>
              <input
                id={`${uid}-endpoint`}
                value={draft.endpoint}
                onChange={(e) => setDraft({ ...draft, endpoint: e.target.value })}
                onBlur={() => setErrors(validateDraft(draft))}
                className={`${inputCls} font-mono`}
                autoComplete="off"
                inputMode="url"
                placeholder="https://…"
              />
              {errors.endpoint ? <p className="mt-1 text-xs text-danger" role="alert">{errors.endpoint}</p> : null}
            </Field>
            <Field label="API key" htmlFor={`${uid}-key`} hint="Stored per account. Only the last 4 characters ever display. Mock only.">
              <input
                id={`${uid}-key`}
                type="password"
                value={draft.apiKey}
                onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                className={`${inputCls} font-mono`}
                autoComplete="new-password"
                placeholder="••••••••"
              />
            </Field>
            <Field label="Model id" htmlFor={`${uid}-model`}>
              <input
                id={`${uid}-model`}
                value={draft.model}
                onChange={(e) => setDraft({ ...draft, model: e.target.value })}
                onBlur={() => setErrors(validateDraft(draft))}
                className={`${inputCls} font-mono`}
                autoComplete="off"
                placeholder={PRESET_DEFAULT_MODEL[draft.preset] || "model-id"}
              />
              {errors.model ? <p className="mt-1 text-xs text-danger" role="alert">{errors.model}</p> : null}
            </Field>
            <Field label="Role" htmlFor={`${uid}-role`} hint="Primary generates, fallback catches failures, validator checks drafts.">
              <select
                id={`${uid}-role`}
                value={draft.role}
                onChange={(e) => setDraft({ ...draft, role: e.target.value as LlmRole })}
                className={inputCls}
              >
                {(["Primary", "Fallback", "Validator", "Unused"] as LlmRole[]).map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Context window (num_ctx)" htmlFor={`${uid}-ctx`}>
              <input
                id={`${uid}-ctx`}
                value={draft.numCtx}
                onChange={(e) => setDraft({ ...draft, numCtx: e.target.value })}
                onBlur={() => setErrors(validateDraft(draft))}
                className={`${inputCls} font-mono`}
                inputMode="numeric"
                autoComplete="off"
              />
              {errors.numCtx ? <p className="mt-1 text-xs text-danger" role="alert">{errors.numCtx}</p> : null}
            </Field>
            <Field label="Max tokens" htmlFor={`${uid}-max`}>
              <input
                id={`${uid}-max`}
                value={draft.maxTokens}
                onChange={(e) => setDraft({ ...draft, maxTokens: e.target.value })}
                onBlur={() => setErrors(validateDraft(draft))}
                className={`${inputCls} font-mono`}
                inputMode="numeric"
                autoComplete="off"
              />
              {errors.maxTokens ? <p className="mt-1 text-xs text-danger" role="alert">{errors.maxTokens}</p> : null}
            </Field>
            <Field label="Temperature" htmlFor={`${uid}-temp`} hint="0 to 2. Lower is more deterministic.">
              <input
                id={`${uid}-temp`}
                value={draft.temperature}
                onChange={(e) => setDraft({ ...draft, temperature: e.target.value })}
                onBlur={() => setErrors(validateDraft(draft))}
                className={`${inputCls} font-mono`}
                inputMode="decimal"
                autoComplete="off"
              />
              {errors.temperature ? <p className="mt-1 text-xs text-danger" role="alert">{errors.temperature}</p> : null}
            </Field>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              variant="primary"
              onClick={saveDraft}
              aria-label={editingId ? "Save connection" : "Add connection to list"}
            >
              {editingId ? "Save" : "Add"}
            </Button>
            <Button
              onClick={() => {
                setEditorOpen(false);
                setEditingId(null);
                setDraft(EMPTY_DRAFT);
                setErrors({});
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-4 rounded-md border border-line p-3" aria-label="Routing">
        <h3 className="text-sm font-semibold">Routing</h3>
        <p className="mt-0.5 text-xs text-muted">Map each pipeline role to a connection. Fallback stays visible and catches primary failures.</p>
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {(
            [
              ["metadata", "Metadata generation"],
              ["validation", "Validation"],
              ["assist", "Transcription assist"],
              ["fallback", "Fallback"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key} label={label} htmlFor={`${uid}-route-${key}`}>
              <select
                id={`${uid}-route-${key}`}
                value={routing[key]}
                onChange={(e) => {
                  setRouting({ ...routing, [key]: e.target.value });
                  show(`Routing updated (mock): ${label} -> ${connections.find((c) => c.id === e.target.value)?.name ?? "none"}.`);
                }}
                className={inputCls}
              >
                {connections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.role}, {c.model})
                  </option>
                ))}
              </select>
            </Field>
          ))}
        </div>
      </div>

      <div className="mt-4" aria-label="Subscription connections">
        <h3 className="text-sm font-semibold">Subscription connections</h3>
        <p className="mt-0.5 text-xs text-muted">
          Subscription access uses an OAuth-style login and may have usage limits vs API keys.
        </p>
        <ul className="mt-2 flex flex-col gap-2">
          {subs.map((s) => (
            <li key={s.key} className="rounded-md border border-line p-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="min-w-0 flex-1 text-sm font-semibold">{s.title}</p>
                <Chip tone={s.state === "connected" ? "ok" : s.state === "idle" ? "neutral" : "info"}>
                  {s.state === "connected" ? "connected" : s.state === "idle" ? "not connected" : s.state === "code" ? "code issued" : "waiting…"}
                </Chip>
              </div>
              <p className="mt-1 text-xs text-muted">{s.detail}</p>
              {s.state === "idle" ? (
                <div className="mt-2">
                  <Button
                    variant="primary"
                    onClick={() => startOAuth(s.key)}
                    aria-label={`Connect with ${s.key === "claude" ? "Claude" : "ChatGPT"} account`}
                  >
                    Connect with {s.key === "claude" ? "Claude" : "ChatGPT"} account
                  </Button>
                </div>
              ) : null}
              {s.state === "code" || s.state === "waiting" ? (
                <div className="mt-2 rounded border border-line bg-ink p-3" role="status" aria-live="polite">
                  <p className="text-xs text-muted">Step 2 of 3: enter this device code on the provider site, then approve.</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <code className="rounded bg-raised px-3 py-2 font-mono text-sm tracking-widest">{s.code}</code>
                    <Button
                      onClick={() => {
                        void navigator.clipboard?.writeText(s.code).catch(() => undefined);
                        show("Device code copied (mock).");
                      }}
                      aria-label="Copy device code"
                    >
                      Copy code
                    </Button>
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    {s.state === "code" ? "Request sent (mock)…" : "Waiting for authorization… (mock, completes on its own)"}
                  </p>
                </div>
              ) : null}
              {s.state === "connected" ? (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <code className="font-mono text-xs text-muted">{s.token} (mock placeholder)</code>
                  <Button variant="danger" onClick={() => disconnectSub(s.key)} aria-label={`Disconnect ${s.title}`}>
                    Disconnect
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete connection?"
        body={pendingDelete ? `Remove "${pendingDelete.name}" from this mock list? This cannot be undone.` : ""}
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDelete) {
            setConnections((cs) => cs.filter((c) => c.id !== pendingDelete.id));
            show(`Connection deleted (mock): ${pendingDelete.name}.`);
          }
          setPendingDelete(null);
        }}
        onClose={() => setPendingDelete(null)}
      />
    </SectionCard>
  );
}
