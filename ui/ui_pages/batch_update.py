"""
Batch Processing Page for SermonPilot

Handles filtering sermons, selecting batches, configuring processing options,
and managing bulk operations with progress tracking.
"""

import datetime
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from ui.pages import jobs

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from sermon_metadata import get_event_types, get_pastors, show_metadata_refresh_section


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

    # Check if there's an active batch job
    job_id = st.session_state.get('current_batch_job_id')
    active_job = None
    is_job_running = False
    
    if job_id:
        try:
            from job_queue import get_job_queue, JobStatus
            job_queue = get_job_queue()
            active_job = job_queue.get_job(job_id)
            if active_job is None:
                # Job not found, clear the session state
                st.session_state.current_batch_job_id = None
                is_job_running = False
            else:
                is_job_running = active_job.status in [JobStatus.QUEUED, JobStatus.RUNNING]
        except Exception as e:
            # If there's any error with job queue, clear the session state
            st.session_state.current_batch_job_id = None
            st.warning(f"⚠️ Could not check job status: {str(e)}")
            active_job = None
            is_job_running = False

    with col1:
        if st.button("▶️ Start Batch", type="primary", width='stretch', disabled=is_job_running):
            start_batch_processing()

    with col2:
        if st.button("⏸️ Pause", width='stretch', disabled=not is_job_running):
            pause_batch_processing()

    with col3:
        if st.button("⏹️ Stop", width='stretch', disabled=not is_job_running):
            stop_batch_processing()

    with col4:
        if st.button("🔄 Reset Queue", width='stretch'):
            reset_batch_queue()

    # Show processing status
    if active_job:
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
    try:
        # Import sermon_updater functions
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        import sermon_updater

        # Get filter values from session state
        start_date = st.session_state.get('batch_start_date')
        end_date = st.session_state.get('batch_end_date')
        speaker_filter_custom = st.session_state.get('batch_speaker_filter_custom', '').strip()
        speaker_filter_select = st.session_state.get('batch_speaker_filter_select', 'All')
        event_type_filter = st.session_state.get('batch_event_filter', 'All')
        content_requirement = st.session_state.get('batch_content_filter', 'Any')

        # Determine speaker filter
        speaker_filter = None
        if speaker_filter_select != "All":
            speaker_filter = speaker_filter_select
        elif speaker_filter_custom:
            speaker_filter = speaker_filter_custom

        # Use real SermonAudio API
        with st.spinner('🔍 Searching SermonAudio...'):
            progress_bar = st.progress(0)
            progress_bar.progress(0.2)

            # Use the existing date range function from sermon_updater
            if start_date and end_date:
                start_str = start_date.strftime('%Y-%m-%d')
                end_str = end_date.strftime('%Y-%m-%d')
                sermons = sermon_updater.get_sermons_in_date_range(start_str, end_str)
            else:
                # Default to last 30 days
                end_date = datetime.date.today()
                start_date = end_date - datetime.timedelta(days=30)
                start_str = start_date.strftime('%Y-%m-%d')
                end_str = end_date.strftime('%Y-%m-%d')
                sermons = sermon_updater.get_sermons_in_date_range(start_str, end_str)

            progress_bar.progress(0.6)

            # Filter results based on criteria
            filtered_sermons = []
            for sermon in sermons:
                # Apply speaker filter
                if speaker_filter and sermon.get('speakerName'):
                    if speaker_filter.lower() not in sermon['speakerName'].lower():
                        continue

                # Apply event type filter
                if event_type_filter != "All" and sermon.get('eventType'):
                    if event_type_filter != sermon['eventType']:
                        continue

                # Convert to UI format
                filtered_sermons.append({
                    'sermon_id': sermon.get('sermonID', ''),
                    'title': sermon.get('displayTitle', 'Untitled'),
                    'speaker': sermon.get('speakerName', 'Unknown'),
                    'date': sermon.get('preachDate', ''),
                    'event_type': sermon.get('eventType', ''),
                    'has_description': False,  # TODO: Check actual metadata
                    'has_hashtags': False,    # TODO: Check actual metadata
                    'has_audio': True,        # Assume true from API
                    'duration': 0             # Not available in lite API
                })

            # Apply content filters
            if content_requirement == "Missing Description":
                filtered_sermons = [s for s in filtered_sermons if not s['has_description']]
            elif content_requirement == "Missing Hashtags":
                filtered_sermons = [s for s in filtered_sermons if not s['has_hashtags']]
            elif content_requirement == "Both Missing":
                filtered_sermons = [s for s in filtered_sermons if not s['has_description'] and not s['has_hashtags']]

            progress_bar.progress(1.0)
            progress_bar.empty()

            st.session_state.search_results = filtered_sermons
            st.success(f"✅ Found {len(filtered_sermons)} matching sermons")

    except Exception as e:
        st.error(f"❌ Error searching sermons: {str(e)}")
        # Fallback to empty results
        st.session_state.search_results = []

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
    """Start batch processing using job queue"""
    try:
        from job_queue import JobType, get_job_queue
        
        # Get selected sermons
        selected_sermons = st.session_state.get('selected_sermons', [])
        if not selected_sermons:
            st.error("❌ No sermons selected for batch processing")
            return
            
        # Get current configuration from session state
        config = st.session_state.get('config', {})
        if not config:
            st.error("❌ No configuration loaded. Please check the Settings page first.")
            st.info("💡 Try going to Settings → Configuration and saving your settings, then return to this page.")
            return

        # Validate that essential config fields are present
        required_fields = ['api_key', 'broadcaster_id']
        missing_fields = [field for field in required_fields if not config.get(field)]
        if missing_fields:
            st.error(f"❌ Configuration is missing required fields: {', '.join(missing_fields)}")
            st.info("Please go to Settings → Configuration and ensure all required fields are filled out.")
            return
            
        # Get sermon IDs
        sermon_ids = [sermon['sermon_id'] for sermon in selected_sermons]
        
        # Get processing actions from session state
        actions = {
            'generate_description': st.session_state.get('batch_update_descriptions', False),
            'generate_hashtags': st.session_state.get('batch_update_hashtags', False),
            'enhance_audio': st.session_state.get('batch_process_audio', False),
            'validate_content': st.session_state.get('batch_validate_content', False)
        }
        
        # Check if any actions are selected
        if not any(actions.values()):
            st.error("❌ No processing actions selected. Please select at least one action to perform.")
            return
        
        # Create batch processing job
        job_queue = get_job_queue()
        
        action_names = [k.replace('_', ' ').title() for k, v in actions.items() if v]
        job_title = f"Batch Processing: {len(sermon_ids)} sermons"
        job_description = f"Processing {len(sermon_ids)} sermons with actions: {', '.join(action_names)}"
        
        job_id = job_queue.add_job(
            job_type=JobType.BATCH_PROCESSING,
            title=job_title,
            description=job_description,
            parameters={
                'sermon_ids': sermon_ids,
                'actions': actions,
                'config': config
            },
            priority=6  # Medium-high priority for batch processing
        )
        
        # Store job ID in session state for tracking
        st.session_state.current_batch_job_id = job_id
        
        st.success(f"✅ Batch processing job created! Job ID: {job_id[:8]}")
        st.info(f"🔍 Processing {len(sermon_ids)} sermons in the background. You can monitor progress on the Jobs page.")
        
        # Add button to go to jobs page
        if st.button("📊 View Job Progress", type="secondary"):
            st.switch_page(jobs)
            
    except Exception as e:
        st.error(f"❌ Failed to start batch processing job: {e}")

