"""
Configuration utilities for the Streamlit UI

Provides functions for loading and reloading configuration with proper
session state management.
"""

from pathlib import Path

import yaml

# Get project root for config path
project_root = Path(__file__).parent.parent

def load_config_from_file():
    """Load configuration from config.yaml file, falling back to database cache."""
    try:
        import sys
        sys.path.insert(0, str(project_root))
        from sermon_updater import load_config

        config_path = project_root / "config.yaml"
        config = None

        if config_path.exists():
            config = load_config(str(config_path))
        else:
            # Try loading from database cache (survives Docker/git resets)
            try:
                from database import SermonDatabase
                db = SermonDatabase()
                config = db.load_config()
                if config:
                    # Restore config.yaml from DB so file-based tools still work
                    with open(config_path, 'w') as f:
                        yaml.dump(config, f, default_flow_style=False, sort_keys=True)
            except Exception:
                pass

        if config is None:
            # Try example config
            example_config = project_root / "config.example.yaml"
            if example_config.exists():
                try:
                    import streamlit as st
                    st.warning(f"⚠️ No config.yaml found. Please copy {example_config} to {config_path} and update with your settings.")
                except ImportError:
                    pass
                return {}
            else:
                try:
                    import streamlit as st
                    st.error("❌ No configuration file found. Please create config.yaml.")
                except ImportError:
                    pass
                return {}

        # Ensure config is never None
        if config is None:
            config = {}
        return config

    except Exception as e:
        try:
            import streamlit as st
            st.error(f"❌ Failed to load configuration: {e}")
        except ImportError:
            pass
        return {}

def reload_configuration():
    """Force reload configuration from file and update session state"""
    try:
        import streamlit as st

        # Load fresh config from file
        config = load_config_from_file()

        # Update session state
        st.session_state.config = config

        # Clear cached objects that depend on config
        if 'llm_manager' in st.session_state:
            st.session_state.llm_manager = None

        return config

    except Exception as e:
        try:
            import streamlit as st
            st.error(f"❌ Failed to reload configuration: {e}")
        except ImportError:
            pass  # Not in Streamlit context
        return {}

def save_config_to_file(config):
    """Save configuration to config.yaml file and database, then reload in session"""
    try:
        config_path = project_root / "config.yaml"

        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=True)

        # Also save to database so settings survive config.yaml loss (Docker, git, etc.)
        try:
            from database import SermonDatabase
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
