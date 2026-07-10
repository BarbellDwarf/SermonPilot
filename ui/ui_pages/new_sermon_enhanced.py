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

logger = logging.getLogger(__name__)


def show_new_sermon_enhanced():
    st.markdown('<div class="main-header">🎵 New Sermon</div>', unsafe_allow_html=True)

    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return

    st.markdown("---")
    _show_upload_section()
    st.markdown("---")
    _show_metadata_section()
    st.markdown("---")
    _show_processing_section()
    st.markdown("---")
    _show_start_section()


def _show_upload_section():
    st.markdown("### 1️⃣ Upload Audio/Video File")

    uploaded_file = st.file_uploader(
        "Select sermon audio or video file",
        type=['mp3', 'wav', 'm4a', 'flac', 'ogg', 'mp4', 'mov', 'webm', 'mkv'],
        help="Supported formats: Audio (MP3, WAV, M4A, FLAC, OGG) and Video (MP4, MOV, WebM, MKV)"
    )

    if uploaded_file:
        st.session_state.uploaded_file = uploaded_file

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("File Size", f"{uploaded_file.size / (1024*1024):.1f} MB")
        with col2:
            st.metric("File Type", uploaded_file.type)
        with col3:
            name = uploaded_file.name[:20] + "..." if len(uploaded_file.name) > 20 else uploaded_file.name
            st.metric("File Name", name)
        with col4:
            duration = _get_media_duration(uploaded_file)
            if duration:
                st.metric("Duration", f"{duration:.1f} min")
            else:
                st.metric("Duration", "\u23F1\uFE0F")

        max_preview_size = 100 * 1024 * 1024
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


def _show_metadata_section():
    st.markdown("### 2️⃣ Sermon Metadata")

    show_metadata_refresh_section()

    col1, col2 = st.columns(2)

    with col1:
        speaker_name = create_pastor_selectbox("Speaker *", key="speaker_name")
        recorded_date = st.date_input("Recording Date *", key="recorded_date", value=datetime.date.today())
        event_type = create_event_type_selectbox("Event Type *", key="event_type")

    with col2:
        bible_text = st.text_input("Bible Text", key="bible_text", placeholder="John 3:16-17")
        title = st.text_input("Sermon Title", key="sermon_title", placeholder="Leave blank for AI generation")
        subtitle = st.text_input("Subtitle", key="sermon_subtitle", placeholder="Additional context")
        series = create_series_selectbox("Series", key="sermon_series")
        st.session_state.sermon_series = series

    description = st.text_area("Description", key="sermon_description",
                               placeholder="Leave blank for AI generation from transcript", height=80)
    hashtags = st.text_input("Hashtags", key="sermon_hashtags",
                             placeholder="Leave blank for AI generation (e.g., #faith #grace)")

    if speaker_name and recorded_date and event_type:
        st.success("✅ Required metadata complete")
        st.session_state.metadata_complete = True
    else:
        st.warning("⚠️ Please fill in all required fields (marked with *)")
        st.session_state.metadata_complete = False


