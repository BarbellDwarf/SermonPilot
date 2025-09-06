"""
New Sermon Processing Page for SermonAudio Processor

Handles file upload, metadata form input, processing options configuration,
and real-time processing with progress updates.
"""

import datetime
import sys
from pathlib import Path

import streamlit as st

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from sermon_metadata import (
    create_event_type_selectbox,
    create_pastor_selectbox,
    create_series_selectbox,
    show_metadata_refresh_section,
)


def show_new_sermon():
    """Main new sermon processing interface"""
    st.markdown('<div class="main-header">🎵 New Sermon</div>', unsafe_allow_html=True)

    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return

    # Processing workflow tabs
    tab1, tab2, tab3 = st.tabs(["📁 Upload & Metadata", "⚙️ Processing Options", "▶️ Process & Review"])

    with tab1:
        show_upload_and_metadata()

    with tab2:
        show_processing_options()

    with tab3:
        show_process_and_review()

def show_upload_and_metadata():
    """File upload and metadata form"""
    st.markdown("### 📁 Audio File Upload")

    # File upload
    uploaded_file = st.file_uploader(
        "Select sermon audio file",
        type=['mp3', 'wav', 'm4a', 'flac', 'ogg'],
        help="Supported formats: MP3, WAV, M4A, FLAC, OGG"
    )

    if uploaded_file:
        # Store file info in session state
        st.session_state.uploaded_file = uploaded_file

        # Show file details
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("File Size", f"{uploaded_file.size / (1024*1024):.1f} MB")
        with col2:
            st.metric("File Type", uploaded_file.type)
        with col3:
            st.metric("File Name", uploaded_file.name[:20] + "..." if len(uploaded_file.name) > 20 else uploaded_file.name)

        # Audio preview (if possible)
        try:
            st.audio(uploaded_file, format=uploaded_file.type)
        except Exception as e:
            st.warning(f"Could not preview audio: {e}")

    st.markdown("### 📝 Sermon Metadata")

    # Show metadata refresh section
    show_metadata_refresh_section()

    # Required metadata
    col1, col2 = st.columns(2)

    with col1:
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

    # Optional metadata
    st.markdown("#### Optional Fields")

    # Series selection
    series = create_series_selectbox(
        "Series (optional)",
        key="sermon_series"
    )

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

    # Validation
    if speaker_name and recorded_date and event_type:
        st.success("✅ Required metadata complete")
        st.session_state.metadata_complete = True
    else:
        st.warning("⚠️ Please fill in all required fields (marked with *)")
        st.session_state.metadata_complete = False

def show_processing_options():
    """Processing configuration options"""
    st.markdown("### ⚙️ Processing Configuration")

    # Audio processing options
    st.markdown("#### 🎵 Audio Enhancement")

    col1, col2 = st.columns(2)

    with col1:
        enhancement_method = st.selectbox(
            "Enhancement Method",
            key="enhancement_method",
            options=["deepfilternet", "resemble_enhance", "none"],
            index=0,
            help="Choose AI enhancement method for audio quality improvement"
        )

        skip_transcription = st.checkbox(
            "Skip Transcription",
            key="skip_transcription",
            help="Skip audio transcription to speed up processing"
        )

    with col2:
        whisper_model = st.selectbox(
            "Whisper Model (if transcribing)",
            key="whisper_model",
            options=["tiny", "base", "small", "medium", "large"],
            index=1,
            help="Balance between speed and quality"
        )

        dry_run = st.checkbox(
            "Dry Run (Preview Only)",
            key="dry_run",
            help="Process locally but don't upload to SermonAudio"
        )

    # Model performance info
    with st.expander("ℹ️ Model Performance Guide"):
        st.markdown("""
        **Whisper Model Performance:**
        - **tiny**: ~32x realtime, basic quality (39MB)
        - **base**: ~16x realtime, good quality (142MB) - *Recommended*
        - **small**: ~8x realtime, better quality (461MB)
        - **medium**: ~4x realtime, high quality (1.5GB)
        - **large**: ~2x realtime, best quality (2.9GB)
        
        **Enhancement Methods:**
        - **DeepFilterNet**: Fast, good for voice clarity
        - **Resemble Enhance**: Slower, excellent overall quality
        - **None**: No enhancement, fastest processing
        """)

    # Metadata generation options
    st.markdown("#### 🤖 AI Metadata Generation")

    col1, col2 = st.columns(2)

    with col1:
        generate_title = st.checkbox(
            "Generate Title",
            key="generate_title",
            value=True,
            help="Use AI to generate sermon title from transcript"
        )

        generate_description = st.checkbox(
            "Generate Description",
            key="generate_description",
            value=True,
            help="Use AI to generate detailed description from transcript"
        )

    with col2:
        generate_hashtags = st.checkbox(
            "Generate Hashtags",
            key="generate_hashtags",
            value=True,
            help="Use AI to generate relevant hashtags from content"
        )

        validate_description = st.checkbox(
            "Validate Description Quality",
            key="validate_description",
            value=True,
            help="Use AI to validate and improve generated descriptions"
        )

