"""
Configuration utilities for the Streamlit UI

Provides the single configuration resolution path used by the UI, the
engine, and the job executors, plus session state helpers.
"""

import copy
import datetime
import logging
import os
import re
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

API_KEY_ENV_BY_PATH = {
    "api_key": "SERMONAUDIO_API_KEY",
    "transcription.whisper_openai.api_key": "OPENAI_API_KEY",
    "transcription.whisper_openrouter.api_key": "OPENROUTER_API_KEY",
    "embeddings.primary.openai.api_key": "OPENAI_API_KEY",
}

_PROVIDER_ENV_BY_NAME = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _env_var_for_key_path(dotted_path: str) -> str | None:
    """Return the env var backing a dotted ``*.api_key`` path, if known."""
    if dotted_path in API_KEY_ENV_BY_PATH:
        return API_KEY_ENV_BY_PATH[dotted_path]
    parts = dotted_path.split(".")
    if len(parts) >= 2 and parts[-1] == "api_key":
        if len(parts) >= 5 and parts[0] == "llm" and parts[1] == "operations":
            provider = parts[-2]
            if provider == "openai":
                return "AUTO_EDIT_LLM_API_KEY"
            return _PROVIDER_ENV_BY_NAME.get(provider)
        return _PROVIDER_ENV_BY_NAME.get(parts[-2])
    return None


def _is_env_placeholder(value: object) -> bool:
    """True when a config value is an unexpanded ``${VAR}`` reference."""
    return isinstance(value, str) and value.strip().startswith("${")


def _placeholder_for_path(dotted_path: str) -> str:
    env_var = _env_var_for_key_path(dotted_path)
    return "${" + env_var + "}" if env_var else ""


