import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  cloudApi,
  isLive,
  type ApiAuthorizeStart,
  type ApiCloudFile,
  type ApiCloudProvider,
  type ApiCloudRemote,
} from "../api/client";
import { Button, Chip, ConfirmDialog, Field, SectionCard, inputCls } from "./ui";

const NAME_RE = /^[A-Za-z0-9._-]{1,64}$/;
const S3_PROVIDERS = new Set(["s3"]);

const MOCK_PROVIDERS: ApiCloudProvider[] = [
  { id: "drive", label: "Google Drive", auth: "oauth" },
  { id: "dropbox", label: "Dropbox", auth: "oauth" },
  { id: "onedrive", label: "OneDrive", auth: "oauth" },
  { id: "s3", label: "S3-compatible", auth: "keys" },
  { id: "b2", label: "Backblaze B2", auth: "keys" },
];

let MOCK_REMOTES: ApiCloudRemote[] = [
  { name: "sermons-drive", provider: "drive", status: "configured" },
];

const MOCK_OAUTH_APPS: Record<string, { has_credentials: boolean }> = {
  drive: { has_credentials: true },
  dropbox: { has_credentials: true },
  onedrive: { has_credentials: true },
};

const MOCK_TREE: Record<string, ApiCloudFile[]> = {
  "": [
    { name: "sermons", path: "sermons", type: "directory", size: null },
    { name: "sample-sermon.mp3", path: "sample-sermon.mp3", type: "file", size: 42_100_000 },
  ],
  sermons: [
    { name: "2026", path: "2026", type: "directory", size: null },
    { name: "old-sermon.mp3", path: "old-sermon.mp3", type: "file", size: 38_000_000 },
  ],
  "sermons/2026": [
    { name: "september.mp3", path: "september.mp3", type: "file", size: 51_200_000 },
  ],
};

function mockAddRemote(name: string, provider: string): ApiCloudRemote {
  const remote: ApiCloudRemote = { name, provider, status: "configured" };
  MOCK_REMOTES = [...MOCK_REMOTES.filter((r) => r.name !== name), remote];
  return remote;
}

function mockRemoveRemote(name: string): void {
  MOCK_REMOTES = MOCK_REMOTES.filter((r) => r.name !== name);
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function joinPath(base: string, rel: string): string {
  return base ? `${base.replace(/\/+$/, "")}/${rel}` : rel;
}

function RemoteRow({
  remote,
  active,
  onBrowse,
  onDelete,
}: {
  remote: ApiCloudRemote;
  active: boolean;
  onBrowse: () => void;
  onDelete: () => void;
}) {
  const ping = useQuery({
    queryKey: ["cloud", "ping", remote.name],
    queryFn: () => cloudApi.browse(remote.name, ""),
    enabled: isLive,
    staleTime: Infinity,
    retry: false,
  });
  const status = !isLive
    ? "ready"
    : ping.isPending
      ? "checking"
      : ping.isError
        ? "unreachable"
        : "reachable";
  const tone =
    status === "reachable" || status === "ready" ? "ok" : status === "checking" ? "neutral" : "error";
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-md border border-line p-3">
      <button
        type="button"
        onClick={onBrowse}
        aria-pressed={active}
        aria-label={`Browse ${remote.name}`}
        className={`min-w-0 flex-1 rounded-md px-1 py-0.5 text-left transition-colors ${
          active ? "bg-raised" : "hover:bg-raised"
        }`}
      >
        <span className="block truncate text-sm font-semibold">{remote.name}</span>
        <span className="block font-mono text-xs text-muted">{remote.provider}</span>
      </button>
      <Chip tone={tone}>{status}</Chip>
      <Button variant="danger" onClick={onDelete} aria-label={`Delete ${remote.name}`}>
        Delete
      </Button>
    </li>
  );
}

function CloudBrowser({
  name,
  path,
  onPath,
  onUse,
}: {
  name: string;
  path: string;
  onPath: (p: string) => void;
  onUse: (item: ApiCloudFile) => void;
}) {
  const browse = useQuery({
    queryKey: ["cloud", "browse", name, path],
    queryFn: () =>
      isLive
        ? cloudApi.browse(name, path)
        : Promise.resolve({ path, items: MOCK_TREE[path] ?? [] }),
    staleTime: 5_000,
  });
  const items = [...(browse.data?.items ?? [])].sort((a, b) => {
    if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const segments = path ? path.split("/") : [];
  const parent = segments.slice(0, -1).join("/");

  return (
    <div className="mt-3 rounded-lg border border-line bg-ink p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">
          Browsing <span className="font-mono text-accent">{name}</span>
        </p>
        <Button onClick={() => onPath(parent)} disabled={!path}>
          Up one level
        </Button>
      </div>
      <nav aria-label="Folder path" className="mt-2 flex flex-wrap items-center gap-1 text-xs">
        <button
          type="button"
          onClick={() => onPath("")}
          className="rounded px-1 font-mono text-muted hover:text-mist"
        >
          root
        </button>
        {segments.map((seg, i) => (
          <span key={`${seg}-${i}`} className="flex items-center gap-1">
            <span aria-hidden="true" className="text-muted">
              /
            </span>
            <button
              type="button"
              onClick={() => onPath(segments.slice(0, i + 1).join("/"))}
              className="rounded px-1 font-mono text-muted hover:text-mist"
            >
              {seg}
            </button>
          </span>
        ))}
      </nav>

      {browse.isError ? (
        <p role="alert" className="mt-3 rounded-md border border-danger px-3 py-2 text-xs text-danger">
          {(browse.error as Error).message}
        </p>
      ) : browse.isPending ? (
        <p className="mt-3 text-xs text-muted" role="status">
          Loading folder…
        </p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-xs text-muted">This folder is empty.</p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-line">
          {items.map((item) => {
            const full = joinPath(path, item.path);
            return (
              <li key={full} className="flex flex-wrap items-center gap-2 py-2">
                <Chip tone="neutral">{item.type === "directory" ? "folder" : "file"}</Chip>
                {item.type === "directory" ? (
                  <button
                    type="button"
                    onClick={() => onPath(full)}
                    className="min-w-0 flex-1 truncate rounded px-1 text-left text-sm hover:text-accent"
                  >
                    {item.name}
                  </button>
                ) : (
                  <>
                    <span className="min-w-0 flex-1 truncate px-1 text-sm">{item.name}</span>
                    <span className="font-mono text-xs text-muted">{formatSize(item.size)}</span>
                    <Button variant="primary" onClick={() => onUse({ ...item, path: full })}>
                      Use this file
                    </Button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

interface KeysForm {
  name: string;
  access: string;
  secret: string;
  endpoint: string;
  region: string;
  account: string;
  key: string;
}

const EMPTY_KEYS: KeysForm = {
  name: "",
  access: "",
  secret: "",
  endpoint: "",
  region: "",
  account: "",
  key: "",
};

export function CloudMountsSection({
  show,
  isAdmin,
}: {
  show: (m: string) => void;
  isAdmin?: boolean;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [connectId, setConnectId] = useState<string | null>(null);
  const [oauthName, setOauthName] = useState("");
  const [starting, setStarting] = useState(false);
  const [paste, setPaste] = useState<ApiAuthorizeStart | null>(null);
  const [pastedUrl, setPastedUrl] = useState("");
  const [pasteError, setPasteError] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [keys, setKeys] = useState<KeysForm>(EMPTY_KEYS);
  const [browseName, setBrowseName] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ApiCloudRemote | null>(null);

  const providersQuery = useQuery({
    queryKey: ["cloud", "providers"],
    queryFn: () =>
      isLive ? cloudApi.providers() : Promise.resolve({ items: MOCK_PROVIDERS, rclone: true }),
    staleTime: 60_000,
  });
  const oauthAppsQuery = useQuery({
    queryKey: ["cloud", "oauth-apps"],
    queryFn: () =>
      isLive
        ? cloudApi.oauthApps()
        : Promise.resolve({ providers: MOCK_OAUTH_APPS }),
    staleTime: 30_000,
  });
  const remotesQuery = useQuery({
    queryKey: ["cloud", "remotes"],
    queryFn: () =>
      isLive
        ? cloudApi.list()
        : Promise.resolve({ items: MOCK_REMOTES, total: MOCK_REMOTES.length }),
    staleTime: 10_000,
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["cloud"] });

  const setOAuthAppMutation = useMutation({
    mutationFn: (body: { provider: string; client_id: string; client_secret: string }) =>
      isLive ? cloudApi.setOAuthApp(body) : Promise.resolve({ provider: body.provider, has_credentials: true }),
    onSuccess: (_data, body) => {
      show(`Saved OAuth client for ${body.provider}.`);
      setClientId("");
      setClientSecret("");
      invalidate();
    },
    onError: (e) => show(`Could not save OAuth client: ${(e as Error).message}`),
  });

  const createMutation = useMutation({
    mutationFn: (body: {
      name: string;
      provider: string;
      keys: Record<string, string>;
    }): Promise<ApiCloudRemote> =>
      isLive ? cloudApi.create(body) : Promise.resolve(mockAddRemote(body.name, body.provider)),
    onSuccess: (remote) => {
      show(`Added remote ${remote.name}.`);
      setConnectId(null);
      setKeys(EMPTY_KEYS);
      invalidate();
    },
    onError: (e) => show(`Could not add remote: ${(e as Error).message}`),
  });

  const deleteMutation = useMutation({
    mutationFn: (name: string): Promise<void> =>
      isLive ? cloudApi.remove(name) : Promise.resolve(mockRemoveRemote(name)),
    onSuccess: (_data, name) => {
      show(`Deleted ${name}.`);
      if (browseName === name) {
        setBrowseName(null);
        setPath("");
      }
      invalidate();
    },
    onError: (e) => show(`Could not delete: ${(e as Error).message}`),
  });

  useEffect(() => {
    if (searchParams.get("cloud") !== "connected") return;
    const name = searchParams.get("name");
    invalidate();
    show(name ? `Connected ${name}.` : "Cloud connection complete.");
    const next = new URLSearchParams(searchParams);
    next.delete("cloud");
    next.delete("name");
    setSearchParams(next, { replace: true });
  }, []);

  const providers = providersQuery.data?.items ?? [];
  const remotes = remotesQuery.data?.items ?? [];
  const oauthApps = oauthAppsQuery.data?.providers ?? {};
  const rcloneMissing = providersQuery.data ? providersQuery.data.rclone === false : false;
  const selected = providers.find((p) => p.id === connectId) ?? null;

  const selectProvider = (id: string) => {
    setConnectId((cur) => (cur === id ? null : id));
    setOauthName("");
    setPaste(null);
    setPastedUrl("");
    setPasteError("");
    setClientId("");
    setClientSecret("");
    setKeys(EMPTY_KEYS);
  };

  const pasteMutation = useMutation({
    mutationFn: (body: { name: string; provider: string; redirect_url: string }): Promise<ApiCloudRemote> =>
      isLive
        ? cloudApi.authorizePaste(body)
        : Promise.resolve(mockAddRemote(body.name, body.provider)),
    onSuccess: (remote) => {
      show(`Connected ${remote.name}.`);
      setPaste(null);
      setPastedUrl("");
      setPasteError("");
      setOauthName("");
      invalidate();
    },
    onError: (e) => setPasteError((e as Error).message),
  });

  const startPasteFlow = (provider: string) => {
    const name = oauthName.trim();
    if (!NAME_RE.test(name)) return;
    setStarting(true);
    setPasteError("");
    if (!isLive) {
      const mock: ApiAuthorizeStart = {
        url: "https://accounts.google.com/o/oauth2/auth?mock",
        name,
        provider,
        session_key: `${name}:${provider}`,
        instructions:
          "Approve access, then copy the full address from your browser address bar and paste it below.",
      };
      setPaste(mock);
      setStarting(false);
      return;
    }
    void cloudApi
      .authUrl(provider, name)
      .then((r) => {
        setPaste(r);
        window.open(r.url, "_blank", "noopener");
      })
      .catch((e) => show(`Could not start authorization: ${(e as Error).message}`))
      .finally(() => setStarting(false));
  };

  const submitPaste = () => {
    if (!paste || !pastedUrl.trim()) return;
    pasteMutation.mutate({
      name: paste.name,
      provider: paste.provider,
      redirect_url: pastedUrl.trim(),
    });
  };

  const startAdvancedOAuth = (provider: string) => {
    const name = oauthName.trim();
    if (!NAME_RE.test(name)) return;
    setStarting(true);
    if (!isLive) {
      mockAddRemote(name, provider);
      show(`Connected ${name}.`);
      setStarting(false);
      invalidate();
      return;
    }
    void cloudApi
      .oauthStart(provider, name)
      .then((r) => {
        window.location.assign(r.url);
      })
      .catch((e) => show(`Could not start authorization: ${(e as Error).message}`))
      .finally(() => setStarting(false));
  };

  const keysProvider = selected && S3_PROVIDERS.has(selected.id) ? "s3" : "b2";
  const keysValid =
    NAME_RE.test(keys.name.trim()) &&
    (keysProvider === "s3"
      ? keys.access.trim().length > 0 && keys.secret.trim().length > 0
      : keys.account.trim().length > 0 && keys.key.trim().length > 0);

  const submitKeys = () => {
    if (!selected || !keysValid) return;
    const payload: Record<string, string> =
      keysProvider === "s3"
        ? {
            access_key_id: keys.access.trim(),
            secret_access_key: keys.secret.trim(),
          }
        : { account: keys.account.trim(), key: keys.key.trim() };
    if (keysProvider === "s3") {
      if (keys.endpoint.trim()) payload.endpoint = keys.endpoint.trim();
      if (keys.region.trim()) payload.region = keys.region.trim();
    }
    createMutation.mutate({ name: keys.name.trim(), provider: selected.id, keys: payload });
  };

  const useFile = (item: ApiCloudFile) => {
    if (!browseName) return;
    const ref = `remote:${browseName}:${item.path}`;
    navigate(`/new?server_path=${encodeURIComponent(ref)}`);
  };

  return (
    <SectionCard
      title="Cloud Mounts"
      sub="Connect Google Drive, Dropbox, OneDrive, S3 or B2 and pick files straight from your cloud storage. Credentials stay in your own server-side config."
    >
      {rcloneMissing ? (
        <div role="alert" className="rounded-md border border-warn bg-ink px-4 py-3 text-xs text-muted">
          <p className="font-semibold text-warn">rclone is not installed on the server</p>
          <p className="mt-1">
            Cloud mounts need the <span className="font-mono">rclone</span> binary on the processing
            host. Ask an administrator to install it, then reload this page.
          </p>
        </div>
      ) : null}
      {providersQuery.isError ? (
        <p role="alert" className="text-xs text-danger">
          Could not load providers: {(providersQuery.error as Error).message}
        </p>
      ) : null}

      <h3 className="mt-4 text-sm font-semibold">Connect a provider</h3>
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((p) => (
          <div
            key={p.id}
            className="flex min-h-[44px] items-center justify-between gap-2 rounded-md border border-line p-3"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{p.label}</p>
              <div className="mt-1">
                <Chip tone={p.auth === "oauth" ? "info" : "accent"}>
                  {p.auth === "oauth" ? "OAuth" : "keys"}
                </Chip>
              </div>
            </div>
            <Button
              variant={connectId === p.id ? "primary" : "secondary"}
              onClick={() => selectProvider(p.id)}
              aria-expanded={connectId === p.id}
            >
              {p.auth === "oauth" ? "Connect" : "Add keys"}
            </Button>
          </div>
        ))}
      </div>

      {selected ? (
        <div className="mt-3 rounded-lg border border-line bg-ink p-3">
          <p className="text-sm font-semibold">
            {selected.label}{" "}
            <span className="font-mono text-xs text-muted">({selected.auth === "oauth" ? "OAuth" : "access keys"})</span>
          </p>
          {selected.auth === "oauth" ? (
            <div className="mt-2 flex flex-col gap-3">
              <Field
                label="Remote name"
                htmlFor="cloud-oauth-name"
                hint="1-64 chars: letters, digits, dot, dash, underscore."
              >
                <input
                  id="cloud-oauth-name"
                  value={oauthName}
                  onChange={(e) => setOauthName(e.target.value)}
                  className={`${inputCls} font-mono`}
                  autoComplete="off"
                  disabled={starting}
                />
              </Field>
              <div>
                <Button
                  variant="primary"
                  onClick={() => startPasteFlow(selected.id)}
                  disabled={!NAME_RE.test(oauthName.trim()) || starting}
                >
                  {starting ? "Opening…" : "Connect"}
                </Button>
                <p className="mt-1 text-xs text-muted">
                  No developer console setup needed. Approve access, then paste the redirect URL
                  back here.
                </p>
              </div>

              {paste ? (
                <div className="rounded-lg border border-line p-3">
                  <p className="text-xs text-muted">{paste.instructions}</p>
                  <p className="mt-2">
                    <a
                      href={paste.url}
                      target="_blank"
                      rel="noreferrer"
                      className="break-all text-xs text-accent underline"
                    >
                      Open the consent page
                    </a>
                  </p>
                  <Field
                    label="Pasted URL"
                    htmlFor="cloud-paste-url"
                    hint="Full address from the browser bar, or just the part after the question mark."
                  >
                    <input
                      id="cloud-paste-url"
                      value={pastedUrl}
                      onChange={(e) => {
                        setPastedUrl(e.target.value);
                        setPasteError("");
                      }}
                      className={`${inputCls} font-mono`}
                      autoComplete="off"
                      placeholder="http://127.0.0.1:53682/?code=..."
                    />
                  </Field>
                  <div className="mt-2">
                    <Button
                      variant="primary"
                      onClick={submitPaste}
                      disabled={!pastedUrl.trim() || pasteMutation.isPending}
                    >
                      {pasteMutation.isPending ? "Finishing…" : "Finish connection"}
                    </Button>
                  </div>
                  {pasteError ? (
                    <p role="alert" className="mt-2 text-xs text-danger">
                      {pasteError}
                    </p>
                  ) : null}
                </div>
              ) : null}

              {isAdmin ? (
                <details className="rounded-md border border-line p-3">
                  <summary className="cursor-pointer text-xs font-semibold text-muted">
                    Advanced: use your own OAuth client
                  </summary>
                  <div className="mt-3 flex flex-col gap-3">
                    {oauthApps[selected.id]?.has_credentials ? (
                      <div>
                        <Button
                          variant="secondary"
                          onClick={() => startAdvancedOAuth(selected.id)}
                          disabled={!NAME_RE.test(oauthName.trim()) || starting}
                        >
                          {starting ? "Redirecting…" : "Connect with OAuth"}
                        </Button>
                        <p className="mt-1 text-xs text-muted">
                          You will be sent to {selected.label} to approve access, then returned here.
                        </p>
                      </div>
                    ) : (
                      <>
                        <p className="text-xs text-muted">
                          Create an OAuth client in the {selected.label} console and paste its
                          credentials here. Authorized redirect URI:{" "}
                          <span className="break-all font-mono">
                            {window.location.origin}/api/cloud/oauth/callback
                          </span>
                        </p>
                        <Field label="Client ID" htmlFor="cloud-oauth-client-id">
                          <input
                            id="cloud-oauth-client-id"
                            value={clientId}
                            onChange={(e) => setClientId(e.target.value)}
                            className={`${inputCls} font-mono`}
                            autoComplete="off"
                          />
                        </Field>
                        <Field
                          label="Client secret"
                          htmlFor="cloud-oauth-client-secret"
                          hint="Stored server-side with 0600 permissions. Never returned by the API."
                        >
                          <input
                            id="cloud-oauth-client-secret"
                            type="password"
                            value={clientSecret}
                            onChange={(e) => setClientSecret(e.target.value)}
                            className={`${inputCls} font-mono`}
                            autoComplete="off"
                            spellCheck={false}
                          />
                        </Field>
                        <div>
                          <Button
                            variant="primary"
                            onClick={() =>
                              setOAuthAppMutation.mutate({
                                provider: selected.id,
                                client_id: clientId.trim(),
                                client_secret: clientSecret.trim(),
                              })
                            }
                            disabled={
                              !clientId.trim() ||
                              !clientSecret.trim() ||
                              setOAuthAppMutation.isPending
                            }
                          >
                            {setOAuthAppMutation.isPending ? "Saving…" : "Save OAuth client"}
                          </Button>
                        </div>
                      </>
                    )}
                  </div>
                </details>
              ) : null}
            </div>
          ) : (
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Remote name" htmlFor="cloud-keys-name">
                <input
                  id="cloud-keys-name"
                  value={keys.name}
                  onChange={(e) => setKeys((k) => ({ ...k, name: e.target.value }))}
                  className={`${inputCls} font-mono`}
                  autoComplete="off"
                />
              </Field>
              {keysProvider === "s3" ? (
                <>
                  <Field label="Access key ID" htmlFor="cloud-keys-access">
                    <input
                      id="cloud-keys-access"
                      type="password"
                      value={keys.access}
                      onChange={(e) => setKeys((k) => ({ ...k, access: e.target.value }))}
                      className={`${inputCls} font-mono`}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </Field>
                  <Field label="Secret access key" htmlFor="cloud-keys-secret">
                    <input
                      id="cloud-keys-secret"
                      type="password"
                      value={keys.secret}
                      onChange={(e) => setKeys((k) => ({ ...k, secret: e.target.value }))}
                      className={`${inputCls} font-mono`}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </Field>
                  <Field label="Endpoint (optional)" htmlFor="cloud-keys-endpoint" hint="e.g. s3.example.com">
                    <input
                      id="cloud-keys-endpoint"
                      value={keys.endpoint}
                      onChange={(e) => setKeys((k) => ({ ...k, endpoint: e.target.value }))}
                      className={`${inputCls} font-mono`}
                      autoComplete="off"
                    />
                  </Field>
                  <Field label="Region (optional)" htmlFor="cloud-keys-region" hint="e.g. us-east-1">
                    <input
                      id="cloud-keys-region"
                      value={keys.region}
                      onChange={(e) => setKeys((k) => ({ ...k, region: e.target.value }))}
                      className={`${inputCls} font-mono`}
                      autoComplete="off"
                    />
                  </Field>
                </>
              ) : (
                <>
                  <Field label="Account ID" htmlFor="cloud-keys-account">
                    <input
                      id="cloud-keys-account"
                      type="password"
                      value={keys.account}
                      onChange={(e) => setKeys((k) => ({ ...k, account: e.target.value }))}
                      className={`${inputCls} font-mono`}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </Field>
                  <Field label="Application key" htmlFor="cloud-keys-key">
                    <input
                      id="cloud-keys-key"
                      type="password"
                      value={keys.key}
                      onChange={(e) => setKeys((k) => ({ ...k, key: e.target.value }))}
                      className={`${inputCls} font-mono`}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </Field>
                </>
              )}
              <div className="sm:col-span-2">
                <Button variant="primary" onClick={submitKeys} disabled={!keysValid || createMutation.isPending}>
                  {createMutation.isPending ? "Adding…" : "Add remote"}
                </Button>
                <p className="mt-1 text-xs text-muted">
                  The server validates the credentials by listing the remote, and rolls back on failure.
                </p>
              </div>
            </div>
          )}
        </div>
      ) : null}

      <h3 className="mt-5 text-sm font-semibold">Connected remotes</h3>
      {remotesQuery.isError ? (
        <p role="alert" className="mt-2 text-xs text-danger">
          Could not load remotes: {(remotesQuery.error as Error).message}
        </p>
      ) : null}
      <ul className="mt-2 flex flex-col gap-2">
        {remotes.map((r) => (
          <RemoteRow
            key={r.name}
            remote={r}
            active={browseName === r.name}
            onBrowse={() => {
              setBrowseName((cur) => (cur === r.name ? null : r.name));
              setPath("");
            }}
            onDelete={() => setPendingDelete(r)}
          />
        ))}
      </ul>
      {!remotesQuery.isError && remotes.length === 0 ? (
        <p className="mt-2 text-xs text-muted">No cloud remotes yet. Connect a provider above.</p>
      ) : null}

      {browseName ? (
        <CloudBrowser name={browseName} path={path} onPath={setPath} onUse={useFile} />
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete remote"
        body={
          pendingDelete
            ? `Remove "${pendingDelete.name}" and its stored credentials? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.name);
        }}
        onClose={() => setPendingDelete(null)}
      />
    </SectionCard>
  );
}
