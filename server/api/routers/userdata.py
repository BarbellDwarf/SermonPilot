"""Per-user connection persistence (LLM + SermonAudio) under /api/me/connections.

P5c: each section stores one JSON blob in user_settings (key
'connections.llm' / 'connections.sermonaudio'). API keys are stored
base64-obfuscated and never returned; responses expose has_key + masked_key
only. user_settings is keyed by (user_id, key), so per-user isolation is
enforced by construction.
"""

from __future__ import annotations

import base64
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.api.accounts import get_setting, set_setting, writable_conn
from server.api.routers.auth import require_user

router = APIRouter(prefix="/api/me/connections", tags=["connections"])

_LLM_KEY = "connections.llm"
_SA_KEY = "connections.sermonaudio"


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
