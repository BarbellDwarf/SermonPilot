"""
Configuration utilities for the Streamlit UI

Provides functions for loading and reloading configuration with proper
session state management.
"""

import copy
import logging
import os
from pathlib import Path

import yaml

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


def load_config_from_file():
    """Load configuration with precedence: environment > database cache > config.yaml.

    The database config_cache holds the latest settings saved from the UI and is
    restored to config.yaml so file-based tooling stays consistent. ConfigManager
    then re-applies environment variable overrides on top, so env vars always win.
    """
    try:
        import sys

        sys.path.insert(0, str(project_root))
        from sermon_updater import load_config

        config_path = project_root / "config.yaml"
        example_config = project_root / "config" / "config.example.yaml"

        # Prefer settings saved in the database (survives container recreation).
        # The file on disk always keeps ${VAR} placeholders; user-typed keys
        # live in the DB cache and are overlaid in memory below.
        db_config = None
        try:
            from ui.database import SermonDatabase

            db = SermonDatabase()
            db_config = db.load_config()
            if db_config:
                sanitized = _sanitize_config_for_file(db_config)
                if sanitized != db_config or not config_path.exists():
                    with open(config_path, "w") as f:
                        yaml.dump(sanitized, f, default_flow_style=False, sort_keys=True)
        except Exception:
            pass

        config = None

        if config_path.exists():
            config = load_config(str(config_path))
        elif db_config:
            config = copy.deepcopy(db_config)
            try:
                with open(config_path, "w") as f:
                    yaml.dump(
                        _sanitize_config_for_file(db_config),
                        f,
                        default_flow_style=False,
                        sort_keys=True,
                    )
            except Exception:
                pass

        if config is None:
            # Try example config
            if example_config.exists():
                try:
                    import streamlit as st

                    st.warning(
                        f"No config.yaml found. Please copy {example_config} to {config_path} "
                        "and update with your settings."
                    )
                except ImportError:
                    pass
                return {}
            else:
                try:
                    import streamlit as st

                    st.error("No configuration file found. Please create config.yaml.")
                except ImportError:
                    pass
                return {}

        # Ensure config is never None
        if config is None:
            config = {}
        if db_config:
            config = _apply_db_keys(config, db_config)
        _warn_plaintext_api_keys()
        return config

    except Exception as e:
        try:
            import streamlit as st

            st.error(f"Failed to load configuration: {e}")
        except Exception:
            pass
        return {}


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


def _warn_plaintext_api_keys() -> None:
    """Log a warning when API keys are stored in plaintext in config.yaml."""
    config_path = project_root / "config.yaml"
    try:
        with open(config_path) as f:
            raw_config = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return
    plaintext_keys = _find_plaintext_api_keys(raw_config)
    if not plaintext_keys:
        return
    message = (
        "API keys are stored in plaintext in config.yaml. "
        "Move them to environment variables, e.g. SERMONAUDIO_API_KEY."
    )
    logging.warning(message)
    try:
        import streamlit as st

        st.warning(message)
    except Exception:
        pass


def reload_configuration():
    """Force reload configuration from file and update session state"""
    try:
        import streamlit as st

        # Load fresh config from file
        config = load_config_from_file()

        # Update session state
        st.session_state.config = config

        # Clear cached objects that depend on config
        if "llm_manager" in st.session_state:
            st.session_state.llm_manager = None

        return config

    except Exception as e:
        try:
            import streamlit as st

            st.error(f"Failed to reload configuration: {e}")
        except Exception:
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