def _show_processing_section():
    st.markdown("### 3️⃣ Processing Options")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Audio Enhancement**")
        enhance_audio = st.checkbox("Enhance Audio", key="enhance_audio", value=True,
                                    help="Apply AI noise suppression to the audio")
        if enhance_audio:
            enhancement_method = st.selectbox(
                "Method", key="enhancement_method",
                options=["deepfilternet", "clear-natural", "clear-studio", "custom", "none"],
                index=0,
                help="DeepFilterNet: standard (best for speech). Clear-Natural: gentler. Clear-Studio: aggressive. Custom: any HF ONNX model."
            )
            if enhancement_method == "custom":
                st.text_input("HF Repo (e.g. tonythethompson/DeepFilterNet3-ONNX)", key="custom_repo")
                st.text_input("ONNX filename (e.g. model.onnx)", key="custom_file")

    with col2:
        st.markdown("**Transcription**")
        transcribe = st.checkbox("Transcribe Audio", key="transcribe", value=True,
                                 help="Generate transcript from the audio")
        if transcribe:
            transcription_backend_label = st.radio(
                "Backend", key="transcription_backend_radio",
                options=["Faster Whisper (Local)", "OpenAI Whisper API"],
                index=0, horizontal=True,
                help="Faster Whisper (local, CTranslate2) or OpenAI API"
            )
            transcription_backend = "faster_whisper_local" if transcription_backend_label == "Faster Whisper (Local)" else "whisper_openai"
            st.session_state.selected_backend = transcription_backend
            if transcription_backend == "whisper_openai":
                _show_openai_whisper_ui()
            else:
                st.selectbox(
                    "Model", key="whisper_model",
                    options=["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en",
                             "large", "large-v2", "large-v3", "large-v3-turbo"],
                    index=8,
                    help="Balance between speed and quality. .en models are English-only (faster)."
                )

    st.markdown("**AI Metadata Generation**")
    gen_col1, gen_col2, gen_col3, gen_col4 = st.columns(4)
    with gen_col1:
        st.checkbox("Generate Title", key="generate_title", value=True,
                    help="Use AI to generate sermon title from transcript")
    with gen_col2:
        st.checkbox("Generate Description", key="generate_description", value=True,
                    help="Use AI to generate detailed description from transcript")
    with gen_col3:
        st.checkbox("Generate Hashtags", key="generate_hashtags", value=True,
                    help="Use AI to generate relevant hashtags from content")
    with gen_col4:
        st.checkbox("Validate Quality", key="validate_description", value=True,
                    help="Use AI to validate and improve generated descriptions")

    st.checkbox("Generate Short Display Title", key="generate_short_title",
                help="Create a short (≤30 chars) display title from the full sermon title")

    st.checkbox("Dry Run (Preview Only)", key="dry_run",
                help="Process locally but don't upload to SermonAudio")


def _show_openai_whisper_ui():
    config = st.session_state.get('config', {})
    openai_cfg = config.get('transcription', {}).get('whisper_openai', {})
    api_key = openai_cfg.get('api_key', '') or os.environ.get('OPENAI_API_KEY', '')
    base_url = openai_cfg.get('base_url', '') or os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')

    if api_key:
        if st.button("🔄 Load Available Models", key="load_whisper_models"):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=base_url)
                models = client.models.list()
                whisper_models = sorted([m.id for m in models.data if 'whisper' in m.id.lower()])
                if whisper_models:
                    st.session_state['openai_whisper_models'] = whisper_models
                    st.success(f"Found {len(whisper_models)} whisper models")
                else:
                    st.warning("No whisper models found on this server")
            except Exception as e:
                st.error(f"Failed to load models: {e}")

        openai_models = st.session_state.get('openai_whisper_models', [])
        if openai_models:
            st.selectbox("Model", key="whisper_model", options=openai_models, index=0,
                         help="Select a whisper model from the server")
        else:
            st.text_input("Model", key="whisper_model", value=openai_cfg.get('model', 'whisper-1'),
                          help="Model name (e.g. whisper-1, openai/whisper-large-v3)")
    else:
        st.warning("OpenAI API key not configured. Set OPENAI_API_KEY in .env or config.")
        st.text_input("Model", key="whisper_model", value="whisper-1",
                      help="Model name (e.g. whisper-1, openai/whisper-large-v3)")


def _show_start_section():
    st.markdown("### 4️⃣ Start Processing")

    has_file = _has_uploaded_file()
    has_metadata = st.session_state.get('metadata_complete', False)

    if not has_file:
        st.warning("⚠️ Please upload a file in section 1")
        return
    if not has_metadata:
        st.warning("⚠️ Please complete required metadata in section 2")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**File & Content:**")
        st.write(f"• File: {st.session_state.uploaded_file.name}")
        st.write(f"• Size: {st.session_state.uploaded_file.size / (1024*1024):.1f} MB")
        st.write(f"• Speaker: {st.session_state.get('speaker_name', 'N/A')}")
        st.write(f"• Date: {st.session_state.get('recorded_date', 'N/A')}")
    with col2:
        st.markdown("**Processing Settings:**")
        st.write(f"• Enhance Audio: {'Yes' if st.session_state.get('enhance_audio', True) else 'No'}")
        st.write(f"• Transcribe: {'Yes' if st.session_state.get('transcribe', True) else 'No'}")
        st.write(f"• AI Metadata: {'Yes' if st.session_state.get('generate_description', True) else 'No'}")
        st.write(f"• Dry Run: {'Yes' if st.session_state.get('dry_run', False) else 'No'}")

    start_col, reset_col = st.columns(2)
    with start_col:
        if st.button("▶️ Start Processing", type="primary", use_container_width=True):
            start_enhanced_processing()
    with reset_col:
        if st.button("🔄 Reset All", use_container_width=True):
            reset_enhanced_form()

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
    try:
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
    return hasattr(st.session_state, 'uploaded_file') and st.session_state.uploaded_file is not None