def pause_batch_processing():
    """Pause batch processing job (cancels it since pause is not supported)"""
    job_id = st.session_state.get('current_batch_job_id')
    if job_id:
        try:
            from job_queue import get_job_queue
            job_queue = get_job_queue()
            if job_queue.cancel_job(job_id):
                st.session_state.current_batch_job_id = None
                st.warning("⏸️ Batch processing job cancelled (pause not supported)")
            else:
                st.warning("⚠️ Could not cancel job (may not be running)")
        except Exception as e:
            st.error(f"❌ Failed to cancel job: {e}")
    else:
        st.warning("⚠️ No active batch processing job found")

def stop_batch_processing():
    """Cancel batch processing job"""
    job_id = st.session_state.get('current_batch_job_id')
    if job_id:
        try:
            from job_queue import get_job_queue
            job_queue = get_job_queue()
            job_queue.cancel_job(job_id)
            st.session_state.current_batch_job_id = None
            st.error("⏹️ Batch processing job cancelled")
        except Exception as e:
            st.error(f"❌ Failed to cancel job: {e}")
    else:
        st.warning("⚠️ No active batch processing job found")

def reset_batch_queue():
    """Reset batch processing state"""
    st.session_state.current_batch_job_id = None
    st.session_state.selected_sermons = []
    st.success("🔄 Batch queue reset")

def show_batch_progress():
    """Show real-time batch processing progress from job queue"""
    st.markdown("#### 🔄 Processing Progress")

    job_id = st.session_state.get('current_batch_job_id')
    if not job_id:
        st.info("No active batch processing job")
        return
        
    try:
        from job_queue import get_job_queue, JobStatus
        job_queue = get_job_queue()
        job = job_queue.get_job(job_id)
        
        if not job:
            st.warning("⚠️ Batch processing job not found")
            st.session_state.current_batch_job_id = None
            return
            
        # Show progress bar
        progress_bar = st.progress(job.progress / 100.0)
        
        # Show status
        status_colors = {
            JobStatus.QUEUED: "🔵",
            JobStatus.RUNNING: "🟡", 
            JobStatus.COMPLETED: "🟢",
            JobStatus.FAILED: "🔴",
            JobStatus.CANCELLED: "⚫",
            JobStatus.PAUSED: "🟠"
        }
        
        status_icon = status_colors.get(job.status, "❓")
        st.text(f"{status_icon} Status: {job.status.value.title()}")
        st.text(f"Progress: {job.progress:.1f}%")
        
        # Show recent logs
        if job.logs:
            with st.expander("📋 Recent Activity", expanded=False):
                for log in job.logs[-5:]:  # Show last 5 log entries
                    st.text(log)
        
        # Clear job ID if completed
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            if st.button("Clear Completed Job"):
                st.session_state.current_batch_job_id = None
                st.rerun()
                
    except Exception as e:
        st.error(f"❌ Error checking job progress: {e}")
        st.session_state.current_batch_job_id = None

def export_sermon_list():
    """Export sermon list"""
    st.info("📥 Sermon list export is coming in a future update")

def export_results_csv():
    """Export results as CSV"""
    st.info("📥 CSV export is coming in a future update")

def generate_batch_report():
    """Generate processing report"""
    st.info("📄 Report generation is coming in a future update")

if __name__ == "__main__":
    show_batch_update()
