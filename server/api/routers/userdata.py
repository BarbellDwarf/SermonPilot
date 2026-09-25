"""Per-user settings persistence under /api/me/*.

P5c/P5d: connections (LLM + SermonAudio) and arbitrary settings keys store
JSON blobs in user_settings (keyed by user_id, so isolation is by
construction). API keys are base64-obfuscated at rest and never returned;
responses expose has_key + masked_key only. Backup downloads re-mask every
stored key; restores reject masked values.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.api.accounts import (
    get_db_path,
    get_setting,
    set_setting,
    writable_conn,
)
from server.api.routers.auth import require_user

router = APIRouter(prefix="/api/me/connections", tags=["connections"])

logger = logging.getLogger(__name__)

_LLM_KEY = "connections.llm"
_SA_KEY = "connections.sermonaudio"
_MASK = "********"


def _obfuscate(key: str) -> str:
    return base64.b64encode(key.encode()).decode()


def _deobfuscate(stored: str | None) -> str:
    if not stored:
        return ""
    try:
        return base64.b64decode(stored.encode()).decode()
    except Exception:
        return ""


def _masked(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * 8
    return "*" * 8 + key[-4:]


def _next_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


class ConnectionBody(BaseModel):
    name: str = ""
    preset: str = ""
    provider: str = ""
    model: str = ""
    endpoint: str = ""
    apiKey: str = ""
    numCtx: str = ""
    maxTokens: str = ""
    temperature: str = ""
    role: str = "Unused"
    broadcasterId: str = ""
    notes: str = ""


class DefaultBody(BaseModel):
    id: str | None = None


def _rows(user: dict, key: str) -> dict:
    with writable_conn() as conn:
        value = get_setting(conn, user["id"], key)
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        return value
    return {"items": [], "default_id": None}


def _put(user: dict, key: str, data: dict) -> None:
    with writable_conn() as conn:
        set_setting(conn, user["id"], key, data)


def _public(item: dict) -> dict:
    stored = item.get("_apiKeyEnc") or ""
    raw = _deobfuscate(stored)
    return {
        "id": item["id"],
        "name": item.get("name", ""),
        "has_key": bool(raw),
        "masked_key": _masked(raw),
    }


def _public_llm(item: dict) -> dict:
    out = _public(item)
    for field in ("name", "preset", "provider", "model", "endpoint", "numCtx", "maxTokens",
        "temperature", "role"):
        out[field] = item.get(field, "")
    return out


def _public_sa(item: dict) -> dict:
    out = _public(item)
    for field in ("name", "broadcasterId", "notes"):
        out[field] = item.get(field, "")
    return out


@router.get("/{kind}")
def list_connections(kind: str, user=Depends(require_user)):
    if kind not in ("llm", "sermonaudio"):
        raise HTTPException(status_code=404, detail="unknown connection kind")
    key = _LLM_KEY if kind == "llm" else _SA_KEY
    data = _rows(user, key)
    pub = _public_llm if kind == "llm" else _public_sa
    return {"items": [pub(i) for i in data["items"]], "total": len(data["items"]),
        "default_id": data.get("default_id")}


@router.post("/{kind}", status_code=201)
def create_connection(kind: str, body: ConnectionBody, user=Depends(require_user)):
    if kind not in ("llm", "sermonaudio"):
        raise HTTPException(status_code=404, detail="unknown connection kind")
    key = _LLM_KEY if kind == "llm" else _SA_KEY
    data = _rows(user, key)
    item = dict(body.model_dump())
    item["id"] = _next_id("conn" if kind == "llm" else "sa")
    item["_apiKeyEnc"] = _obfuscate(body.apiKey or "")
    item.pop("apiKey", None)
    data["items"].append(item)
    if kind == "sermonaudio" and data.get("default_id") is None and body.apiKey:
        data["default_id"] = item["id"]
    _put(user, key, data)
    pub = _public_llm if kind == "llm" else _public_sa
    return pub(item)


@router.put("/{kind}/default")
def set_default(kind: str, body: DefaultBody, user=Depends(require_user)):
    if kind != "sermonaudio":
        raise HTTPException(status_code=404, detail="default applies to sermonaudio only")
    key = _SA_KEY
    data = _rows(user, key)
    if body.id is not None and not any(i["id"] == body.id for i in data["items"]):
        raise HTTPException(status_code=404, detail="no such connection")
    data["default_id"] = body.id
    _put(user, key, data)
    return {"default_id": body.id}


@router.get("/{kind}/{conn_id}")
def get_connection(kind: str, conn_id: str, user=Depends(require_user)):
    if kind not in ("llm", "sermonaudio"):
        raise HTTPException(status_code=404, detail="unknown connection kind")
    key = _LLM_KEY if kind == "llm" else _SA_KEY
    data = _rows(user, key)
    for item in data["items"]:
        if item["id"] == conn_id:
            pub = _public_llm if kind == "llm" else _public_sa
            return pub(item)
    raise HTTPException(status_code=404, detail="no such connection")


@router.put("/{kind}/{conn_id}")
def update_connection(kind: str, conn_id: str, body: ConnectionBody, user=Depends(require_user)):
    if kind not in ("llm", "sermonaudio"):
        raise HTTPException(status_code=404, detail="unknown connection kind")
    key = _LLM_KEY if kind == "llm" else _SA_KEY
    data = _rows(user, key)
    for item in data["items"]:
        if item["id"] == conn_id:
            updates = body.model_dump(exclude_unset=True)
            for field, value in updates.items():
                if field == "apiKey":
                    if value:
                        item["_apiKeyEnc"] = _obfuscate(value)
                else:
                    item[field] = value
            _put(user, key, data)
            pub = _public_llm if kind == "llm" else _public_sa
            return pub(item)
    raise HTTPException(status_code=404, detail="no such connection")


@router.delete("/{kind}/{conn_id}", status_code=204)
def delete_connection(kind: str, conn_id: str, user=Depends(require_user)):
    if kind not in ("llm", "sermonaudio"):
        raise HTTPException(status_code=404, detail="unknown connection kind")
    key = _LLM_KEY if kind == "llm" else _SA_KEY
    data = _rows(user, key)
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i["id"] != conn_id]
    if len(data["items"]) == before:
        raise HTTPException(status_code=404, detail="no such connection")
    if data.get("default_id") == conn_id:
        data["default_id"] = None
    _put(user, key, data)


me_router = APIRouter(prefix="/api/me", tags=["me"])


class ProfileBody(BaseModel):
    display_name: str | None = None
    email: str | None = None


class RestoreBody(BaseModel):
    settings: dict[str, object]


def _all_setting_keys(conn: sqlite3.Connection, user_id: str) -> list[str]:
    return [
        r["key"]
        for r in conn.execute(
            "SELECT key FROM user_settings WHERE user_id = ? ORDER BY key", (user_id,)
        ).fetchall()
    ]


def _mask_blob(value: object) -> object:
    if isinstance(value, dict):
        if "_apiKeyEnc" in value:
            out = {k: v for k, v in value.items() if k != "_apiKeyEnc"}
            out["masked_key"] = _MASK
            return out
        return {k: _mask_blob(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_blob(v) for v in value]
    return value


def _blob_contains_mask(value: object) -> bool:
    if isinstance(value, dict):
        return any(_blob_contains_mask(v) for v in value.values())
    if isinstance(value, list):
        return any(_blob_contains_mask(v) for v in value)
    return value == _MASK


@me_router.get("/backup")
def backup_user(user=Depends(require_user)):
    with writable_conn() as conn:
        keys = _all_setting_keys(conn, user["id"])
        settings = {k: _mask_blob(get_setting(conn, user["id"], k)) for k in keys}
        row = conn.execute(
            "SELECT id, username, display_name, role FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
    return {
        "app": "sermonpilot",
        "backup_kind": "user-settings",
        "account": dict(row) if row else None,
        "settings": settings,
    }


@me_router.post("/restore")
def restore_user(body: dict, user=Depends(require_user)):
    settings = body.get("settings")
    if not isinstance(settings, dict):
        raise HTTPException(status_code=422, detail="settings must be an object")
    if _blob_contains_mask(settings):
        raise HTTPException(status_code=400, detail="backup contains masked secrets")
    with writable_conn() as conn:
        for key, value in settings.items():
            set_setting(conn, user["id"], key, value)
    return {"restored": len(settings)}


@me_router.get("/sermonaudio-connection")
def effective_sermonaudio_connection(user=Depends(require_user)):
    """The SermonAudio account this user's uploads will use, secret-free."""
    from ui.sermonaudio_accounts import describe, resolve_connection

    return describe(resolve_connection(user["id"]))


@me_router.patch("")
def update_profile(body: ProfileBody, user=Depends(require_user)):
    with writable_conn() as conn:
        if body.display_name is not None:
            name = body.display_name.strip()
            if not name:
                raise HTTPException(status_code=422, detail="display_name cannot be empty")
            conn.execute(
                "UPDATE users SET display_name = ? WHERE id = ?", (name, user["id"])
            )
        if body.email is not None:
            conn.execute("UPDATE users SET email = ? WHERE id = ?", (body.email, user["id"]))
        row = conn.execute(
            "SELECT id, username, display_name, role, is_active, email FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
    return dict(row)


admin_backup_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_backup_router.get("/backup")
def backup_full_db(user=Depends(require_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        tables = sorted(
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        )
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
        settings = {}
        for r in conn.execute(
            "SELECT user_id, key, value FROM user_settings ORDER BY user_id, key"
        ).fetchall():
            bucket = settings.setdefault(r["user_id"], {})
            try:
                bucket[r["key"]] = _mask_blob(__import__("json").loads(r["value"]))
            except Exception:
                bucket[r["key"]] = _MASK
    finally:
        conn.close()
    return {
        "app": "sermonpilot",
        "backup_kind": "full-database",
        "tables": counts,
        "user_settings": settings,
    }


files_router = APIRouter(prefix="/api/me/files", tags=["files"])

_APP_ROOT = Path(__file__).resolve().parents[3]

_DEFAULT_OUTPUT_DIR = "processed_sermons"


def _resolve_output_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _APP_ROOT / path
    return path.resolve()


def _user_ingest_dir(user_id: str | None) -> Path:
    base = os.environ.get("SERMONPILOT_RAW_INGEST", "/data/raw_ingest")
    return _resolve_output_path(base) / re.sub(
        r"[^A-Za-z0-9_-]", "_", user_id or "anon"
    )


def _operator_output_roots() -> list[Path]:
    """Stable, operator-controlled roots an output directory may live under.

    The per-user output directory is user-settable, so without a root model a
    user could point it at ``/etc`` and read the whole filesystem through the
    file views. Allowed roots are the app default and the configured
    input/output directories; anything else falls back to the default.
    """
    candidates = [_resolve_output_path(_DEFAULT_OUTPUT_DIR)]
    try:
        from ui.config_utils import resolve_config

        config = resolve_config() or {}
        for key in ("output_directory", "input_directory"):
            configured = str(config.get(key) or "").strip()
            if configured and not configured.startswith("remote:"):
                candidates.append(_resolve_output_path(configured))
    except Exception as exc:
        logger.warning("Could not resolve output roots: %s", exc)
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            continue
        if str(resolved) not in seen:
            seen.add(str(resolved))
            roots.append(resolved)
    return roots


def _within_output_roots(path: Path) -> bool:
    return any(path == root or root in path.parents for root in _operator_output_roots())


def resolve_user_output_dir(user: dict) -> Path:
    """Absolute output root for a user: settings.general.output_dir or the default.

    A configured cloud reference (``remote:<name>:<sub>``) has no local root, so
    the local file views fall back to the default directory. A stored path
    outside the operator roots (for example one written by a settings restore)
    also falls back, so it can never become a read root.
    """
    with writable_conn() as conn:
        general = get_setting(conn, user["id"], "settings.general")
    configured = ""
    if isinstance(general, dict):
        configured = str(general.get("output_dir") or "").strip()
    if configured.startswith("remote:"):
        return _resolve_output_path(_DEFAULT_OUTPUT_DIR)
    resolved = _resolve_output_path(configured or _DEFAULT_OUTPUT_DIR)
    if not _within_output_roots(resolved):
        return _resolve_output_path(_DEFAULT_OUTPUT_DIR)
    return resolved


def _validate_remote_output(value: str, user: dict) -> str | None:
    """Normalise ``remote:<name>:<sub>`` output refs; raise 422 for unknown remotes."""
    from server.api.routers.cloud import list_remote_names, parse_remote_path

    parsed = parse_remote_path(value)
    if parsed is None:
        return None
    name, sub = parsed
    if name not in list_remote_names(user.get("id")):
        raise HTTPException(status_code=422, detail=f"no such cloud remote: {name}")
    return f"remote:{name}:{sub}"


def validate_output_dir(value: str, user: dict) -> str:
    """Validate an output destination: a local directory or a cloud remote ref."""
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="output_dir cannot be empty")
    remote = _validate_remote_output(raw, user)
    if remote is not None:
        return remote
    if raw.startswith("remote:"):
        raise HTTPException(status_code=422, detail="invalid cloud remote path")
    return str(validate_output_path(raw))


def validate_output_path(value: str) -> Path:
    """Resolve and validate an output directory; raise 422 when unusable."""
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="output_dir cannot be empty")
    resolved = _resolve_output_path(raw)
    if resolved == Path(resolved.anchor):
        raise HTTPException(status_code=422, detail="output_dir cannot be the filesystem root")
    if not _within_output_roots(resolved):
        raise HTTPException(status_code=422, detail="output_dir is outside the allowed roots")
    if resolved.exists():
        if not resolved.is_dir():
            raise HTTPException(status_code=422, detail="output_dir is not a directory")
        return resolved
    parent = resolved.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.is_dir():
        raise HTTPException(status_code=422, detail="output_dir has no writable parent")
    return resolved


@files_router.get("")
def list_user_files(user=Depends(require_user)):
    root = resolve_user_output_dir(user)
    items = []
    if root.is_dir():
        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                items.append({"name": entry.name, "type": "directory", "size": None})
            elif entry.is_file():
                items.append({"name": entry.name, "type": "file", "size": entry.stat().st_size})
    return {"items": items, "root": str(root)}


@files_router.get("/download")
def download_file(path: str, user=Depends(require_user)):
    root = resolve_user_output_dir(user).resolve()
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=400, detail="path escapes the output directory")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    from fastapi.responses import FileResponse

    return FileResponse(str(candidate), filename=candidate.name)


