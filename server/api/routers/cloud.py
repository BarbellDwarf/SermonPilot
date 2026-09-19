"""Per-user cloud remotes backed by isolated rclone config files (INC1 #296).

Each user gets their own config at ``SERMONPILOT_RCLONE_DIR/<user_id>/config``
(rclone INI format, 0600). Secrets stay server-side: listing returns name and
provider only. Every endpoint resolves the caller's own config path, so one
user can never reach another user's remotes.

OAuth providers run headless through ``rclone authorize <provider>
--auth-no-open-browser``: ``GET /auth-url`` starts the subprocess and returns
the 127.0.0.1 callback URL it prints, the user completes consent, and
``POST /authorize`` reads the token JSON rclone emits on stdout and stores it.
Key providers (S3, B2) take credentials directly on create. rclone is resolved
at runtime with ``shutil.which``; without it these endpoints return 503.
"""

from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.api.routers.auth import require_user

router = APIRouter(prefix="/api/cloud", tags=["cloud"])

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
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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


class _AuthorizeSession:
    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
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


def _start_authorize(user_id: str | None, name: str, provider: str) -> str:
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
    url = _wait_for(lambda: extract_authorize_url(session.text()), 15)
    if not url:
        _discard_session(key)
        raise HTTPException(status_code=502, detail="rclone did not emit an authorization URL")
    return url


def _collect_authorize_token(user_id: str | None, name: str, timeout: float = 180) -> str:
    key = _session_key(user_id, name)
    session = _SESSIONS.get(key)
    if session is None:
        return ""
    token = _wait_for(lambda: extract_authorize_token(session.text()), timeout)
    _discard_session(key)
    return token


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


class BrowseBody(BaseModel):
    path: str = ""


@router.get("/providers")
def providers(user=Depends(require_user)) -> dict[str, Any]:
    return {"items": PROVIDERS, "rclone": bool(shutil.which("rclone"))}


@router.get("/auth-url")
def auth_url(provider: str, name: str, user=Depends(require_user)) -> dict[str, Any]:
    provider = _require_provider(provider)
    name = _validate_name(name)
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"{provider} uses key credentials, not oauth")
    url = _start_authorize(user.get("id"), name, provider)
    return {"url": url, "name": name, "provider": provider}


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
