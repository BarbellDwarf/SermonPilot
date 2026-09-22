"""DB-backed prompt templates.

Settings > Prompt Templates reads and writes the same ``prompt_templates``
block the pipeline resolves from ``config_cache.app_config``. A GET returns the
effective templates (built-in defaults merged with saved edits) plus the
built-in defaults, so the console can show the default prompt for a task the
operator has never edited. A PUT deep-merges the submitted task fields over the
stored block: a field left out keeps its stored value, and a field set to an
empty string clears it.
"""

from __future__ import annotations

import copy
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from server.api.routers.auth import require_user
from ui.config_utils import BUILTIN_PROMPT_TEMPLATES

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

logger = logging.getLogger(__name__)

_FIELDS = ("enabled", "system", "user")


class PromptTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool | None = None
    system: str | None = None
    user: str | None = None


class PromptsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    templates: dict[str, PromptTemplate] = {}


def _database():
    from ui.database import SermonDatabase

    db_path = os.environ.get("DATABASE_URL") or os.environ.get("SERMONPILOT_DB")
    return SermonDatabase(db_path=db_path) if db_path else SermonDatabase()


def _load_stored() -> dict[str, Any]:
    try:
        stored = _database().load_config()
    except Exception as exc:
        logger.warning("Could not read stored prompt templates: %s", exc)
        return {}
    return stored if isinstance(stored, dict) else {}


def _stored_templates() -> dict[str, Any]:
    templates = _load_stored().get("prompt_templates")
    return templates if isinstance(templates, dict) else {}


def _merge_templates(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(copy.deepcopy(value))
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _effective_templates() -> dict[str, Any]:
    try:
        from ui.config_utils import resolve_config

        templates = resolve_config().get("prompt_templates")
        if isinstance(templates, dict):
            return templates
    except Exception as exc:
        logger.warning("Could not resolve prompt templates: %s", exc)
    return _merge_templates(BUILTIN_PROMPT_TEMPLATES, _stored_templates())


def _view() -> dict[str, Any]:
    return {
        "templates": _effective_templates(),
        "defaults": copy.deepcopy(BUILTIN_PROMPT_TEMPLATES),
    }


def _apply_update(stored: dict[str, Any], updates: dict[str, PromptTemplate]) -> None:
    for key, update in updates.items():
        if not isinstance(key, str) or not key.strip():
            continue
        current = stored.get(key)
        if not isinstance(current, dict):
            current = {}
        for field in _FIELDS:
            value = getattr(update, field)
            if value is not None:
                current[field] = value
        stored[key] = current


@router.get("/config")
def get_prompt_config(user=Depends(require_user)):
    return _view()


@router.put("/config")
def update_prompt_config(body: PromptsUpdate, user=Depends(require_user)):
    db = _database()
    full = db.load_config()
    if not isinstance(full, dict):
        full = {}
    stored = full.get("prompt_templates")
    if not isinstance(stored, dict):
        stored = {}
    _apply_update(stored, body.templates)
    full["prompt_templates"] = stored
    db.save_config(full)
    return _view()
