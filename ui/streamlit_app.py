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

import streamlit as st

# Add project root and src to Python path for imports
project_root = Path(__file__).parent.parent
ui_dir = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

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

def load_configuration():
    """Load configuration from config.yaml"""
    try:
        from sermon_updater import load_config, CONFIG_PATH
        
        config_path = project_root / "config.yaml"
        if not config_path.exists():
            # Try example config
            example_config = project_root / "config.example.yaml"
            if example_config.exists():
                st.warning(f"⚠️ No config.yaml found. Please copy {example_config} to {config_path} and update with your settings.")
                # Return empty config instead of None
                config = {}
                st.session_state.config = config
                return config
            else:
                st.error("❌ No configuration file found. Please create config.yaml.")
                # Return empty config instead of None
                config = {}
                st.session_state.config = config
                return config
        
        config = load_config(str(config_path))
        # Ensure config is never None
        if config is None:
            config = {}
        st.session_state.config = config
        return config
        
    except Exception as e:
        st.error(f"❌ Failed to load configuration: {e}")
        # Return empty config instead of None
        config = {}
        st.session_state.config = config
        return config

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

def render_sidebar():
    """Render sidebar with navigation and status"""
    st.sidebar.markdown('<div class="main-header">🎵 SermonAudio<br>Processor</div>', unsafe_allow_html=True)
    
    # Navigation
    st.sidebar.markdown("### 📋 Navigation")
    
    pages = {
        "📊 Dashboard": "dashboard",
        "🎵 New Sermon": "new_sermon", 
        "🔄 Batch Update": "batch_update",
        "✅ Validation": "validation",
        "📈 Analytics": "analytics",
        "⚙️ Settings": "settings"
    }
    
    # Create navigation buttons
    for page_name, page_key in pages.items():
        if st.sidebar.button(page_name, key=f"nav_{page_key}", width='stretch'):
            st.session_state.current_page = page_key
    
    # System Status
    st.sidebar.markdown("### 🔍 System Status")
    status = check_system_status()
    
    for component, is_healthy in status.items():
        icon = "✅" if is_healthy else "❌"
        color = "success-text" if is_healthy else "error-text"
        st.sidebar.markdown(f'{icon} <span class="{color}">{component.replace("_", " ").title()}</span>', unsafe_allow_html=True)
    
    # Quick Actions
    st.sidebar.markdown("### ⚡ Quick Actions")
    if st.sidebar.button("🔄 Refresh Status", width='stretch'):
        st.rerun()
    
    if st.sidebar.button("📁 Open Config Folder", width='stretch'):
        st.info(f"Config location: {project_root}/config.yaml")

def main():
    """Main application entry point"""
    # Initialize session state
    initialize_session_state()
    
    # Set default page if not set
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'dashboard'
    
    # Load configuration
    if not st.session_state.config:
        load_configuration()
    
    # Render sidebar
    render_sidebar()
    
    # Main content area
    current_page = st.session_state.current_page
    
    if current_page == 'dashboard':
        show_dashboard()
    elif current_page == 'new_sermon':
        show_new_sermon()
    elif current_page == 'batch_update':
        show_batch_update()
    elif current_page == 'validation':
        show_validation()
    elif current_page == 'analytics':
        show_analytics()
    elif current_page == 'settings':
        show_settings()
    else:
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