def start_enhanced_processing():
    try:
        from job_queue import JobType, get_job_queue

        config = st.session_state.get('config', {})
        if not config:
            st.error("❌ No configuration loaded. Please check the Settings page first.")
            return

        required_fields = ['api_key', 'broadcaster_id']
        missing_fields = [field for field in required_fields if not config.get(field)]
        if missing_fields:
            st.error(f"❌ Configuration is missing required fields: {', '.join(missing_fields)}")
            return

        if not st.session_state.get('metadata_complete', False):
            st.error("❌ Required metadata incomplete. Please fill in speaker, date, and event type.")
            return

        uploaded_file = st.session_state.get('uploaded_file')
        if uploaded_file is None:
            st.error("❌ No file uploaded.")
            return

        upload_dir = Path(tempfile.gettempdir()) / "sermon_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(uploaded_file.name).name
        saved_path = upload_dir / f"{int(_time.time() * 1000)}_{safe_name}"
        with open(saved_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        speaker_name = st.session_state.get('speaker_name_select')
        if not speaker_name or speaker_name == '[Select Pastor]':
            speaker_name = st.session_state.get('speaker_name_custom')
        event_type = st.session_state.get('event_type_select')
        if not event_type or event_type == '[Select Event Type]':
            event_type = st.session_state.get('event_type_custom')

        recorded_date = st.session_state.get('recorded_date')
        if recorded_date is not None and hasattr(recorded_date, 'isoformat'):
            recorded_date = recorded_date.isoformat()

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

        enhance_audio = st.session_state.get('enhance_audio', True)
        transcribe = st.session_state.get('transcribe', True)
        generate_ai = st.session_state.get('generate_description', True)

        form_data = {
            'speaker_name': speaker_name,
            'recorded_date': recorded_date,
            'event_type': event_type,
            'bible_text': st.session_state.get('bible_text'),
            'title': None if st.session_state.get('generate_title', True) else (st.session_state.get('sermon_title') or None),
            'subtitle': st.session_state.get('sermon_subtitle') or None,
            'series_title': st.session_state.get('sermon_series') or None,
            'description': st.session_state.get('sermon_description') or None,
            'hashtags': st.session_state.get('sermon_hashtags') or None,
            'skip_audio': not enhance_audio,
            'skip_transcription': not transcribe,
            'skip_ai_generation': not generate_ai,
            'whisper_model': st.session_state.get('whisper_model', 'large'),
            'transcription_backend': st.session_state.get('selected_backend', 'faster_whisper_local'),
            'enhancement_method': st.session_state.get('enhancement_method', 'deepfilternet'),
            'custom_repo': st.session_state.get('custom_repo', ''),
            'custom_file': st.session_state.get('custom_file', ''),
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
    keys_to_clear = [
        'uploaded_file', 'metadata_complete',
        'speaker_name', 'recorded_date', 'event_type', 'bible_text',
        'sermon_title', 'sermon_subtitle', 'sermon_description', 'sermon_hashtags',
        'sermon_series', 'enhance_audio', 'transcribe', 'enhancement_method',
        'transcription_backend', 'whisper_model', 'custom_repo', 'custom_file',
        'selected_backend',
        'generate_title', 'generate_description', 'generate_hashtags',
        'validate_description', 'generate_short_title', 'dry_run',
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    st.success("✅ Form reset successfully!")
    st.rerun()


def _show_enhanced_processing_progress(job):
    st.markdown("#### 🔄 Processing Progress")
    from job_queue import JobStatus

    st.progress(job.progress / 100.0)

    status_colors = {
        JobStatus.QUEUED: "🔵", JobStatus.RUNNING: "🟡", JobStatus.COMPLETED: "🟢",
        JobStatus.FAILED: "🔴", JobStatus.CANCELLED: "⚫", JobStatus.PAUSED: "🟠"
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