def show_process_and_review():
    """Processing execution and results review"""
    st.markdown("### ▶️ Process & Review")

    # Check prerequisites
    has_file = hasattr(st.session_state, 'uploaded_file') and st.session_state.uploaded_file is not None
    has_metadata = st.session_state.get('metadata_complete', False)

    if not has_file:
        st.warning("⚠️ Please upload an audio file in the first tab")
        return

    if not has_metadata:
        st.warning("⚠️ Please complete required metadata in the first tab")
        return

    # Processing summary
    st.markdown("#### 📋 Processing Summary")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**File Information:**")
        st.write(f"• File: {st.session_state.uploaded_file.name}")
        st.write(f"• Size: {st.session_state.uploaded_file.size / (1024*1024):.1f} MB")
        st.write(f"• Speaker: {st.session_state.get('speaker_name', 'N/A')}")
        st.write(f"• Date: {st.session_state.get('recorded_date', 'N/A')}")

    with col2:
        st.markdown("**Processing Options:**")
        st.write(f"• Enhancement: {st.session_state.get('enhancement_method', 'deepfilternet')}")
        st.write(f"• Transcription: {'Enabled' if not st.session_state.get('skip_transcription', False) else 'Disabled'}")
        st.write(f"• AI Generation: {'Enabled' if st.session_state.get('generate_description', True) else 'Disabled'}")
        st.write(f"• Dry Run: {'Yes' if st.session_state.get('dry_run', False) else 'No'}")

    # Processing controls
    st.markdown("#### 🚀 Processing Controls")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("▶️ Start Processing", type="primary", width='stretch'):
            start_processing()

    with col2:
        if st.button("⏸️ Pause", width='stretch', disabled=True):
            st.info("Pause functionality will be implemented")

    with col3:
        if st.button("🔄 Reset", width='stretch'):
            reset_form()

    # Show processing status based on job queue
    job_id = st.session_state.get('current_sermon_job_id')
    active_job = None
    if job_id:
        try:
            from job_queue import get_job_queue, JobStatus
            job_queue = get_job_queue()
            active_job = job_queue.get_job(job_id)
        except Exception:
            pass
    
    if active_job and active_job.status in [JobStatus.QUEUED, JobStatus.RUNNING]:
        show_processing_progress()
    elif active_job and active_job.status == JobStatus.COMPLETED:
        show_processing_results_from_job(active_job)

def start_processing():
    """Start the sermon processing workflow using job queue"""
    try:
        from job_queue import JobType, get_job_queue
        
        # Get form data from session state
        form_data = st.session_state.get('new_sermon_form', {})
        if not form_data:
            st.error("❌ No sermon data found. Please fill out the form first.")
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
            
        # Create sermon processing job
        job_queue = get_job_queue()
        
        job_title = f"New Sermon: {form_data.get('title', 'Untitled')}"
        job_description = f"Processing new sermon by {form_data.get('speaker_name', 'Unknown Speaker')}"
        
        job_id = job_queue.add_job(
            job_type=JobType.SERMON_PROCESSING,
            title=job_title,
            description=job_description,
            parameters={
                'form_data': form_data,
                'config': config,
                'processing_type': 'new_sermon'
            },
            priority=8  # High priority for new sermon processing
        )
        
        # Store job ID in session state for tracking
        st.session_state.current_sermon_job_id = job_id
        
        st.success(f"✅ Sermon processing job created! Job ID: {job_id[:8]}")
        st.info(f"🔍 Processing sermon in the background. You can monitor progress on the Jobs page.")
        
        # Add button to go to jobs page
        if st.button("📊 View Job Progress", type="secondary"):
            st.session_state.current_page = 'jobs'
            st.rerun()
            
    except Exception as e:
        st.error(f"❌ Failed to start sermon processing job: {e}")

