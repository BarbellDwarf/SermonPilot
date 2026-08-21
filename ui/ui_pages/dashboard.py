"""
Dashboard Page for SermonPilot

Displays recent activity, quick stats, system status, and provides quick access
to common tasks like new sermon processing and validation.
"""

import datetime

import pandas as pd
import streamlit as st

from ui.pages import batch_update, new_sermon, settings, validation


def show_dashboard():
    """Main dashboard display"""
    st.markdown('<div class="main-header">Dashboard</div>', unsafe_allow_html=True)

    if not st.session_state.config:
        st.error("Configuration not loaded. Please check the Settings page.")
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
    """Display key metrics from the real database"""
    st.markdown("### Quick Statistics")
    try:
        from database import SermonRepository
        repo = SermonRepository()
        sermons = repo.get_all_sermons()
    except Exception:
        sermons = []

    total_sermons = len(sermons)
    now = datetime.datetime.now()
    twenty_four_hours = now - datetime.timedelta(hours=24)

    last_24h = 0
    processed_status = 0
    for s in sermons:
        updated = s.get('updated_at')
        if updated and isinstance(updated, str):
            try:
                parsed = datetime.datetime.fromisoformat(updated.replace('Z', '+00:00'))
                if parsed > twenty_four_hours:
                    last_24h += 1
            except Exception:
                pass
        if s.get('status') == 'processed':
            processed_status += 1

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Sermons", str(total_sermons),
                  f"+{last_24h} today" if last_24h > 0 else "No recent activity",
                  delta_color="off" if last_24h == 0 else "normal")

    with col2:
        st.metric("Processed", str(processed_status),
                  f"{processed_status}/{total_sermons}" if total_sermons > 0 else "N/A",
                  delta_color="off")

    with col3:
        uploaded = sum(1 for s in sermons if s.get('upload_status'))
        st.metric("Uploaded to SA", str(uploaded),
                  f"{uploaded}/{total_sermons}" if total_sermons > 0 else "N/A",
                  delta_color="off")

    with col4:
        st.metric("Last 24h", str(last_24h),
                  f"out of {total_sermons} total" if total_sermons > 0 else "N/A",
                  delta_color="off")

def show_recent_activity():
    """Show recent sermons from the database"""
    st.markdown("### Recent Activity")
    try:
        from database import SermonRepository
        repo = SermonRepository()
        sermons = repo.get_all_sermons(limit=10)
    except Exception:
        sermons = []

    if not sermons:
        st.info("No sermons in the database yet. Start processing to see activity here.")
        return

    formatted_data = []
    for s in sermons:
        formatted_data.append({
            'Date': s.get(
                'recorded_date', s.get('updated_at', '')[:10] if s.get('updated_at') else ''
            ),
            'Title': s.get('title', '(no title)'),
            'Speaker': s.get('speaker', ''),
            'Status': _status_label(s.get('status')),
        })

    df = pd.DataFrame(formatted_data)
    event = st.dataframe(
        df,
        width='stretch',
        hide_index=True,
        height=260,
        on_select='rerun',
        selection_mode='single-row',
    )
    selected_rows = event.selection.rows
    if selected_rows:
        if st.button(
            "View in Library",
            key="dash_view_in_library",
            help="Open the selected sermon in the Library",
        ):
            from ui.pages import library as library_page

            st.session_state.selected_sermon = sermons[selected_rows[0]]
            st.session_state.editing_sermon = False
            st.switch_page(library_page)


def _status_label(status):
    """Map a stored sermon status to its display label"""
    labels = {
        'processed': 'Processed',
        'processing': 'Processing',
        'pending': 'Pending',
        'draft': 'Draft',
        'error': 'Error',
    }
    if status in labels:
        return labels[status]
    return str(status).capitalize() if status else 'Unknown'

def show_quick_actions():
    """Show quick action shortcuts for common tasks"""
    st.markdown("### Quick Start")
    st.markdown("*Quick shortcuts to get started with common tasks*")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Process New Sermon", type="primary", width='stretch'):
            st.switch_page(new_sermon)

    with col2:
        if st.button("Batch Update", width='stretch'):
            st.switch_page(batch_update)

    with col3:
        if st.button("Validate Descriptions", width='stretch'):
            st.switch_page(validation)

def show_system_status():
    """Show compact system health metrics"""
    st.markdown("### System Health")

    status = check_system_components()
    items = list(status.items())
    for row_start in range(0, len(items), 2):
        row = st.columns(2)
        for col, (component, details) in zip(row, items[row_start:row_start + 2], strict=False):
            with col:
                healthy = details['status']
                st.metric(
                    component, f"{'OK' if healthy else 'Error'}",
                    help=details.get('message', ''),
                )

def show_processing_queue():
    """Show current processing queue from job_queue module"""
    st.markdown("### Processing Queue")
    try:
        from job_queue import JobStatus, get_job_queue
        jq = get_job_queue()
        active = jq.get_all_jobs(JobStatus.RUNNING) or []
        queued = jq.get_all_jobs(JobStatus.QUEUED) or []
    except Exception:
        active = []
        queued = []

    if not active and not queued:
        st.info("No items in processing queue")
        return

    for job in active:
        sid = job.parameters.get(
            'sermon_id', job.parameters.get('form_data', {}).get('title', job.id)
        )
        st.write(f"{sid} — running ({job.progress:.0f}%)")

    for job in queued[:5]:
        sid = job.parameters.get(
            'sermon_id', job.parameters.get('form_data', {}).get('title', job.id)
        )
        st.write(f"{sid} — queued")

    remaining = len(queued) - 5
    if remaining > 0:
        st.caption(f"... and {remaining} more queued")

def show_setup_guide():
    """Show setup guide when configuration is missing"""
    st.markdown("### Welcome to SermonPilot!")

    st.markdown("""
    To get started, please complete the setup:

    1. **Configuration**: Copy `config.example.yaml` to `config.yaml` and update your settings
    2. **API Keys**: Add your SermonAudio API credentials
    3. **LLM Provider**: Configure OpenAI or Ollama for AI processing
    4. **Audio Enhancement**: Choose your preferred enhancement method
    """)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Go to Settings", type="primary", width='stretch'):
            st.switch_page(settings)

    with col2:
        st.link_button(
            "View Documentation",
            "https://github.com/BarbellDwarf/SermonPilot/tree/master/docs",
            width='stretch',
        )

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