class OutputDirBody(BaseModel):
    output_dir: str = ""


@me_router.get("/output-dir")
def get_output_dir(user=Depends(require_user)):
    with writable_conn() as conn:
        general = get_setting(conn, user["id"], "settings.general")
    configured = ""
    if isinstance(general, dict):
        configured = str(general.get("output_dir") or "").strip()
    if configured.startswith("remote:"):
        return {"output_dir": configured, "source": "user"}
    if configured and _within_output_roots(_resolve_output_path(configured)):
        return {"output_dir": configured, "source": "user"}
    return {"output_dir": _DEFAULT_OUTPUT_DIR, "source": "default"}


@me_router.put("/output-dir")
def put_output_dir(body: OutputDirBody, user=Depends(require_user)):
    stored = validate_output_dir(body.output_dir, user)
    with writable_conn() as conn:
        general = get_setting(conn, user["id"], "settings.general")
        general = dict(general) if isinstance(general, dict) else {}
        general["output_dir"] = stored
        set_setting(conn, user["id"], "settings.general", general)
    return {"output_dir": stored, "source": "user"}


explore_router = APIRouter(prefix="/api/files", tags=["files"])


def _within_roots(candidate: Path, roots: list[Path]) -> bool:
    return any(candidate == root or root in candidate.parents for root in roots)


