# ui/ui_pages/new_sermon_enhanced.py
"""
Enhanced New Sermon Processing Page with Audio Editing

Integrates audio editing capabilities with the sermon upload workflow,
providing a comprehensive interface for content creators.
"""

import datetime
import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path
import logging
import time as _time

import streamlit as st

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ui"))
sys.path.insert(0, str(project_root / "src"))

from ui.sermon_metadata import (
    create_event_type_selectbox,
    create_pastor_selectbox,
    create_series_selectbox,
    show_metadata_refresh_section,
)

from ui.components.processing_modes import ProcessingModeSelector

logger = logging.getLogger(__name__)


def show_new_sermon_enhanced():
    """Enhanced new sermon processing interface with audio editing."""
    st.markdown('<div class="main-header">🎵 New Sermon</div>', unsafe_allow_html=True)
    
    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return
    
    # Simplified workflow tabs (no audio analysis/editing - too resource intensive)
    tab1, tab2, tab3 = st.tabs([
        "📁 Upload & Metadata",
        "🎛️ Configure Processing",
        "▶️ Process & Upload"
    ])

    with tab1:
        show_upload_and_metadata()

    with tab2:
        show_processing_configuration()

    with tab3:
        show_process_and_upload()


def show_upload_and_metadata():
    """File upload and metadata form with enhanced features."""
    st.markdown("### 📁 Audio File Upload")

    # File upload with additional instructions
    st.info("💡 Upload your sermon audio/video file and fill in the metadata below.")
    
    uploaded_file = st.file_uploader(
        "Select sermon audio or video file",
        type=['mp3', 'wav', 'm4a', 'flac', 'ogg', 'mp4', 'mov', 'webm', 'mkv'],
        help="Supported formats: Audio (MP3, WAV, M4A, FLAC, OGG) and Video (MP4, MOV, WebM, MKV)"
    )

    if uploaded_file:
        # Store file info in session state
        st.session_state.uploaded_file = uploaded_file

        # Show enhanced file details
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("File Size", f"{uploaded_file.size / (1024*1024):.1f} MB")
        with col2:
            st.metric("File Type", uploaded_file.type)
        with col3:
            file_name_display = uploaded_file.name[:15] + "..." if len(uploaded_file.name) > 15 else uploaded_file.name
            st.metric("File Name", file_name_display)
        with col4:
            duration = _get_media_duration(uploaded_file)
            if duration:
                st.metric("Duration", f"{duration:.1f} min")
            else:
                st.metric("Duration", "\u23F1\uFE0F")

        # Audio/Video preview (skip for large files to avoid browser limits)
        max_preview_size = 100 * 1024 * 1024  # 100 MB
        if uploaded_file.size <= max_preview_size:
            try:
                video_exts = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v')
                if any(uploaded_file.name.lower().endswith(e) for e in video_exts):
                    st.video(uploaded_file)
                else:
                    st.audio(uploaded_file, format=uploaded_file.type)
            except Exception as e:
                st.warning(f"Could not preview file: {e}")
        else:
            st.info(f"ℹ️ Preview skipped for files over {max_preview_size // (1024*1024)} MB")

        

    st.markdown("### 📝 Sermon Metadata")

    # Show metadata refresh section
    show_metadata_refresh_section()

    # Required metadata with enhanced layout
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Required Information")
        speaker_name = create_pastor_selectbox(
            "Speaker Name *",
            key="speaker_name"
        )

        recorded_date = st.date_input(
            "Recording Date *",
            key="recorded_date",
            value=datetime.date.today()
        )

        event_type = create_event_type_selectbox(
            "Event Type *",
            key="event_type"
        )

    with col2:
        st.markdown("#### Content Information")
        bible_text = st.text_input(
            "Bible Text/Scripture",
            key="bible_text",
            placeholder="John 3:16-17"
        )

        title = st.text_input(
            "Sermon Title",
            key="sermon_title",
            placeholder="Leave blank for AI generation"
        )

        subtitle = st.text_input(
            "Subtitle (optional)",
            key="sermon_subtitle",
            placeholder="Additional context or series info"
        )

    # Optional metadata in expander
    with st.expander("Optional Fields", expanded=False):
        series = create_series_selectbox(
            "Series (optional)",
            key="sermon_series"
        )
        st.session_state.sermon_series = series

        description = st.text_area(
            "Description",
            key="sermon_description",
            placeholder="Leave blank for AI generation from transcript",
            height=100
        )

        hashtags = st.text_input(
            "Hashtags",
            key="sermon_hashtags",
            placeholder="Leave blank for AI generation (e.g., #faith #grace #salvation)"
        )

    # Enhanced validation with visual feedback
    if speaker_name and recorded_date and event_type:
        st.success("✅ Required metadata complete")
        st.session_state.metadata_complete = True
    else:
        st.warning("⚠️ Please fill in all required fields (marked with *)")
        st.session_state.metadata_complete = False





