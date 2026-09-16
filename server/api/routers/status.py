from __future__ import annotations

import datetime
from importlib import metadata
from typing import Any

from fastapi import APIRouter

from server.api.db import db_is_readable
from server.api.schemas import HealthOut, StatusOut

router = APIRouter(tags=["status"])


def _version() -> str:
    try:
        return metadata.version("sermon-audio-updater")
    except Exception:
        return "0.0.0"


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
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
    return StatusOut(
        status=_serialize(comprehensive),
        checked_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )
