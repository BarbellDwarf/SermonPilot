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
        job_queue = get_job_queue()

        with st.sidebar:
            st.markdown("### 🎛️ Controls")
            
            if st.button("🔄 Refresh", type="primary", width='stretch'):
                st.rerun()

            if st.button("🧹 Clear Completed", type="secondary", width='stretch'):
                cleared = job_queue.clear_completed_jobs()
                st.success(f"Cleared {cleared} completed jobs")
                st.rerun()

            if st.button("➕ Test Job", type="secondary", width='stretch'):
                add_test_job(job_queue)
                st.rerun()

        _render_job_list(job_queue)

        if job_queue.get_all_jobs(JobStatus.RUNNING) or job_queue.get_all_jobs(JobStatus.QUEUED):
            time.sleep(2)
            st.rerun()

    except ImportError as e:
        st.error(f"❌ Job queue system not available: {e}")
        st.info("The background job system requires additional setup.")
    except Exception as e:
        st.error(f"❌ Error loading jobs interface: {e}")
        st.info("Please check the job queue system and try again.")


@st.fragment
def _render_job_list(job_queue):
    """Job list display"""
    all_jobs = job_queue.get_all_jobs()
    running_count = len([j for j in all_jobs if j.status == JobStatus.RUNNING])
    queued_count = len([j for j in all_jobs if j.status == JobStatus.QUEUED])
    completed_count = len([j for j in all_jobs if j.status == JobStatus.COMPLETED])
    failed_count = len([j for j in all_jobs if j.status == JobStatus.FAILED])
    cancelled_count = len([j for j in all_jobs if j.status == JobStatus.CANCELLED])

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        f"🔄 Active ({running_count + queued_count})",
        f"✅ Completed ({completed_count})",
        f"❌ Failed ({failed_count})",
        f"🚫 Cancelled ({cancelled_count})",
        "📊 Stats"
    ])

    with tab1:
        show_active_jobs_compact(job_queue)

    with tab2:
        show_completed_jobs_compact(job_queue)

    with tab3:
        show_failed_jobs_compact(job_queue)

    with tab4:
        show_cancelled_jobs_compact(job_queue)

    with tab5:
        show_queue_statistics_compact(job_queue)


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
        show_job_card_compact(job, job_queue, show_actions=True)


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


def show_cancelled_jobs_compact(job_queue):
    """Show cancelled jobs in compact format"""
    cancelled_jobs = job_queue.get_all_jobs(JobStatus.CANCELLED)

    if not cancelled_jobs:
        st.success("No cancelled jobs.")
        return

    cancelled_jobs.sort(key=lambda j: j.completed_at or j.created_at, reverse=True)

    for job in cancelled_jobs:
        show_job_card_compact(job, job_queue, show_actions=True)


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
                    if job.can_retry and job.status in [JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED]:
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
                    if job.parameters:
                        st.markdown("**Key Parameters:**")
                        relevant_params = ['sermon_ids', 'actions', 'enhance_audio', 'generate_description',
                                           'skip_audio', 'skip_transcription', 'whisper_model', 'dry_run']
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
                    if job.result and not job.result.success:
                        st.error(f"❌ {job.result.message}")
                        if job.result.error:
                            error_text = job.result.error
                            if len(error_text) > 200:
                                error_text = error_text[:197] + "..."
                            st.code(error_text, language="text")
                    
                    if job.logs:
                        recent_logs = job.logs[-3:]
                        st.text_area("Recent Activity", "\n".join(f"• {log}" for log in recent_logs), height=80, disabled=True)

                if job.status in [JobStatus.FAILED, JobStatus.CANCELLED] and job.type == JobType.SERMON_PROCESSING:
                    st.markdown("---")
                    st.markdown("**🔄 Retry with Modified Settings**")
                    params = job.parameters or {}
                    form_data = params.get('form_data', {})

                    retry_col1, retry_col2, retry_col3 = st.columns(3)
                    with retry_col1:
                        new_skip_audio = st.checkbox(
                            "Skip Audio Enhancement",
                            value=bool(form_data.get('skip_audio', False)),
                            key=f"retry_skip_audio_{job.id}"
                        )
                        new_skip_transcription = st.checkbox(
                            "Skip Transcription",
                            value=bool(form_data.get('skip_transcription', False)),
                            key=f"retry_skip_transcription_{job.id}"
                        )
                    with retry_col2:
                        new_skip_ai = not st.checkbox(
                            "Generate Metadata (AI)",
                            value=not form_data.get('skip_ai_generation', False),
                            key=f"retry_ai_{job.id}"
                        )
                        new_dry_run = st.checkbox(
                            "Dry Run",
                            value=bool(form_data.get('dry_run', False)),
                            key=f"retry_dry_run_{job.id}"
                        )
                    with retry_col3:
                        _whisper_options = ["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large", "large-v2", "large-v3", "large-v3-turbo"]
                        _current_wm = form_data.get('whisper_model', 'base')
                        _wm_index = _whisper_options.index(_current_wm) if _current_wm in _whisper_options else 2
                        new_whisper_model = st.selectbox(
                            "Whisper Model",
                            options=_whisper_options,
                            index=_wm_index,
                            key=f"retry_whisper_{job.id}",
                            help="Larger model = better accuracy but slower. .en models are English-only (faster)."
                        )

                    if st.button("🔄 Retry with These Settings", type="primary", key=f"retry_modified_{job.id}"):
                        new_params = dict(params)
                        new_form_data = dict(form_data)
                        new_form_data['skip_audio'] = new_skip_audio
                        new_form_data['skip_transcription'] = new_skip_transcription
                        new_form_data['skip_ai_generation'] = new_skip_ai
                        new_form_data['dry_run'] = new_dry_run
                        new_form_data['whisper_model'] = new_whisper_model
                        new_params['form_data'] = new_form_data
                        new_job_id = job_queue.add_job(
                            job_type=job.type,
                            title=f"(Retry) {job.title}",
                            description=job.description,
                            parameters=new_params,
                            priority=job.priority,
                        )
                        st.success(f"Retry job created: {new_job_id[:8]}")
                        st.rerun()

        st.markdown("---")





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
