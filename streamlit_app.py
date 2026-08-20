"""
Streamlit Web UI for SermonPilot

A modern web interface for the SermonAudio AI audio processing pipeline.
Provides intuitive access to sermon processing, batch operations, validation,
analytics, and configuration management.

Features:
- Dashboard with recent activity and system status
- New sermon processing with file upload and metadata forms
- Batch processing with filtering and progress tracking
- Validation dashboard with quality metrics
- Analytics with interactive charts
- Settings management with configuration editing
"""

import os
import sys
import warnings
from pathlib import Path

import streamlit as st

# Suppress PyTorch/Torchaudio warnings before any imports
warnings.filterwarnings('ignore', category=UserWarning, message='.*Torchaudio.*backend.*')
warnings.filterwarnings('ignore', category=UserWarning, message='.*torchaudio.*')
warnings.filterwarnings('ignore', category=UserWarning, message='.*backend dispatch.*')
warnings.filterwarnings('ignore', category=RuntimeWarning)
os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "1"
os.environ["TORCHAUDIO_ENABLE_BACKEND_DISPATCH"] = "1"
os.environ["TORCHAUDIO_BACKEND"] = "soundfile"

# Suppress Windows path warnings
warnings.filterwarnings('ignore', message='.*commonpath.*')
warnings.filterwarnings('ignore', message='.*path.*dispatcher.*')
warnings.filterwarnings('ignore', message=".*Paths don't have the same drive.*")

# Set environment variable to disable problematic file watchers
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

# Add project root and src to Python path for imports
project_root = Path(__file__).parent  # Now we're in the root directory
ui_dir = project_root / "ui"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

from ui.pages import (  # noqa: E402
    analytics,
    batch_update,
    dashboard,
    jobs,
    library,
    new_sermon,
    sermon_import,
    settings,
    validation,
)
from ui.shared_navigation import render_sidebar_extras  # noqa: E402

# Configure Streamlit page
st.set_page_config(
    page_title="SermonPilot",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/BarbellDwarf/SermonPilot',
        'Report a bug': 'https://github.com/BarbellDwarf/SermonPilot/issues',
        'About': 'SermonPilot - Enhance sermons with AI'
    }
)

