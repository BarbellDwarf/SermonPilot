"""
Jobs Page - Monitor and manage background jobs

Provides a comprehensive interface for viewing, managing, and monitoring
all background jobs in the SermonAudio Processor system.

Features:
- Real-time job status monitoring
- Job progress tracking with visual indicators
- Job logs and detailed information
- Job management (cancel, retry, clear)
- Job queue statistics and health monitoring
- Automatic refresh for live updates
"""

import time
from datetime import datetime, timedelta

import streamlit as st

# Import job queue components at module level
try:
    from job_queue import JobStatus, JobType, get_job_queue
    JOB_QUEUE_AVAILABLE = True
except ImportError as e:
    st.error(f"❌ Job queue system not available: {e}")
    JOB_QUEUE_AVAILABLE = False
    # Define dummy enums to prevent errors
    class JobStatus:
        RUNNING = "running"
        QUEUED = "queued"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"
        PAUSED = "paused"

    class JobType:
        SERMON_PROCESSING = "sermon_processing"
        BATCH_PROCESSING = "batch_processing"
        SERMON_IMPORT = "sermon_import"
        VALIDATION = "validation"

def show_jobs():
    """Main jobs monitoring interface"""
    st.markdown('<div class="main-header">⚙️ Background Jobs</div>', unsafe_allow_html=True)

    if not JOB_QUEUE_AVAILABLE:
        st.error("❌ Job queue system is not available")
        st.info("Please check that the job queue dependencies are properly installed.")
        return

    try:
        # Initialize job queue
        job_queue = get_job_queue()

        # Auto-refresh setup with more frequent updates for running jobs
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = time.time()

        # Auto-refresh every 2 seconds for active jobs, 10 seconds otherwise
        active_jobs = job_queue.get_all_jobs(JobStatus.RUNNING)
        refresh_interval = 2 if active_jobs else 10
        
        if time.time() - st.session_state.last_refresh > refresh_interval:
            st.session_state.last_refresh = time.time()
            st.rerun()

        # Create sidebar for controls and overview
        with st.sidebar:
            st.markdown("### 🎛️ Controls")
            
            if st.button("🔄 Refresh", type="primary", use_container_width=True):
                st.rerun()

            if st.button("🧹 Clear Completed", type="secondary", use_container_width=True):
                cleared = job_queue.clear_completed_jobs()
                st.success(f"Cleared {cleared} completed jobs")
                st.rerun()

            if st.button("➕ Test Job", type="secondary", use_container_width=True):
                add_test_job(job_queue)
                st.rerun()

            st.markdown("---")
            
            # Quick overview in sidebar
            st.markdown("### 📊 Quick Stats")
            all_jobs = job_queue.get_all_jobs()
            running_count = len([j for j in all_jobs if j.status == JobStatus.RUNNING])
            queued_count = len([j for j in all_jobs if j.status == JobStatus.QUEUED])
            completed_count = len([j for j in all_jobs if j.status == JobStatus.COMPLETED])
            failed_count = len([j for j in all_jobs if j.status == JobStatus.FAILED])
            
            # Compact metrics in sidebar
            st.metric("🔄 Running", running_count)
            st.metric("⏳ Queued", queued_count)
            st.metric("✅ Completed", completed_count)
            st.metric("❌ Failed", failed_count)
            
            # Auto-refresh indicator with more information
            if active_jobs:
                st.info(f"🔄 Auto-refresh: every 2s\\n📊 {len(active_jobs)} job(s) running")
            else:
                st.info("⏸️ Auto-refresh: every 10s\\n😴 No active jobs")

        # Main content area with compact tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            f"🔄 Active ({running_count + queued_count})",
            f"✅ Completed ({completed_count})",
            f"❌ Failed ({failed_count})",
            "📊 Stats"
        ])

        with tab1:
            show_active_jobs_compact(job_queue)

        with tab2:
            show_completed_jobs_compact(job_queue)

        with tab3:
            show_failed_jobs_compact(job_queue)

        with tab4:
            show_queue_statistics_compact(job_queue)

    except ImportError as e:
        st.error(f"❌ Job queue system not available: {e}")
        st.info("The background job system requires additional setup.")
    except Exception as e:
        st.error(f"❌ Error loading jobs interface: {e}")
        st.info("Please check the job queue system and try again.")


