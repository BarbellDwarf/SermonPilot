"""
Configuration utilities for the Streamlit UI

Provides the single configuration resolution path used by the UI, the
engine, and the job executors, plus session state helpers.
"""

import copy
import datetime
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

try:
    from src.core.config import (
        ENV_CONFIG_MAP,
        apply_env_overrides,
        expand_env_value,
    )
except ImportError:  # src dir placed directly on sys.path
    from core.config import (  # type: ignore[no-redef]
        ENV_CONFIG_MAP,
        apply_env_overrides,
        expand_env_value,
    )

# Get project root for config path
project_root = Path(__file__).parent.parent

logger = logging.getLogger(__name__)

CONFIG_SEED_VERSION = 1

INFRA_ONLY_ENV_VARS: dict[str, str] = {
    "DATABASE_URL": "SQLite location consumed directly by ui.database",
    "APP_PASSWORD": "UI authentication consumed directly by ui.auth",
    "ENVIRONMENT": "container runtime label with no in-app consumer",
}

BUILTIN_DEFAULTS: dict[str, Any] = {
    "llm": {
        "primary": {
            "provider": "ollama",
            "ollama": {"host": "http://localhost:11434", "model": "llama3"},
        },
        "fallback": {
            "enabled": True,
            "provider": "openai",
            "ollama": {"host": "http://localhost:11434", "model": "llama3"},
        },
    },
}


def default_cache_root() -> Path:
    """Return the disk-backed cache root: $XDG_CACHE_HOME/sermonpilot or ~/.cache/sermonpilot."""
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
    return base / "sermonpilot"


def sweep_stale_job_files(config: dict | None = None, max_age_hours: float = 24.0) -> None:
    """Delete files and per-job dirs older than max_age_hours under the job temp roots."""
    if not config:
        config = load_config_from_file()
    roots = [
        Path(config.get('upload_dir') or (default_cache_root() / "sermon_uploads")),
        Path(config.get('processing_temp_dir') or (default_cache_root() / "sermon_processing")),
    ]
    output_root = Path(config.get('output_directory') or 'processed_sermons')
    if not output_root.is_absolute():
        output_root = project_root / output_root
    try:
        output_root = output_root.resolve()
    except OSError:
        return
    cutoff = time.time() - max_age_hours * 3600
    for root in roots:
        try:
            resolved = root.resolve()
            if (
                resolved == output_root
                or output_root in resolved.parents
                or resolved in output_root.parents
            ):
                continue
            if not resolved.is_dir():
                continue
            for entry in resolved.iterdir():
                try:
                    is_dir = not entry.is_symlink() and entry.is_dir()
                    if entry.lstat().st_mtime >= cutoff:
                        continue
                    if is_dir:
                        shutil.rmtree(entry, ignore_errors=True)
                    else:
                        entry.unlink(missing_ok=True)
                except OSError:
                    continue
        except OSError:
            continue


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base in place; nested dicts merge, other values replace."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _load_file_layer() -> dict[str, Any]:
    """Load the optional explicit config file layer ($SA_UPDATER_CONFIG).

    Only the path pointed at by SA_UPDATER_CONFIG is honored; config.yaml is
    never required and never read for resolution.
    """
    config_path = os.environ.get("SA_UPDATER_CONFIG")
    if not config_path or not Path(config_path).exists():
        return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load config file %s: %s", config_path, exc)
        return {}


def _expand_env_placeholders(config: dict[str, Any]) -> None:
    """Expand ${VAR} patterns in string leaves of the config in place."""
    for key, value in config.items():
        if isinstance(value, str):
            config[key] = expand_env_value(value)
        elif isinstance(value, dict):
            _expand_env_placeholders(value)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    value[index] = expand_env_value(item)
                elif isinstance(item, dict):
                    _expand_env_placeholders(item)


def _seed_database_from_env(db) -> dict[str, Any] | None:
    """Seed an empty config_cache once from built-in defaults plus env overrides.

    Only runs when the database has never stored a config and at least one
    mapped environment variable is present, so a fresh container started with
    only a .env file persists its settings on first load. Idempotent: once
    app_config exists, this never writes again.
    """
    active_vars = [var for var in ENV_CONFIG_MAP if os.environ.get(var)]
    if not active_vars:
        return None
    seeded = apply_env_overrides(copy.deepcopy(BUILTIN_DEFAULTS))
    db.save_config(seeded)
    db.save_config_meta({
        "seeded_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "version": CONFIG_SEED_VERSION,
        "env_vars": active_vars,
    })
    logger.info(
        "Seeded settings database from environment variables: %s", ", ".join(active_vars)
    )
    return seeded


def _open_database():
    from ui.database import SermonDatabase

    return SermonDatabase()


