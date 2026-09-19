"""Per-user cloud remotes backed by isolated rclone config files (INC1 #296).

Each user gets their own config at ``SERMONPILOT_RCLONE_DIR/<user_id>/config``
(rclone INI format, 0600). Secrets stay server-side: listing returns name and
provider only. Every endpoint resolves the caller's own config path, so one
user can never reach another user's remotes.

OAuth providers run headless through ``rclone authorize <provider>
--auth-no-open-browser``: ``GET /auth-url`` starts the subprocess and returns
a callback URL on the request's own origin under ``/rclone-auth/<session>/``,
the user completes consent, and ``POST /authorize`` reads the token JSON
rclone emits on stdout and stores it. The proxy route forwards that path to
the per-session loopback port rclone bound, so the consent page is reachable
from any browser on the LAN, not just the server's loopback.
Key providers (S3, B2) take credentials directly on create. rclone is resolved
at runtime with ``shutil.which``; without it these endpoints return 503.
"""

from __future__ import annotations

import base64
import configparser
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from server.api.routers.auth import admin_only, require_user

router = APIRouter(prefix="/api/cloud", tags=["cloud"])
proxy_router = APIRouter(tags=["cloud"])

PROVIDERS = [
    {"id": "drive", "label": "Google Drive", "auth": "oauth"},
    {"id": "dropbox", "label": "Dropbox", "auth": "oauth"},
    {"id": "onedrive", "label": "OneDrive", "auth": "oauth"},
    {"id": "s3", "label": "S3-compatible", "auth": "keys"},
    {"id": "b2", "label": "Backblaze B2", "auth": "keys"},
]

_OAUTH_PROVIDERS = frozenset({"drive", "dropbox", "onedrive"})
_PROVIDER_IDS = frozenset(p["id"] for p in PROVIDERS)

REMOTE_PREFIX = "remote:"

DEFAULT_RCLONE_DIR = "/data/rclone"
_AUTHORIZE_TTL = 900.0
_OAUTH_STATE_TTL = 900.0
_PASTE_STATE_GRACE = 600.0
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

PASTE_INSTRUCTIONS = (
    "Approve access on the consent page. Your browser will then try to open a "
    "local page that will not load - that is expected. Copy the FULL address "
    "from your browser address bar (it contains code=) and paste it below."
)

# App-native OAuth: the app (not rclone) runs the consent dance, so the
# redirect_uri points back at this console origin and any LAN browser works.
# rclone still reads the resulting remote; client_id/client_secret live in the
# remote block so rclone can refresh the access token itself.
PROVIDER_OAUTH: dict[str, dict[str, Any]] = {
    "drive": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/drive",
        "authorize_extra": {"access_type": "offline", "prompt": "consent"},
        "validate_url": "https://www.googleapis.com/drive/v3/about",
        "validate_params": {"fields": "user"},
        "remote_type": "drive",
    },
    "dropbox": {
        "authorize_url": "https://www.dropbox.com/oauth2/authorize",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
        "scope": "",
        "authorize_extra": {"token_access_type": "offline"},
        "validate_url": "https://api.dropboxapi.com/2/users/get_current_account",
        "validate_method": "POST",
        "remote_type": "dropbox",
    },
    "onedrive": {
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "offline_access Files.ReadWrite.All User.Read",
        "authorize_extra": {},
        "validate_url": "https://graph.microsoft.com/v1.0/me",
        "remote_type": "onedrive",
    },
}

_OAUTH_APP_FILE = "oauth_apps.json"
_STATE_SECRET_FILE = ".oauth_state_secret"
_CONSUMED_STATES: dict[str, float] = {}
_STATE_LOCK = threading.Lock()
_STATE_SECRET: str | None = None


def _rclone_dir() -> Path:
    return Path(os.environ.get("SERMONPILOT_RCLONE_DIR", DEFAULT_RCLONE_DIR))


def _safe_segment(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value or "anon") or "anon"


def _config_path(user_id: str | None) -> Path:
    return _rclone_dir() / _safe_segment(user_id) / "config"


def _rclone_exe() -> str:
    exe = shutil.which("rclone")
    if not exe:
        raise HTTPException(
            status_code=503, detail="rclone is not installed on the server"
        )
    return exe


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail="remote name must be 1-64 chars of letters, digits, dot, dash or underscore",
        )
    return name


