import { useCallback, useEffect, useId, useRef, useState } from "react";
import { connectionsApi, type ApiConnection, type ApiEffectiveConnection } from "../api/client";
import { sourceCopy } from "./SermonAudioCredentials";
import { Button, Chip, ConfirmDialog, EmptyState, Field, SectionCard, inputCls } from "./ui";

export interface SermonAudioAccount {
  id: string;
  name: string;
  broadcasterId: string;
  notes: string;
  hasKey: boolean;
  maskedKey: string;
}

/** Human-readable description of where this user's uploads will go. */
export function routingCopy(view: ApiEffectiveConnection | null): string {
  if (!view) return "Checking which SermonAudio account uploads will use...";
  if (!view.configured) {
    return view.message || "Connect your SermonAudio account in Settings before publishing.";
  }
  const broadcaster = view.broadcaster_id ? ` (${view.broadcaster_id})` : "";
  if (view.source === "user") {
    return `Uploads use ${view.account_name || "your account"}${broadcaster}.`;
  }
  if (view.source === "db") {
    return `No account connected. Uploads fall back to the saved single-account credentials${broadcaster}.`;
  }
  return `No account connected. Uploads fall back to the environment variable ${view.source}${broadcaster}.`;
}

interface EditorDraft {
  name: string;
  broadcasterId: string;
  apiKey: string;
  notes: string;
}

const EMPTY_DRAFT: EditorDraft = { name: "", broadcasterId: "", apiKey: "", notes: "" };

type EditorErrors = Partial<Record<"name" | "broadcasterId" | "apiKey", string>>;

function validateDraft(d: EditorDraft, requireKey: boolean): EditorErrors {
  const e: EditorErrors = {};
  if (!d.name.trim()) e.name = "Broadcaster display name is required.";
  if (!d.broadcasterId.trim()) e.broadcasterId = "Broadcaster ID is required.";
  else if (!/^[A-Za-z0-9_-]+$/.test(d.broadcasterId.trim()))
    e.broadcasterId = "Broadcaster ID may only contain letters, numbers, dashes, underscores.";
  if (requireKey && !d.apiKey.trim()) e.apiKey = "API key is required.";
  return e;
}

function draftFromAccount(a: SermonAudioAccount): EditorDraft {
  return { name: a.name, broadcasterId: a.broadcasterId, apiKey: "", notes: a.notes };
}

function fromApi(c: ApiConnection): SermonAudioAccount {
  return {
    id: c.id,
    name: c.name,
    broadcasterId: c.broadcasterId || "",
    notes: c.notes || "",
    hasKey: c.has_key,
    maskedKey: c.masked_key || "",
  };
}

function AccountCard({
  account,
  isDefault,
  onSetDefault,
  onEdit,
  onDelete,
}: {
  account: SermonAudioAccount;
  isDefault: boolean;
  onSetDefault: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
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
          <dd
            className="min-w-0 flex-1 truncate font-mono"
            aria-label={`Stored API key for ${account.name}`}
          >
            {account.hasKey ? account.maskedKey : "not set"}
          </dd>
        </div>
        {account.notes ? (
          <div className="flex gap-1.5 sm:col-span-2">
            <dt className="shrink-0 text-muted">Notes</dt>
            <dd className="min-w-0 truncate">{account.notes}</dd>
          </div>
        ) : null}
      </dl>
      <p className="mt-1 text-xs text-muted">
        {account.hasKey ? `API key ${sourceCopy("db")}.` : "No API key stored."}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button onClick={onEdit} aria-label={`Edit ${account.name}`}>
          Edit
        </Button>
        <Button variant="danger" onClick={onDelete} aria-label={`Delete ${account.name}`}>
          Delete
        </Button>
      </div>
    </li>
  );
}