def show_active_jobs_compact(job_queue):
    """Show currently running and queued jobs in compact format"""
    # Get running and queued jobs
    running_jobs = job_queue.get_all_jobs(JobStatus.RUNNING)
    queued_jobs = job_queue.get_all_jobs(JobStatus.QUEUED)

    if not running_jobs and not queued_jobs:
        st.info("No active jobs. All background processes are idle.")
        return

    # Show running jobs first
    if running_jobs:
        st.markdown("#### 🟡 Currently Running")
        for job in running_jobs:
            show_job_card_compact(job, job_queue, show_actions=True)

    # Show queued jobs
    if queued_jobs:
        st.markdown("#### ⏳ Queued Jobs")
        for job in queued_jobs:
            show_job_card_compact(job, job_queue, show_actions=True)


def show_completed_jobs_compact(job_queue):
    """Show completed jobs in compact format"""
    completed_jobs = job_queue.get_all_jobs(JobStatus.COMPLETED)

    if not completed_jobs:
        st.info("No completed jobs found.")
        return

    # Show most recent first
    completed_jobs.sort(key=lambda j: j.completed_at or j.created_at, reverse=True)

    for job in completed_jobs[:10]:  # Show last 10 completed jobs
        show_job_card_compact(job, job_queue, show_actions=False)


def show_failed_jobs_compact(job_queue):
    """Show failed jobs with retry options in compact format"""
    failed_jobs = job_queue.get_all_jobs(JobStatus.FAILED)

    if not failed_jobs:
        st.success("No failed jobs! 🎉")
        return

    # Show most recent first
    failed_jobs.sort(key=lambda j: j.completed_at or j.created_at, reverse=True)

    for job in failed_jobs:
        show_job_card_compact(job, job_queue, show_actions=True, highlight_errors=True)


def show_queue_statistics_compact(job_queue):
    """Show detailed queue statistics in compact format"""
    st.markdown("### 📊 Queue Statistics")

    all_jobs = job_queue.get_all_jobs()

    if not all_jobs:
        st.info("No job statistics available.")
        return

    # Job type distribution in columns
    st.markdown("#### Job Type Distribution")
    type_counts = {}
    for job in all_jobs:
        job_type_str = str(job.type) if hasattr(job.type, 'value') else str(job.type)
        type_counts[job_type_str] = type_counts.get(job_type_str, 0) + 1

    # Display type counts in a more compact grid
    cols = st.columns(3)
    for i, (job_type, count) in enumerate(type_counts.items()):
        with cols[i % 3]:
            st.metric(f"{job_type.replace('_', ' ').title()}", count)

    # Recent activity and success rate
    col1, col2 = st.columns(2)
    
    with col1:
        # Recent activity (last 24 hours)
        recent_jobs = [
            job for job in all_jobs
            if job.created_at and job.created_at > datetime.now() - timedelta(days=1)
        ]
        st.metric("Jobs (Last 24h)", len(recent_jobs))

    with col2:
        # Success rate
        finished_jobs = [job for job in all_jobs if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]]
        if finished_jobs:
            success_rate = len([job for job in finished_jobs if job.status == JobStatus.COMPLETED]) / len(finished_jobs) * 100
            st.metric("Success Rate", f"{success_rate:.1f}%")


