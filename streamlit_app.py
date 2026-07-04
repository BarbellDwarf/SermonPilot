"""
Streamlit Web UI for SermonAudio Processor

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

from ui.pages import (dashboard, new_sermon, batch_update, validation,
                       jobs, sermon_import, library, analytics, settings)
from ui.shared_navigation import render_sidebar_extras

# Configure Streamlit page
st.set_page_config(
    page_title="SermonAudio Processor",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/SpirusNox/sermon-ai-audio-processor',
        'Report a bug': 'https://github.com/SpirusNox/sermon-ai-audio-processor/issues',
        'About': 'SermonAudio AI Audio Processor - Enhance sermons with AI'
    }
)

# Custom CSS for styling
st.markdown("""
<style>
    /* Dark mode support for system health components */
    [data-theme="dark"] {
        --background-color: rgba(16, 185, 129, 0.15);
        --text-color: #f1f5f9;
        --border-color: rgba(16, 185, 129, 0.3);
    }
    
    [data-theme="light"] {
        --background-color: rgba(16, 185, 129, 0.1);
        --text-color: #334155;
        --border-color: rgba(16, 185, 129, 0.2);
    }
    
    /* Auto-detect dark mode */
    @media (prefers-color-scheme: dark) {
        :root {
            --background-color: rgba(16, 185, 129, 0.15);
            --text-color: #f1f5f9;
            --border-color: rgba(16, 185, 129, 0.3);
        }
    }
    
    @media (prefers-color-scheme: light) {
        :root {
            --background-color: rgba(16, 185, 129, 0.1);
            --text-color: #334155;
            --border-color: rgba(16, 185, 129, 0.2);
        }
    }
    
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .status-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        margin: 0.5rem 0;
    }
    
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    
    .success-text {
        color: #10b981;
        font-weight: bold;
    }
    
    .error-text {
        color: #ef4444;
        font-weight: bold;
    }
    
    .warning-text {
        color: #f59e0b;
        font-weight: bold;
    }
    
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize Streamlit session state variables"""
    if 'config' not in st.session_state:
        st.session_state.config = {}  # Initialize with empty dict instead of None

    if 'llm_manager' not in st.session_state:
        st.session_state.llm_manager = None

    if 'processing_history' not in st.session_state:
        st.session_state.processing_history = []

    if 'current_user' not in st.session_state:
        st.session_state.current_user = "User"

    if 'theme' not in st.session_state:
        st.session_state.theme = "light"

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

def main():
    """Main application entry point"""
    initialize_session_state()

    if not st.session_state.config:
        load_configuration()

    # Restore last page on refresh when URL loses page param
    if 'active_page_url' not in st.session_state:
        st.session_state.active_page_url = None

    # If no page param in URL but we have a stored page, set it in query params
    if 'page' not in st.query_params and st.session_state.active_page_url:
        st.query_params['page'] = st.session_state.active_page_url

    pg = st.navigation({
        "Main": [dashboard, new_sermon, batch_update, validation, jobs],
        "Data & Analytics": [library, analytics],
        "Tools": [sermon_import],
        "Configuration": [settings],
    })
    current_page = pg.run()

    # Store current page URL for refresh resilience
    if current_page and hasattr(current_page, 'url_path'):
        st.session_state.active_page_url = current_page.url_path

    render_sidebar_extras()

if __name__ == "__main__":
    main()
