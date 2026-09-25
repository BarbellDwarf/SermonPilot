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
  description_needs_review: boolean;
  files: ApiSermonFile[];
  transcript_available: boolean;
  transcript_length: number;
  sermonaudio_id: string | null;
  upload_date: string | null;
  upload_status: string | null;
  bible_text: string | null;
  scripture_reference: string | null;
}

export interface SermonDetailsPatch {
  title?: string;
  speaker?: string;
  series_title?: string;
  recorded_date?: string;
  description?: string;
}

export interface ApiTranscript {
  id: string;
  transcript: string;
  truncated: boolean;
  total_length: number;
}

export interface ApiRemoveSegment {
  start_sec: number;
  end_sec: number;
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
  remove_segments: ApiRemoveSegment[];
  offset_sec: number;
  detection_status: string;
  reasoning: string;
  notes: string;
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

export interface ApiErrorDetail {
  code?: string;
  message?: string;
  job_id?: string;
  can_regenerate?: boolean;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  jobId?: string;
  canRegenerate: boolean;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    const parsed = (detail ?? {}) as ApiErrorDetail;
    if (typeof parsed.code === "string") this.code = parsed.code;
    if (typeof parsed.job_id === "string") this.jobId = parsed.job_id;
    this.canRegenerate = parsed.can_regenerate === true;
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

export interface ApiTrashRecord {
  source: string;
  destination: string;
  mode: "local" | "remote" | "remote-kept" | string;
  reason: string;
  deleted_at: string;
  sermon_id?: string | null;
  job_id?: string | null;
  stage?: string | null;
  moved: boolean;
  recoverable: boolean;
}

export interface ApiDeleteSermonResult {
  deleted: boolean;
  id: string;
  recoverable?: boolean;
  trash?: ApiTrashRecord[];
}

export const api = {
  sermons: (params?: { search?: string; sort?: string; limit?: number; offset?: number }) =>
    authed<ApiSermonList>("/api/sermons", params),
  sermon: (id: string) => authed<ApiSermonDetail>(`/api/sermons/${encodeURIComponent(id)}`),
  transcript: (id: string) => authed<ApiTranscript>(`/api/sermons/${encodeURIComponent(id)}/transcript`),
  deleteSermon: (id: string) => send<ApiDeleteSermonResult>(`/api/sermons/${encodeURIComponent(id)}`, "DELETE"),
  updateSermon: (id: string, patch: SermonDetailsPatch) =>
    send<ApiSermonDetail>(`/api/sermons/${encodeURIComponent(id)}`, "PATCH", patch),
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

export interface ApiEffectiveConnection {
  configured: boolean;
  source: string;
  account_id: string | null;
  account_name: string | null;
  broadcaster_id: string;
  masked_key: string;
  message: string;
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await authFetch(path, {
    method,
    headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    let message = `${method} ${path} failed with ${res.status}`;
    let detail: unknown;
    try {
      const parsed = (await res.json()) as { detail?: unknown };
      detail = parsed.detail;
      if (typeof parsed.detail === "string") {
        message = parsed.detail;
      } else if (
        parsed.detail &&
        typeof parsed.detail === "object" &&
        typeof (parsed.detail as ApiErrorDetail).message === "string"
      ) {
        message = (parsed.detail as ApiErrorDetail).message as string;
      }
    } catch {
    }
    throw new ApiError(message, res.status, detail);
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
  effective: () =>
    send<ApiEffectiveConnection>("/api/me/sermonaudio-connection", "GET"),
};

export const settingsApi = {
  get: (key: string) => send<{ key: string; value: unknown }>(`/api/me/settings/${encodeURIComponent(key)}`, "GET"),
  put: (key: string, value: unknown) =>
    send<{ key: string; value: unknown }>(`/api/me/settings/${encodeURIComponent(key)}`, "PUT", { value }),
};

export type LlmRole = "primary" | "fallback" | "validator";
export type LlmRouteRole = "metadata" | "validation" | "transcription_assist" | "fallback";

export interface ApiLlmSlot {
  role: LlmRole;
  enabled: boolean;
  provider: string;
  preset: string;
  model: string;
  endpoint: string;
  numCtx: string;
  maxTokens: string;
  temperature: string;
  hasKey: boolean;
  maskedKey: string;
}

export interface ApiLlmRouting {
  metadata: LlmRole;
  validation: LlmRole;
  transcription_assist: LlmRole;
  fallback: LlmRole;
}

export interface ApiLlmConfig {
  primary: ApiLlmSlot;
  fallback: ApiLlmSlot;
  validator: ApiLlmSlot;
  routing: ApiLlmRouting;
}

export interface ApiLlmTestResult {
  ok: boolean;
  latency_ms: number;
  model_echo: string | null;
  error: string | null;
}

export interface ApiLlmSlotUpdate {
  enabled?: boolean;
  provider?: string;
  model?: string;
  endpoint?: string;
  numCtx?: string;
  maxTokens?: string;
  temperature?: string;
  apiKey?: string;
}

export interface ApiLlmConfigUpdate {
  primary?: ApiLlmSlotUpdate;
  fallback?: ApiLlmSlotUpdate;
  validator?: ApiLlmSlotUpdate;
  routing?: Partial<Record<LlmRouteRole, LlmRole>>;
}

export const llmConfigApi = {
  get: () => send<ApiLlmConfig>("/api/llm/config", "GET"),
  put: (body: ApiLlmConfigUpdate) => send<ApiLlmConfig>("/api/llm/config", "PUT", body),
  test: (role: LlmRole, timeoutSeconds?: number) =>
    send<ApiLlmTestResult>("/api/llm/test-connection", "POST", {
      role,
      ...(timeoutSeconds === undefined ? {} : { timeout_seconds: timeoutSeconds }),
    }),
};

export interface ApiConfigField {
  source: string;
  secret: boolean;
  value?: unknown;
  has_value?: boolean;
  masked?: string;
}

export interface ApiConfigSection {
  section: string;
  fields: Record<string, ApiConfigField>;
}

export const configApi = {
  section: (name: string) => send<ApiConfigSection>(`/api/config/sections/${name}`, "GET"),
  save: (name: string, values: Record<string, unknown>) =>
    send<ApiConfigSection>(`/api/config/sections/${name}`, "PUT", { values }),
  sources: () => send<{ sources: Record<string, string> }>("/api/config/sources", "GET"),
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
  applyPlan: (id: string, body: { start: number; end: number; audio_offset: number; render_only: boolean; re_detect?: boolean; enhance_audio?: boolean; remove_segments?: ApiRemoveSegment[] }) =>
    send<{ job_id: string; status: string }>(`/api/sermons/${encodeURIComponent(id)}/plan/apply`, "POST", body),
  uploadOnly: (id: string, body?: { confirm_missing_description?: boolean }) =>
    send<{ job_id: string; status: string; render?: { name: string; size: number; size_human: string } }>(
      `/api/sermons/${encodeURIComponent(id)}/plan/apply`,
      "POST",
      { upload_only: true, confirm_missing_description: body?.confirm_missing_description ?? false },
    ),
  refinePlan: (id: string, notes: string) =>
    send<{ job_id: string; status: string }>(`/api/sermons/${encodeURIComponent(id)}/plan/refine`, "POST", { notes }),
  reDetectPlan: (id: string) =>
    send<{ job_id: string; status: string }>(`/api/sermons/${encodeURIComponent(id)}/plan/re-detect`, "POST"),
  uploadNow: (id: string) =>
    send<{ job_id: string; status: string }>(`/api/sermons/${encodeURIComponent(id)}/upload`, "POST"),
  regenerateDescription: (id: string) =>
    send<{ job_id: string; status: string }>(`/api/sermons/${encodeURIComponent(id)}/description/regenerate`, "POST"),
  pushMetadata: (id: string, fullPush = true) =>
    send<{ job_id: string; status: string; full_push: boolean }>(
      `/api/sermons/${encodeURIComponent(id)}/metadata/push`,
      "POST",
      { full_push: fullPush },
    ),
  cancelJob: (id: string) => send<{ cancelled: boolean; job_id: string }>(`/api/jobs/${encodeURIComponent(id)}/cancel`, "POST"),
};

export interface ApiPromptTemplate {
  enabled: boolean;
  system: string;
  user: string;
}

export interface ApiPromptsConfig {
  templates: Record<string, ApiPromptTemplate>;
  defaults: Record<string, ApiPromptTemplate>;
}

export interface ApiPromptsUpdate {
  templates: Record<string, Partial<ApiPromptTemplate>>;
}

export const promptsApi = {
  get: () => send<ApiPromptsConfig>("/api/prompts/config", "GET"),
  put: (body: ApiPromptsUpdate) => send<ApiPromptsConfig>("/api/prompts/config", "PUT", body),
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
  modified?: string | null;
  mime?: string;
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

export interface ApiFacet {
  name: string;
  count: number;
}

export interface ApiFacets {
  speakers: ApiFacet[];
  series: ApiFacet[];
  event_types: ApiFacet[];
}

export const libraryApi = {
  facets: () => send<ApiFacets>("/api/library/facets", "GET"),
};

export interface ApiMediaItem {
  kind: string;
  label: string;
  available: boolean;
  content_type: string | null;
  size: number | null;
  start_sec?: number;
  end_sec?: number;
}

export interface ApiSermonMedia {
  id: string;
  items: ApiMediaItem[];
  primary: string | null;
  audio: string | null;
}

export function mediaStreamUrl(sermonId: string, kind: string): string {
  const base = `${BASE}/api/media/sermons/${encodeURIComponent(sermonId)}/${encodeURIComponent(kind)}`;
  if (!isLive) return base;
  const token = getToken();
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

export const mediaApi = {
  list: (id: string) => send<ApiSermonMedia>(`/api/media/sermons/${encodeURIComponent(id)}`, "GET"),
  url: mediaStreamUrl,
  fetchJson: async <T,>(id: string, kind: string): Promise<T> => {
    const res = await authFetch(
      `/api/media/sermons/${encodeURIComponent(id)}/${encodeURIComponent(kind)}`,
    );
    if (!res.ok) throw new Error(`media ${kind} failed with ${res.status}`);
    return (await res.json()) as T;
  },
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
  modified?: string | null;
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
