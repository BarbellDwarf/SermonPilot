import { useId, useRef, useState } from "react";
import { Button, Chip, ConfirmDialog, Field, SectionCard, inputCls } from "./ui";

export type SaStatus = "ok" | "warn" | "error" | "unknown";

export interface SermonAudioAccount {
  id: string;
  name: string;
  broadcasterId: string;
  apiKey: string;
  notes: string;
  status: SaStatus;
}

const STATUS_DOT: Record<SaStatus, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  error: "bg-danger",
  unknown: "bg-muted",
};

function maskKey(key: string): string {
  if (!key) return "not set";
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
  return `sa-${seq}`;
}

interface EditorDraft {
  name: string;
  broadcasterId: string;
  apiKey: string;
  notes: string;
}

const EMPTY_DRAFT: EditorDraft = { name: "", broadcasterId: "", apiKey: "", notes: "" };

type EditorErrors = Partial<Record<"name" | "broadcasterId" | "apiKey", string>>;

function validateDraft(d: EditorDraft): EditorErrors {
  const e: EditorErrors = {};
  if (!d.name.trim()) e.name = "Broadcaster name is required.";
  if (!d.broadcasterId.trim()) e.broadcasterId = "Broadcaster ID is required.";
  else if (!/^[A-Za-z0-9_-]+$/.test(d.broadcasterId.trim()))
    e.broadcasterId = "Broadcaster ID may only contain letters, numbers, dashes, underscores.";
  if (!d.apiKey.trim()) e.apiKey = "API key is required.";
  return e;
}

function draftFromAccount(a: SermonAudioAccount): EditorDraft {
  return { name: a.name, broadcasterId: a.broadcasterId, apiKey: "", notes: a.notes };
}

const INITIAL_ACCOUNTS: SermonAudioAccount[] = [
  {
    id: "sa-1",
    name: "Grace Sample Church",
    broadcasterId: "grace-sample",
    apiKey: "mock-••••-7f3a",
    notes: "Main Sunday broadcast.",
    status: "ok",
  },
  {
    id: "sa-2",
    name: "Grace Sample Church — Youth",
    broadcasterId: "grace-sample-youth",
    apiKey: "mock-••••-b21e",
    notes: "",
    status: "unknown",
  },
];