def _sanitize_config_for_file(config: dict) -> dict:
    """Return a copy with no literal API keys.

    Every ``api_key`` leaf becomes its ``${VAR}`` placeholder (or ``""``
    when no env var is known). Placeholders and empty values stay as
    placeholders; literals are never written to ``config.yaml``. The
    caller keeps the original dict for the DB cache, where user-typed
    keys are allowed.
    """
    sanitized = copy.deepcopy(config)

    def walk(node: object, prefix: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                dotted = f"{prefix}.{key}" if prefix else str(key)
                if key == "api_key":
                    if _is_env_placeholder(value):
                        continue
                    if isinstance(value, str) and not value.strip():
                        node[key] = _placeholder_for_path(dotted)
                    elif isinstance(value, str):
                        node[key] = _placeholder_for_path(dotted)
                    elif value is None:
                        node[key] = _placeholder_for_path(dotted)
                else:
                    walk(value, dotted)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{prefix}[{index}]")

    walk(sanitized, "")
    return sanitized


def _is_missing_key_value(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return not stripped or stripped.startswith("${")


def _get_dotted(config: dict, dotted_path: str) -> object:
    node: object = config
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_dotted(config: dict, dotted_path: str, value: object) -> None:
    node = config
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _iter_key_paths(config: object, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(config, dict):
        for key, value in config.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            if key == "api_key":
                paths.append(dotted)
            else:
                paths.extend(_iter_key_paths(value, dotted))
    elif isinstance(config, list):
        for index, item in enumerate(config):
            paths.extend(_iter_key_paths(item, f"{prefix}[{index}]"))
    return paths


def _apply_db_keys(loaded: dict, db_config: dict) -> dict:
    """Overlay DB-cached keys onto a file-loaded config in memory.

    Precedence is environment > DB cache > file. Env wins are already
    applied by the config loader; here a DB value fills in only when
    the loaded value is missing (empty or an unresolved placeholder)
    and the corresponding env var is not set. The file on disk is
    never touched.
    """
    merged = loaded
    for dotted in _iter_key_paths(db_config):
        env_var = _env_var_for_key_path(dotted)
        if env_var and os.getenv(env_var):
            continue
        db_value = _get_dotted(db_config, dotted)
        if not isinstance(db_value, str) or _is_missing_key_value(db_value):
            continue
        if _is_missing_key_value(_get_dotted(merged, dotted)):
            _set_dotted(merged, dotted, db_value)
    return merged


logger = logging.getLogger(__name__)

CONFIG_SEED_VERSION = 1

INFRA_ONLY_ENV_VARS: dict[str, str] = {
    "DATABASE_URL": "SQLite location consumed directly by ui.database",
    "APP_PASSWORD": "UI authentication consumed directly by ui.auth",
    "ENVIRONMENT": "container runtime label with no in-app consumer",
    "STREAMLIT_SERVER_MAX_UPLOAD_SIZE": (
        "Streamlit runtime upload limit, read by the Streamlit server rather than app config"
    ),
}

BUILTIN_PROMPT_TEMPLATES: dict[str, Any] = {
    "title": {
        "enabled": False,
        "system": "",
        "user": (
            "You are a sermon title generator.\n"
            "Create a compelling, descriptive title for this sermon.\n\n"
            "{context}\n\n"
            "Guidelines for the title:\n"
            "- Maximum 85 characters (STRICT LIMIT for API)\n"
            "- Capture the main theme or message\n"
            "- Be specific and engaging, not generic\n"
            "- Avoid cliche Christian phrases\n"
            "- Focus on the practical application or key insight\n"
            "- If a Bible reference is given, you may include it briefly\n"
            "- Do not use quotation marks around the title\n"
            "- Return ONLY the title, no explanation or commentary\n\n"
            "Sermon content (first 1000 characters):\n"
            "{transcript}...\n\n"
            "Generate a compelling sermon title:"
        ),
    },
    "short_title": {
        "enabled": False,
        "system": "",
        "user": (
            "Shorten this sermon title to a concise version\n"
            "(maximum 30 characters, STRICT LIMIT).\n"
            "Keep the core meaning but make it brief. No quotes, no explanation, "
            "just the shortened title.\n\n"
            "Original title: {full_title}\n\n"
            "Shortened title (max 30 chars):"
        ),
    },
    "description": {
        "enabled": False,
        "system": "",
        "user": (
            "You are a {role_desc}. Read the following {body_desc} transcript and write a single, "
            "concise description of the main message and application. Focus on what "
            "the speaker wanted the audience to understand, believe, or do. "
            "Avoid generic statements; emphasize unique focus.\n\n"
            "Transcript:\n{transcript}\n\nGuidelines:\n"
            "- Target 900 to 1200 characters; stay under 1400 (the API rejects text over 1700)\n"
            "- One paragraph format\n"
            "{speaker_instruction}"
            "- No intro/closing words\n- No markdown or bullets\n"
            "- Do not prefix with 'Summary:'\n- If incomplete, infer likely main message\n"
            "- Keep within the target length or the upload will fail\n"
            "- Use the actual speaker name, not placeholder text\n"
            "- Include specific scripture references, source material, and concrete "
            "examples from the transcript\n"
            "- Mention the specific doctrines, rules, or texts the speaker expounded\n"
            "- Describe the practical application the speaker gave\n"
            "- IMPORTANT: Return ONLY the final summary paragraph. Do not include any reasoning, "
            "thinking process, explanations, or commentary. "
            "Start directly with the summary content."
        ),
    },
    "hashtags": {
        "enabled": False,
        "system": "",
        "user": (
            "Generate 5-10 highly relevant, search-friendly hashtags (<=150 chars total) for this "
            "sermon. Combine multi-word phrases (#ChristianLiving). Avoid duplicates & generic "
            "(#sermon #church) unless uniquely relevant. Output ONLY space-delimited hashtags.\n\n"
            "Text:\n{text}\n\nHashtags:"
        ),
    },
    "hashtag_verification": {
        "enabled": False,
        "system": "",
        "user": (
            "You are a hashtag validator. Your job is to extract ONLY valid hashtags "
            "from the input below. "
            "Rules:\n"
            "1. Output ONLY hashtags (words starting with #)\n"
            "2. Remove any comments, explanations, or non-hashtag text\n"
            "3. Keep hashtags space-separated\n"
            "4. Maximum 150 characters total\n"
            "5. If you see obvious formatting issues, fix them\n"
            "6. If no valid hashtags found, generate 3-5 relevant ones for the sermon topic\n\n"
            "Original sermon topic context: {original_text}...\n\n"
            "Hashtag input to verify:\n{initial_hashtags}\n\n"
            "Valid hashtags only:"
        ),
    },
}

BUILTIN_DEFAULTS: dict[str, Any] = {
    "llm": {
        "primary": {
            "provider": "ollama",
            "ollama": {"host": "http://localhost:11434"},
        },
        "fallback": {
            "enabled": True,
            "provider": "openai",
            "ollama": {"host": "http://localhost:11434"},
        },
    },
    "embeddings": {
        "primary": {
            "provider": "sentence_transformers",
            "model": "all-MiniLM-L6-v2",
            "dimensions": 384,
            "ollama": {
                "host": "http://localhost:11434",
                "model": "nomic-embed-text",
                "auto_download": True,
            },
        },
    },
    "prompt_templates": BUILTIN_PROMPT_TEMPLATES,
}


def default_cache_root() -> Path:
    """Return the disk-backed cache root: $XDG_CACHE_HOME/sermonpilot or ~/.cache/sermonpilot."""
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
    return base / "sermonpilot"


def sweep_stale_job_files(config: dict | None = None, max_age_hours: float = 24.0) -> None:
    """Delete files and per-job dirs older than max_age_hours under the job temp roots.

    The uploads root is filtered to the engine's own upload names (epoch-ms
    prefix) so a custom upload_dir pointed at real media stays untouched; the
    processing root is swept wholesale (per-job uuid dirs). A job with a silent
    phase longer than max_age_hours could in principle have its live directory
    swept; 24h makes that practically impossible.
    """
    if not config:
        config = load_config_from_file()
    upload_root = Path(
        config.get('upload_dir') or (default_cache_root() / "sermon_uploads")
    )
    processing_root = Path(
        config.get('processing_temp_dir') or (default_cache_root() / "sermon_processing")
    )
    roots = [
        (upload_root, True),
        (processing_root, False),
    ]
    output_root = Path(config.get('output_directory') or 'processed_sermons')
    if not output_root.is_absolute():
        output_root = project_root / output_root
    try:
        output_root = output_root.resolve()
    except OSError:
        return
    cutoff = time.time() - max_age_hours * 3600
    for root, uploads_only in roots:
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
                    if uploads_only and not re.match(r"^\d{10,}_", entry.name):
                        continue
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


def _variant_template_layer() -> dict[str, Any]:
    """Load the built-in variant template for this image flavor, if present.

    Docker images ship config/templates/{cpu,cuda,rocm}.yaml (SERMONPILOT_VARIANT
    selects one). A fresh install seeds from this template so the settings page
    starts populated with variant-appropriate choices instead of blank defaults.
    Values keep their ${VAR} placeholders: resolution expands them at read time,
    so environment changes keep applying after seeding.
    """
    variant = os.environ.get("SERMONPILOT_VARIANT")
    if not variant:
        return {}
    candidates = [
        Path("/app/config/templates") / f"{variant}.yaml",
        project_root / "config" / "templates" / f"{variant}.yaml",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Failed to load variant template %s: %s", path, exc)
            return {}
        if isinstance(data, dict):
            logger.info("Variant template layer loaded from %s", path)
            return data
        return {}
    return {}


def _seed_database_from_env(db) -> dict[str, Any] | None:
    """Seed an empty config_cache once from defaults plus the variant template
    plus env overrides.

    Only runs when the database has never stored a config, and when there is
    something to seed: at least one mapped environment variable or a built-in
    variant template. A fresh container started with only a .env file persists
    its settings on first load, with variant-appropriate choices already in
    place. Idempotent: once app_config exists, this never writes again.
    """
    active_vars = [var for var in ENV_CONFIG_MAP if os.environ.get(var)]
    template_layer = _variant_template_layer()
    if not active_vars and not template_layer:
        return None
    base = copy.deepcopy(BUILTIN_DEFAULTS)
    if template_layer:
        _deep_merge(base, template_layer)
    seeded = apply_env_overrides(base)
    try:
        db.save_config(seeded)
        db.save_config_meta({
            "seeded_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "version": CONFIG_SEED_VERSION,
            "env_vars": active_vars,
            "variant": os.environ.get("SERMONPILOT_VARIANT", ""),
        })
    except Exception as exc:
        logger.warning("Could not persist env seeding to the settings database: %s", exc)
        return seeded
    logger.info(
        "Seeded settings database from environment variables and variant template: %s",
        ", ".join(active_vars) or "no env vars",
    )
    return seeded


def _migrate_legacy_config_yaml(db) -> None:
    """Import config.yaml into the settings database once, for existing installs.

    Config resolution no longer reads config.yaml (ticket #201 demoted it to
    an explicit import/export artifact). This carries hand-tuned settings from
    pre-existing local installs across that change. Skipped when
    $SA_UPDATER_CONFIG is set (the test harness owns the file layer) and when
    the database already holds a config or a seed marker.
    """
    if os.environ.get("SA_UPDATER_CONFIG"):
        return
    try:
        if db.load_config_meta() or db.load_config():
            return
        legacy = project_root / "config.yaml"
        if not legacy.exists():
            return
        migrated = yaml.safe_load(legacy.read_text()) or {}
        if not isinstance(migrated, dict) or not migrated:
            return
        db.save_config(migrated)
        logger.info("Imported legacy config.yaml into the settings database")
    except Exception as exc:
        logger.warning("Legacy config.yaml import skipped: %s", exc)


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
    try:
        from dotenv import load_dotenv

        load_dotenv(project_root / ".env")
    except ImportError:
        pass
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
            _migrate_legacy_config_yaml(db)
            db_layer = db.load_config()
            if db_layer is None:
                db_layer = _seed_database_from_env(db) or {}

    config = copy.deepcopy(BUILTIN_DEFAULTS)
    template_layer = _variant_template_layer()
    if template_layer:
        _deep_merge(config, template_layer)
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
    """Return dotted paths of api_key values that are not env placeholders.

    Empty, whitespace-only, and ``${VAR}`` values are not plaintext: they
    mean the key lives in the environment or the DB cache. Anything else
    is a literal that must not be stored in config.yaml.
    """
    found: list[str] = []
    for key, value in config.items():
        if key == "api_key" and isinstance(value, str):
            stripped = value.strip()
            if stripped and not stripped.startswith("${"):
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


def _env_var_for_path(path: str) -> str | None:
    """Return the environment variable that maps to a dotted config path."""
    from core.config import ENV_CONFIG_MAP

    for env_var, config_paths in ENV_CONFIG_MAP.items():
        for config_path in config_paths:
            if ".".join(config_path) == path:
                return env_var
    return None


def _warn_plaintext_api_keys(
    config: dict[str, Any] | None = None, sources: dict[str, str] | None = None
) -> None:
    """Warn when an API key is stored in plaintext.

    The resolver calls this with the effective config and its sources.
    Called with no arguments it inspects config.yaml on disk, which is the
    console's pre-resolution path.
    """
    if config is None:
        config_path = project_root / "config.yaml"
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            return
        sources = None
    plaintext_keys = _find_plaintext_api_keys(config)
    if sources is not None:
        plaintext_keys = [path for path in plaintext_keys if sources.get(path) != "env"]
    if not plaintext_keys:
        return
    suggestions = []
    for path in plaintext_keys:
        env_var = _env_var_for_key_path(path)
        suggestions.append(f"{path} -> {env_var}" if env_var else path)
    message = (
        "API keys are stored in plaintext in config.yaml "
        f"({', '.join(suggestions)}). "
        "Set the listed environment variables to keep them out of the file and database."
    )
    logger.warning(message)
    try:
        import streamlit as st

        st.warning(message)
    except Exception:
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
    """Save configuration to config.yaml file and database, then reload in session.

    The file copy is sanitized: every ``api_key`` leaf is stored as its
    ``${VAR}`` placeholder so literals never land in config.yaml. The
    database keeps the full dict (user-typed keys are allowed there) and
    is overlaid in memory on load, with environment variables winning.
    """
    try:
        config_path = project_root / "config.yaml"

        with open(config_path, "w") as f:
            yaml.dump(
                _sanitize_config_for_file(config), f, default_flow_style=False, sort_keys=True
            )

        # Also save to database so settings survive config.yaml loss (Docker, git, etc.)
        try:
            from ui.database import SermonDatabase

            db = SermonDatabase()
            db.save_config(config)
        except Exception:
            pass  # DB save is best-effort

        # Reload the configuration from file to ensure consistency
        try:
            reload_configuration()
        except Exception:
            pass

        try:
            import streamlit as st

            st.info(f"Configuration saved to {config_path}")
        except Exception:
            pass  # Not in Streamlit context

        return True

    except Exception as e:
        try:
            import streamlit as st

            st.error(f"Failed to save configuration: {e}")
        except Exception:
            pass  # Not in Streamlit context
        return False