def show_processing_configuration():
    """Processing configuration with enhanced mode selection."""
    st.markdown("### 🎛️ Processing Configuration")

    processing_mode = st.radio(
        "Processing Mode",
        options=[
            "Full (Enhance + Transcribe + AI Metadata)",
            "Transcribe + AI Only (Skip Audio Enhancement)",
            "Transcribe Only (No Audio, No AI Gen)",
            "Upload Only (Just Upload, No Processing)",
        ],
        index=0,
        key="processing_mode",
        help="Select the type of processing to perform on this sermon",
    )

    is_upload_only = processing_mode.startswith("Upload Only")
    is_transcribe_only = processing_mode.startswith("Transcribe Only")
    is_transcribe_ai = processing_mode.startswith("Transcribe + AI")
    is_skip_audio = is_transcribe_ai or is_transcribe_only or is_upload_only
    is_skip_transcription = is_upload_only
    is_skip_ai = is_upload_only or is_transcribe_only

    st.session_state.skip_audio_enhancement = is_skip_audio
    st.session_state.skip_transcription = is_skip_transcription
    st.session_state.generate_description = not is_skip_ai
    st.session_state.generate_hashtags = not is_skip_ai

    mode_details = {
        "Full (Enhance + Transcribe + AI Metadata)": "🎵 Audio enhancement → 🎙️ Transcription → 🤖 AI description & hashtags → 📤 Upload",
        "Transcribe + AI Only (Skip Audio Enhancement)": "⏭️ Skip audio enhancement → 🎙️ Transcription → 🤖 AI description & hashtags → 📤 Upload",
        "Transcribe Only (No Audio, No AI Gen)": "⏭️ Skip audio enhancement → 🎙️ Transcription → 📤 Upload (no AI generation)",
        "Upload Only (Just Upload, No Processing)": "⏭️ Skip audio enhancement → ⏭️ Skip transcription → 📤 Upload as-is",
    }
    st.caption(mode_details[processing_mode])

    # Initialize processing mode selector
    if 'mode_selector' not in st.session_state:
        st.session_state.mode_selector = ProcessingModeSelector()

    mode_selector = st.session_state.mode_selector

    # Render mode selector
    mode_result = mode_selector.render_mode_selector()
    
    if mode_result:
        # Store processing configuration
        st.session_state.processing_config = mode_result['processing_config']
        st.session_state.selected_mode = mode_result['mode']

    # Legacy processing options for compatibility
    st.markdown("### 🔧 Advanced Options")
    
    with st.expander("Additional Options", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            enhancement_method = st.selectbox(
                "Enhancement Method",
                key="enhancement_method",
                options=["clear", "deepfilternet", "none"],
                index=0 if not is_skip_audio else 2,
                disabled=is_skip_audio,
                help="Choose AI enhancement method for audio quality improvement"
            )

        with col2:
            transcription_backend = st.radio(
                "Transcription Backend",
                key="transcription_backend",
                options=["whisper_local", "whisper_openai"],
                index=0,
                horizontal=True,
                help="Local Whisper (runs on your machine) or OpenAI API (requires OPENAI_API_KEY)"
            )
            whisper_model = st.selectbox(
                "Whisper Model (if transcribing locally)",
                key="whisper_model",
                options=["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large", "large-v2", "large-v3", "large-v3-turbo"],
                index=8,
                help="Balance between speed and quality. .en models are English-only (faster). large-v3-turbo ≈ large quality with ~2x speed."
            )

        col1, col2 = st.columns(2)
        with col1:
            dry_run = st.checkbox(
                "Dry Run (Preview Only)",
                key="dry_run",
                help="Process locally but don't upload to SermonAudio"
            )

    # AI Metadata Generation
    st.markdown("### 🤖 AI Metadata Generation")

    col1, col2 = st.columns(2)

    with col1:
        # Auto-adjust generate_title default when manual title presence changes
        has_manual_title = bool(st.session_state.get('sermon_title', '').strip())
        prev_title_state = st.session_state.get('_prev_has_title', None)
        if prev_title_state is not None and prev_title_state != has_manual_title:
            st.session_state.generate_title = not has_manual_title and not is_skip_ai
        st.session_state._prev_has_title = has_manual_title

        generate_title = st.checkbox(
            "Generate Title",
            key="generate_title",
            disabled=is_skip_ai,
            help="Use AI to generate sermon title from transcript. Unchecked by default when you type a title."
        )

        generate_description = st.checkbox(
            "Generate Description",
            key="generate_description",
            disabled=is_skip_ai,
            help="Use AI to generate detailed description from transcript"
        )

    with col2:
        generate_hashtags = st.checkbox(
            "Generate Hashtags",
            key="generate_hashtags",
            disabled=is_skip_ai,
            help="Use AI to generate relevant hashtags from content"
        )

        validate_description = st.checkbox(
            "Validate Description Quality",
            key="validate_description",
            value=not is_skip_ai,
            disabled=is_skip_ai,
            help="Use AI to validate and improve generated descriptions"
        )

        generate_short_title = st.checkbox(
            "Generate Short Display Title",
            key="generate_short_title",
            value=False,
            disabled=is_skip_ai,
            help="Use AI to create a short (≤30 chars) display title from the full sermon title"
        )


def show_process_and_upload():
    """Final processing and upload with enhanced workflow."""
    st.markdown("### ▶️ Process & Upload")

    # Check prerequisites
    has_file = _has_uploaded_file()
    has_metadata = st.session_state.get('metadata_complete', False)

    if not has_file:
        st.warning("⚠️ Please upload an audio file in the first tab")
        return

    if not has_metadata:
        st.warning("⚠️ Please complete required metadata in the first tab")
        return

    # Enhanced processing summary
    st.markdown("#### 📋 Processing Summary")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**File & Content:**")
        st.write(f"• File: {st.session_state.uploaded_file.name}")
        st.write(f"• Size: {st.session_state.uploaded_file.size / (1024*1024):.1f} MB")
        st.write(f"• Speaker: {st.session_state.get('speaker_name', 'N/A')}")
        st.write(f"• Date: {st.session_state.get('recorded_date', 'N/A')}")

    with col2:
        st.markdown("**Processing Settings:**")
        mode_name = st.session_state.get('processing_mode', 'Full')
        st.write(f"• Mode: {mode_name}")
        st.write(f"• Enhancement: {st.session_state.get('enhancement_method', 'deepfilternet')} {'(skipped)' if st.session_state.get('skip_audio_enhancement') else ''}")
        st.write(f"• Transcription: {'Enabled' if not st.session_state.get('skip_transcription', False) else 'Disabled'}")
        st.write(f"• Dry Run: {'Yes' if st.session_state.get('dry_run', False) else 'No'}")

    # Processing controls
    st.markdown("#### 🚀 Processing Controls")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("▶️ Start Processing", type="primary", width='stretch'):
            start_enhanced_processing()

    with col2:
        if st.button("🔄 Reset All", width='stretch'):
            reset_enhanced_form()

    # Show processing status based on job queue
    job_id = st.session_state.get('current_sermon_job_id')
    active_job = None
    if job_id:
        try:
            from job_queue import JobStatus, get_job_queue
            job_queue = get_job_queue()
            active_job = job_queue.get_job(job_id)
        except Exception:
            pass

    if active_job and active_job.status in [JobStatus.QUEUED, JobStatus.RUNNING]:
        _show_enhanced_processing_progress(active_job)
    elif active_job and active_job.status == JobStatus.COMPLETED:
        _show_enhanced_processing_results(active_job)
    elif active_job and active_job.status in [JobStatus.CANCELLED, JobStatus.FAILED]:
        icon = "🚫" if active_job.status == JobStatus.CANCELLED else "🔴"
        label = "Cancelled" if active_job.status == JobStatus.CANCELLED else "Failed"
        st.warning(f"{icon} Job {label}")
        if st.button("Clear", key="clear_cancelled_job"):
            st.session_state.current_sermon_job_id = None
            st.rerun()


def _get_media_duration(uploaded_file):
    """Get media file duration using ffprobe (fast, metadata-only)."""
    try:
        import subprocess
        import json
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', tmp_path],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(tmp_path)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            duration_sec = float(info['format']['duration'])
            return duration_sec / 60.0
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    return None


def _has_uploaded_file():
    """Check if user has uploaded a file."""
    return hasattr(st.session_state, 'uploaded_file') and st.session_state.uploaded_file is not None


def start_enhanced_processing():
    """Start sermon processing with audio editing support using job queue."""
    try:
        from job_queue import JobType, get_job_queue

        config = st.session_state.get('config', {})
        if not config:
            st.error("❌ No configuration loaded. Please check the Settings page first.")
            st.info("💡 Try going to Settings → Configuration and saving your settings, then return to this page.")
            return

        required_fields = ['api_key', 'broadcaster_id']
        missing_fields = [field for field in required_fields if not config.get(field)]
        if missing_fields:
            st.error(f"❌ Configuration is missing required fields: {', '.join(missing_fields)}")
            st.info("Please go to Settings → Configuration and ensure all required fields are filled out.")
            return

        if not st.session_state.get('metadata_complete', False):
            st.error("❌ Required metadata incomplete. Please fill in speaker, date, and event type.")
            return

        uploaded_file = st.session_state.get('uploaded_file')
        if uploaded_file is None:
            st.error("❌ No file uploaded. Please upload an audio file in the first tab.")
            return

        upload_dir = Path(tempfile.gettempdir()) / "sermon_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(uploaded_file.name).name
        saved_path = upload_dir / f"{int(_time.time() * 1000)}_{safe_name}"
        with open(saved_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Extract widget values from correct session state keys
        speaker_name = st.session_state.get('speaker_name_select')
        if not speaker_name or speaker_name == '[Select Pastor]':
            speaker_name = st.session_state.get('speaker_name_custom')
        event_type = st.session_state.get('event_type_select')
        if not event_type or event_type == '[Select Event Type]':
            event_type = st.session_state.get('event_type_custom')

        recorded_date = st.session_state.get('recorded_date')
        if recorded_date is not None and hasattr(recorded_date, 'isoformat'):
            recorded_date = recorded_date.isoformat()

        # Validate required form fields
        missing_form_fields = []
        if not speaker_name:
            missing_form_fields.append('Speaker Name')
        if not recorded_date:
            missing_form_fields.append('Recording Date')
        if not event_type:
            missing_form_fields.append('Event Type')
        if missing_form_fields:
            st.error(f"❌ Missing required fields: {', '.join(missing_form_fields)}")
            return

        form_data = {
            'speaker_name': speaker_name,
            'recorded_date': recorded_date,
            'event_type': event_type,
            'bible_text': st.session_state.get('bible_text'),
            'title': None if st.session_state.get('generate_title', False) else (st.session_state.get('sermon_title') or None),
            'subtitle': st.session_state.get('sermon_subtitle') or None,
            'series_title': st.session_state.get('sermon_series') or None,
            'description': st.session_state.get('sermon_description') or None,
            'hashtags': st.session_state.get('sermon_hashtags') or None,
            'skip_audio': bool(st.session_state.get('skip_audio_enhancement', False)),
            'skip_transcription': bool(st.session_state.get('skip_transcription', False)),
            'skip_ai_generation': not bool(st.session_state.get('generate_description', True)),
            'whisper_model': st.session_state.get('whisper_model', 'large'),
            'transcription_backend': st.session_state.get('transcription_backend', 'whisper_local'),
            'enhancement_method': st.session_state.get('enhancement_method', 'deepfilternet'),
            'dry_run': bool(st.session_state.get('dry_run', False)),
            'generate_short_title': bool(st.session_state.get('generate_short_title', False)),
        }

        form_data['uploaded_file_path'] = str(saved_path)
        form_data['original_filename'] = uploaded_file.name

        job_queue = get_job_queue()
        job_id = job_queue.add_job(
            job_type=JobType.SERMON_PROCESSING,
            title=f"New Sermon: {form_data.get('title') or 'Untitled'}",
            description=f"Processing new sermon by {form_data.get('speaker_name', 'Unknown Speaker')}",
            parameters={
                'form_data': form_data,
                'config': config,
                'processing_type': 'new_sermon',
                'uploaded_file_path': str(saved_path),
            },
            priority=8
        )

        st.session_state.current_sermon_job_id = job_id
        st.success(f"✅ Sermon processing job created! Job ID: {job_id[:8]}")
        st.info("🔍 Processing sermon in the background. Monitor progress below.")

    except Exception as e:
        st.error(f"❌ Failed to start sermon processing job: {e}")
        logger.exception("Failed to start processing")





def reset_enhanced_form():
    """Reset the enhanced form to initial state."""
    # Clear session state variables
    keys_to_clear = [
        'uploaded_file', 'metadata_complete', 'mode_selector',
        'processing_config', 'selected_mode',
        'speaker_name', 'recorded_date', 'event_type', 'bible_text',
        'sermon_title', 'sermon_subtitle', 'sermon_description', 'sermon_hashtags'
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    st.success("✅ Enhanced form reset successfully!")
    st.rerun()


def _show_enhanced_processing_progress(job):
    """Show real-time processing progress from job queue."""
    st.markdown("#### 🔄 Processing Progress")

    from job_queue import JobStatus

    progress_bar = st.progress(job.progress / 100.0)

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

    if job.logs:
        with st.expander("📋 Recent Activity", expanded=True):
            for log in job.logs[-5:]:
                st.text(log)

    if job.status == JobStatus.COMPLETED and job.result:
        _show_enhanced_processing_results(job)

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        if st.button("Clear Completed Job"):
            st.session_state.current_sermon_job_id = None
            st.rerun()


def _show_enhanced_processing_results(job):
    """Show processing results from completed job."""
    if not job.result or not job.result.success:
        st.error("❌ Processing failed")
        if job.result and job.result.error:
            st.error(f"Error: {job.result.error}")
        return

    results = job.result.data
    if not results:
        st.warning("⚠️ No results data available")
        return

    st.markdown("#### ✅ Processing Results")
    st.success("✅ Processing completed successfully!")

    col1, col2 = st.columns(2)

    with col1:
        sermon_id = results.get('sermon_id') or 'Dry run (no upload)'
        st.metric("Sermon ID", sermon_id)
        if results.get('speaker'):
            st.metric("Speaker", results.get('speaker'))
        if results.get('event_type'):
            st.metric("Event", results.get('event_type'))

    with col2:
        st.metric("Status", "Success" if results.get('success') else "Failed")
        if results.get('title'):
            title = results.get('title')
            display = title[:50] + "..." if len(str(title)) > 50 else title
            st.metric("Title", display)
        if results.get('recorded_date'):
            st.metric("Recorded Date", results.get('recorded_date'))

    sermon_id = results.get('sermon_id')
    if sermon_id:
        sermon_url = f"https://www.sermonaudio.com/sermoninfo.asp?SID={sermon_id}"
        st.markdown(f"[🎧 View on SermonAudio]({sermon_url})")

    if results.get('description'):
        st.markdown("**Generated Description:**")
        st.text_area("Description", results['description'], height=150, disabled=True)

    if results.get('hashtags'):
        st.markdown("**Generated Hashtags:**")
        st.write(results['hashtags'])

    if results.get('transcript_file') or results.get('output_dir'):
        transcript_path = results.get('transcript_file')
        if not transcript_path and results.get('output_dir'):
            from src.sermon_paths import get_file_path
            transcript_path = str(get_file_path(results['output_dir'], "transcript"))
        st.markdown(f"**Transcript File:** `{transcript_path or '(not saved)'}`")
    if results.get('enhanced_audio') or results.get('enhanced_audio_path'):
        audio_path = results.get('enhanced_audio') or results.get('enhanced_audio_path')
        st.markdown(f"**Enhanced Audio:** `{audio_path}`")


if __name__ == "__main__":
    show_new_sermon_enhanced()