def _resolve_layers(db=None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Resolve config layers and return (config, db_layer, file_layer).

    Precedence, lowest to highest:
      1. Built-in defaults.
      2. Optional file layer: $SA_UPDATER_CONFIG when that file exists.
      3. SQLite config_cache (app_config row). On a fresh database with
         environment variables present, the env-derived config is seeded into
         the database once (see _seed_database_from_env).
      4. Environment overrides for mapped keys: env always wins over the
         database because it is operator intent for the running process.
      5. ${VAR} / ${VAR:-default} expansion of remaining string values.

    DATABASE_URL, APP_PASSWORD, and ENVIRONMENT are infra-only variables
    consumed directly from the environment and never enter the config dict.
    """
    file_layer = _load_file_layer()
    db_layer: dict[str, Any] | None = None
    if db is None:
        try:
            db = _open_database()
        except Exception as exc:
            logger.warning("Settings database unavailable: %s", exc)
    if db is not None:
        try:
            db_layer = db.load_config()
        except Exception as exc:
            logger.warning("Failed to read settings database: %s", exc)
            db_layer = None
        if db_layer is None:
            db_layer = _seed_database_from_env(db) or {}

    config = copy.deepcopy(BUILTIN_DEFAULTS)
    if file_layer:
        _deep_merge(config, file_layer)
    if db_layer:
        _deep_merge(config, db_layer)
    _expand_env_placeholders(config)
    apply_env_overrides(config)
    return config, db_layer or {}, file_layer


def resolve_config(db=None) -> dict[str, Any]:
    """Resolve the effective configuration; see _resolve_layers for precedence."""
    config, _, _ = _resolve_layers(db)
    return config


def resolve_config_with_sources(db=None) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve the effective configuration and map each leaf path to its source.

    Source is one of 'env', 'file', 'db', or 'default'.
    """
    config, db_layer, file_layer = _resolve_layers(db)
    return config, _config_sources(config, db_layer, file_layer)


def _flatten_leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts into dotted leaf paths; lists count as leaves."""
    leaves: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            leaves.update(_flatten_leaves(item, path))
    elif prefix:
        leaves[prefix] = value
    return leaves


def _config_sources(
    config: dict[str, Any],
    db_layer: dict[str, Any],
    file_layer: dict[str, Any],
) -> dict[str, str]:
    """Map each dotted leaf path of a resolved config to env/file/db/default."""
    env_paths: set[str] = set()
    for env_var, config_paths in ENV_CONFIG_MAP.items():
        if os.environ.get(env_var):
            for config_path in config_paths:
                env_paths.add(".".join(config_path))
    db_leaves = _flatten_leaves(db_layer)
    file_leaves = _flatten_leaves(file_layer)
    sources: dict[str, str] = {}
    for path in _flatten_leaves(config):
        if path in env_paths:
            sources[path] = "env"
        elif path in file_leaves:
            sources[path] = "file"
        elif path in db_leaves:
            sources[path] = "db"
        else:
            sources[path] = "default"
    return sources


def load_config_from_file():
    """Resolve the effective configuration (database, env overrides, defaults).

    config.yaml is never required: resolution reads the settings database,
    applies environment overrides, and falls back to built-in defaults.
    See resolve_config / _resolve_layers for the exact precedence.
    """
    try:
        config, db_layer, file_layer = _resolve_layers()
        sources = _config_sources(config, db_layer, file_layer)
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        try:
            import streamlit as st

            st.error(f"Failed to load configuration: {e}")
        except ImportError:
            pass
        return {}
    _warn_plaintext_api_keys(config, sources)
    return config


def _find_plaintext_api_keys(config: dict) -> list[str]:
    """Return dotted paths of api_key values that are not env placeholders."""
    found: list[str] = []
    for key, value in config.items():
        if key == "api_key" and isinstance(value, str) and value and not value.startswith("${"):
            found.append(key)
        elif isinstance(value, dict):
            for nested in _find_plaintext_api_keys(value):
                found.append(f"{key}.{nested}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    for nested in _find_plaintext_api_keys(item):
                        found.append(f"{key}[{index}].{nested}")
    return found


def _warn_plaintext_api_keys(
    config: dict[str, Any], sources: dict[str, str] | None = None
) -> None:
    """Warn when a secret is stored in the settings database in plaintext.

    Values supplied by environment variables or kept as ${VAR} placeholders
    are fine; anything else in the database layer is plaintext at rest, so
    recommend moving it to the environment instead.
    """
    plaintext_keys = _find_plaintext_api_keys(config)
    if sources is not None:
        plaintext_keys = [path for path in plaintext_keys if sources.get(path) != "env"]
    if not plaintext_keys:
        return
    message = (
        "API keys are stored in plaintext in the settings database "
        f"({', '.join(plaintext_keys)}). "
        "Move them to environment variables, e.g. SERMONAUDIO_API_KEY."
    )
    logger.warning(message)
    try:
        import streamlit as st

        st.warning(message)
    except ImportError:
        pass


def reload_configuration():
    """Re-resolve the effective configuration and update session state"""
    try:
        import streamlit as st

        config = load_config_from_file()

        st.session_state.config = config

        if "llm_manager" in st.session_state:
            st.session_state.llm_manager = None

        return config

    except Exception as e:
        try:
            import streamlit as st

            st.error(f"Failed to reload configuration: {e}")
        except ImportError:
            pass  # Not in Streamlit context
        return {}


def save_config_to_file(config):
    """Persist configuration to the settings database, then reload the session.

    The database is the primary store and survives container recreation. A
    config.yaml export is written only when the file already exists (container
    users often cannot write the app directory); it is never created.
    """
    try:
        try:
            from ui.database import SermonDatabase

            SermonDatabase().save_config(config)
        except Exception as e:
            logger.error("Failed to save configuration to the database: %s", e)
            try:
                import streamlit as st

                st.error(f"Failed to save configuration to the database: {e}")
            except ImportError:
                pass
            return False

        exported = False
        config_path = project_root / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=True)
                exported = True
            except OSError as e:
                logger.warning("Could not export config.yaml: %s", e)

        reload_configuration()

        try:
            import streamlit as st

            message = "Configuration saved to the settings database."
            if exported:
                message += " Exported a copy to config.yaml."
            st.info(message)
        except ImportError:
            pass  # Not in Streamlit context

        return True

    except Exception as e:
        try:
            import streamlit as st

            st.error(f"Failed to save configuration: {e}")
        except ImportError:
            pass  # Not in Streamlit context
        return False
