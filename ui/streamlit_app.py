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
project_root = Path(__file__).parent.parent
ui_dir = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

from shared_navigation import render_shared_sidebar

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
    
    .sidebar .sidebar-content {
        background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
    }
    
    /* Continuous navigation styling */
    .sidebar .stButton > button {
        margin-bottom: 0.25rem;
        border-radius: 0.5rem;
        transition: all 0.2s ease;
    }
    
    .sidebar .stButton > button[data-baseweb="button"][kind="primary"] {
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        border: none;
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
    }
    
    .sidebar .stButton > button[data-baseweb="button"][kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(59, 130, 246, 0.4);
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
            from job_queue import initialize_job_queue
            initialize_job_queue()
            st.session_state.job_queue_initialized = True
        except Exception:
            st.session_state.job_queue_initialized = False
            # Don't show error here as it would be shown on every page load

def load_configuration(force_reload=False):
    """Load configuration from config.yaml"""
    from config_utils import load_config_from_file, reload_configuration

    if force_reload:
        return reload_configuration()
    else:
        config = load_config_from_file()
        st.session_state.config = config
        return config

def reload_configuration():
    """Force reload configuration from file and clear cached objects"""
    from config_utils import reload_configuration as _reload_config
    return _reload_config()

def check_system_status():
    """Check system status and dependencies"""
    status = {
        "config": False,
        "llm_primary": False,
        "llm_fallback": False,
        "audio_processing": False,
        "api_connection": False
    }

    # Check configuration
    if st.session_state.config:
        status["config"] = True

        # Check LLM providers
        try:
            from src.llm_manager import LLMManager
            llm_manager = LLMManager(st.session_state.config)
            st.session_state.llm_manager = llm_manager

            if llm_manager.primary_provider:
                status["llm_primary"] = True
            if llm_manager.fallback_provider:
                status["llm_fallback"] = True

        except Exception as e:
            st.sidebar.warning(f"LLM Manager Error: {e}")

        # Check audio processing
        try:
            from src.audio_processing import AudioProcessor
            processor = AudioProcessor()
            status["audio_processing"] = True
        except Exception as e:
            st.sidebar.warning(f"Audio Processing Error: {e}")

    return status

def main():
    """Main application entry point"""
    # Initialize session state
    initialize_session_state()

    # Load configuration
    if not st.session_state.config:
        load_configuration()

    # Render shared sidebar navigation
    render_shared_sidebar()

    # Main content area - show the appropriate page based on session state
    current_page = st.session_state.get('current_page', 'dashboard')

    if current_page == 'dashboard':
        show_dashboard()
    elif current_page == 'new_sermon':
        show_new_sermon()
    elif current_page == 'batch_update':
        show_batch_update()
    elif current_page == 'validation':
        show_validation()
    elif current_page == 'jobs':
        show_jobs()
    elif current_page == 'library':
        show_library()
    elif current_page == 'analytics':
        show_analytics()
    elif current_page == 'settings':
        show_settings()
    else:
        # Default to dashboard
        show_dashboard()

def show_dashboard():
    """Dashboard page"""
    try:
        from ui_pages.dashboard import show_dashboard as dashboard_main
        dashboard_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">📊 Dashboard</div>', unsafe_allow_html=True)
        st.error("❌ Dashboard module not found. Please check the installation.")

def show_new_sermon():
    """New sermon page"""
    try:
        from ui_pages.new_sermon import show_new_sermon as new_sermon_main
        new_sermon_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">🎵 New Sermon</div>', unsafe_allow_html=True)
        st.error("❌ New sermon module not found. Please check the installation.")

def show_batch_update():
    """Batch update page"""
    try:
        from ui_pages.batch_update import show_batch_update as batch_main
        batch_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">🔄 Batch Update</div>', unsafe_allow_html=True)
        st.error("❌ Batch update module not found. Please check the installation.")

def show_validation():
    """Validation page"""
    try:
        from ui_pages.validation import show_validation as validation_main
        validation_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">✅ Validation</div>', unsafe_allow_html=True)
        st.error("❌ Validation module not found. Please check the installation.")

def show_jobs():
    """Jobs page"""
    try:
        from ui_pages.jobs import show_jobs as jobs_main
        jobs_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">⚙️ Jobs</div>', unsafe_allow_html=True)
        st.error("❌ Jobs module not found. Please check the installation.")

def show_library():
    """Library page"""
    try:
        from ui_pages.library import show_library as library_main
        library_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">📚 Library</div>', unsafe_allow_html=True)
        st.error("❌ Library module not found. Please check the installation.")

def show_analytics():
    """Analytics page"""
    try:
        from ui_pages.analytics import show_analytics as analytics_main
        analytics_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">📈 Analytics</div>', unsafe_allow_html=True)
        st.error("❌ Analytics module not found. Please check the installation.")

def show_settings():
    """Settings page"""
    try:
        from ui_pages.settings import show_settings as settings_main
        settings_main()
    except ImportError:
        # Fallback if pages module not available
        st.markdown('<div class="main-header">⚙️ Settings</div>', unsafe_allow_html=True)
        st.error("❌ Settings module not found. Please check the installation.")

if __name__ == "__main__":
    main()