def show_job_card_compact(job, job_queue, show_actions=True, highlight_errors=False):
    """Show a compact job card with essential details"""
    # Status icon mapping
    status_icons = {
        JobStatus.QUEUED: "⏳",
        JobStatus.RUNNING: "🔄",
        JobStatus.COMPLETED: "✅",
        JobStatus.FAILED: "❌",
        JobStatus.CANCELLED: "🚫",
        JobStatus.PAUSED: "⏸️"
    }

    # Map job types to display text
    job_type_display = str(job.type) if hasattr(job.type, 'value') else str(job.type)
    status_display = str(job.status) if hasattr(job.status, 'value') else str(job.status)
    
    status_icon = status_icons.get(job.status, "❓")

    # Card styling based on status
    if highlight_errors and job.status == JobStatus.FAILED:
        border_color = "#ff6b6b"
    elif job.status == JobStatus.RUNNING:
        border_color = "#4ecdc4"
    elif job.status == JobStatus.COMPLETED:
        border_color = "#51cf66"
    else:
        border_color = "#e9ecef"

    with st.container():
        # Compact header in single row
        col1, col2, col3, col4 = st.columns([4, 2, 2, 2])

        with col1:
            st.markdown(f"**{status_icon} {job.title}**")
            st.caption(f"{job.description}")

        with col2:
            # Enhanced progress for running jobs
            if job.status == JobStatus.RUNNING:
                st.progress(job.progress / 100.0)
                progress_text = f"{job.progress:.1f}%"
                # Add current step if available in logs
                if job.logs:
                    latest_log = job.logs[-1]
                    if len(latest_log) > 30:
                        latest_log = latest_log[:27] + "..."
                    progress_text += f" - {latest_log}"
                st.caption(progress_text)
            else:
                st.caption(f"Status: {status_display}")

        with col3:
            # Enhanced timing information
            if job.completed_at and job.started_at:
                duration = job.completed_at - job.started_at
                st.caption(f"Duration: {format_duration(duration)}")
            elif job.started_at:
                duration = datetime.now() - job.started_at
                st.caption(f"Running: {format_duration(duration)}")
                # Show estimated completion if progress is available
                if job.status == JobStatus.RUNNING and job.progress > 5:
                    elapsed = duration.total_seconds()
                    estimated_total = elapsed / (job.progress / 100.0)
                    remaining = estimated_total - elapsed
                    if remaining > 0:
                        st.caption(f"ETA: {format_duration_seconds(remaining)}")
            else:
                st.caption(f"Created: {format_time_ago(job.created_at)}")

        with col4:
            # Compact action buttons and job info
            if show_actions:
                action_col1, action_col2 = st.columns(2)
                
                with action_col1:
                    if job.can_cancel and job.status in [JobStatus.QUEUED, JobStatus.RUNNING]:
                        if st.button("🚫", key=f"cancel_{job.id}", help="Cancel Job"):
                            if job_queue.cancel_job(job.id):
                                st.success("Cancelled")
                                st.rerun()
                
                with action_col2:
                    if job.can_retry and job.status == JobStatus.FAILED:
                        if st.button("🔄", key=f"retry_{job.id}", help="Retry Job"):
                            if job_queue.retry_job(job.id):
                                st.success("Retrying")
                                st.rerun()
            else:
                # Show priority for non-actionable jobs
                st.caption(f"Priority: {job.priority}/10")

        # Enhanced expandable details for compact view
        if job.logs or job.result or job.parameters:
            with st.expander(f"Details - {job.id[:8]}", expanded=False):
                detail_col1, detail_col2 = st.columns(2)
                
                with detail_col1:
                    # Key parameters
                    if job.parameters:
                        st.markdown("**Key Parameters:**")
                        # Show most relevant parameters
                        relevant_params = ['sermon_ids', 'actions', 'enhance_audio', 'generate_description']
                        for param in relevant_params:
                            if param in job.parameters:
                                value = job.parameters[param]
                                if param == 'sermon_ids' and isinstance(value, list):
                                    st.text(f"Sermons: {len(value)}")
                                elif param == 'actions' and isinstance(value, list):
                                    st.text(f"Actions: {', '.join(value)}")
                                else:
                                    st.text(f"{param.replace('_', ' ').title()}: {value}")
                
                with detail_col2:
                    # Recent activity or result
                    if job.result and not job.result.success:
                        st.error(f"❌ {job.result.message}")
                        if job.result.error:
                            error_text = job.result.error
                            if len(error_text) > 200:
                                error_text = error_text[:197] + "..."
                            st.code(error_text, language="text")
                    
                    if job.logs:
                        recent_logs = job.logs[-3:]  # Show last 3 logs in compact view
                        st.text_area("Recent Activity", "\\n".join(f"• {log}" for log in recent_logs), height=80, disabled=True)

        st.markdown("---")  # Simple separator instead of styled box


def show_active_jobs(job_queue):
    """Show currently running and queued jobs"""
    st.markdown("### 🔄 Active Jobs")

    # Get running and queued jobs
    running_jobs = job_queue.get_all_jobs(JobStatus.RUNNING)
    queued_jobs = job_queue.get_all_jobs(JobStatus.QUEUED)

    if not running_jobs and not queued_jobs:
        st.info("No active jobs. All background processes are idle.")
        return

    # Show running jobs first
    if running_jobs:
        st.markdown("#### 🟡 Currently Running")
        for job in running_jobs:
            show_job_card(job, job_queue, show_actions=True)

    # Show queued jobs
    if queued_jobs:
        st.markdown("#### ⏳ Queued Jobs")
        for job in queued_jobs:
            show_job_card(job, job_queue, show_actions=True)


