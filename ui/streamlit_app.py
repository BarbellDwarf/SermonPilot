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

from datetime import datetime

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

def render_sidebar():
    """Render enhanced sidebar with comprehensive system status"""
    st.sidebar.markdown('<div class="main-header">🎵 SermonAudio<br>Processor</div>', unsafe_allow_html=True)
    
    # Navigation - Single continuous section
    st.sidebar.markdown("### 📋 Navigation")
    
    # All pages in one continuous list
    all_pages = {
        "📊 Dashboard": "dashboard",
        "🎵 New Sermon": "new_sermon", 
        "🔄 Batch Update": "batch_update",
        "✅ Validation": "validation",
        "📚 Library 🆕": "library",
        "📖 Viewer 🆕": "viewer", 
        "📈 Analytics 🆕": "analytics",
        "⚙️ Settings": "settings"
    }
    
    for page_name, page_key in all_pages.items():
        # Use primary button style for new pages
        button_type = "primary" if page_key in ['library', 'viewer', 'analytics'] else "secondary"
        
        if st.sidebar.button(page_name, key=f"nav_{page_key}", use_container_width=True, type=button_type):
            st.session_state.current_page = page_key
            if page_key == 'library':
                st.switch_page("pages/07_📚_Library.py")
            elif page_key == 'viewer':
                st.switch_page("pages/08_📖_Viewer.py")
            elif page_key == 'analytics':
                st.switch_page("pages/09_📈_Analytics.py")
    
    # Enhanced System Status
    st.sidebar.markdown("### 🔍 System Status")
    
    # Get comprehensive status
    try:
        from system_status import get_status_manager, get_status_emoji
        status_manager = get_status_manager(st.session_state.config)
        
        # Check if we should refresh status (every 60 seconds)
        current_time = datetime.now()
        if ('last_status_check' not in st.session_state or 
            (current_time - st.session_state.last_status_check).seconds > 60):
            
            with st.sidebar:
                with st.spinner("Checking system status..."):
                    comprehensive_status = status_manager.get_comprehensive_status()
                    st.session_state.system_status = comprehensive_status
                    st.session_state.last_status_check = current_time
        
        # Display status from cache
        if 'system_status' in st.session_state:
            status_data = st.session_state.system_status
            
            # Core system components
            core_components = [
                ('sermonaudio_api', 'SermonAudio API'),
                ('database', 'Database'),
                ('llm_primary', 'Primary LLM'),
                ('audio_enhancement', 'Audio Enhancement'),
                ('local_storage', 'Local Storage')
            ]
            
            for status_key, display_name in core_components:
                if status_key in status_data:
                    status_info = status_data[status_key]
                    emoji = get_status_emoji(status_info['status'])
                    
                    # Create expandable status item
                    with st.sidebar.expander(f"{emoji} {display_name}", expanded=False):
                        st.write(f"**Status:** {status_info['status'].title()}")
                        st.write(f"**Message:** {status_info['message']}")
                        if status_info.get('details'):
                            st.caption(status_info['details'])
                        st.caption(f"Last checked: {status_info['timestamp'].strftime('%H:%M:%S')}")
            
            # Overall system health indicator
            error_count = sum(1 for s in status_data.values() if s.get('status') == 'error')
            warning_count = sum(1 for s in status_data.values() if s.get('status') == 'warning')
            
            if error_count > 0:
                st.sidebar.error(f"⚠️ {error_count} system errors detected")
            elif warning_count > 0:
                st.sidebar.warning(f"⚠️ {warning_count} warnings")
            else:
                st.sidebar.success("✅ All systems operational")
        
    except Exception as e:
        # Fallback to basic status check
        st.sidebar.warning("⚠️ Status monitoring unavailable")
        status = check_system_status()
        
        for component, is_healthy in status.items():
            icon = "✅" if is_healthy else "❌"
            color = "success-text" if is_healthy else "error-text"
            st.sidebar.markdown(f'{icon} <span class="{color}">{component.replace("_", " ").title()}</span>', unsafe_allow_html=True)
    
    # Quick Actions
    st.sidebar.markdown("### ⚡ Quick Actions")
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("🔄 Refresh", help="Refresh system status", use_container_width=True):
            # Clear status cache to force refresh
            if 'system_status' in st.session_state:
                del st.session_state.system_status
            if 'last_status_check' in st.session_state:
                del st.session_state.last_status_check
            st.rerun()
    
    with col2:
        if st.button("📊 Status", help="View detailed system status", use_container_width=True):
            st.session_state.show_detailed_status = True
            st.rerun()
    
    # Show detailed status modal if requested
    if st.session_state.get('show_detailed_status', False):
        show_detailed_status_modal()
    
    if st.sidebar.button("📁 Config", help="Show config file location", use_container_width=True):
        st.sidebar.info(f"Config: {project_root}/config.yaml")

def show_detailed_status_modal():
    """Show detailed system status in a modal"""
    if 'system_status' in st.session_state:
        st.subheader("🔍 Detailed System Status")
        
        status_data = st.session_state.system_status
        
        # Create tabs for different categories
        tabs = st.tabs(["🔗 Connectivity", "💾 Storage", "🤖 AI Services", "⚙️ System"])
        
        with tabs[0]:  # Connectivity
            st.markdown("#### SermonAudio API")
            if 'sermonaudio_api' in status_data:
                display_status_details(status_data['sermonaudio_api'])
            
            st.markdown("#### Database Connection") 
            if 'database' in status_data:
                display_status_details(status_data['database'])
        
        with tabs[1]:  # Storage
            st.markdown("#### Local Storage")
            if 'local_storage' in status_data:
                display_status_details(status_data['local_storage'])
            
            st.markdown("#### Processing Queue")
            if 'processing_queue' in status_data:
                display_status_details(status_data['processing_queue'])
        
        with tabs[2]:  # AI Services
            st.markdown("#### Primary LLM Provider")
            if 'llm_primary' in status_data:
                display_status_details(status_data['llm_primary'])
            
            st.markdown("#### Fallback LLM Provider")
            if 'llm_fallback' in status_data:
                display_status_details(status_data['llm_fallback'])
            
            st.markdown("#### Audio Enhancement")
            if 'audio_enhancement' in status_data:
                display_status_details(status_data['audio_enhancement'])
        
        with tabs[3]:  # System
            st.markdown("#### System Resources")
            if 'system_resources' in status_data:
                display_status_details(status_data['system_resources'])
        
        if st.button("✖️ Close", type="primary"):
            st.session_state.show_detailed_status = False
            st.rerun()

def display_status_details(status_info):
    """Display detailed status information"""
    from system_status import get_status_emoji
    
    emoji = get_status_emoji(status_info['status'])
    status_color = {
        'ok': 'green',
        'warning': 'orange', 
        'error': 'red',
        'processing': 'blue'
    }.get(status_info['status'], 'gray')
    
    st.markdown(f"""
    **Status:** {emoji} ::{status_color}[{status_info['status'].upper()}]  
    **Message:** {status_info['message']}  
    **Details:** {status_info.get('details', 'No additional details')}  
    **Last Updated:** {status_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}
    """)
    
    st.divider()

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
    elif current_page == 'library':
        # Redirect to Library page
        st.switch_page("pages/07_📚_Library.py")
    elif current_page == 'viewer':
        # Redirect to Viewer page  
        st.switch_page("pages/08_📖_Viewer.py")
    elif current_page == 'analytics':
        # Redirect to Analytics page
        st.switch_page("pages/09_📈_Analytics.py")
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