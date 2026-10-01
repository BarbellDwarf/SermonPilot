from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter

from server.api.db import db_is_readable
from server.api.schemas import HealthOut, StatusOut
from ui.version import app_version

router = APIRouter(tags=["status"])

logger = logging.getLogger(__name__)

# The checks the console renders as service cards, in display order.
SERVICE_KEYS = (
    "sermonaudio_api",
    "database",
    "llm_primary",
    "llm_fallback",
    "audio_enhancement",
    "local_storage",
    "processing_queue",
    "system_resources",
)

UNKNOWN_STATUS = "unknown"


def _resolved_config() -> dict[str, Any] | None:
    """The app config every other consumer resolves, or ``None`` on failure.

    This is the same call ``server/api/routers/app_config.py`` makes, so the
    dashboard reads exactly the values the pipeline would use, including
    environment overrides. Returning ``None`` rather than ``{}`` matters: an
    empty dict makes every credential check fail and reports a healthy install
    as broken.
    """
    try:
        from ui.config_utils import resolve_config

        return resolve_config()
    except Exception:
        logger.exception("Status check could not resolve config")
        return None


def _accounts_exist() -> bool:
    try:
        from ui.sermonaudio_accounts import any_user_connection

        return any_user_connection()
    except Exception:
        logger.exception("Status check could not read stored accounts")
        return False


def _normalize(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Give every entry a recognised status and a way to fix a bad one."""
    from ui.system_status import KNOWN_STATUSES, with_remediation

    status = str(entry.get("status") or "")
    if status not in KNOWN_STATUSES:
        entry = {
            **entry,
            "status": UNKNOWN_STATUS,
            "message": "State not determined",
            "details": f"The check reported an unrecognised state ({status or 'none'}).",
        }
    return with_remediation(key, entry)


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
    from ui.system_status import SystemStatusManager, unresolved_status

    config = _resolved_config()
    if config is None:
        comprehensive = unresolved_status(list(SERVICE_KEYS))
    else:
        manager = SystemStatusManager(
            config, sermonaudio_accounts_exist=_accounts_exist()
        )
        comprehensive = {
            key: _normalize(key, value)
            for key, value in manager.get_comprehensive_status().items()
            if isinstance(value, dict)
        }
    return StatusOut(
        status=_serialize(comprehensive),
        checked_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )
