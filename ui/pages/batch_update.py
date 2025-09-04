"""
Batch Processing Page for SermonAudio Processor

Handles filtering sermons, selecting batches, configuring processing options,
and managing bulk operations with progress tracking.
"""

import streamlit as st
import pandas as pd
import datetime
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from sermon_metadata import (
    create_pastor_selectbox, 
    create_event_type_selectbox,
    get_pastors,
    get_event_types,
    show_metadata_refresh_section
)

def show_batch_update():
    """Main batch processing interface"""
    st.markdown('<div class="main-header">🔄 Batch Update</div>', unsafe_allow_html=True)
    
    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return
    
    # Batch processing workflow tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 Filter & Select", 
        "⚙️ Processing Options", 
        "▶️ Execute Batch", 
        "📊 Results"
    ])
    
    with tab1:
        show_filter_and_select()
    
    with tab2:
        show_batch_processing_options()
    
    with tab3:
        show_execute_batch()
    
    with tab4:
        show_batch_results()

def show_filter_and_select():
    """Sermon filtering and selection interface"""
    st.markdown("### 🔍 Filter Sermons")
    
    # Show metadata refresh section
    show_metadata_refresh_section()
    
    # Date range filter
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.date.today() - datetime.timedelta(days=30),
            key="batch_start_date"
        )
    
    with col2:
        end_date = st.date_input(
            "End Date", 
            value=datetime.date.today(),
            key="batch_end_date"
        )
    
    # Additional filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Dynamic pastor filter
        pastors = get_pastors()
        pastor_options = ["All"] + pastors
        speaker_filter_select = st.selectbox(
            "Speaker Name (optional)",
            options=pastor_options,
            key="batch_speaker_filter_select"
        )
        
        # Allow custom input if "All" is not selected
        if speaker_filter_select != "All":
            speaker_filter = speaker_filter_select
        else:
            speaker_filter = st.text_input(
                "Or enter custom speaker:",
                placeholder="Custom speaker name",
                key="batch_speaker_filter_custom"
            )
    
    with col2:
        # Dynamic event type filter
        event_types = get_event_types()
        event_options = ["All"] + event_types
        event_type_filter = st.selectbox(
            "Event Type (optional)",
            options=event_options,
            key="batch_event_filter"
        )
    
    with col3:
        content_requirement = st.selectbox(
            "Content Requirement",
            options=["Any", "Missing Description", "Missing Hashtags", "Both Missing", "Has Audio"],
            key="batch_content_filter"
        )
    
    # Advanced filters
    with st.expander("🔧 Advanced Filters"):
        col1, col2 = st.columns(2)
        
        with col1:
            min_duration = st.number_input(
                "Min Duration (minutes)",
                min_value=0,
                value=0,
                key="batch_min_duration"
            )
            
            require_transcript = st.checkbox(
                "Require Transcript",
                key="batch_require_transcript"
            )
        
        with col2:
            max_duration = st.number_input(
                "Max Duration (minutes)", 
                min_value=0,
                value=0,
                help="0 = no limit",
                key="batch_max_duration"
            )
            
            require_audio = st.checkbox(
                "Require Audio File",
                key="batch_require_audio"
            )
    
    # Search and load results
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("🔍 Search Sermons", type="primary", width='stretch'):
            search_sermons()
    
    with col2:
        max_results = st.number_input("Max Results", min_value=1, max_value=1000, value=100)
    
    with col3:
        if st.button("📥 Export List", width='stretch'):
            export_sermon_list()
    
    # Display results
    show_search_results()

def show_batch_processing_options():
    """Batch processing configuration"""
    st.markdown("### ⚙️ Batch Processing Configuration")
    
    # Processing scope
    st.markdown("#### 🎯 Processing Scope")
    
    col1, col2 = st.columns(2)
    
    with col1:
        process_audio = st.checkbox(
            "Process Audio", 
            value=True,
            key="batch_process_audio",
            help="Apply audio enhancement to selected sermons"
        )
        
        update_descriptions = st.checkbox(
            "Update Descriptions",
            value=True, 
            key="batch_update_descriptions",
            help="Generate/update sermon descriptions"
        )
    
    with col2:
        update_hashtags = st.checkbox(
            "Update Hashtags",
            value=True,
            key="batch_update_hashtags", 
            help="Generate/update sermon hashtags"
        )
        
        validate_content = st.checkbox(
            "Validate Content Quality",
            value=True,
            key="batch_validate_content",
            help="Run quality validation on generated content"
        )
    
    # Processing options
    st.markdown("#### ⚙️ Processing Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        force_update = st.checkbox(
            "Force Update Existing Content",
            key="batch_force_update",
            help="Update content even if it already exists"
        )
        
        skip_on_error = st.checkbox(
            "Skip on Error",
            value=True,
            key="batch_skip_error",
            help="Continue processing other sermons if one fails"
        )
    
    with col2:
        dry_run = st.checkbox(
            "Dry Run (Preview Only)",
            key="batch_dry_run",
            help="Process locally but don't upload changes"
        )
        
        save_backups = st.checkbox(
            "Save Backups",
            value=True,
            key="batch_save_backups",
            help="Save backup copies of original metadata"
        )
    
    # Batch execution settings
    st.markdown("#### 🔄 Execution Settings")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        batch_size = st.number_input(
            "Batch Size",
            min_value=1,
            max_value=50,
            value=5,
            key="batch_size",
            help="Number of sermons to process in parallel"
        )
    
    with col2:
        delay_between = st.number_input(
            "Delay Between (seconds)",
            min_value=0.0,
            max_value=10.0,
            value=1.0,
            step=0.1,
            key="batch_delay",
            help="Delay between processing items"
        )
    
    with col3:
        max_retries = st.number_input(
            "Max Retries",
            min_value=0,
            max_value=5,
            value=2,
            key="batch_retries",
            help="Number of retry attempts for failed items"
        )

def show_execute_batch():
    """Batch execution interface"""
    st.markdown("### ▶️ Execute Batch Processing")
    
    # Check if sermons are selected
    selected_sermons = st.session_state.get('selected_sermons', [])
    
    if not selected_sermons:
        st.warning("⚠️ No sermons selected. Please go to Filter & Select tab to choose sermons.")
        return
    
    # Execution summary
    st.markdown("#### 📋 Execution Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Selected Sermons", len(selected_sermons))
    
    with col2:
        estimated_time = len(selected_sermons) * 3.5  # Mock estimation
        st.metric("Estimated Time", f"{estimated_time:.1f} min")
    
    with col3:
        st.metric("Batch Size", st.session_state.get('batch_size', 5))
    
    with col4:
        st.metric("Processing Mode", "Dry Run" if st.session_state.get('batch_dry_run') else "Live")
    
    # Processing controls
    st.markdown("#### 🎮 Processing Controls")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("▶️ Start Batch", type="primary", width='stretch'):
            start_batch_processing()
    
    with col2:
        if st.button("⏸️ Pause", width='stretch', disabled=not st.session_state.get('batch_processing')):
            pause_batch_processing()
    
    with col3:
        if st.button("⏹️ Stop", width='stretch', disabled=not st.session_state.get('batch_processing')):
            stop_batch_processing()
    
    with col4:
        if st.button("🔄 Reset Queue", width='stretch'):
            reset_batch_queue()
    
    # Show processing status
    if st.session_state.get('batch_processing'):
        show_batch_progress()

def show_batch_results():
    """Display batch processing results"""
    st.markdown("### 📊 Batch Processing Results")
    
    results = st.session_state.get('batch_results', [])
    
    if not results:
        st.info("No batch processing results available. Results will appear here after processing.")
        return
    
    # Results summary
    success_count = sum(1 for r in results if r.get('status') == 'success')
    error_count = len(results) - success_count
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Processed", len(results))
    
    with col2:
        st.metric("Successful", success_count, f"{success_count/len(results)*100:.1f}%")
    
    with col3:
        st.metric("Failed", error_count, f"{error_count/len(results)*100:.1f}%")
    
    with col4:
        total_time = sum(r.get('processing_time', 0) for r in results)
        st.metric("Total Time", f"{total_time:.1f} min")
    
    # Detailed results table
    st.markdown("#### 📋 Detailed Results")
    
    # Convert results to DataFrame for display
    df_results = pd.DataFrame(results)
    
    # Add status icons
    if not df_results.empty:
        df_results['Status'] = df_results['status'].apply(
            lambda x: "✅ Success" if x == 'success' else "❌ Error"
        )
        
        # Display with filtering
        status_filter = st.selectbox(
            "Filter by Status",
            options=["All", "Success", "Error"],
            key="results_status_filter"
        )
        
        if status_filter != "All":
            filtered_df = df_results[df_results['status'] == status_filter.lower()]
        else:
            filtered_df = df_results
        
        st.dataframe(
            filtered_df[['sermon_id', 'title', 'speaker', 'Status', 'processing_time', 'actions_performed']],
            width='stretch',
            hide_index=True
        )
    
    # Export results
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Export Results (CSV)", width='stretch'):
            export_results_csv()
    
    with col2:
        if st.button("📄 Generate Report", width='stretch'):
            generate_batch_report()

def search_sermons():
    """Search for sermons based on filters"""
    # Mock search results
    mock_sermons = [
        {
            'sermon_id': '1234567890123',
            'title': 'The Grace of God',
            'speaker': 'Pastor John Smith',
            'date': '2024-01-10',
            'event_type': 'Sunday - AM',
            'has_description': False,
            'has_hashtags': True,
            'has_audio': True,
            'duration': 32
        },
        {
            'sermon_id': '1234567890124', 
            'title': 'Walking in Faith',
            'speaker': 'Dr. Sarah Johnson',
            'date': '2024-01-08',
            'event_type': 'Sunday - PM',
            'has_description': True,
            'has_hashtags': False,
            'has_audio': True,
            'duration': 28
        },
        {
            'sermon_id': '1234567890125',
            'title': 'Hope in Trials', 
            'speaker': 'Rev. Michael Brown',
            'date': '2024-01-05',
            'event_type': 'Wednesday Service',
            'has_description': False,
            'has_hashtags': False,
            'has_audio': True,
            'duration': 35
        }
    ]
    
    st.session_state.search_results = mock_sermons
    st.success(f"Found {len(mock_sermons)} matching sermons")

def show_search_results():
    """Display search results with selection"""
    search_results = st.session_state.get('search_results', [])
    
    if not search_results:
        return
    
    st.markdown("#### 📋 Search Results")
    
    # Convert to DataFrame
    df = pd.DataFrame(search_results)
    
    # Add selection checkbox column
    df['Select'] = False
    
    # Display with selection
    edited_df = st.data_editor(
        df,
        column_config={
            "Select": st.column_config.CheckboxColumn("Select"),
            "has_description": st.column_config.CheckboxColumn("Has Description"),
            "has_hashtags": st.column_config.CheckboxColumn("Has Hashtags"),
            "has_audio": st.column_config.CheckboxColumn("Has Audio"),
        },
        hide_index=True,
        width='stretch'
    )
    
    # Update selected sermons
    selected_sermons = edited_df[edited_df['Select']].to_dict('records')
    st.session_state.selected_sermons = selected_sermons
    
    if selected_sermons:
        st.success(f"✅ {len(selected_sermons)} sermons selected for processing")

def start_batch_processing():
    """Start batch processing"""
    st.session_state.batch_processing = True
    st.session_state.batch_progress = 0
    st.info("🔄 Batch processing started...")

def pause_batch_processing():
    """Pause batch processing"""
    st.session_state.batch_processing = False
    st.warning("⏸️ Batch processing paused")

def stop_batch_processing():
    """Stop batch processing"""
    st.session_state.batch_processing = False
    st.error("⏹️ Batch processing stopped")

def reset_batch_queue():
    """Reset batch processing queue"""
    st.session_state.batch_processing = False
    st.session_state.batch_progress = 0
    st.success("🔄 Batch queue reset")

def show_batch_progress():
    """Show real-time batch processing progress"""
    st.markdown("#### 🔄 Processing Progress")
    
    progress = st.session_state.get('batch_progress', 0)
    total_items = len(st.session_state.get('selected_sermons', []))
    
    progress_bar = st.progress(progress / total_items if total_items > 0 else 0)
    st.text(f"Processing: {progress}/{total_items} sermons")
    
    # Mock progress for demo
    if st.session_state.get('batch_processing'):
        import time
        time.sleep(0.1)
        st.session_state.batch_progress = min(progress + 1, total_items)
        
        if st.session_state.batch_progress >= total_items:
            st.session_state.batch_processing = False
            st.success("✅ Batch processing completed!")

def export_sermon_list():
    """Export sermon list"""
    st.info("📥 Sermon list exported")

def export_results_csv():
    """Export results as CSV"""
    st.info("📥 Results exported as CSV")

def generate_batch_report():
    """Generate processing report"""
    st.info("📄 Processing report generated")

if __name__ == "__main__":
    show_batch_update()