function AccountCard({
  account,
  isDefault,
  testing,
  testResult,
  keyVisible,
  onToggleKey,
  onTest,
  onSetDefault,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  account: SermonAudioAccount;
  isDefault: boolean;
  testing: boolean;
  testResult: string | null;
  keyVisible: boolean;
  onToggleKey: () => void;
  onTest: () => void;
  onSetDefault: () => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span aria-label={`status ${account.status}`} title={`status: ${account.status}`} className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[account.status]}`} />
        <p className="min-w-0 flex-1 truncate text-sm font-semibold">{account.name}</p>
        {isDefault ? (
          <Chip tone="accent">★ default</Chip>
        ) : (
          <button
            type="button"
            onClick={onSetDefault}
            aria-pressed={false}
            aria-label={`Set ${account.name} as default account`}
            className="inline-flex min-h-[44px] items-center rounded-full border border-line px-2.5 font-mono text-xs uppercase tracking-wide text-muted hover:border-muted hover:text-mist"
          >
            ☆ set default
          </button>
        )}
      </div>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        <div className="flex gap-1.5">
          <dt className="shrink-0 text-muted">Broadcaster ID</dt>
          <dd className="min-w-0 truncate font-mono">{account.broadcasterId || "—"}</dd>
        </div>
        <div className="flex items-center gap-1.5 sm:col-span-2">
          <dt className="shrink-0 text-muted">API key</dt>
          <dd className="min-w-0 flex-1 truncate font-mono">{keyVisible ? account.apiKey || "(empty mock)" : maskKey(account.apiKey)}</dd>
          <dd className="shrink-0">
            <button
              type="button"
              onClick={onToggleKey}
              aria-pressed={keyVisible}
              aria-label={keyVisible ? `Hide API key for ${account.name}` : `Show API key for ${account.name}`}
              className="min-h-[44px] rounded px-2 text-xs font-semibold text-muted hover:bg-raised hover:text-mist"
            >
              {keyVisible ? "Hide" : "Show"}
            </button>
          </dd>
        </div>
        {account.notes ? (
          <div className="flex gap-1.5 sm:col-span-2">
            <dt className="shrink-0 text-muted">Notes</dt>
            <dd className="min-w-0 truncate">{account.notes}</dd>
          </div>
        ) : null}
      </dl>
      {testResult ? (
        <p className="mt-2 text-xs text-muted" role="status">
          {testResult}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button onClick={onTest} disabled={testing} aria-label={`Test account ${account.name}`}>
          {testing ? "Testing…" : "Test"}
        </Button>
        <Button onClick={onEdit} aria-label={`Edit ${account.name}`}>
          Edit
        </Button>
        <Button onClick={onDuplicate} aria-label={`Duplicate ${account.name}`}>
          Duplicate
        </Button>
        <Button variant="danger" onClick={onDelete} aria-label={`Delete ${account.name}`}>
          Delete
        </Button>
      </div>
    </li>
  );
}

export function SermonAudioAccountsSection({ show }: { show: (m: string) => void }) {
  const [accounts, setAccounts] = useState<SermonAudioAccount[]>(INITIAL_ACCOUNTS);
  const [defaultId, setDefaultId] = useState("sa-1");
  const [saved, setSaved] = useState({ accounts: INITIAL_ACCOUNTS, defaultId: "sa-1" });
  const [visibleKeys, setVisibleKeys] = useState<string[]>([]);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditorDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<EditorErrors>({});
  const [showSecret, setShowSecret] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SermonAudioAccount | null>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const uid = useId();

  const dirty = JSON.stringify({ accounts, defaultId }) !== JSON.stringify(saved);
  const defaultAccount = accounts.find((a) => a.id === defaultId);

  const openEditor = (d: EditorDraft, id: string | null) => {
    setDraft(d);
    setErrors({});
    setShowSecret(false);
    setEditingId(id);
    setEditorOpen(true);
    window.setTimeout(() => {
      editorRef.current?.scrollIntoView({ block: "nearest" });
      const first = editorRef.current?.querySelector("input,textarea");
      if (first instanceof HTMLElement) first.focus();
    }, 50);
  };

  const saveDraft = () => {
    const e = validateDraft({ ...draft, apiKey: editingId ? draft.apiKey || "kept" : draft.apiKey });
    setErrors(e);
    if (Object.keys(e).length > 0) return;
    if (editingId) {
      setAccounts((as) =>
        as.map((a) =>
          a.id === editingId
            ? {
                ...a,
                name: draft.name.trim(),
                broadcasterId: draft.broadcasterId.trim(),
                apiKey: draft.apiKey ? `mock-••••-${draft.apiKey.slice(-4)}` : a.apiKey,
                notes: draft.notes.trim(),
              }
            : a,
        ),
      );
      show(`Account saved (mock): ${draft.name.trim()}.`);
    } else {
      const a: SermonAudioAccount = {
        id: nextId(),
        name: draft.name.trim(),
        broadcasterId: draft.broadcasterId.trim(),
        apiKey: `mock-••••-${draft.apiKey.slice(-4)}`,
        notes: draft.notes.trim(),
        status: "unknown",
      };
      setAccounts((as) => [...as, a]);
      show(`Account added (mock): ${a.name}.`);
    }
    setEditorOpen(false);
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
  };

  const testAccount = (id: string) => {
    const account = accounts.find((a) => a.id === id);
    if (!account) return;
    setTesting(id);
    setTestResults((r) => ({ ...r, [id]: "" }));
    window.setTimeout(() => {
      const ok = account.broadcasterId.trim().length > 0 && account.apiKey.trim().length > 0;
      const ms = latencyFor(id);
      const msg = ok
        ? `Success (mock): ${ms} ms as ${account.broadcasterId}.`
        : "Failed (mock): broadcaster ID or API key is missing.";
      setTestResults((r) => ({ ...r, [id]: msg }));
      setAccounts((as) => as.map((a) => (a.id === id ? { ...a, status: ok ? "ok" : "error" } : a)));
      setTesting(null);
      show(ok ? `Test passed (mock): ${account.name}, ${ms} ms.` : `Test failed (mock): ${account.name}.`);
    }, 900);
  };

  return (
    <SectionCard
      title="SermonAudio Accounts"
      sub="Per-broadcaster upload accounts (mock). Shape mirrors the live app config: api_key plus broadcaster_id per account, one default used when no account is picked. Nothing here calls the network."
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">
          {accounts.length} account{accounts.length === 1 ? "" : "s"} configured.
          {defaultAccount ? ` Default: ${defaultAccount.name}.` : " No default set."}
        </p>
        <Button variant="primary" onClick={() => openEditor({ ...EMPTY_DRAFT }, null)} aria-label="Add SermonAudio account">
          Add account
        </Button>
      </div>

      <ul className="mt-3 flex flex-col gap-2" aria-label="SermonAudio accounts">
        {accounts.map((a) => (
          <AccountCard
            key={a.id}
            account={a}
            isDefault={a.id === defaultId}
            testing={testing === a.id}
            testResult={testResults[a.id] ?? null}
            keyVisible={visibleKeys.includes(a.id)}
            onToggleKey={() => setVisibleKeys((v) => (v.includes(a.id) ? v.filter((x) => x !== a.id) : [...v, a.id]))}
            onTest={() => testAccount(a.id)}
            onSetDefault={() => {
              setDefaultId(a.id);
              show(`Default account (mock): ${a.name}.`);
            }}
            onEdit={() => openEditor(draftFromAccount(a), a.id)}
            onDuplicate={() => {
              const copy: SermonAudioAccount = { ...a, id: nextId(), name: `${a.name} copy`, status: "unknown" };
              setAccounts((as) => [...as, copy]);
              show(`Account duplicated (mock): ${copy.name}.`);
            }}
            onDelete={() => setPendingDelete(a)}
          />
        ))}
      </ul>

      {editorOpen ? (
        <div ref={editorRef} className="mt-4 rounded-md border border-line bg-ink p-4" role="form" aria-label="Account editor">
          <h3 className="text-sm font-semibold">{editingId ? "Edit account" : "New account"}</h3>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Broadcaster display name" htmlFor={`${uid}-name`}>
              <input
                id={`${uid}-name`}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                onBlur={() => setErrors(validateDraft({ ...draft, apiKey: editingId ? draft.apiKey || "kept" : draft.apiKey }))}
                className={inputCls}
                autoComplete="off"
                placeholder="e.g. Grace Sample Church"
              />
              {errors.name ? <p className="mt-1 text-xs text-danger" role="alert">{errors.name}</p> : null}
            </Field>
            <Field label="Broadcaster ID" htmlFor={`${uid}-bid`} hint="Letters, numbers, dashes, underscores.">
              <input
                id={`${uid}-bid`}
                value={draft.broadcasterId}
                onChange={(e) => setDraft({ ...draft, broadcasterId: e.target.value })}
                onBlur={() => setErrors(validateDraft({ ...draft, apiKey: editingId ? draft.apiKey || "kept" : draft.apiKey }))}
                className={`${inputCls} font-mono`}
                autoComplete="off"
                placeholder="e.g. grace-sample"
              />
              {errors.broadcasterId ? <p className="mt-1 text-xs text-danger" role="alert">{errors.broadcasterId}</p> : null}
            </Field>
            <Field
              label="API key"
              htmlFor={`${uid}-key`}
              hint={editingId ? "Leave blank to keep the stored key. Stored masked; only the last 4 characters ever display." : "Stored masked; only the last 4 characters ever display."}
            >
              <div className="flex gap-2">
                <input
                  id={`${uid}-key`}
                  type={showSecret ? "text" : "password"}
                  value={draft.apiKey}
                  onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                  onBlur={() => setErrors(validateDraft({ ...draft, apiKey: editingId ? draft.apiKey || "kept" : draft.apiKey }))}
                  className={`${inputCls} font-mono`}
                  autoComplete="new-password"
                  placeholder="••••••••"
                />
                <Button onClick={() => setShowSecret((s) => !s)} aria-pressed={showSecret} aria-label={showSecret ? "Hide API key" : "Show API key"}>
                  {showSecret ? "Hide" : "Show"}
                </Button>
              </div>
              {errors.apiKey ? <p className="mt-1 text-xs text-danger" role="alert">{errors.apiKey}</p> : null}
            </Field>
            <Field label="Notes (optional)" htmlFor={`${uid}-notes`}>
              <textarea
                id={`${uid}-notes`}
                value={draft.notes}
                onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
                className={`${inputCls} min-h-[44px] py-2`}
                autoComplete="off"
                placeholder="e.g. Main Sunday broadcast"
                rows={2}
              />
            </Field>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="primary" onClick={saveDraft} aria-label={editingId ? "Save account" : "Add account to list"}>
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

      <div className="mt-4 rounded-md border border-line p-3" aria-label="Upload routing">
        <h3 className="text-sm font-semibold">Upload routing</h3>
        <p className="mt-0.5 text-xs text-muted">
          Uploads and metadata pushes use the account selected per sermon when one is picked, otherwise the ★ default account.
        </p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={!dirty}
          onClick={() => {
            setSaved({ accounts, defaultId });
            show(`SermonAudio accounts saved (mock): ${accounts.length} account${accounts.length === 1 ? "" : "s"}.`);
          }}
        >
          Save
        </Button>
        {!dirty ? (
          <span className="text-xs text-muted">No unsaved changes.</span>
        ) : (
          <span className="text-xs text-warn" role="status">
            Unsaved changes.
          </span>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete account?"
        body={pendingDelete ? `Remove "${pendingDelete.name}" (${pendingDelete.broadcasterId}) from this mock list? This cannot be undone.` : ""}
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDelete) {
            setAccounts((as) => as.filter((a) => a.id !== pendingDelete.id));
            if (pendingDelete.id === defaultId) {
              const next = accounts.filter((a) => a.id !== pendingDelete.id)[0];
              setDefaultId(next ? next.id : "");
            }
            show(`Account deleted (mock): ${pendingDelete.name}.`);
          }
          setPendingDelete(null);
        }}
        onClose={() => setPendingDelete(null)}
      />
    </SectionCard>
  );
}