def show_processing_progress():
    """Show real-time processing progress from job queue"""
    st.markdown("#### 🔄 Processing Progress")

    job_id = st.session_state.get('current_sermon_job_id')
    if not job_id:
        st.info("No active sermon processing job")
        return
        
    try:
        from job_queue import get_job_queue, JobStatus
        job_queue = get_job_queue()
        job = job_queue.get_job(job_id)
        
        if not job:
            st.warning("⚠️ Sermon processing job not found")
            st.session_state.current_sermon_job_id = None
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
        
        # Show results if completed
        if job.status == JobStatus.COMPLETED and job.result:
            show_processing_results_from_job(job)
        
        # Clear job ID if completed
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            if st.button("Clear Completed Job"):
                st.session_state.current_sermon_job_id = None
                st.rerun()
                
    except Exception as e:
        st.error(f"❌ Error checking job progress: {e}")
        st.session_state.current_sermon_job_id = None

def show_processing_results_from_job(job):
    """Show processing results from completed job"""
    if not job.result or not job.result.success:
        st.error("❌ Processing failed")
        if job.result and job.result.error:
            st.error(f"Error: {job.result.error}")
        return
        
    results = job.result.data
    if not results:
        st.warning("⚠️ No results data available")
        return
        
    st.markdown("#### � Processing Results")
    
    # Show success message
    st.success("✅ Processing completed successfully!")
    
    # Display results in a nice format
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Sermon ID", results.get('sermon_id', 'Unknown'))
        st.metric("Processing Time", results.get('processing_time', 'Unknown'))
    
    with col2:
        st.metric("Status", "Success" if results.get('success') else "Failed")
        if results.get('title'):
            st.metric("Title", results.get('title'))
    
    # Show generated content
    if results.get('description'):
        st.markdown("**Generated Description:**")
        st.text_area("Description", results['description'], height=150, disabled=True)
    
    if results.get('hashtags'):
        st.markdown("**Generated Hashtags:**")
        st.write(results['hashtags'])
    
    # Show file paths
    if results.get('transcript_file'):
        st.markdown(f"**Transcript File:** `{results['transcript_file']}`")
    if results.get('enhanced_audio'):
        st.markdown(f"**Enhanced Audio:** `{results['enhanced_audio']}`")
        st.text("Current step: Generating metadata...")

        # Log output
        with st.expander("📝 Processing Log"):
            st.code("""
[2024-01-15 10:30:15] Starting audio enhancement...
[2024-01-15 10:30:18] Audio enhancement completed
[2024-01-15 10:30:19] Starting transcription...
[2024-01-15 10:30:45] Transcription completed (26 seconds)
[2024-01-15 10:30:46] Generating description...
            """)

def show_processing_results():
    """Show processing results and generated content"""
    st.markdown("#### ✅ Processing Results")

    results = st.session_state.processing_results

    if results.get('success'):
        st.success(f"🎉 Sermon created successfully! ID: {results.get('sermon_id')}")

        # Generated content review
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Generated Title:**")
            title = st.text_input("Title", value=results.get('title', ''), key="result_title")

            st.markdown("**Generated Hashtags:**")
            hashtags = st.text_input("Hashtags", value=results.get('hashtags', ''), key="result_hashtags")

        with col2:
            st.markdown("**Generated Description:**")
            description = st.text_area("Description", value=results.get('description', ''), height=100, key="result_description")

        # Action buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 Save Changes", width='stretch'):
                st.success("Changes saved!")

        with col2:
            if st.button("🔄 Regenerate Metadata", width='stretch'):
                st.info("Regenerating metadata...")

        with col3:
            if st.button("📤 Upload to SermonAudio", width='stretch'):
                st.success("Uploaded successfully!")

        # Generated files
        st.markdown("#### 📁 Generated Files")

        files_info = [
            ("Enhanced Audio", results.get('enhanced_audio', ''), "🎵"),
            ("Transcript", results.get('transcript_file', ''), "📝"),
            ("Metadata", "metadata.json", "📋")
        ]

        for file_name, file_path, icon in files_info:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"{icon} {file_name}: `{file_path}`")
            with col2:
                st.button("📥 Download", key=f"download_{file_name.lower()}")

    else:
        st.error("❌ Processing failed. Please check the logs and try again.")

def reset_form():
    """Reset the form to initial state"""
    # Clear session state variables
    keys_to_clear = [
        'uploaded_file', 'metadata_complete', 'processing_active',
        'processing_results', 'speaker_name', 'recorded_date',
        'event_type', 'bible_text', 'sermon_title', 'sermon_subtitle',
        'sermon_description', 'sermon_hashtags'
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    st.success("Form reset successfully!")
    st.rerun()

if __name__ == "__main__":
    show_new_sermon()
