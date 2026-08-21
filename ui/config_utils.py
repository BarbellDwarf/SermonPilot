"""
Configuration utilities for the Streamlit UI

Provides functions for loading and reloading configuration with proper
session state management.
"""

import logging
from pathlib import Path

import yaml

# Get project root for config path
project_root = Path(__file__).parent.parent


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
