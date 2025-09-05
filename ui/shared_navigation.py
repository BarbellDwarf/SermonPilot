"""
Shared Navigation Component for SermonAudio Processor

Provides consistent navigation across all pages with system status monitoring.
"""

import streamlit as st
from datetime import datetime
from pathlib import Path
import sys

# Add paths
ui_dir = Path(__file__).parent
project_root = ui_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

def render_shared_sidebar():
    """Render shared sidebar navigation for all pages"""
    st.sidebar.markdown(
        '<div style="font-size: 2rem; font-weight: bold; color: #1E3A8A; margin-bottom: 1rem; text-align: center;">🎵 SermonAudio<br>Processor</div>', 
        unsafe_allow_html=True
    )
    
    # Navigation - Single continuous section
    st.sidebar.markdown("### 📋 Navigation")
    
    # Get current page
    current_page = st.session_state.get('current_page', 'dashboard')
    
    # All pages in one continuous list
    navigation_pages = [
        ("📊 Dashboard", "dashboard", "streamlit_app.py"),
        ("🎵 New Sermon", "new_sermon", "streamlit_app.py"), 
        ("🔄 Batch Update", "batch_update", "streamlit_app.py"),
        ("✅ Validation", "validation", "streamlit_app.py"),
        ("📚 Library", "library", "pages/07_📚_Library.py"),
        ("📖 Viewer", "viewer", "pages/08_📖_Viewer.py"), 
        ("📈 Analytics", "analytics", "pages/09_📈_Analytics.py"),
        ("⚙️ Settings", "settings", "streamlit_app.py")
    ]
    
    for page_name, page_key, page_file in navigation_pages:
        # Use primary button style for new pages
        button_type = "primary" if page_key in ['library', 'viewer', 'analytics'] else "secondary"
        button_key = f"nav_{page_key}_{page_file.replace('/', '_').replace('.py', '')}"
        
        if st.sidebar.button(page_name, key=button_key, use_container_width=True, type=button_type):
            st.session_state.current_page = page_key
            
            # Navigate to appropriate page
            if page_file.startswith("pages/"):
                st.switch_page(page_file)
            else:
                # For main app pages, redirect to main app with page state
                st.switch_page("streamlit_app.py")
    
    # Enhanced System Status
    render_system_status()
    
    # Quick Actions
    render_quick_actions()

def render_system_status():
    """Render system status section"""
    st.sidebar.markdown("### 🔍 System Status")
    
    # Get comprehensive status
    try:
        from system_status import get_status_manager, get_status_emoji
        
        # Load config
        config = load_config_safely()
        status_manager = get_status_manager(config)
        
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
                    
                    # Create compact status display
                    status_text = f"{emoji} {display_name}"
                    if status_info['status'] == 'error':
                        st.sidebar.error(status_text)
                    elif status_info['status'] == 'warning':
                        st.sidebar.warning(status_text)
                    else:
                        st.sidebar.success(status_text)
            
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
        st.sidebar.caption(f"Error: {str(e)}")

def render_quick_actions():
    """Render quick actions section"""
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

def load_config_safely():
    """Safely load configuration with fallback"""
    try:
        import yaml
        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
    except Exception:
        pass
    return {}

def initialize_session_state():
    """Initialize session state variables"""
    if 'config' not in st.session_state:
        st.session_state.config = load_config_safely()
    
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'dashboard'
    
    if 'processing_history' not in st.session_state:
        st.session_state.processing_history = []
    
    if 'current_user' not in st.session_state:
        st.session_state.current_user = "User"
    
    if 'theme' not in st.session_state:
        st.session_state.theme = "light"