def _require_provider(provider: str) -> str:
    provider = (provider or "").strip().lower()
    if provider not in _PROVIDER_IDS:
        raise HTTPException(status_code=422, detail=f"unknown provider: {provider or '?'}")
    return provider


def _run(
    user_id: str | None, *args: str, check: bool = True, timeout: int = 60
) -> subprocess.CompletedProcess:
    cfg = _config_path(user_id)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    exe = _rclone_exe()
    try:
        proc = subprocess.run(
            [exe, "--config", str(cfg), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="rclone timed out") from None
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "rclone failed").strip()
        raise HTTPException(status_code=422, detail=detail[:500])
    return proc


def _read_config(user_id: str | None) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    cfg = _config_path(user_id)
    if cfg.is_file():
        parser.read(cfg, encoding="utf-8")
    return parser


def list_remote_names(user_id: str | None) -> list[str]:
    return [s for s in _read_config(user_id).sections() if s and not s.startswith("__")]


def _remote_provider(user_id: str | None, name: str) -> str:
    parser = _read_config(user_id)
    if parser.has_section(name) and parser.has_option(name, "type"):
        return parser.get(name, "type").strip().lower()
    return ""


def _public_remote(user_id: str | None, name: str) -> dict[str, Any]:
    return {"name": name, "provider": _remote_provider(user_id, name), "status": "configured"}


def _write_remote(user_id: str | None, name: str, provider: str, keys: dict[str, str]) -> None:
    args = ["config", "create", name, provider]
    for field, value in keys.items():
        if value:
            args.append(f"{field}={value}")
    _run(user_id, *args)
    try:
        os.chmod(_config_path(user_id), 0o600)
    except OSError:
        pass


def _validate_remote(user_id: str | None, name: str) -> None:
    proc = _run(user_id, "lsf", f"{name}:", "--max-items", "1", check=False, timeout=120)
    if proc.returncode != 0:
        _run(user_id, "config", "delete", name, check=False)
        detail = (proc.stderr or proc.stdout or "remote did not validate").strip()
        raise HTTPException(status_code=422, detail=detail[:500])


def _create_remote(
    user_id: str | None,
    name: str,
    provider: str,
    token: str = "",
    keys: dict[str, str] | None = None,
) -> None:
    name = _validate_name(name)
    provider = _require_provider(provider)
    if provider in _OAUTH_PROVIDERS:
        if not (token or "").strip():
            raise HTTPException(status_code=422, detail="token is required for oauth providers")
        fields = {"token": token.strip(), "config_refresh_token": "false"}
    elif provider == "s3":
        supplied = keys or {}
        if not supplied.get("access_key_id") or not supplied.get("secret_access_key"):
            raise HTTPException(
                status_code=422, detail="access_key_id and secret_access_key are required"
            )
        fields = {
            "provider": supplied.get("provider") or "Other",
            "access_key_id": supplied.get("access_key_id", ""),
            "secret_access_key": supplied.get("secret_access_key", ""),
        }
        for field in ("endpoint", "region"):
            if supplied.get(field):
                fields[field] = supplied[field]
    else:
        supplied = keys or {}
        if not supplied.get("account") or not supplied.get("key"):
            raise HTTPException(status_code=422, detail="account and key are required")
        fields = {"account": supplied.get("account", ""), "key": supplied.get("key", "")}
    _write_remote(user_id, name, provider, fields)
    _validate_remote(user_id, name)


def _require_oauth_provider(provider: str) -> str:
    provider = _require_provider(provider)
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"{provider} uses key credentials, not oauth")
    return provider


def _oauth_apps_path() -> Path:
    return _rclone_dir() / _OAUTH_APP_FILE


def _load_oauth_apps() -> dict[str, dict[str, str]]:
    path = _oauth_apps_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        provider: {
            "client_id": str(app.get("client_id", "")),
            "client_secret": str(app.get("client_secret", "")),
        }
        for provider, app in data.items()
        if isinstance(app, dict)
    }


def _save_oauth_apps(data: dict[str, dict[str, str]]) -> None:
    path = _oauth_apps_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _get_oauth_app(provider: str) -> dict[str, str] | None:
    app = _load_oauth_apps().get(provider)
    if not app or not app.get("client_id") or not app.get("client_secret"):
        return None
    return app