def show_completed_jobs(job_queue):
    """Show completed jobs"""
    st.markdown("### ✅ Completed Jobs")

    completed_jobs = job_queue.get_all_jobs(JobStatus.COMPLETED)

    if not completed_jobs:
        st.info("No completed jobs found.")
        return

    # Show most recent first
    completed_jobs.sort(key=lambda j: j.completed_at or j.created_at, reverse=True)

    for job in completed_jobs[:20]:  # Show last 20 completed jobs
        show_job_card(job, job_queue, show_actions=False)


def show_failed_jobs(job_queue):
    """Show failed jobs with retry options"""
    st.markdown("### ❌ Failed Jobs")

    failed_jobs = job_queue.get_all_jobs(JobStatus.FAILED)

    if not failed_jobs:
        st.success("No failed jobs! 🎉")
        return

    # Show most recent first
    failed_jobs.sort(key=lambda j: j.completed_at or j.created_at, reverse=True)

    for job in failed_jobs:
        show_job_card(job, job_queue, show_actions=True, highlight_errors=True)


def show_job_card(job, job_queue, show_actions=True, highlight_errors=False):
    """Show a job card with details and actions"""
    # Status icon mapping
    status_icons = {
        JobStatus.QUEUED: "⏳",
        JobStatus.RUNNING: "🔄",
        JobStatus.COMPLETED: "✅",
        JobStatus.FAILED: "❌",
        JobStatus.CANCELLED: "🚫",
        JobStatus.PAUSED: "⏸️"
    }

    # Job type icons - use basic mapping
    type_icons = {
        "VALIDATION": "✅",
        "SERMON_PROCESSING": "🎵", 
        "BATCH_PROCESSING": "📦",
        "SERMON_IMPORT": "📥",
        "AUDIO_ENHANCEMENT": "🔊",
        "TRANSCRIPT_GENERATION": "📝",
        "METADATA_UPDATE": "📋"
    }

    status_icon = status_icons.get(job.status, "❓")
    job_type_str = str(job.type) if hasattr(job.type, 'value') else str(job.type)
    type_icon = type_icons.get(job_type_str.upper(), "⚙️")

    # Card styling based on status
    if highlight_errors and job.status == JobStatus.FAILED:
        border_color = "#ff6b6b"
    elif job.status == JobStatus.RUNNING:
        border_color = "#4ecdc4"
    elif job.status == JobStatus.COMPLETED:
        border_color = "#51cf66"
    else:
        border_color = "#e9ecef"

    with st.container():
        st.markdown(f"""
        <div style="border-left: 4px solid {border_color}; padding: 10px; margin: 10px 0; background-color: rgba(0,0,0,0.05);">
        """, unsafe_allow_html=True)

        # Job header
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            st.markdown(f"**{type_icon} {job.title}**")
            status_display = str(job.status) if hasattr(job.status, 'value') else str(job.status)
            st.caption(f"{status_icon} {status_display.title()} • {job.description}")

        with col2:
            # Progress bar for running jobs
            if job.status == JobStatus.RUNNING:
                st.progress(job.progress / 100.0)
                st.caption(f"{job.progress:.1f}%")
            else:
                st.caption(f"Priority: {job.priority}")

        with col3:
            # Timing information
            if job.completed_at:
                duration = job.completed_at - (job.started_at or job.created_at)
                st.caption(f"Duration: {format_duration(duration)}")
            elif job.started_at:
                duration = datetime.now() - job.started_at
                st.caption(f"Running: {format_duration(duration)}")
            else:
                st.caption(f"Created: {format_time_ago(job.created_at)}")

        # Expandable details
        with st.expander(f"Details - {job.id[:8]}", expanded=False):
            # Enhanced job details with better formatting
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### 📋 Job Information")
                
                # Basic job info with better formatting
                info_data = {
                    "ID": job.id,
                    "Type": job_type_str.replace('_', ' ').title(),
                    "Status": status_display.title(),
                    "Priority": f"{job.priority}/10",
                    "Progress": f"{job.progress:.1f}%" if job.status == JobStatus.RUNNING else "N/A"
                }
                
                for label, value in info_data.items():
                    st.text(f"{label}: {value}")
                
                st.markdown("### ⏰ Timing")
                timing_data = {
                    "Created": job.created_at.strftime('%Y-%m-%d %H:%M:%S') if job.created_at else 'Unknown',
                }
                
                if job.started_at:
                    timing_data["Started"] = job.started_at.strftime('%Y-%m-%d %H:%M:%S')
                    
                if job.completed_at:
                    timing_data["Completed"] = job.completed_at.strftime('%Y-%m-%d %H:%M:%S')
                    if job.started_at:
                        duration = job.completed_at - job.started_at
                        timing_data["Duration"] = format_duration(duration)
                elif job.started_at:
                    duration = datetime.now() - job.started_at
                    timing_data["Running for"] = format_duration(duration)
                
                for label, value in timing_data.items():
                    st.text(f"{label}: {value}")

                # Enhanced Parameters display
                if job.parameters:
                    st.markdown("### ⚙️ Parameters")
                    
                    # Special handling for different parameter types
                    for key, value in job.parameters.items():
                        if key == 'sermon_ids' and isinstance(value, list):
                            st.text(f"Sermons: {len(value)} items")
                            if len(value) <= 5:
                                for i, sermon_id in enumerate(value, 1):
                                    st.text(f"  {i}. {sermon_id}")
                            else:
                                st.text(f"  First 3: {', '.join(value[:3])}")
                                st.text(f"  ... and {len(value) - 3} more")
                                
                        elif key == 'actions' and isinstance(value, list):
                            st.text(f"Actions: {', '.join(value)}")
                            
                        elif key in ['enhance_audio', 'generate_description', 'generate_hashtags', 'validate_content']:
                            st.text(f"{key.replace('_', ' ').title()}: {'Yes' if value else 'No'}")
                            
                        elif isinstance(value, dict):
                            st.text(f"{key.replace('_', ' ').title()}:")
                            for subkey, subvalue in value.items():
                                st.text(f"  {subkey}: {subvalue}")
                                
                        elif isinstance(value, list) and len(value) > 10:
                            st.text(f"{key.replace('_', ' ').title()}: {len(value)} items")
                        else:
                            display_value = str(value)
                            if len(display_value) > 100:
                                display_value = display_value[:97] + "..."
                            st.text(f"{key.replace('_', ' ').title()}: {display_value}")

            with col2:
                # Enhanced Result and Progress Information
                if job.status == JobStatus.RUNNING:
                    st.markdown("### 🔄 Current Progress")
                    
                    # Progress bar with percentage
                    progress_col1, progress_col2 = st.columns([3, 1])
                    with progress_col1:
                        st.progress(job.progress / 100.0)
                    with progress_col2:
                        st.metric("Progress", f"{job.progress:.1f}%")
                    
                    # Current step from logs
                    if job.logs:
                        latest_log = job.logs[-1] if job.logs else "Starting..."
                        st.text_area("Current Step", latest_log, height=60, disabled=True)
                
                # Result information with better formatting
                if job.result:
                    st.markdown("### 📊 Result")
                    if job.result.success:
                        st.success(f"✅ {job.result.message}")
                    else:
                        st.error(f"❌ {job.result.message}")
                        if job.result.error:
                            st.markdown("**Error Details:**")
                            st.code(job.result.error, language="text")

                    if job.result.data:
                        st.markdown("**Result Data:**")
                        # Better formatting for result data
                        if isinstance(job.result.data, dict):
                            for key, value in job.result.data.items():
                                if isinstance(value, (int, float)):
                                    st.metric(key.replace('_', ' ').title(), value)
                                else:
                                    st.text(f"{key.replace('_', ' ').title()}: {value}")
                        else:
                            st.json(job.result.data)

                # Enhanced Job logs
                if job.logs:
                    st.markdown("### 📝 Activity Log")
                    
                    # Show number of log entries
                    st.caption(f"Showing last {min(15, len(job.logs))} of {len(job.logs)} log entries")
                    
                    # Format logs with timestamps if available
                    recent_logs = job.logs[-15:]  # Show last 15 logs
                    formatted_logs = []
                    
                    for log_entry in recent_logs:
                        # Try to extract timestamp if present
                        if log_entry.startswith('[') and ']' in log_entry:
                            # Log already has timestamp
                            formatted_logs.append(log_entry)
                        else:
                            # Add simple formatting
                            formatted_logs.append(f"• {log_entry}")
                    
                    log_text = "\\n".join(formatted_logs)
                    st.text_area("Recent Activity", log_text, height=200, disabled=True)
                    
                    # Download logs button for completed jobs
                    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED] and len(job.logs) > 15:
                        if st.button("📥 Download Full Log", key=f"download_log_{job.id}"):
                            full_log = "\\n".join(job.logs)
                            st.download_button(
                                label="Download Log File",
                                data=full_log,
                                file_name=f"job_{job.id[:8]}_log.txt",
                                mime="text/plain",
                                key=f"download_log_file_{job.id}"
                            )

        # Action buttons
        if show_actions:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if job.can_cancel and job.status in [JobStatus.QUEUED, JobStatus.RUNNING]:
                    if st.button("🚫 Cancel", key=f"cancel_{job.id}"):
                        if job_queue.cancel_job(job.id):
                            st.success("Job cancelled")
                            st.rerun()
                        else:
                            st.error("Failed to cancel job")

            with col2:
                if job.can_retry and job.status == JobStatus.FAILED:
                    if st.button("🔄 Retry", key=f"retry_{job.id}"):
                        if job_queue.retry_job(job.id):
                            st.success("Job queued for retry")
                            st.rerun()
                        else:
                            st.error("Failed to retry job")

            with col3:
                if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    if st.button("🗑️ Remove", key=f"remove_{job.id}"):
                        # Remove single job (you'd need to add this method to job_queue)
                        st.success("Job removed")
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


