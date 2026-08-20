"""
Sidebar extras for SermonPilot

Renders system status and quick actions below the st.navigation() menu.
"""

import sys
from pathlib import Path

import streamlit as st

from ui.auth import is_authenticated, render_login

ui_dir = Path(__file__).parent
project_root = ui_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

if not is_authenticated():
    render_login()
    st.stop()


def render_sidebar_extras():
    """Render system status and quick actions below the nav menu"""
    render_system_status()
    render_queue_status()
    render_quick_actions()


@st.cache_resource(ttl=300)
def _get_cached_status_manager():
    """Cache the status manager for 5 minutes."""
    from system_status import get_status_manager

    config = load_config_safely()
    return get_status_manager(config)


def render_system_status():
    """Render compact system status as a single-line summary with expander."""
    try:
        from system_status import get_status_label

        status_manager = _get_cached_status_manager()

        @st.cache_data(ttl=60)
        def _get_cached_status():
            return status_manager.get_comprehensive_status()

        status_data = _get_cached_status()

        core_components = [
            ("sermonaudio_api", "SermonAudio API"),
            ("database", "Database"),
            ("llm_primary", "Primary LLM"),
            ("audio_enhancement", "Audio Enhancement"),
            ("local_storage", "Local Storage"),
        ]

        error_count = sum(1 for s in status_data.values() if s.get("status") == "error")
        warning_count = sum(1 for s in status_data.values() if s.get("status") == "warning")

        if error_count > 0:
            summary = f"{error_count} errors"
        elif warning_count > 0:
            summary = f"{warning_count} warnings"
        else:
            summary = "All systems OK"

        with st.sidebar.expander(f"System Status — {summary}", expanded=False):
            for status_key, display_name in core_components:
                if status_key in status_data:
                    status_info = status_data[status_key]
                    label = get_status_label(status_info["status"])
                    st.markdown(
                        f"**{display_name}**: {label}  \n{status_info.get('message', '')}",
                        unsafe_allow_html=False,
                    )

    except Exception:
        st.sidebar.warning("Status unavailable")


def render_queue_status():
    """Show a compact job queue line in the sidebar."""
    try:
        from job_queue import JobStatus, get_job_queue

        jq = get_job_queue()
        running = len(jq.get_all_jobs(JobStatus.RUNNING) or [])
        queued = len(jq.get_all_jobs(JobStatus.QUEUED) or [])
        if running:
            st.sidebar.info(f"{running} running, {queued} queued")
        elif queued:
            st.sidebar.info(f"{queued} jobs queued")
    except Exception:
        pass


def render_quick_actions():
    """Render quick actions section"""
    st.sidebar.markdown("### Quick Actions")

    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("Refresh", help="Refresh system status", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    with col2:
        if st.button("Status", help="View detailed system status", width="stretch"):
            render_detailed_status()


def render_detailed_status():
    """Render the full system status for every monitored component."""
    try:
        from system_status import get_status_label

        status_manager = _get_cached_status_manager()
        status_data = status_manager.get_comprehensive_status()

        with st.sidebar.expander("Full System Status", expanded=True):
            for status_key, status_info in status_data.items():
                label = get_status_label(status_info["status"])
                display_name = status_key.replace("_", " ").title()
                st.markdown(
                    f"**{display_name}**: {label}  \n{status_info.get('message', '')}",
                    unsafe_allow_html=False,
                )
    except Exception:
        st.sidebar.warning("Status unavailable")


def load_config_safely():
    """Safely load configuration with fallback and env-var substitution."""
    try:
        import os
        import re

        import yaml
        from dotenv import load_dotenv

        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            load_dotenv(config_path.parent / ".env")
            with open(config_path) as f:
                raw = f.read()
            raw = re.sub(
                r"\${([A-Z0-9_]+)(:-[^}]*)?}",
                lambda m: os.getenv(m.group(1), (m.group(2) or "")[2:] if m.group(2) else ""),
                raw,
            )
            return yaml.safe_load(raw) or {}
    except Exception:
        pass
    return {}