def _oauth_apps_status() -> dict[str, dict[str, bool]]:
    return {
        provider: {"has_credentials": _get_oauth_app(provider) is not None}
        for provider in sorted(_OAUTH_PROVIDERS)
    }


def _state_secret() -> str:
    global _STATE_SECRET
    env = os.environ.get("SERMONPILOT_OAUTH_STATE_SECRET", "").strip()
    if env:
        return env
    with _STATE_LOCK:
        if _STATE_SECRET:
            return _STATE_SECRET
        path = _rclone_dir() / _STATE_SECRET_FILE
        if path.is_file():
            _STATE_SECRET = path.read_text(encoding="utf-8").strip()
        if not _STATE_SECRET:
            _STATE_SECRET = secrets.token_urlsafe(48)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_STATE_SECRET, encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        return _STATE_SECRET


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign_state(payload: dict[str, Any]) -> str:
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_state_secret().encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def _sweep_consumed() -> None:
    cutoff = time.time() - _OAUTH_STATE_TTL
    for nonce, used_at in list(_CONSUMED_STATES.items()):
        if used_at < cutoff:
            _CONSUMED_STATES.pop(nonce, None)


def _verify_state(state: str) -> dict[str, Any]:
    body, _, sig = (state or "").partition(".")
    if not body or not sig:
        raise HTTPException(status_code=400, detail="invalid oauth state")
    expected = hmac.new(_state_secret().encode(), body.encode(), hashlib.sha256).digest()
    try:
        provided = _b64d(sig)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid oauth state") from None
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=400, detail="invalid oauth state")
    try:
        payload = json.loads(_b64d(body))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid oauth state") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid oauth state")
    if float(payload.get("exp") or 0) < time.time():
        raise HTTPException(status_code=400, detail="oauth state expired")
    nonce = str(payload.get("nonce") or "")
    if not nonce or nonce in _CONSUMED_STATES:
        raise HTTPException(status_code=400, detail="oauth state already used")
    _CONSUMED_STATES[nonce] = time.time()
    _sweep_consumed()
    return payload


def _build_auth_url(provider: str, client_id: str, redirect_uri: str, state: str) -> str:
    spec = PROVIDER_OAUTH[provider]
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        **spec.get("authorize_extra", {}),
    }
    if spec.get("scope"):
        params["scope"] = spec["scope"]
    return f"{spec['authorize_url']}?{urlencode(params)}"


def _rclone_token(token: dict[str, Any]) -> str:
    block: dict[str, Any] = {
        "access_token": token.get("access_token", ""),
        "token_type": token.get("token_type") or "Bearer",
    }
    if token.get("refresh_token"):
        block["refresh_token"] = token["refresh_token"]
    expires_in = token.get("expires_in")
    if expires_in:
        try:
            expiry = time.gmtime(time.time() + float(expires_in))
            block["expiry"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", expiry)
        except (TypeError, ValueError):
            pass
    return json.dumps(block, separators=(",", ":"))


def _write_oauth_remote(
    user_id: str | None,
    name: str,
    provider: str,
    client_id: str,
    client_secret: str,
    token_json: str,
) -> None:
    name = _validate_name(name)
    fields = {
        "token": token_json,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    scope = PROVIDER_OAUTH[provider].get("scope")
    if scope:
        fields["scope"] = scope
    _write_remote(user_id, name, PROVIDER_OAUTH[provider]["remote_type"], fields)


async def _exchange_code(
    provider: str, code: str, client_id: str, client_secret: str, redirect_uri: str
) -> dict[str, Any]:
    spec = PROVIDER_OAUTH[provider]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(spec["token_url"], data=data)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"{provider} token exchange failed")
    return resp.json()


async def _validate_token(provider: str, access_token: str) -> None:
    spec = PROVIDER_OAUTH[provider]
    headers = {"Authorization": f"Bearer {access_token}"}
    method = spec.get("validate_method", "GET")
    kwargs: dict[str, Any] = {"headers": headers}
    if spec.get("validate_params"):
        kwargs["params"] = spec["validate_params"]
    if method == "POST":
        headers["Content-Type"] = "application/json"
        kwargs["content"] = b"null"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, spec["validate_url"], **kwargs)
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"{provider} rejected the token")


