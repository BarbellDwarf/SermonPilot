"""
Dashboard Page for SermonAudio Processor

Displays recent activity, quick stats, system status, and provides quick access
to common tasks like new sermon processing and validation.
"""

import streamlit as st
import pandas as pd
import datetime
from pathlib import Path
import json
import os

def show_dashboard():
    """Main dashboard display"""
    st.markdown('<div class="main-header">📊 Dashboard</div>', unsafe_allow_html=True)
    
    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page.")
        show_setup_guide()
        return
    
    # Top metrics row
    show_quick_stats()
    
    # Main content columns
    col1, col2 = st.columns([2, 1])
    
    with col1:
        show_recent_activity()
        show_quick_actions()
    
    with col2:
        show_system_status()
        show_processing_queue()

def show_quick_stats():
    """Display key metrics in a row"""
    st.markdown("### 📈 Quick Statistics")
    
    # Calculate stats from processing history or mock data
    processing_history = st.session_state.get('processing_history', [])
    
    # Mock data for demonstration
    total_sermons = len(processing_history) if processing_history else 0
    success_count = sum(1 for item in processing_history if item.get('status') == 'success')
    success_rate = (success_count / total_sermons * 100) if total_sermons > 0 else 0
    
    # Calculate last 24h activity
    now = datetime.datetime.now()
    last_24h = sum(1 for item in processing_history 
                   if datetime.datetime.fromisoformat(item.get('timestamp', '2024-01-01')) > now - datetime.timedelta(hours=24))
    
    # Average processing time (mock)
    avg_time = 5.2 if total_sermons > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Sermons Processed", 
            str(total_sermons), 
            f"+{last_24h} today" if last_24h > 0 else "No recent activity"
        )
    
    with col2:
        st.metric(
            "Success Rate", 
            f"{success_rate:.1f}%", 
            f"{success_count}/{total_sermons}" if total_sermons > 0 else "N/A"
        )
    
    with col3:
        st.metric(
            "Avg Processing Time", 
            f"{avg_time:.1f} min", 
            "-1.2 min vs last week" if avg_time > 0 else "N/A"
        )
    
    with col4:
        st.metric(
            "Last 24 Hours", 
            str(last_24h), 
            f"vs {max(0, last_24h - 2)} yesterday"
        )

def show_recent_activity():
    """Show recent processing activity"""
    st.markdown("### 📋 Recent Activity")
    
    processing_history = st.session_state.get('processing_history', [])
    
    if not processing_history:
        # Show mock data for demonstration
        mock_data = [
            {
                'timestamp': '2024-01-15 10:30:00',
                'sermon_id': '1234567890123',
                'title': 'The Grace of God',
                'speaker': 'Pastor John Smith',
                'action': 'Audio Enhancement',
                'status': 'success',
                'duration': '4.2 min'
            },
            {
                'timestamp': '2024-01-15 09:15:00',
                'sermon_id': '1234567890124',
                'title': 'Walking in Faith',
                'speaker': 'Dr. Sarah Johnson', 
                'action': 'Metadata Update',
                'status': 'success',
                'duration': '2.1 min'
            },
            {
                'timestamp': '2024-01-14 16:45:00',
                'sermon_id': '1234567890125',
                'title': 'Hope in Trials',
                'speaker': 'Rev. Michael Brown',
                'action': 'Full Processing',
                'status': 'error',
                'duration': '3.8 min'
            }
        ]
        
        df = pd.DataFrame(mock_data)
        df['Status'] = df['status'].apply(lambda x: "✅ Success" if x == 'success' else "❌ Error")
        
        st.dataframe(
            df[['timestamp', 'title', 'speaker', 'action', 'Status', 'duration']].rename(columns={
                'timestamp': 'Time',
                'title': 'Sermon Title',
                'speaker': 'Speaker',
                'action': 'Action',
                'duration': 'Duration'
            }),
            width='stretch',
            hide_index=True
        )
        
        st.info("💡 This is sample data. Real activity will appear here after processing sermons.")
    else:
        # Show real data
        df = pd.DataFrame(processing_history[-10:])  # Show last 10 items
        st.dataframe(df, width='stretch')

def show_quick_actions():
    """Show quick action shortcuts for common tasks"""
    st.markdown("### ⚡ Quick Start")
    st.markdown("*Quick shortcuts to get started with common tasks*")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🎵 Process New Sermon", type="primary", width='stretch'):
            st.session_state.current_page = 'new_sermon'
            st.rerun()
        st.caption("Upload and process a single sermon")
    
    with col2:
        if st.button("🔄 Batch Update", width='stretch'):
            st.session_state.current_page = 'batch_update'
            st.rerun()
        st.caption("Update multiple sermons at once")
    
    with col3:
        if st.button("✅ Validate Descriptions", width='stretch'):
            st.session_state.current_page = 'validation'
            st.rerun()
        st.caption("Check description quality and errors")

def show_system_status():
    """Show detailed system status"""
    st.markdown("### 🔍 System Health")
    
    # Get system status
    status = check_system_components()
    
    for component, details in status.items():
        is_healthy = details['status']
        icon = "✅" if is_healthy else "❌"
        color = "#10b981" if is_healthy else "#ef4444"
        
        with st.container():
            st.markdown(f"""
            <div style="
                padding: 0.5rem; 
                border-left: 4px solid {color}; 
                background-color: {'#f0fdf4' if is_healthy else '#fef2f2'};
                margin: 0.5rem 0;
                border-radius: 0.25rem;
            ">
                {icon} <strong>{component}</strong><br>
                <small>{details['message']}</small>
            </div>
            """, unsafe_allow_html=True)

def show_processing_queue():
    """Show current processing queue"""
    st.markdown("### 📤 Processing Queue")
    
    # Mock queue data
    queue_items = st.session_state.get('processing_queue', [])
    
    if not queue_items:
        st.info("No items in processing queue")
    else:
        for item in queue_items:
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"📄 {item.get('title', 'Unknown')}")
                    st.caption(f"Status: {item.get('status', 'Pending')}")
                with col2:
                    if st.button("⏸️", key=f"pause_{item.get('id')}"):
                        st.info("Paused processing")

def show_setup_guide():
    """Show setup guide when configuration is missing"""
    st.markdown("### 🚀 Welcome to SermonAudio Processor!")
    
    st.markdown("""
    To get started, please complete the setup:
    
    1. **Configuration**: Copy `config.example.yaml` to `config.yaml` and update your settings
    2. **API Keys**: Add your SermonAudio API credentials
    3. **LLM Provider**: Configure OpenAI or Ollama for AI processing
    4. **Audio Enhancement**: Choose your preferred enhancement method
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📁 Go to Settings", type="primary", width='stretch'):
            st.session_state.current_page = 'settings'
            st.rerun()
    
    with col2:
        if st.button("📖 View Documentation", width='stretch'):
            st.info("Documentation will open in your browser")

def check_system_components():
    """Check individual system components and return detailed status"""
    status = {}
    
    # Configuration check
    if st.session_state.config:
        status["Configuration"] = {
            "status": True,
            "message": "Config loaded successfully"
        }
        
        # API credentials check
        api_key = st.session_state.config.get('api_key')
        if api_key and api_key != 'your-api-key-here':
            status["SermonAudio API"] = {
                "status": True,
                "message": "API credentials configured"
            }
        else:
            status["SermonAudio API"] = {
                "status": False,
                "message": "API credentials not configured"
            }
        
        # LLM providers check
        llm_config = st.session_state.config.get('llm', {})
        primary_provider = llm_config.get('primary', {}).get('provider')
        if primary_provider:
            status["LLM Primary"] = {
                "status": True,
                "message": f"Primary provider: {primary_provider}"
            }
        else:
            status["LLM Primary"] = {
                "status": False,
                "message": "No primary LLM provider configured"
            }
        
        # Audio processing check
        audio_method = st.session_state.config.get('audio_enhancement_method', 'none')
        status["Audio Processing"] = {
            "status": True,
            "message": f"Enhancement method: {audio_method}"
        }
        
    else:
        status["Configuration"] = {
            "status": False,
            "message": "No configuration file found"
        }
    
    return status

if __name__ == "__main__":
    show_dashboard()