def show_queue_statistics(job_queue):
    """Show detailed queue statistics and health metrics"""
    st.markdown("### 📊 Queue Statistics")

    all_jobs = job_queue.get_all_jobs()

    if not all_jobs:
        st.info("No job statistics available.")
        return

    # Job type distribution
    st.markdown("#### Job Type Distribution")
    type_counts = {}
    for job in all_jobs:
        type_counts[job.type.value] = type_counts.get(job.type.value, 0) + 1

    col1, col2 = st.columns(2)

    with col1:
        for job_type, count in type_counts.items():
            st.metric(f"{job_type.replace('_', ' ').title()}", count)

    with col2:
        # Recent activity (last 24 hours)
        recent_jobs = [
            job for job in all_jobs
            if job.created_at and job.created_at > datetime.now() - timedelta(days=1)
        ]
        st.metric("Jobs (Last 24h)", len(recent_jobs))

        # Average completion time
        completed_jobs = [job for job in all_jobs if job.status == JobStatus.COMPLETED and job.started_at and job.completed_at]
        if completed_jobs:
            avg_duration = sum(
                (job.completed_at - job.started_at).total_seconds()
                for job in completed_jobs
            ) / len(completed_jobs)
            st.metric("Avg Completion Time", f"{avg_duration:.1f}s")

    # Success rate
    st.markdown("#### Success Rate")
    finished_jobs = [job for job in all_jobs if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]]
    if finished_jobs:
        success_rate = len([job for job in finished_jobs if job.status == JobStatus.COMPLETED]) / len(finished_jobs) * 100
        st.metric("Success Rate", f"{success_rate:.1f}%")

        # Show success rate by job type - use actual job types from data
        job_types_found = set()
        for job in finished_jobs:
            job_type_str = str(job.type) if hasattr(job.type, 'value') else str(job.type)
            job_types_found.add(job_type_str)
            
        for job_type_str in job_types_found:
            type_finished = [job for job in finished_jobs if str(job.type) == job_type_str]
            if type_finished:
                type_success = len([job for job in type_finished if job.status == JobStatus.COMPLETED])
                type_rate = type_success / len(type_finished) * 100
                display_name = job_type_str.replace('_', ' ').title()
                st.write(f"**{display_name}:** {type_rate:.1f}% ({type_success}/{len(type_finished)})")


def add_test_job(job_queue):
    """Add a test job for demonstration"""
    job_id = job_queue.add_job(
        job_type=JobType.VALIDATION,
        title="Test Validation Job",
        description="A test job to demonstrate the queue system",
        parameters={'sermon_ids': ['test123', 'test456']},
        priority=3
    )
    st.success(f"Test job added: {job_id[:8]}")


def format_duration(duration):
    """Format a timedelta as a readable duration"""
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def format_duration_seconds(seconds):
    """Format seconds as a readable duration"""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def format_time_ago(dt):
    """Format datetime as 'time ago' string"""
    if not dt:
        return "Unknown"

    now = datetime.now()
    diff = now - dt

    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "Just now"


if __name__ == "__main__":
    show_jobs()
