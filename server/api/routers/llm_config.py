"""LLM provider configuration and live connection tests.

The Settings > LLM Providers console reads and writes the same ``llm`` block
the processing pipeline resolves from ``config_cache.app_config``. API keys
never leave the server: responses carry only ``has_key`` and a last-four mask.
The test endpoint calls the configured provider with a fixed trivial prompt and
reports measured latency plus the model the provider echoed; it never
fabricates a result.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from server.api.routers.auth import require_user

router = APIRouter(prefix="/api/llm", tags=["llm"])

ROLES = ("primary", "fallback", "validator")
ROUTE_ROLES = ("metadata", "validation", "transcription_assist", "fallback")
DEFAULT_ROUTING: dict[str, str] = {
    "metadata": "primary",
    "validation": "validator",
    "transcription_assist": "primary",
    "fallback": "fallback",
}

# The engine understands ollama plus the OpenAI-compatible family
# (openai/xai/groq/openrouter). Presets with local or custom endpoints all speak
# one of those two protocols.
_ENGINE_PROVIDERS = ("ollama", "openai", "xai", "groq", "openrouter")
_PRESET_PROVIDERS: dict[str, str] = {
    "ollama": "ollama",
    "ollama-cloud": "ollama",
    "openai": "openai",
    "grok": "xai",
    "xai": "xai",
    "groq": "groq",
    "openrouter": "openrouter",
    "lmstudio": "openai",
    "vllm": "openai",
    "custom": "openai",
}
_OPENAI_PROTOCOL = {"openai": "openai", "xai": "openai", "groq": "openai", "openrouter": "openai"}

_TEST_PROMPT = "ping"
_DEFAULT_TEST_TIMEOUT = 10.0
_MAX_TEST_TIMEOUT = 30.0


class LlmSlotUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    numCtx: str | int | float | None = None
    maxTokens: str | int | float | None = None
    temperature: str | int | float | None = None
    apiKey: str | None = None


class LlmConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    primary: LlmSlotUpdate | None = None
    fallback: LlmSlotUpdate | None = None
    validator: LlmSlotUpdate | None = None
    routing: dict[str, str] | None = None


class TestConnectionBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str = "primary"
    timeout_seconds: float | None = None


def _database():
    from ui.database import SermonDatabase

    db_path = os.environ.get("DATABASE_URL") or os.environ.get("SERMONPILOT_DB")
    return SermonDatabase(db_path=db_path) if db_path else SermonDatabase()


def _load_stored() -> dict[str, Any]:
    try:
        stored = _database().load_config()
    except Exception:
        return {}
    return stored if isinstance(stored, dict) else {}


def _stored_llm() -> dict[str, Any]:
    llm = _load_stored().get("llm")
    return llm if isinstance(llm, dict) else {}


def _effective_llm() -> dict[str, Any]:
    """The ``llm`` block the pipeline actually resolves (db + env + defaults)."""
    try:
        from ui.config_utils import resolve_config

        llm = resolve_config().get("llm")
        if isinstance(llm, dict):
            return llm
    except Exception:
        pass
    return _stored_llm()


def _save_stored_llm(llm: dict[str, Any]) -> None:
    db = _database()
    full = db.load_config()
    if not isinstance(full, dict):
        full = {}
    full["llm"] = llm
    db.save_config(full)


def _normalise_provider(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in _ENGINE_PROVIDERS:
        return text
    return _PRESET_PROVIDERS.get(text, "openai")


def _derive_preset(provider_type: str, endpoint: str) -> str:
    host = (endpoint or "").lower()
    if provider_type == "ollama":
        return "ollama-cloud" if "ollama.com" in host else "ollama"
    if provider_type == "xai":
        return "grok"
    if provider_type == "groq":
        return "groq"
    if provider_type == "openrouter":
        return "openrouter"
    if provider_type == "openai":
        if "api.x.ai" in host:
            return "grok"
        if "groq.com" in host:
            return "groq"
        if "openrouter.ai" in host:
            return "openrouter"
        if "localhost:1234" in host or "127.0.0.1:1234" in host:
            return "lmstudio"
        if "localhost:8000" in host or "127.0.0.1:8000" in host:
            return "vllm"
        if "api.openai.com" in host:
            return "openai"
        return "custom"
    return "custom"


def _mask_secret(value: object) -> tuple[bool, str]:
    """Return (has_key, masked). Only the last four characters of a literal key.

    An unresolved ``${VAR}`` placeholder is reported as "no key": the secret is
    not present in this process, and echoing the env var name would leak
    configuration we do not return anywhere else.
    """
    if not isinstance(value, str):
        return False, ""
    text = value.strip()
    if not text or text.startswith("${"):
        return False, ""
    if len(text) <= 8:
        return True, "********"
    return True, "********" + text[-4:]


def _provider_conf(llm: dict[str, Any], role: str, provider_type: str) -> dict[str, Any]:
    slot = llm.get(role)
    if not isinstance(slot, dict):
        return {}
    pconf = slot.get(provider_type)
    return pconf if isinstance(pconf, dict) else {}


def _slot_view(llm: dict[str, Any], role: str) -> dict[str, Any]:
    slot = llm.get(role)
    if not isinstance(slot, dict):
        slot = {}
    provider_type = str(slot.get("provider") or "ollama").strip().lower()
    if provider_type not in _ENGINE_PROVIDERS:
        provider_type = "ollama"
    pconf = _provider_conf(llm, role, provider_type)
    endpoint = pconf.get("host") or pconf.get("base_url") or ""
    has_key, masked = _mask_secret(pconf.get("api_key"))
    if role == "primary":
        enabled = True
    else:
        enabled = bool(slot.get("enabled", False))
    return {
        "role": role,
        "enabled": enabled,
        "provider": provider_type,
        "preset": _derive_preset(provider_type, str(endpoint)),
        "model": str(pconf.get("model") or ""),
        "endpoint": str(endpoint or ""),
        "numCtx": str(pconf.get("num_ctx") or ""),
        "maxTokens": str(pconf.get("max_tokens") or ""),
        "temperature": str(pconf.get("temperature") or ""),
        "hasKey": has_key,
        "maskedKey": masked,
    }


def _view() -> dict[str, Any]:
    llm = _effective_llm()
    routing = llm.get("routing")
    merged_routing = dict(DEFAULT_ROUTING)
    if isinstance(routing, dict):
        for key, value in routing.items():
            if key in ROUTE_ROLES and value in ROLES:
                merged_routing[key] = value
    return {
        "primary": _slot_view(llm, "primary"),
        "fallback": _slot_view(llm, "fallback"),
        "validator": _slot_view(llm, "validator"),
        "routing": merged_routing,
    }


def _coerce_number(value: object, field: str) -> int | float:
    if isinstance(value, bool):
        raise HTTPException(status_code=422, detail=f"{field} must be a number")
    if isinstance(value, (int, float)):
        return value if field == "temperature" else int(value)
    text = str(value).strip()
    if not text:
        raise HTTPException(status_code=422, detail=f"{field} must be a number")
    try:
        number = float(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be a number") from exc
    return number if field == "temperature" else int(number)


def _is_mask(value: str) -> bool:
    return value.startswith("•") or value.strip().startswith("****")


def _apply_slot(llm: dict[str, Any], role: str, update: LlmSlotUpdate) -> None:
    slot = llm.get(role)
    if not isinstance(slot, dict):
        slot = {}
        llm[role] = slot

    if update.enabled is not None and role != "primary":
        slot["enabled"] = bool(update.enabled)

    provider_type = _normalise_provider(update.provider) if update.provider else (
        str(slot.get("provider") or "ollama").strip().lower()
    )
    if provider_type not in _ENGINE_PROVIDERS:
        provider_type = "ollama"
    slot["provider"] = provider_type

    pconf = slot.get(provider_type)
    if not isinstance(pconf, dict):
        pconf = {}
        slot[provider_type] = pconf

    if update.model is not None:
        pconf["model"] = update.model.strip()

    if update.endpoint is not None:
        endpoint = update.endpoint.strip()
        endpoint_key = "host" if provider_type == "ollama" else "base_url"
        if endpoint:
            pconf[endpoint_key] = endpoint
        else:
            pconf.pop(endpoint_key, None)

    for field, key in (
        ("numCtx", "num_ctx"),
        ("maxTokens", "max_tokens"),
        ("temperature", "temperature"),
    ):
        value = getattr(update, field)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            pconf.pop(key, None)
        else:
            pconf[key] = _coerce_number(value, field)

    if update.apiKey is not None:
        key_value = update.apiKey
        if key_value.strip() and not _is_mask(key_value):
            pconf["api_key"] = key_value


def _apply_routing(llm: dict[str, Any], routing: dict[str, str]) -> None:
    current = llm.get("routing")
    if not isinstance(current, dict):
        current = {}
    for role, target in routing.items():
        if role in ROUTE_ROLES and target in ROLES:
            current[role] = target
    llm["routing"] = current


def _bounded_timeout(timeout_seconds: float | None) -> float:
    if timeout_seconds is None:
        return _DEFAULT_TEST_TIMEOUT
    try:
        value = float(timeout_seconds)
    except (TypeError, ValueError):
        return _DEFAULT_TEST_TIMEOUT
    if value <= 0:
        return _DEFAULT_TEST_TIMEOUT
    return min(value, _MAX_TEST_TIMEOUT)


def _elapsed_ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


def _error_text(response: httpx.Response) -> str:
    text = (response.text or "").strip()
    try:
        data = response.json()
        if isinstance(data, dict):
            for key in ("error", "message", "detail"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    except Exception:
        pass
    return text[:500] or f"HTTP {response.status_code}"


def _failure(message: str) -> dict[str, Any]:
    return {"ok": False, "latency_ms": 0, "model_echo": None, "error": message}


def _test_connection(
    llm: dict[str, Any], role: str, timeout_seconds: float | None = None
) -> dict[str, Any]:
    view = _slot_view(llm, role)
    provider_type = str(view["provider"])
    endpoint = str(view["endpoint"]).strip()
    model = str(view["model"]).strip()
    timeout = _bounded_timeout(timeout_seconds)

    if not endpoint:
        return _failure("No endpoint configured.")
    if not model:
        return _failure("No model configured.")

    pconf = _provider_conf(llm, role, provider_type)
    api_key = pconf.get("api_key")
    api_key = api_key.strip() if isinstance(api_key, str) else ""
    if api_key.startswith("${"):
        api_key = ""

    start = time.perf_counter()
    try:
        if provider_type == "ollama":
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": _TEST_PROMPT}],
                "stream": False,
                "options": {"num_predict": 1},
            }
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            response = httpx.post(
                endpoint.rstrip("/") + "/api/chat",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        elif provider_type in _OPENAI_PROTOCOL:
            if not api_key:
                return _failure("No API key configured.")
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": _TEST_PROMPT}],
                "max_tokens": 1,
            }
            response = httpx.post(
                endpoint.rstrip("/") + "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout,
            )
        else:
            return _failure(f"Provider {provider_type} does not support a live test yet.")
    except httpx.TimeoutException:
        return {
            "ok": False,
            "latency_ms": _elapsed_ms(start),
            "model_echo": None,
            "error": f"Timed out after {timeout:g}s.",
        }
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "latency_ms": _elapsed_ms(start),
            "model_echo": None,
            "error": str(exc),
        }

    latency_ms = _elapsed_ms(start)
    if response.status_code >= 400:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "model_echo": None,
            "error": _error_text(response),
        }

    echo: str | None = None
    try:
        data = response.json()
        if isinstance(data, dict) and isinstance(data.get("model"), str):
            echo = data["model"]
    except Exception:
        echo = None
    return {"ok": True, "latency_ms": latency_ms, "model_echo": echo or model, "error": None}


@router.get("/config")
def get_llm_config(user=Depends(require_user)):
    return _view()


@router.put("/config")
def update_llm_config(body: LlmConfigUpdate, user=Depends(require_user)):
    llm = _stored_llm()
    for role in ROLES:
        update = getattr(body, role)
        if update is not None:
            _apply_slot(llm, role, update)
    if body.routing is not None:
        _apply_routing(llm, body.routing)
    _save_stored_llm(llm)
    return _view()


@router.post("/test-connection")
def test_llm_connection(body: TestConnectionBody, user=Depends(require_user)):
    if body.role not in ROLES:
        raise HTTPException(status_code=422, detail="role must be primary, fallback, or validator")
    return _test_connection(_effective_llm(), body.role, body.timeout_seconds)
