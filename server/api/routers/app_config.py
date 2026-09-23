"""Application configuration sections for the web console Settings page.

The console reads and writes the same ``config_cache.app_config`` the
processing pipeline resolves. Each section exposes an explicit allowlist of
dotted config paths; unknown paths in a write are ignored, so the API cannot
create arbitrary keys. Secret values never leave the server: a secret path
reports only ``has_value`` and a last-four mask, plus the source that supplied
it. The source is the winning environment variable name, ``db`` for a saved
value, or ``default`` for a built-in, so the UI can name the variable that is
overriding a saved setting.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from server.api.routers.auth import require_user

router = APIRouter(prefix="/api/config", tags=["config"])

# Dotted path -> value kind. ``json`` accepts a whole sub-tree (prompt
# templates); ``secret`` is write-only and never echoed.
SECTIONS: dict[str, dict[str, str]] = {
    "general": {
        "dry_run": "bool",
        "debug": "bool",
        "hashtag_verification": "bool",
        "output_directory": "str",
        "save_original_audio": "bool",
        "save_transcript": "bool",
    },
    "audio": {
        "audio_enhancement_method": "str",
        "enhancement.device": "str",
        "clear_custom_repo": "str",
        "clear_custom_file": "str",
        "audio_noise_reduction": "bool",
        "audio_amplify": "bool",
        "audio_normalize": "bool",
        "audio_gain_db": "float",
        "audio_target_level_db": "float",
        "metadata_processing.process_audio": "bool",
    },
    "transcription": {
        "transcription.backend": "str",
        "transcription.compute_type": "str",
        "transcription.whisper_local.model": "str",
        "transcription.whisper_local.device": "str",
        "transcription.whisper_local.language": "str",
        "transcription.faster_whisper_local.model": "str",
        "transcription.faster_whisper_local.device": "str",
        "transcription.faster_whisper_local.language": "str",
        "transcription.whisper_openai.base_url": "str",
        "transcription.whisper_openai.model": "str",
        "transcription.whisper_openai.api_key": "secret",
        "transcription.whisper_openrouter.base_url": "str",
        "transcription.whisper_openrouter.model": "str",
        "transcription.whisper_openrouter.api_key": "secret",
    },
    "validation": {
        "metadata_processing.description.validation.enabled": "bool",
        "metadata_processing.description.validation.criteria": "list",
        "metadata_processing.description.update_if_missing": "bool",
        "metadata_processing.description.update_if_minimal": "bool",
        "metadata_processing.description.min_length_threshold": "int",
        "metadata_processing.hashtags.update_if_missing": "bool",
        "metadata_processing.hashtags.update_if_minimal": "bool",
        "metadata_processing.hashtags.min_length_threshold": "int",
    },
    "prompts": {
        "prompt_templates": "json",
    },
    "sermonaudio": {
        "api_key": "secret",
        "broadcaster_id": "str",
    },
}


class ConfigSectionUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    values: dict[str, Any] = {}


def _database():
    from ui.database import SermonDatabase

    db_path = os.environ.get("DATABASE_URL") or os.environ.get("SERMONPILOT_DB")
    return SermonDatabase(db_path=db_path) if db_path else SermonDatabase()


def _get_dotted(config: dict[str, Any], dotted: str) -> Any:
    node: Any = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_dotted(config: dict[str, Any], dotted: str, value: Any) -> None:
    node = config
    parts = dotted.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _mask_secret(value: Any) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, ""
    text = value.strip()
    if not text or text.startswith("${"):
        return False, ""
    if len(text) <= 8:
        return True, "********"
    return True, "********" + text[-4:]


def _is_mask(value: str) -> bool:
    return value.startswith("•") or value.strip().startswith("****")


def _coerce(kind: str, path: str, value: Any) -> Any:
    raw = value
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
    elif kind == "int":
        if isinstance(value, bool):
            value = None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
    elif kind == "float":
        if isinstance(value, bool):
            value = None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                value = None
    elif kind == "str":
        if isinstance(value, str):
            return value
    elif kind == "list":
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return list(value)
    elif kind == "json":
        if isinstance(value, dict):
            return value
    length = len(raw) if isinstance(raw, str) else 0
    raise HTTPException(
        status_code=422,
        detail=(
            f"Invalid value for {path} (source: saved setting): "
            f"expected {kind}, got {length} characters"
        ),
    )


def _effective() -> tuple[dict[str, Any], dict[str, str]]:
    try:
        from ui.config_utils import resolve_config_with_sources

        return resolve_config_with_sources()
    except Exception:
        return {}, {}


def _section_view(section: str) -> dict[str, Any]:
    config, sources = _effective()
    fields: dict[str, dict[str, Any]] = {}
    for path, kind in SECTIONS[section].items():
        value = _get_dotted(config, path)
        source = sources.get(path, "default")
        if kind == "secret":
            has_value, masked = _mask_secret(value)
            fields[path] = {
                "source": source,
                "secret": True,
                "has_value": has_value,
                "masked": masked,
            }
        else:
            fields[path] = {"value": value, "source": source, "secret": False}
    return {"section": section, "fields": fields}


def _require_section(section: str) -> dict[str, str]:
    spec = SECTIONS.get(section)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown config section '{section}'")
    return spec


@router.get("/sources")
def get_config_sources(user=Depends(require_user)) -> dict[str, Any]:
    """Return the winning source for every resolved leaf path, no values."""
    _, sources = _effective()
    return {"sources": sources}


@router.get("/sections/{section}")
def get_config_section(section: str, user=Depends(require_user)) -> dict[str, Any]:
    _require_section(section)
    return _section_view(section)


@router.put("/sections/{section}")
def update_config_section(
    section: str, body: ConfigSectionUpdate, user=Depends(require_user)
) -> dict[str, Any]:
    spec = _require_section(section)
    updates: dict[str, Any] = {}
    for path, value in body.values.items():
        kind = spec.get(path)
        if kind is None:
            continue
        if kind == "secret":
            if not isinstance(value, str) or not value.strip() or _is_mask(value):
                continue
            updates[path] = value
            continue
        updates[path] = _coerce(kind, path, value)

    if updates:
        db = _database()
        full = db.load_config()
        if not isinstance(full, dict):
            full = {}
        for path, value in updates.items():
            _set_dotted(full, path, value)
        db.save_config(full)
    return _section_view(section)
