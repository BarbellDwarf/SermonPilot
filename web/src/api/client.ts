export type ApiMode = "mock" | "live";

export const API_MODE: ApiMode =
  import.meta.env.VITE_API_MODE === "live" ? "live" : "mock";

export const isLive = API_MODE === "live";

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export interface ApiSermonListItem {
  id: string;
  title: string;
  speaker: string;
  date: string;
  duration: string;
  series: string;
  status: string;
}

export interface ApiSermonList {
  items: ApiSermonListItem[];
  total: number;
}

export interface ApiSermonFile {
  file_type: string;
  file_path: string;
  file_size: number | null;
}

export interface ApiSermonDetail extends ApiSermonListItem {
  duration_seconds: number | null;
  description: string | null;
  files: ApiSermonFile[];
  transcript_available: boolean;
  transcript_length: number;
}

export interface ApiTranscript {
  id: string;
  transcript: string;
  truncated: boolean;
  total_length: number;
}

export interface ApiEditPlan {
  sermon_id: string;
  status: string;
  revision: number;
  revisions_total: number;
  confidence: number;
  qa_judgment: string;
  evidence: string;
  start_sec: number | null;
  end_sec: number | null;
  offset_sec: number;
}

export interface ApiSermonPlan {
  plan: ApiEditPlan | null;
  history: ApiEditPlan[];
}

export interface ApiJob {
  id: string;
  type: string;
  title: string;
  description: string | null;
  status: string;
  created_at: string | null;
  completed_at: string | null;
  duration: string;
  error: string | null;
}

export interface ApiJobList {
  items: ApiJob[];
  total: number;
}

export interface ApiJobDetail extends ApiJob {
  logs: string[];
  parameters: Record<string, unknown>;
  result: Record<string, unknown> | null;
}

export interface ApiServiceState {
  status: string;
  message: string;
  details: string;
  timestamp?: string;
}

export interface ApiStatus {
  status: Record<string, ApiServiceState>;
  checked_at: string;
}

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  role: string;
  is_active: boolean;
}

export interface LoginResult {
  token: string;
  user: AuthUser;
}

export const TOKEN_KEY = "sp_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
  }
}

export class AuthError extends Error {
  needsBootstrap: boolean;
  constructor(message: string, needsBootstrap: boolean) {
    super(message);
    this.needsBootstrap = needsBootstrap;
  }
}

function authHeaders(extra?: HeadersInit): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (extra) {
    for (const [k, v] of new Headers(extra).entries()) headers[k] = v;
  }
  if (isLive) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function parseNeedsBootstrap(res: Response): Promise<boolean> {
  try {
    const body = (await res.clone().json()) as {
      detail?: string | { needs_bootstrap?: boolean };
    };
    if (body && typeof body.detail === "object") return body.detail.needs_bootstrap === true;
  } catch {
  }
  return false;
}

export async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: authHeaders(init?.headers),
  });
  if (res.status === 401 && isLive) {
    const needsBootstrap = await parseNeedsBootstrap(res);
    clearToken();
    throw new AuthError("authentication required", needsBootstrap);
  }
  return res;
}

async function authed<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const qs = params
    ? `?${new URLSearchParams(
        Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)])),
      ).toString()}`
    : "";
  const res = await authFetch(`${path}${qs}`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new Error(`GET ${path} failed with ${res.status}`);
  }
  return (await res.json()) as T;
}

const MOCK_USER: AuthUser = {
  id: "mock-admin",
  username: "admin",
  display_name: "Admin",
  role: "admin",
  is_active: true,
};

export const auth = {
  me: async (): Promise<AuthUser> => {
    if (!isLive) return MOCK_USER;
    const res = await authFetch("/api/auth/me");
    if (!res.ok) throw new Error(`GET /api/auth/me failed with ${res.status}`);
    return (await res.json()) as AuthUser;
  },
  login: async (username: string, password: string): Promise<LoginResult> => {
    if (!isLive) return { token: "mock-token", user: MOCK_USER };
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (res.status === 401) throw new AuthError("Invalid username or password.", false);
    if (!res.ok) throw new Error(`Login failed with ${res.status}`);
    const data = (await res.json()) as LoginResult;
    setToken(data.token);
    return data;
  },
  bootstrap: async (): Promise<AuthUser> => {
    const res = await fetch(`${BASE}/api/auth/bootstrap`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`Bootstrap failed with ${res.status}`);
    return (await res.json()) as AuthUser;
  },
  logout: async (): Promise<void> => {
    if (isLive) {
      try {
        await authFetch("/api/auth/logout", { method: "POST" });
      } catch {
      }
    }
    clearToken();
  },
};

export const api = {
  sermons: (params?: { search?: string; sort?: string; limit?: number; offset?: number }) =>
    authed<ApiSermonList>("/api/sermons", params),
  sermon: (id: string) => authed<ApiSermonDetail>(`/api/sermons/${encodeURIComponent(id)}`),
  transcript: (id: string) => authed<ApiTranscript>(`/api/sermons/${encodeURIComponent(id)}/transcript`),
  deleteSermon: (id: string) => send<{ deleted: boolean; id: string }>(`/api/sermons/${encodeURIComponent(id)}`, "DELETE"),
  plan: (id: string) => authed<ApiSermonPlan>(`/api/sermons/${encodeURIComponent(id)}/plan`),
  jobs: (params?: { status?: string; limit?: number }) => authed<ApiJobList>("/api/jobs", params),
  job: (id: string) => authed<ApiJobDetail>(`/api/jobs/${encodeURIComponent(id)}`),
  status: () => authed<ApiStatus>("/api/status"),
};

export interface ApiConnection {
  id: string;
  name: string;
  preset?: string;
  provider?: string;
  model?: string;
  endpoint?: string;
  numCtx?: string;
  maxTokens?: string;
  temperature?: string;
  role?: string;
  broadcasterId?: string;
  notes?: string;
  has_key: boolean;
  masked_key: string;
}

export interface ApiConnectionList {
  items: ApiConnection[];
  total: number;
  default_id: string | null;
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await authFetch(path, {
    method,
    headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    let detail = `${method} ${path} failed with ${res.status}`;
    try {
      const parsed = (await res.json()) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const connectionsApi = {
  list: (kind: "llm" | "sermonaudio") =>
    send<ApiConnectionList>(`/api/me/connections/${kind}`, "GET"),
  create: (kind: "llm" | "sermonaudio", body: Record<string, unknown>) =>
    send<ApiConnection>(`/api/me/connections/${kind}`, "POST", body),
  update: (kind: "llm" | "sermonaudio", id: string, body: Record<string, unknown>) =>
    send<ApiConnection>(`/api/me/connections/${kind}/${encodeURIComponent(id)}`, "PUT", body),
  remove: (kind: "llm" | "sermonaudio", id: string) =>
    send<void>(`/api/me/connections/${kind}/${encodeURIComponent(id)}`, "DELETE"),
  setDefault: (id: string | null) =>
    send<{ default_id: string | null }>("/api/me/connections/sermonaudio/default", "PUT", { id }),
};

export const settingsApi = {
  get: (key: string) => send<{ key: string; value: unknown }>(`/api/me/settings/${encodeURIComponent(key)}`, "GET"),
  put: (key: string, value: unknown) =>
    send<{ key: string; value: unknown }>(`/api/me/settings/${encodeURIComponent(key)}`, "PUT", { value }),
};

export const meApi = {
  patch: (body: { display_name?: string; email?: string }) =>
    send<AuthUser>("/api/me", "PATCH", body),
};

export interface UserBackup {
  app: string;
  backup_kind: string;
  account: { id: string; username: string; display_name: string; role: string } | null;
  settings: Record<string, unknown>;
}

export const backupApi = {
  download: () => send<UserBackup>("/api/me/backup", "GET"),
  restore: (backup: { settings: Record<string, unknown> }) =>
    send<{ restored: number }>("/api/me/restore", "POST", backup),
};

export const writeApi = {
  applyPlan: (id: string, body: { start: number; end: number; audio_offset: number; render_only: boolean; re_detect?: boolean }) =>
    send<{ job_id: string; status: string }>(`/api/sermons/${encodeURIComponent(id)}/plan/apply`, "POST", body),
  uploadNow: (id: string) =>
    send<{ job_id: string; status: string }>(`/api/sermons/${encodeURIComponent(id)}/upload`, "POST"),
  cancelJob: (id: string) => send<{ cancelled: boolean; job_id: string }>(`/api/jobs/${encodeURIComponent(id)}/cancel`, "POST"),
};

export interface SermonUploadResult {
  id: string;
  job_id: string;
  status: string;
  filename: string;
}

export const uploadApi = {
  upload: async (form: FormData): Promise<SermonUploadResult> => {
    const res = await authFetch("/api/sermons/upload", { method: "POST", body: form });
    if (!res.ok) {
      let detail = `Upload failed with ${res.status}`;
      try {
        const parsed = (await res.json()) as { detail?: unknown };
        if (typeof parsed.detail === "string") detail = parsed.detail;
      } catch {
      }
      throw new Error(detail);
    }
    return (await res.json()) as SermonUploadResult;
  },
};

export interface ServerPathStat {
  exists: boolean;
  is_file?: boolean;
  size: number | null;
  size_human: string;
  ext: string;
  kind: string;
  name: string;
}

export interface ServerPathResult {
  id: string;
  job_id: string;
  status: string;
  filename: string;
  size: number;
  size_human: string;
  ext: string;
  kind: string;
}

export interface ServerPathPayload {
  container_path: string;
  title: string;
  speaker: string;
  recorded_date: string;
  event_type: string;
  series_title?: string;
  bible_text?: string;
  scripture?: string;
  skip_audio?: boolean;
  skip_transcription?: boolean;
  skip_ai_generation?: boolean;
  dry_run?: boolean;
  auto_edit_enabled?: boolean;
  auto_edit_mode?: string | null;
  logo_path?: string;
  fade_to_black?: boolean;
}

export const serverPathApi = {
  stat: (path: string) =>
    authed<ServerPathStat>("/api/sermons/server-path/stat", { path }),
  create: (body: ServerPathPayload) =>
    send<ServerPathResult>("/api/sermons/server-path", "POST", body),
};

export interface ApiCloudProvider {
  id: string;
  label: string;
  auth: "oauth" | "keys";
}

export interface ApiCloudRemote {
  name: string;
  provider: string;
  status: string;
  team_drive?: string;
}

export interface ApiSharedDrive {
  id: string;
  name: string;
}

export interface ApiCloudFile {
  name: string;
  path: string;
  type: "directory" | "file";
  size: number | null;
}

export interface ApiOAuthAppStatus {
  providers: Record<string, { has_credentials: boolean }>;
}

export interface ApiAuthorizeStart {
  url: string;
  name: string;
  provider: string;
  session_key: string;
  instructions: string;
}

export const cloudApi = {
  providers: () =>
    send<{ items: ApiCloudProvider[]; rclone: boolean }>("/api/cloud/providers", "GET"),
  oauthApps: () => send<ApiOAuthAppStatus>("/api/cloud/oauth-app", "GET"),
  setOAuthApp: (body: { provider: string; client_id: string; client_secret: string }) =>
    send<{ provider: string; has_credentials: boolean }>("/api/cloud/oauth-app", "PUT", body),
  authUrl: (provider: string, name: string) =>
    send<ApiAuthorizeStart>(
      `/api/cloud/auth-url?provider=${encodeURIComponent(provider)}&name=${encodeURIComponent(name)}`,
      "GET",
    ),
  authorizePaste: (body: { name: string; provider: string; redirect_url: string }) =>
    send<ApiCloudRemote>("/api/cloud/authorize/paste", "POST", body),
  oauthStart: (provider: string, name: string) =>
    send<{ url: string; name: string; provider: string }>(
      `/api/cloud/oauth/start?provider=${encodeURIComponent(provider)}&name=${encodeURIComponent(name)}`,
      "GET",
    ),
  list: () => send<{ items: ApiCloudRemote[]; total: number }>("/api/cloud/remotes", "GET"),
  create: (body: { name: string; provider: string; keys: Record<string, string> }) =>
    send<ApiCloudRemote>("/api/cloud/remotes", "POST", body),
  remove: (name: string) =>
    send<void>(`/api/cloud/remotes/${encodeURIComponent(name)}`, "DELETE"),
  browse: (name: string, path: string, driveId?: string) =>
    send<{ path: string; items: ApiCloudFile[] }>(
      `/api/cloud/remotes/${encodeURIComponent(name)}/browse${
        driveId ? `?drive_id=${encodeURIComponent(driveId)}` : ""
      }`,
      "POST",
      { path },
    ),
  sharedDrives: (name: string) =>
    send<{ items: ApiSharedDrive[] }>(
      `/api/cloud/remotes/${encodeURIComponent(name)}/shared-drives`,
      "GET",
    ),
  attachSharedDrive: (name: string, drive_id: string) =>
    send<{ ok: boolean; name: string; team_drive: string }>(
      `/api/cloud/remotes/${encodeURIComponent(name)}/attach-shared-drive`,
      "POST",
      { drive_id },
    ),
  detachSharedDrive: (name: string) =>
    send<{ ok: boolean; name: string; team_drive: string }>(
      `/api/cloud/remotes/${encodeURIComponent(name)}/detach-shared-drive`,
      "POST",
    ),
};

export interface BrandingItem {
  name: string;
  path: string;
}

export const brandingApi = {
  list: () => send<{ items: BrandingItem[] }>("/api/branding", "GET"),
  upload: async (file: File): Promise<{ path: string; filename: string }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await authFetch("/api/branding", { method: "POST", body: form });
    if (!res.ok) {
      let detail = `Branding upload failed with ${res.status}`;
      try {
        const parsed = (await res.json()) as { detail?: unknown };
        if (typeof parsed.detail === "string") detail = parsed.detail;
      } catch {
      }
      throw new Error(detail);
    }
    return (await res.json()) as { path: string; filename: string };
  },
};
export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  role: string;
  is_active: boolean;
  email?: string | null;
}

export const adminApi = {
  listUsers: () => send<{ users: AdminUser[] }>("/api/admin/users", "GET"),
  createUser: (body: { username: string; display_name: string; password: string; role: string }) =>
    send<AdminUser>("/api/admin/users", "POST", body),
  patchUser: (id: string, body: { is_active?: boolean; role?: string; new_password?: string }) =>
    send<AdminUser>(`/api/admin/users/${encodeURIComponent(id)}`, "PATCH", body),
};

export interface MeFile {
  name: string;
  type: string;
  size: number | null;
}

export interface ApiFileEntry {
  name: string;
  path: string;
  type: "file" | "dir";
  size: number | null;
}

export interface ApiExploreResult {
  path: string;
  parent: string | null;
  root: string;
  roots: { name: string; path: string }[];
  items: ApiFileEntry[];
}

export interface ApiOutputDir {
  output_dir: string;
  source: "user" | "default";
}

export const filesApi = {
  list: () => send<{ items: MeFile[]; root: string }>("/api/me/files", "GET"),
  downloadUrl: (path: string) =>
    `${BASE}/api/me/files/download?path=${encodeURIComponent(path)}`,
  explore: (path: string) => authed<ApiExploreResult>("/api/files/explore", { path }),
};

export const outputDirApi = {
  get: () => send<ApiOutputDir>("/api/me/output-dir", "GET"),
  put: (output_dir: string) =>
    send<ApiOutputDir>("/api/me/output-dir", "PUT", { output_dir }),
};

export const metaApi = {
  retirement: async (): Promise<{ streamlit_ready: boolean }> => {
    if (!isLive) return { streamlit_ready: false };
    const res = await fetch(`${BASE}/api/meta/retirement`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`GET /api/meta/retirement failed with ${res.status}`);
    return (await res.json()) as { streamlit_ready: boolean };
  },
};
