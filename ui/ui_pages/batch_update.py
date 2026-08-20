"""
Batch Processing Page for SermonPilot

Handles filtering sermons, selecting batches, configuring processing options,
and managing bulk operations with progress tracking.
"""

import datetime
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from ui.pages import jobs

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from sermon_metadata import (
    create_series_selectbox,
    get_event_types,
    get_pastors,
    show_metadata_refresh_section,
)


def show_batch_update():
    """Main batch processing interface."""
    st.markdown('<div class="main-header">Batch Update</div>', unsafe_allow_html=True)

    if not st.session_state.config:
        st.error("Configuration not loaded. Please check the Settings page first.")
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "Filter & Select",
        "Processing Options",
        "Execute Batch",
        "Results",
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
    """Sermon filtering and selection interface."""
    st.markdown("### Filter Sermons")

    show_metadata_refresh_section()

    col1, col2 = st.columns(2)

    with col1:
        st.date_input(
            "Start Date",
            value=datetime.date.today() - datetime.timedelta(days=30),
            key="batch_start_date",
        )

    with col2:
        st.date_input("End Date", value=datetime.date.today(), key="batch_end_date")

    col1, col2, col3 = st.columns(3)

    with col1:
        pastors = get_pastors()
        pastor_options = ["All"] + pastors
        speaker_filter_select = st.selectbox(
            "Speaker Name (optional)",
            options=pastor_options,
            key="batch_speaker_filter_select",
        )
        if speaker_filter_select == "All":
            st.text_input(
                "Or enter custom speaker:",
                placeholder="Custom speaker name",
                key="batch_speaker_filter_custom",
            )

    with col2:
        event_types = get_event_types()
        event_options = ["All"] + event_types
        st.selectbox(
            "Event Type (optional)",
            options=event_options,
            key="batch_event_filter",
        )

    with col3:
        st.selectbox(
            "Content Requirement",
            options=[
                "Any",
                "Missing Description",
                "Missing Hashtags",
                "Both Missing",
                "Has Audio",
            ],
            key="batch_content_filter",
        )

    with st.expander("Advanced Filters"):
        col1, col2 = st.columns(2)

        with col1:
            st.number_input(
                "Min Duration (minutes)",
                min_value=0,
                value=0,
                key="batch_min_duration",
            )
            st.checkbox("Require Transcript", key="batch_require_transcript")

        with col2:
            st.number_input(
                "Max Duration (minutes)",
                min_value=0,
                value=0,
                help="0 = no limit",
                key="batch_max_duration",
            )
            st.checkbox("Require Audio File", key="batch_require_audio")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("Search Sermons", type="primary", width="stretch"):
            search_sermons()

    with col2:
        st.number_input(
            "Max Results",
            min_value=1,
            max_value=1000,
            value=100,
            key="batch_max_results",
        )

    with col3:
        export_csv = sermon_list_csv()
        st.download_button(
            "Export List",
            data=export_csv or "",
            file_name="sermon_search_results.csv",
            mime="text/csv",
            disabled=export_csv is None,
            width="stretch",
        )

    show_search_results()