export function SermonAudioAccountsSection({ show }: { show: (m: string) => void }) {
  const [accounts, setAccounts] = useState<SermonAudioAccount[]>([]);
  const [defaultId, setDefaultId] = useState("");
  const [routing, setRouting] = useState<ApiEffectiveConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditorDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<EditorErrors>({});
  const [showSecret, setShowSecret] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SermonAudioAccount | null>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  const uid = useId();

  const load = useCallback(async () => {
    try {
      const r = await connectionsApi.list("sermonaudio");
      if (!alive.current) return;
      setAccounts(r.items.map(fromApi));
      setDefaultId(r.default_id ?? "");
      setLoadError(null);
    } catch (e) {
      if (!alive.current) return;
      setLoadError((e as Error).message);
    } finally {
      if (alive.current) setLoading(false);
    }
    try {
      const effective = await connectionsApi.effective();
      if (alive.current) setRouting(effective);
    } catch {
      if (alive.current) setRouting(null);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
    };
  }, [load]);

  const defaultAccount = accounts.find((a) => a.id === defaultId);
  const editingAccount = editingId ? accounts.find((a) => a.id === editingId) ?? null : null;

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

  const closeEditor = () => {
    setEditorOpen(false);
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setErrors({});
  };

  const saveDraft = () => {
    const e = validateDraft(draft, editingId === null);
    setErrors(e);
    if (Object.keys(e).length > 0) return;
    const payload: Record<string, unknown> = {
      name: draft.name.trim(),
      broadcasterId: draft.broadcasterId.trim(),
      notes: draft.notes.trim(),
    };
    if (draft.apiKey.trim()) payload.apiKey = draft.apiKey.trim();
    setSaving(true);
    const call = editingId
      ? connectionsApi.update("sermonaudio", editingId, payload)
      : connectionsApi.create("sermonaudio", payload);
    void call
      .then(async (row) => {
        await load();
        if (!alive.current) return;
        show(`${editingId ? "Account saved" : "Account added"}: ${row.name}.`);
        closeEditor();
      })
      .catch((err) => {
        if (alive.current) setErrors({ name: (err as Error).message });
      })
      .finally(() => {
        if (alive.current) setSaving(false);
      });
  };

  const setDefault = (account: SermonAudioAccount) => {
    void connectionsApi
      .setDefault(account.id)
      .then(async () => {
        await load();
        if (alive.current) show(`Default account: ${account.name}.`);
      })
      .catch((e) => show(`Could not set default: ${(e as Error).message}`));
  };

  const confirmDelete = () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    void connectionsApi
      .remove("sermonaudio", target.id)
      .then(async () => {
        await load();
        if (alive.current) show(`Account deleted: ${target.name}.`);
      })
      .catch((e) => show(`Could not delete: ${(e as Error).message}`));
  };

  return (
    <SectionCard
      title="SermonAudio Accounts"
      sub="Per-broadcaster upload accounts stored on the server. Each account pairs an API key with a broadcaster ID; the ★ default is used when a sermon does not pick one. Only the last four characters of a stored key ever display."
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

      {loading ? <p className="mt-3 text-sm text-muted">Loading accounts...</p> : null}

      {!loading && loadError ? (
        <div className="mt-3 rounded-md border border-danger p-3">
          <p className="text-sm font-semibold text-danger">Could not load accounts</p>
          <p className="mt-1 text-xs text-muted">{loadError}</p>
          <div className="mt-2">
            <Button onClick={() => { setLoading(true); void load(); }}>Retry</Button>
          </div>
        </div>
      ) : null}

      {!loading && !loadError ? (
        <>
          {accounts.length === 0 && !editorOpen ? (
            <div className="mt-3">
              <EmptyState
                title="No SermonAudio accounts configured"
                body="Add an account with its API key and broadcaster ID. Until one is picked, uploads fall back to the single-account credentials below."
              />
            </div>
          ) : null}

          <ul className="mt-3 flex flex-col gap-2" aria-label="SermonAudio accounts">
            {accounts.map((a) => (
              <AccountCard
                key={a.id}
                account={a}
                isDefault={a.id === defaultId}
                onSetDefault={() => setDefault(a)}
                onEdit={() => openEditor(draftFromAccount(a), a.id)}
                onDelete={() => setPendingDelete(a)}
              />
            ))}
          </ul>
        </>
      ) : null}

      {editorOpen ? (
        <div ref={editorRef} className="mt-4 rounded-md border border-line bg-ink p-4" role="form" aria-label="Account editor">
          <h3 className="text-sm font-semibold">{editingId ? "Edit account" : "New account"}</h3>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Broadcaster display name" htmlFor={`${uid}-name`}>
              <input
                id={`${uid}-name`}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                onBlur={() => setErrors(validateDraft(draft, editingId === null))}
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
                onBlur={() => setErrors(validateDraft(draft, editingId === null))}
                className={`${inputCls} font-mono`}
                autoComplete="off"
                placeholder="e.g. grace-sample"
              />
              {errors.broadcasterId ? <p className="mt-1 text-xs text-danger" role="alert">{errors.broadcasterId}</p> : null}
            </Field>
            <Field
              label="API key"
              htmlFor={`${uid}-key`}
              hint={
                editingId
                  ? `A key is stored${editingAccount?.maskedKey ? ` (${editingAccount.maskedKey})` : ""}. Leave blank to keep it, or enter a new value to replace it.`
                  : "Stored on the server; only the last four characters display."
              }
            >
              <div className="flex gap-2">
                <input
                  id={`${uid}-key`}
                  type={showSecret ? "text" : "password"}
                  value={draft.apiKey}
                  onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                  onBlur={() => setErrors(validateDraft(draft, editingId === null))}
                  className={`${inputCls} font-mono`}
                  autoComplete="new-password"
                  placeholder={editingId && editingAccount?.hasKey ? "stored key unchanged" : "••••••••"}
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
            <Button variant="primary" onClick={saveDraft} disabled={saving} aria-label={editingId ? "Save account" : "Add account to list"}>
              {editingId ? "Save" : "Add"}
            </Button>
            <Button onClick={closeEditor}>Cancel</Button>
          </div>
        </div>
      ) : null}

      <div className="mt-4 rounded-md border border-line p-3" aria-label="Upload routing">
        <h3 className="text-sm font-semibold">Upload routing</h3>
        <p className="mt-0.5 text-xs text-muted" role="status">
          {routingCopy(routing)}
        </p>
        {routing && !routing.configured ? (
          <p className="mt-1 text-xs text-warn">
            Uploads and metadata pushes are refused until an account is connected.
          </p>
        ) : null}
      </div>

      <p className="mt-3 text-xs text-muted">Changes save to your account immediately.</p>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete account?"
        body={pendingDelete ? `Remove "${pendingDelete.name}" (${pendingDelete.broadcasterId})? This cannot be undone.` : ""}
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onClose={() => setPendingDelete(null)}
      />
    </SectionCard>
  );
}