def _matching_root(candidate: Path, roots: list[Path]) -> Path:
    for root in roots:
        if candidate == root or root in candidate.parents:
            return root
    return roots[0]


def _root_entries(roots: list[Path]) -> list[dict[str, str]]:
    return [{"name": root.name or str(root), "path": str(root)} for root in roots]


def _explore_roots(user: dict) -> list[Path]:
    candidates = [resolve_user_output_dir(user), _user_ingest_dir(user.get("id"))]
    try:
        from ui.config_utils import resolve_config

        configured = str(resolve_config().get("input_directory") or "").strip()
        if configured:
            candidates.append(Path(configured))
    except Exception:
        pass
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = _resolve_output_path(str(candidate))
        if str(resolved) in seen:
            continue
        seen.add(str(resolved))
        roots.append(resolved)
    return roots


def _entry_size(entry: os.DirEntry) -> int | None:
    try:
        return entry.stat(follow_symlinks=True).st_size
    except OSError:
        return None


def _entry_modified(entry: os.DirEntry) -> str | None:
    try:
        stamp = entry.stat(follow_symlinks=True).st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(stamp).isoformat(timespec="seconds")


@explore_router.get("/explore")
def explore_files(path: str = "", user=Depends(require_user)) -> dict[str, Any]:
    roots = _explore_roots(user)
    raw = (path or "").strip()
    if raw:
        target = _resolve_output_path(raw)
        if not _within_roots(target, roots):
            raise HTTPException(status_code=403, detail="path is outside the allowed roots")
        if not target.is_dir():
            raise HTTPException(status_code=404, detail="directory not found")
    else:
        target = roots[0]
    root = _matching_root(target, roots)
    items: list[dict[str, Any]] = []
    if target.is_dir():
        try:
            entries = list(os.scandir(target))
        except OSError as exc:
            raise HTTPException(status_code=404, detail=f"cannot read directory: {exc}") from exc
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=True)
            except OSError:
                is_dir = False
            items.append(
                {
                    "name": entry.name,
                    "path": str(Path(entry.path)),
                    "type": "dir" if is_dir else "file",
                    "size": None if is_dir else _entry_size(entry),
                    "modified": _entry_modified(entry),
                }
            )
    items.sort(key=lambda item: (0 if item["type"] == "dir" else 1, item["name"].lower()))
    parent = (
        str(target.parent)
        if target != root and _within_roots(target.parent, roots)
        else None
    )
    return {
        "path": str(target),
        "parent": parent,
        "root": str(root),
        "roots": _root_entries(roots),
        "items": items,
    }