def _callback_page(title: str, message: str) -> HTMLResponse:
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{safe_title}</title></head><body style='font-family:sans-serif;padding:2rem'>"
        f"<h1 style='font-size:1.1rem'>{safe_title}</h1><p>{safe_message}</p>"
        "<p><a href='/settings'>Back to Settings</a></p></body></html>"
    )
    return HTMLResponse(page)


class _AuthorizeSession:
    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
        self.port: int | None = None
        self.state = ""
        self.provider = ""
        self.lines: list[str] = []
        self.lock = threading.Lock()
        self.started = time.time()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        try:
            for line in self.proc.stdout:
                with self.lock:
                    self.lines.append(line)
        except Exception:
            pass

    def text(self) -> str:
        with self.lock:
            return "".join(self.lines)


_SESSIONS: dict[str, _AuthorizeSession] = {}


def _session_key(user_id: str | None, name: str) -> str:
    return f"{_safe_segment(user_id)}:{name}"


def _discard_session(key: str) -> None:
    session = _SESSIONS.pop(key, None)
    if session is None:
        return
    try:
        session.proc.kill()
    except Exception:
        pass


def _sweep_sessions() -> None:
    now = time.time()
    for key, session in list(_SESSIONS.items()):
        if now - session.started > _AUTHORIZE_TTL:
            _discard_session(key)


def extract_authorize_url(text: str) -> str:
    """Return the consent-launcher URL from rclone's stdout.

    rclone prints multiple URLs: the redirect-notice mentions the bare callback
    (http://127.0.0.1:53682/) BEFORE the actual link ("go to the following link:
    .../auth?state=..."). The launcher URL is the one carrying /auth?state= -
    grabbing the first URL yields the bare callback and the proxied page then
    serves rclone's Failure page instead of the consent flow.
    """
    match = re.search(r"https?://[^\s'\"/]+/auth\?state=[^\s'\"&]+", text)
    if match:
        return match.group(0)
    match = re.search(r"https?://[^\s'\"]+", text)
    return match.group(0) if match else ""


def extract_authorize_token(text: str) -> str:
    match = re.search(r'\{"access_token".*?\}', text, re.DOTALL)
    if not match:
        return ""
    try:
        obj = json.loads(match.group(0))
    except ValueError:
        return ""
    return json.dumps(obj) if obj.get("access_token") else ""


def _wait_for(getter, timeout: float) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = getter()
        if value:
            return value
        time.sleep(0.05)
    return ""


def _public_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    if proto or host:
        host = host or request.headers.get("host", "")
        if host:
            root = (request.scope.get("root_path") or "").rstrip("/")
            return f"{proto or request.url.scheme}://{host}{root}/"
    return str(request.base_url)


