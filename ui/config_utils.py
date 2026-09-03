"""
Configuration utilities for the Streamlit UI

Provides functions for loading and reloading configuration with proper
session state management.
"""

import logging
import os
import shutil
import time
from pathlib import Path

import yaml

# Get project root for config path
project_root = Path(__file__).parent.parent


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

        # Prefer settings saved in the database (survives container recreation)
        try:
            from ui.database import SermonDatabase

            db = SermonDatabase()
            db_config = db.load_config()
            if db_config:
                # Restore config.yaml from DB so file-based tools still work
                with open(config_path, "w") as f:
                    yaml.dump(db_config, f, default_flow_style=False, sort_keys=True)
        except Exception:
            pass

        config = None

        if config_path.exists():
            config = load_config(str(config_path))
        else:
            # Try loading from database cache (survives Docker/git resets)
            try:
                from ui.database import SermonDatabase

                db = SermonDatabase()
                config = db.load_config()
                if config:
                    # Restore config.yaml from DB so file-based tools still work
                    with open(config_path, "w") as f:
                        yaml.dump(config, f, default_flow_style=False, sort_keys=True)
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
        _warn_plaintext_api_keys()
        return config

    except Exception as e:
        try:
            import streamlit as st

            st.error(f"Failed to load configuration: {e}")
        except ImportError:
            pass
        return {}


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
    except ImportError:
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
        except ImportError:
            pass  # Not in Streamlit context
        return {}


def save_config_to_file(config):
    """Save configuration to config.yaml file and database, then reload in session"""
    try:
        config_path = project_root / "config.yaml"

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=True)

        # Also save to database so settings survive config.yaml loss (Docker, git, etc.)
        try:
            from ui.database import SermonDatabase

            db = SermonDatabase()
            db.save_config(config)
        except Exception:
            pass  # DB save is best-effort

        # Reload the configuration from file to ensure consistency
        reload_configuration()

        try:
            import streamlit as st

            st.info(f"Configuration saved to {config_path}")
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