def show_batch_processing_options():
    """Show batch processing configuration."""
    st.markdown("### Batch Processing Configuration")

    st.markdown("#### Processing Scope")

    col1, col2 = st.columns(2)

    with col1:
        st.checkbox(
            "Process Audio",
            value=True,
            key="batch_process_audio",
            help="Apply audio enhancement to selected sermons",
        )
        st.checkbox(
            "Update Descriptions",
            value=True,
            key="batch_update_descriptions",
            help="Generate/update sermon descriptions",
        )

    with col2:
        st.checkbox(
            "Update Hashtags",
            value=True,
            key="batch_update_hashtags",
            help="Generate/update sermon hashtags",
        )
        st.checkbox(
            "Validate Content Quality",
            value=True,
            key="batch_validate_content",
            help="Run quality validation on generated content",
        )

    st.markdown("#### Processing Options")

    col1, col2 = st.columns(2)

    with col1:
        st.checkbox(
            "Force Update Existing Content",
            key="batch_force_update",
            help="Update content even if it already exists",
        )
        st.checkbox(
            "Skip on Error",
            value=True,
            key="batch_skip_error",
            help="Continue processing other sermons if one fails",
        )

    with col2:
        st.checkbox(
            "Dry Run (Preview Only)",
            key="batch_dry_run",
            help="Process locally but don't upload changes",
        )
        st.checkbox(
            "Save Backups",
            value=True,
            key="batch_save_backups",
            help="Save backup copies of original metadata",
        )

    st.markdown("#### Series Assignment")
    create_series_selectbox(
        "Series (optional)",
        key="batch_series",
        help="Assign the selected sermons to a series",
    )

    st.markdown("#### Execution Settings")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.number_input(
            "Batch Size",
            min_value=1,
            max_value=50,
            value=5,
            key="batch_size",
            help="Number of sermons to process in parallel",
        )

    with col2:
        st.number_input(
            "Delay Between (seconds)",
            min_value=0.0,
            max_value=10.0,
            value=1.0,
            step=0.1,
            key="batch_delay",
            help="Delay between processing items",
        )

    with col3:
        st.number_input(
            "Max Retries",
            min_value=0,
            max_value=5,
            value=2,
            key="batch_retries",
            help="Number of retry attempts for failed items",
        )


def show_execute_batch():
    """Show batch execution controls."""
    st.markdown("### Execute Batch Processing")

    selected_sermons = st.session_state.get("selected_sermons", [])

    if not selected_sermons:
        st.warning(
            "No sermons selected. Please go to Filter & Select tab to choose sermons."
        )
        return

    st.markdown("#### Execution Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Selected Sermons", len(selected_sermons))

    with col2:
        per_sermon_min = (
            (2.0 if st.session_state.get("batch_process_audio", False) else 0.0)
            + (1.0 if st.session_state.get("batch_update_descriptions", False) else 0.0)
            + (1.0 if st.session_state.get("batch_update_hashtags", False) else 0.0)
            + (0.5 if st.session_state.get("batch_validate_content", False) else 0.0)
        )
        estimated_time = len(selected_sermons) * max(per_sermon_min, 0.5)
        st.metric("Estimated Time", f"{estimated_time:.1f} min")

    with col3:
        st.metric("Batch Size", st.session_state.get("batch_size", 5))

    with col4:
        st.metric(
            "Processing Mode",
            "Dry Run" if st.session_state.get("batch_dry_run") else "Live",
        )

    st.markdown("#### Processing Controls")

    job_id = st.session_state.get("current_batch_job_id")
    active_job = None
    is_job_running = False

    if job_id:
        try:
            from job_queue import JobStatus, get_job_queue

            job_queue = get_job_queue()
            active_job = job_queue.get_job(job_id)
            if active_job is None:
                st.session_state.current_batch_job_id = None
            else:
                is_job_running = active_job.status in [
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                ]
        except Exception as e:
            st.session_state.current_batch_job_id = None
            st.warning(f"Could not check job status: {str(e)}")
            active_job = None

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(
            "Start Batch",
            type="primary",
            width="stretch",
            disabled=is_job_running,
        ):
            start_batch_processing()

    with col2:
        if st.button("Cancel Job", width="stretch", disabled=not is_job_running):
            cancel_batch_processing()

    with col3:
        if st.button("Reset Queue", width="stretch"):
            reset_batch_queue()

    if active_job:
        show_batch_progress()


def show_batch_results():
    """Display batch processing results."""
    st.markdown("### Batch Processing Results")

    results = collect_batch_results()

    if not results:
        st.info(
            "No batch processing results available. "
            "Results will appear here after processing."
        )
        return

    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = len(results) - success_count

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Processed", len(results))

    with col2:
        st.metric(
            "Successful", success_count, f"{success_count / len(results) * 100:.1f}%"
        )

    with col3:
        st.metric("Failed", error_count, f"{error_count / len(results) * 100:.1f}%")

    st.markdown("#### Detailed Results")

    df_results = build_results_frame(results)

    status_filter = st.selectbox(
        "Filter by Status",
        options=["All", "Success", "Error"],
        key="results_status_filter",
    )

    if status_filter != "All":
        filtered_df = df_results[df_results["status"] == status_filter.lower()]
    else:
        filtered_df = df_results

    st.dataframe(
        filtered_df[["sermon_id", "title", "speaker", "Status", "actions_performed"]],
        width="stretch",
        hide_index=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "Export Results (CSV)",
            data=df_results.to_csv(index=False),
            file_name="batch_results.csv",
            mime="text/csv",
            width="stretch",
        )

    with col2:
        st.download_button(
            "Generate Report",
            data=build_batch_report(df_results),
            file_name="batch_report.md",
            mime="text/markdown",
            width="stretch",
        )