# Custom CSS for styling
st.markdown("""
<style>
    /* Theme tokens: light is the default, dark overrides follow */
    :root, [data-theme="light"] {
        --header-color: #1e3a8a;
        --surface-color: #ffffff;
        --surface-border: #e5e7eb;
        --muted-text: #475569;
        --card-grad-a: #4f46e5;
        --card-grad-b: #6d28d9;
        --status-ok: #047857;
        --status-warn: #b45309;
        --status-error: #b91c1c;
        --status-progress: #1d4ed8;
        --status-neutral: #475569;
    }

    [data-theme="dark"] {
        --header-color: #93c5fd;
        --surface-color: #141419;
        --surface-border: rgba(255, 255, 255, 0.08);
        --muted-text: #94a3b8;
        --card-grad-a: #4338ca;
        --card-grad-b: #5b21b6;
        --status-ok: #34d399;
        --status-warn: #fbbf24;
        --status-error: #f87171;
        --status-progress: #60a5fa;
        --status-neutral: #94a3b8;
    }

    @media (prefers-color-scheme: dark) {
        :root {
            --header-color: #93c5fd;
            --surface-color: #141419;
            --surface-border: rgba(255, 255, 255, 0.08);
            --muted-text: #94a3b8;
            --card-grad-a: #4338ca;
            --card-grad-b: #5b21b6;
            --status-ok: #34d399;
            --status-warn: #fbbf24;
            --status-error: #f87171;
            --status-progress: #60a5fa;
            --status-neutral: #94a3b8;
        }
    }

    @media (prefers-color-scheme: light) {
        :root {
            --header-color: #1e3a8a;
            --surface-color: #ffffff;
            --surface-border: #e5e7eb;
            --muted-text: #475569;
            --card-grad-a: #4f46e5;
            --card-grad-b: #6d28d9;
            --status-ok: #047857;
            --status-warn: #b45309;
            --status-error: #b91c1c;
            --status-progress: #1d4ed8;
            --status-neutral: #475569;
        }
    }

    .main-header {
        font-size: 2.25rem;
        line-height: 1.3;
        font-weight: bold;
        color: var(--header-color);
        margin: 0 0 1rem;
        text-align: center;
    }

    .status-card {
        background: linear-gradient(135deg, var(--card-grad-a) 0%, var(--card-grad-b) 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        margin: 0.5rem 0;
    }

    .metric-card {
        background: var(--surface-color);
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid var(--surface-border);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .success-text {
        color: var(--status-ok);
        font-weight: bold;
    }

    .error-text {
        color: var(--status-error);
        font-weight: bold;
    }

    .warning-text {
        color: var(--status-warn);
        font-weight: bold;
    }

    /* Status labels: one meaning per colour in both modes */
    .status-ok { color: var(--status-ok); font-weight: 600; }
    .status-warn { color: var(--status-warn); font-weight: 600; }
    .status-error { color: var(--status-error); font-weight: 600; }
    .status-progress { color: var(--status-progress); font-weight: 600; }
    .status-neutral { color: var(--status-neutral); font-weight: 600; }

    /* Library list rows: fixed slot model, one flexible title slot */
    .sermon-title {
        display: block;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .sermon-meta {
        color: var(--muted-text);
        font-size: 0.85rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* Compact, even row rhythm inside the sermon list */
    .st-key-sermon_list {
        gap: 0.2rem;
    }

    /* Pull the page content up under the header bar */
    [data-testid="stMainBlockContainer"] {
        padding-top: 3.75rem;
    }

    /* Sidebar: divide the nav from the status and actions sections */
    [data-testid="stSidebarNav"] {
        border-bottom: 1px solid var(--surface-border);
        padding-bottom: 0.75rem;
        margin-bottom: 0.25rem;
    }

    [data-testid="stSidebar"] h3 {
        border-top: 1px solid var(--surface-border);
        margin-top: 0.5rem;
        padding-top: 0.5rem;
    }

    /* Hide the Streamlit skills promo banner */
    [data-testid="stSkillsNudgeAnchor"] {
        display: none !important;
    }

</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize Streamlit session state variables"""
    if 'config' not in st.session_state:
        st.session_state.config = {}  # Initialize with empty dict instead of None

    # Initialize job queue system
    if 'job_queue_initialized' not in st.session_state:
        try:
            from ui.job_queue import initialize_job_queue
            initialize_job_queue()
            st.session_state.job_queue_initialized = True
        except Exception:
            st.session_state.job_queue_initialized = False
            # Don't show error here as it would be shown on every page load

def load_configuration(force_reload=False):
    """Load configuration from config.yaml"""
    from ui.config_utils import load_config_from_file, reload_configuration

    if force_reload:
        return reload_configuration()
    else:
        config = load_config_from_file()
        st.session_state.config = config
        return config

def reload_configuration():
    """Force reload configuration from file and clear cached objects"""
    from ui.config_utils import reload_configuration as _reload_config
    return _reload_config()

def ensure_metadata_cache_refresh():
    """Start a non-blocking background refresh when the cached metadata is missing or stale."""
    if st.session_state.get('metadata_cache_refresh_started'):
        return
    st.session_state.metadata_cache_refresh_started = True
    try:
        from ui.sermon_metadata import needs_metadata_refresh, refresh_metadata_in_background
        if needs_metadata_refresh():
            refresh_metadata_in_background()
    except Exception:
        pass


def _dashboard_landing():
    """Forward the root URL to the dashboard page."""
    st.switch_page(dashboard)


def main():
    """Main application entry point"""
    initialize_session_state()

    if not st.session_state.config:
        load_configuration()

    ensure_metadata_cache_refresh()

    landing = st.Page(
        _dashboard_landing, title="Dashboard", visibility="hidden"
    )

    pg = st.navigation({
        "Main": [landing, dashboard, new_sermon, batch_update, validation, jobs],
        "Data & Analytics": [library, analytics],
        "Tools": [sermon_import],
        "Configuration": [settings],
    })
    pg.run()

    render_sidebar_extras()

if __name__ == "__main__":
    main()