def _proxied_authorize_url(base_url: str, key: str, raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if not parsed.port:
        return ""
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return f"{base_url.rstrip('/')}/rclone-auth/{key}{path}"


def _parse_redirect(redirect_url: str) -> tuple[str, str, str]:
    raw = (redirect_url or "").strip()
    if not raw:
        return "", "", ""
    query = raw.split("?", 1)[1] if "?" in raw else raw
    params = parse_qs(query)
    code = (params.get("code") or [""])[0].strip()
    state = (params.get("state") or [""])[0].strip()
    scope = (params.get("scope") or [""])[0].strip()
    if not code and "=" not in raw:
        code = raw
    return code, state, scope


def _start_authorize(user_id: str | None, name: str, provider: str, base_url: str) -> str:
    _sweep_sessions()
    proc = subprocess.Popen(
        [_rclone_exe(), "authorize", provider, "--auth-no-open-browser"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    key = _session_key(user_id, name)
    session = _AuthorizeSession(proc)
    _SESSIONS[key] = session
    raw_url = _wait_for(lambda: extract_authorize_url(session.text()), 15)
    if not raw_url:
        _discard_session(key)
        raise HTTPException(status_code=502, detail="rclone did not emit an authorization URL")
    url = _proxied_authorize_url(base_url, key, raw_url)
    if not url:
        _discard_session(key)
        raise HTTPException(status_code=502, detail="rclone authorization URL has no callback port")
    parsed = urlsplit(raw_url)
    session.port = parsed.port
    session.provider = provider
    session.state = (parse_qs(parsed.query).get("state") or [""])[0].strip()
    return url


def _collect_authorize_token(user_id: str | None, name: str, timeout: float = 180) -> str:
    key = _session_key(user_id, name)
    session = _SESSIONS.get(key)
    if session is None:
        return ""
    token = _wait_for(lambda: extract_authorize_token(session.text()), timeout)
    _discard_session(key)
    return token


_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


async def _forward(
    port: int,
    method: str,
    path: str,
    query: str,
    headers: dict[str, str],
    body: bytes,
) -> httpx.Response:
    url = f"http://127.0.0.1:{port}{path}"
    if query:
        url = f"{url}?{query}"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        return await client.request(method, url, headers=headers, content=body)


@proxy_router.api_route(
    "/rclone-auth/{session_key}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
async def rclone_auth_proxy(session_key: str, path: str, request: Request) -> Response:
    session = _SESSIONS.get(session_key)
    if session is None or session.port is None:
        raise HTTPException(status_code=404, detail="no such authorization session")
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _HOP_BY_HOP and name.lower() not in ("host", "content-length")
    }
    upstream = await _forward(
        session.port,
        request.method,
        f"/{path}",
        request.url.query,
        headers,
        await request.body(),
    )
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() not in _HOP_BY_HOP
        and name.lower() not in ("content-length", "content-encoding")
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


_SERVE_LOCK = threading.Lock()
_SERVES: dict[str, dict[str, Any]] = {}


def _serve_key(user_id: str | None, name: str, path: str) -> str:
    return f"{_safe_segment(user_id)}:{name}:{path}"


def _serve_state_path(user_id: str | None) -> Path:
    return _rclone_dir() / _safe_segment(user_id) / "serve.json"


def _load_serves(user_id: str | None) -> dict[str, Any]:
    path = _serve_state_path(user_id)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_serves(user_id: str | None, data: dict[str, Any]) -> None:
    path = _serve_state_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError:
        pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _pid_alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def ensure_remote_serve(user_id: str | None, name: str, path: str = "") -> str:
    key = _serve_key(user_id, name, path)
    with _SERVE_LOCK:
        live = _SERVES.get(key)
        if live and live.get("proc") is not None and live["proc"].poll() is None:
            return live["url"]
        persisted = _load_serves(user_id).get(key)
        if isinstance(persisted, dict) and _pid_alive(persisted.get("pid")):
            url = f"http://127.0.0.1:{persisted['port']}/"
            _SERVES[key] = {"proc": None, "url": url}
            return url
        exe = _rclone_exe()
        cfg = _config_path(user_id)
        port = _free_port()
        target = f"{name}:{path}".rstrip(":")
        proc = subprocess.Popen(
            [exe, "--config", str(cfg), "serve", "webdav", target, "--addr", f"127.0.0.1:{port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}/"
        _SERVES[key] = {"proc": proc, "url": url}
        data = _load_serves(user_id)
        data[key] = {"pid": proc.pid, "port": port}
        _save_serves(user_id, data)
        return url


def parse_remote_path(container_path: str) -> tuple[str, str] | None:
    if not container_path.startswith(REMOTE_PREFIX):
        return None
    rest = container_path[len(REMOTE_PREFIX):]
    name, _, sub = rest.partition(":")
    name = name.strip()
    if not name:
        return None
    return name, sub.strip("/")


def resolve_remote_uri(user_id: str | None, container_path: str) -> str | None:
    parsed = parse_remote_path(container_path)
    if parsed is None:
        return None
    name, sub = parsed
    if name not in list_remote_names(user_id):
        raise HTTPException(status_code=404, detail=f"no such remote: {name}")
    base = ensure_remote_serve(user_id, name)
    return f"{base}{quote(sub)}" if sub else base


def _parse_lsf(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line:
            continue
        size: int | None = None
        if ";" in line:
            size_raw, _, path = line.partition(";")
            try:
                size = int(size_raw)
            except ValueError:
                size = None
        else:
            path = line
        if not path:
            continue
        is_dir = path.endswith("/")
        clean = path.rstrip("/")
        items.append(
            {
                "name": clean.rsplit("/", 1)[-1],
                "path": clean,
                "type": "directory" if is_dir else "file",
                "size": None if is_dir or (size is None or size < 0) else size,
            }
        )
    return items


class RemoteBody(BaseModel):
    name: str
    provider: str
    token: str = ""
    keys: dict[str, str] = Field(default_factory=dict)


class AuthorizeBody(BaseModel):
    name: str
    provider: str
    token: str = ""


class AuthorizePasteBody(BaseModel):
    name: str
    provider: str
    redirect_url: str


class OAuthAppBody(BaseModel):
    provider: str
    client_id: str
    client_secret: str


class BrowseBody(BaseModel):
    path: str = ""


@router.get("/providers")
def providers(user=Depends(require_user)) -> dict[str, Any]:
    return {"items": PROVIDERS, "rclone": bool(shutil.which("rclone"))}


@router.put("/oauth-app")
def put_oauth_app(body: OAuthAppBody, user=Depends(admin_only)) -> dict[str, Any]:
    provider = _require_oauth_provider(body.provider)
    client_id = body.client_id.strip()
    client_secret = body.client_secret.strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=422, detail="client_id and client_secret are required")
    apps = _load_oauth_apps()
    apps[provider] = {"client_id": client_id, "client_secret": client_secret}
    _save_oauth_apps(apps)
    return {"provider": provider, "has_credentials": True}


@router.get("/oauth-app")
def get_oauth_app(user=Depends(require_user)) -> dict[str, Any]:
    return {"providers": _oauth_apps_status()}


@router.get("/oauth/start")
def oauth_start(
    provider: str, name: str, request: Request, user=Depends(require_user)
) -> dict[str, Any]:
    provider = _require_oauth_provider(provider)
    name = _validate_name(name)
    app = _get_oauth_app(provider)
    if app is None:
        raise HTTPException(
            status_code=422,
            detail=f"no OAuth client configured for {provider}; an admin must add one",
        )
    redirect_uri = f"{_public_base_url(request)}api/cloud/oauth/callback"
    state = _sign_state(
        {
            "user_id": user.get("id"),
            "name": name,
            "provider": provider,
            "redirect_uri": redirect_uri,
            "nonce": secrets.token_urlsafe(16),
            "exp": time.time() + _OAUTH_STATE_TTL,
        }
    )
    url = _build_auth_url(provider, app["client_id"], redirect_uri, state)
    return {"url": url, "name": name, "provider": provider}


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> Response:
    if error:
        return _callback_page("Authorization failed", f"The provider returned: {error}")
    payload = _verify_state(state)
    provider = str(payload.get("provider") or "")
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="invalid oauth state")
    app = _get_oauth_app(provider)
    if app is None:
        raise HTTPException(status_code=400, detail="oauth client no longer configured")
    if not code:
        return _callback_page("Authorization failed", "No authorization code was returned.")
    token = await _exchange_code(
        provider, code, app["client_id"], app["client_secret"], str(payload["redirect_uri"])
    )
    access_token = str(token.get("access_token") or "")
    if not access_token:
        raise HTTPException(status_code=400, detail="provider returned no access token")
    await _validate_token(provider, access_token)
    _write_oauth_remote(
        payload.get("user_id"),
        str(payload.get("name") or ""),
        provider,
        app["client_id"],
        app["client_secret"],
        _rclone_token(token),
    )
    name = quote(str(payload.get("name") or ""))
    target = f"{_public_base_url(request)}settings?cloud=connected&name={name}"
    return RedirectResponse(target, status_code=303)


# Paste-the-redirect flow (#296): rclone's own OAuth client redirects the
# user's browser to http://127.0.0.1:<port>, which cannot load on their machine.
# The user copies that address and posts it here; we replay the callback against
# rclone's listener on the server loopback and rclone prints the token.
@router.get("/auth-url")
def auth_url(
    provider: str, name: str, request: Request, user=Depends(require_user)
) -> dict[str, Any]:
    provider = _require_provider(provider)
    name = _validate_name(name)
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"{provider} uses key credentials, not oauth")
    url = _start_authorize(user.get("id"), name, provider, _public_base_url(request))
    return {
        "url": url,
        "name": name,
        "provider": provider,
        "session_key": _session_key(user.get("id"), name),
        "instructions": PASTE_INSTRUCTIONS,
    }


@router.post("/authorize/paste", status_code=201)
async def authorize_paste(
    body: AuthorizePasteBody, user=Depends(require_user)
) -> dict[str, Any]:
    provider = _require_provider(body.provider)
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"{provider} uses key credentials, not oauth")
    name = _validate_name(body.name)
    key = _session_key(user.get("id"), name)
    session = _SESSIONS.get(key)
    if session is None or (session.provider and session.provider != provider):
        raise HTTPException(status_code=404, detail="no such authorization session")
    code, pasted_state, scope = _parse_redirect(body.redirect_url)
    if not code:
        raise HTTPException(status_code=422, detail="no authorization code found in the pasted URL")
    # State security: a pasted state must match the state rclone printed, so a
    # confused deputy cannot submit someone else's code. Code-only pastes are
    # accepted only for a session young enough that the code could not have been
    # replayed; the session key already binds it to this user.
    if pasted_state:
        if session.state and session.state != pasted_state:
            _discard_session(key)
            raise HTTPException(status_code=422, detail="oauth state does not match this session")
    elif time.time() - session.started > _PASTE_STATE_GRACE:
        _discard_session(key)
        raise HTTPException(status_code=422, detail="authorization session expired")
    if session.port is None:
        _discard_session(key)
        raise HTTPException(
            status_code=422, detail="authorization session has no callback listener"
        )
    params = {"code": code}
    if scope:
        params["scope"] = scope
    query = urlencode(params)
    try:
        upstream = await _forward(session.port, "GET", "/", query, {}, b"")
    except Exception as exc:
        _discard_session(key)
        raise HTTPException(
            status_code=422, detail=f"could not reach rclone listener: {exc}"
        ) from None
    if upstream.status_code >= 400:
        _discard_session(key)
        detail = (upstream.text or "rclone rejected the authorization code").strip()
        raise HTTPException(status_code=422, detail=detail[:500])
    token = _collect_authorize_token(user.get("id"), name)
    if not token:
        raise HTTPException(status_code=422, detail="authorization not completed")
    _create_remote(user.get("id"), name, provider, token=token)
    return _public_remote(user.get("id"), name)


@router.post("/authorize", status_code=201)
def authorize(body: AuthorizeBody, user=Depends(require_user)) -> dict[str, Any]:
    provider = _require_provider(body.provider)
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"{provider} uses key credentials, not oauth")
    token = body.token.strip() or _collect_authorize_token(user.get("id"), body.name)
    if not token:
        raise HTTPException(status_code=422, detail="authorization not completed")
    _create_remote(user.get("id"), body.name, provider, token=token)
    return _public_remote(user.get("id"), _validate_name(body.name))


@router.post("/remotes", status_code=201)
def create_remote(body: RemoteBody, user=Depends(require_user)) -> dict[str, Any]:
    _create_remote(user.get("id"), body.name, body.provider, token=body.token, keys=body.keys)
    return _public_remote(user.get("id"), _validate_name(body.name))


@router.get("/remotes")
def list_remotes(user=Depends(require_user)) -> dict[str, Any]:
    names = list_remote_names(user.get("id"))
    return {"items": [_public_remote(user.get("id"), n) for n in names], "total": len(names)}


@router.delete("/remotes/{name}", status_code=204)
def delete_remote(name: str, user=Depends(require_user)) -> None:
    name = _validate_name(name)
    if name not in list_remote_names(user.get("id")):
        raise HTTPException(status_code=404, detail="no such remote")
    _run(user.get("id"), "config", "delete", name)


@router.post("/remotes/{name}/browse")
def browse_remote(name: str, body: BrowseBody, user=Depends(require_user)) -> dict[str, Any]:
    name = _validate_name(name)
    if name not in list_remote_names(user.get("id")):
        raise HTTPException(status_code=404, detail="no such remote")
    sub = (body.path or "").strip("/")
    proc = _run(
        user.get("id"),
        "lsf",
        f"{name}:{sub}",
        "--max-items",
        "200",
        "--format",
        "sp",
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "could not list remote").strip()
        raise HTTPException(status_code=422, detail=detail[:500])
    return {"path": sub, "items": _parse_lsf(proc.stdout)}