def search_sermons():
    """Search sermons with the current filters."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        import sermon_updater

        start_date = st.session_state.get("batch_start_date")
        end_date = st.session_state.get("batch_end_date")
        speaker_filter_custom = st.session_state.get(
            "batch_speaker_filter_custom", ""
        ).strip()
        speaker_filter_select = st.session_state.get("batch_speaker_filter_select", "All")
        event_type_filter = st.session_state.get("batch_event_filter", "All")
        content_requirement = st.session_state.get("batch_content_filter", "Any")
        max_results = st.session_state.get("batch_max_results", 100)
        min_duration = st.session_state.get("batch_min_duration", 0)
        max_duration = st.session_state.get("batch_max_duration", 0)
        require_transcript = st.session_state.get("batch_require_transcript", False)
        require_audio = st.session_state.get("batch_require_audio", False)

        speaker_filter = None
        if speaker_filter_select != "All":
            speaker_filter = speaker_filter_select
        elif speaker_filter_custom:
            speaker_filter = speaker_filter_custom

        with st.spinner("Searching SermonAudio..."):
            progress_bar = st.progress(0)
            progress_bar.progress(0.2)

            if start_date and end_date:
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
            else:
                end_date = datetime.date.today()
                start_date = end_date - datetime.timedelta(days=30)
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")

            sermons = sermon_updater.search_broadcaster_sermons(
                start_str,
                end_str,
                max_results=max_results,
                speaker_filter=speaker_filter,
                event_type_filter=None if event_type_filter == "All" else event_type_filter,
            )

            progress_bar.progress(0.6)

            filtered_sermons = []
            for sermon in sermons:
                if min_duration and sermon.get("duration", 0) < min_duration:
                    continue
                if max_duration and sermon.get("duration", 0) > max_duration:
                    continue
                if require_audio and not sermon.get("has_audio"):
                    continue
                if require_transcript and not sermon.get("has_transcript"):
                    continue
                filtered_sermons.append(sermon)

            if content_requirement == "Missing Description":
                filtered_sermons = [
                    s for s in filtered_sermons if not s.get("has_description")
                ]
            elif content_requirement == "Missing Hashtags":
                filtered_sermons = [
                    s for s in filtered_sermons if not s.get("has_hashtags")
                ]
            elif content_requirement == "Both Missing":
                filtered_sermons = [
                    s
                    for s in filtered_sermons
                    if not s.get("has_description") and not s.get("has_hashtags")
                ]
            elif content_requirement == "Has Audio":
                filtered_sermons = [s for s in filtered_sermons if s.get("has_audio")]

            progress_bar.progress(1.0)
            progress_bar.empty()

        st.session_state.search_results = filtered_sermons
        st.session_state.selected_sermons = []
        st.session_state.pop("batch_selection_editor", None)
        st.success(f"Found {len(filtered_sermons)} matching sermons")

    except Exception as e:
        st.error(f"Error searching sermons: {str(e)}")
        st.session_state.search_results = []
        st.session_state.selected_sermons = []
        st.session_state.pop("batch_selection_editor", None)


def show_search_results():
    """Display search results with persistent selection."""
    search_results = st.session_state.get("search_results", [])

    if not search_results:
        return

    st.markdown("#### Search Results")

    df = pd.DataFrame(search_results)
    selected_ids = {
        s["sermon_id"] for s in st.session_state.get("selected_sermons", [])
    }
    df["Select"] = df["sermon_id"].isin(selected_ids)
    df = df[
        [
            "Select",
            "sermon_id",
            "title",
            "speaker",
            "date",
            "event_type",
            "duration",
            "has_audio",
            "has_description",
            "has_hashtags",
            "has_transcript",
        ]
    ]

    edited_df = st.data_editor(
        df,
        column_config={
            "Select": st.column_config.CheckboxColumn("Select"),
            "has_description": st.column_config.CheckboxColumn(
                "Has Description", disabled=True
            ),
            "has_hashtags": st.column_config.CheckboxColumn(
                "Has Hashtags", disabled=True
            ),
            "has_audio": st.column_config.CheckboxColumn("Has Audio", disabled=True),
            "has_transcript": st.column_config.CheckboxColumn(
                "Has Transcript", disabled=True
            ),
        },
        hide_index=True,
        width="stretch",
        key="batch_selection_editor",
    )

    selected = edited_df[edited_df["Select"].fillna(False)].to_dict("records")
    st.session_state.selected_sermons = selected

    if selected:
        st.success(f"{len(selected)} sermons selected for processing")
    else:
        st.caption("No sermons selected")


def start_batch_processing():
    """Create a batch processing job."""
    try:
        from job_queue import JobType, get_job_queue

        selected_sermons = st.session_state.get("selected_sermons", [])
        if not selected_sermons:
            st.error("No sermons selected for batch processing")
            return

        config = st.session_state.get("config", {})
        if not config:
            st.error("No configuration loaded. Please check the Settings page first.")
            st.info(
                "Try going to Settings → Configuration and saving your settings, "
                "then return to this page."
            )
            return

        required_fields = ["api_key", "broadcaster_id"]
        missing_fields = [field for field in required_fields if not config.get(field)]
        if missing_fields:
            st.error(
                f"Configuration is missing required fields: {', '.join(missing_fields)}"
            )
            st.info(
                "Please go to Settings → Configuration and ensure all required fields "
                "are filled out."
            )
            return

        sermon_ids = [sermon["sermon_id"] for sermon in selected_sermons]

        actions = {
            "generate_description": st.session_state.get(
                "batch_update_descriptions", False
            ),
            "generate_hashtags": st.session_state.get("batch_update_hashtags", False),
            "enhance_audio": st.session_state.get("batch_process_audio", False),
            "validate_content": st.session_state.get("batch_validate_content", False),
        }

        if not any(actions.values()):
            st.error(
                "No processing actions selected. "
                "Please select at least one action to perform."
            )
            return

        job_queue = get_job_queue()

        action_names = [k.replace("_", " ").title() for k, v in actions.items() if v]
        job_title = f"Batch Processing: {len(sermon_ids)} sermons"
        job_description = (
            f"Processing {len(sermon_ids)} sermons with actions: "
            f"{', '.join(action_names)}"
        )

        job_id = job_queue.add_job(
            job_type=JobType.BATCH_PROCESSING,
            title=job_title,
            description=job_description,
            parameters={
                "sermon_ids": sermon_ids,
                "actions": actions,
                "config": config,
                "series_id": st.session_state.get("batch_series_id"),
                "series_title": st.session_state.get("batch_series_select"),
                "force_update": st.session_state.get("batch_force_update", False),
                "form_data": {
                    "dry_run": st.session_state.get("batch_dry_run", False),
                },
            },
            priority=6,
        )

        st.session_state.current_batch_job_id = job_id

        st.success(f"Batch processing job created! Job ID: {job_id[:8]}")
        st.info(
            f"Processing {len(sermon_ids)} sermons in the background. "
            "You can monitor progress on the Jobs page."
        )

        if st.button("View Job Progress", type="secondary"):
            st.switch_page(jobs)

    except Exception as e:
        st.error(f"Failed to start batch processing job: {e}")


def cancel_batch_processing():
    """Cancel the active batch processing job."""
    job_id = st.session_state.get("current_batch_job_id")
    if not job_id:
        st.warning("No active batch processing job found")
        return

    try:
        from job_queue import get_job_queue

        job_queue = get_job_queue()
        if job_queue.cancel_job(job_id):
            st.session_state.current_batch_job_id = None
            st.warning("Batch processing job cancelled")
        else:
            st.warning("Could not cancel job (may not be running)")
    except Exception as e:
        st.error(f"Failed to cancel job: {e}")


def reset_batch_queue():
    """Cancel any running job and clear batch selection state."""
    job_id = st.session_state.get("current_batch_job_id")
    if job_id:
        try:
            from job_queue import JobStatus, get_job_queue

            job_queue = get_job_queue()
            job = job_queue.get_job(job_id)
            if job and job.status in [JobStatus.QUEUED, JobStatus.RUNNING]:
                job_queue.cancel_job(job_id)
        except Exception as e:
            st.error(f"Failed to cancel active job: {e}")

    st.session_state.current_batch_job_id = None
    st.session_state.selected_sermons = []
    st.session_state.pop("batch_selection_editor", None)
    st.success("Batch queue reset")


def show_batch_progress():
    """Show real-time batch processing progress from the job queue."""
    st.markdown("#### Processing Progress")

    job_id = st.session_state.get("current_batch_job_id")
    if not job_id:
        st.info("No active batch processing job")
        return

    try:
        from job_queue import JobStatus, get_job_queue

        job_queue = get_job_queue()
        job = job_queue.get_job(job_id)

        if not job:
            st.warning("Batch processing job not found")
            st.session_state.current_batch_job_id = None
            return

        st.progress(job.progress / 100.0)

        st.text(f"Status: {job.status.value.title()}")
        st.text(f"Progress: {job.progress:.1f}%")

        if job.logs:
            with st.expander("Recent Activity", expanded=False):
                for log in job.logs[-5:]:
                    st.text(log)

        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            if st.button("Clear Completed Job"):
                st.session_state.current_batch_job_id = None
                st.rerun()

    except Exception as e:
        st.error(f"Error checking job progress: {e}")
        st.session_state.current_batch_job_id = None


def collect_batch_results() -> list[dict[str, Any]]:
    """Return batch results from state or the finished batch job."""
    results = st.session_state.get("batch_results", [])
    if results:
        return results

    job_id = st.session_state.get("current_batch_job_id")
    if not job_id:
        return []

    try:
        from job_queue import get_job_queue

        job = get_job_queue().get_job(job_id)
        if job and job.result and job.result.data:
            details = job.result.data.get("details", [])
            if details:
                st.session_state.batch_results = details
                return details
    except Exception:
        pass
    return []


def build_results_frame(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a display DataFrame from batch result records."""
    info_by_id = {s["sermon_id"]: s for s in st.session_state.get("search_results", [])}
    rows = []
    for r in results:
        info = info_by_id.get(r.get("sermon_id"), {})
        rows.append({
            "sermon_id": r.get("sermon_id", ""),
            "title": info.get("title", "Unknown"),
            "speaker": info.get("speaker", "Unknown"),
            "status": r.get("status", "error"),
            "actions_performed": ", ".join(r.get("actions_performed") or []),
        })
    df = pd.DataFrame(rows)
    df["Status"] = df["status"].apply(
        lambda x: "Success" if x == "success" else "Error"
    )
    return df


def build_batch_report(results_df: pd.DataFrame) -> str:
    """Build a markdown report from batch results."""
    success_count = int((results_df["status"] == "success").sum())
    error_count = len(results_df) - success_count
    lines = [
        "# Batch Processing Report",
        "",
        f"- Total processed: {len(results_df)}",
        f"- Successful: {success_count}",
        f"- Failed: {error_count}",
        "",
        "## Details",
        "",
        "| Sermon ID | Title | Speaker | Status | Actions |",
        "|---|---|---|---|---|",
    ]
    for _, row in results_df.iterrows():
        lines.append(
            f"| {row['sermon_id']} | {row['title']} | {row['speaker']} | "
            f"{row['status']} | {row['actions_performed']} |"
        )
    return "\n".join(lines)


def sermon_list_csv() -> str | None:
    """CSV export of the current search results, or None when empty."""
    results = st.session_state.get("search_results", [])
    if not results:
        return None
    return pd.DataFrame(results).to_csv(index=False)


if __name__ == "__main__":
    show_batch_update()
