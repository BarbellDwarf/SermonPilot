from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter

from server.api.db import db_is_readable
from server.api.schemas import HealthOut, StatusOut
from ui.version import app_version

router = APIRouter(tags=["status"])

_CONTEXT_NOTE = "unconfigured in API context"


def _context_tolerant(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("status") != "error":
        return entry
    message = str(entry.get("message") or "")
    details = str(entry.get("details") or "")
    unconfigured_llm = key in ("llm_primary", "llm_fallback") and (
        "LLM not configured" in message
        or ("llm" in key and "No " in details and "provider configured" in details)
    )
    unconfigured_api = key == "sermonaudio_api" and (
        message == "API credentials not configured"
        or "Missing api_key or broadcaster_id" in details
    )
    if not (unconfigured_llm or unconfigured_api):
        return entry
    return {
        **entry,
        "status": "warning",
        "message": f"{message} ({_CONTEXT_NOTE})" if message else _CONTEXT_NOTE,
    }


def _version() -> str:
    return app_version()


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_serialize(item) for item in value]
    return value


@router.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(ok=True, version=_version(), db_path_ok=db_is_readable())


@router.get("/api/status", response_model=StatusOut)
def status() -> StatusOut:
    from ui.system_status import SystemStatusManager

    manager = SystemStatusManager({})
    comprehensive = manager.get_comprehensive_status()
    comprehensive = {
        key: _context_tolerant(key, value)
        for key, value in comprehensive.items()
        if isinstance(value, dict)
    }
    return StatusOut(
        status=_serialize(comprehensive),
        checked_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )
