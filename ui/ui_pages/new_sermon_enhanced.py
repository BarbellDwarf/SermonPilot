# ui/ui_pages/new_sermon_enhanced.py
"""
Enhanced New Sermon Processing Page with Audio Editing

Integrates audio editing capabilities with the sermon upload workflow,
providing a comprehensive interface for content creators.
"""

import datetime
import sys
import tempfile
import os
from pathlib import Path
import numpy as np

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

# Import our new audio editing components
try:
    from ui.components.audio_waveform import AudioWaveformViewer
    from ui.components.audio_editor import AudioEditor
    from ui.components.audio_preview import AudioPreview
    from ui.components.processing_modes import ProcessingModeSelector
    from src.audio.question_processor import QuestionProcessor
    from src.audio.adaptive_processor import AdaptiveAudioProcessor
    AUDIO_EDITING_AVAILABLE = True
except ImportError as e:
    st.error(f"Audio editing components not available: {e}")
    AUDIO_EDITING_AVAILABLE = False


def show_new_sermon_enhanced():
    """Enhanced new sermon processing interface with audio editing."""
    st.markdown('<div class="main-header">🎵 Enhanced New Sermon</div>', unsafe_allow_html=True)
    
    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return
    
    if not AUDIO_EDITING_AVAILABLE:
        st.error("❌ Audio editing components not available. Please check the installation.")
        return

    # Enhanced workflow tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📁 Upload & Metadata",
        "📊 Analyze Audio", 
        "✂️ Edit Audio",
        "🎛️ Configure Processing",
        "▶️ Process & Upload"
    ])

    with tab1:
        show_upload_and_metadata()

    with tab2:
        if _has_uploaded_file():
            show_audio_analysis()
        else:
            st.info("📁 Please upload an audio file in the first tab to analyze it.")

    with tab3:
        if _has_uploaded_file():
            show_audio_editing()
        else:
            st.info("📁 Please upload an audio file in the first tab to edit it.")

    with tab4:
        show_processing_configuration()

    with tab5:
        show_process_and_upload()


def show_upload_and_metadata():
    """File upload and metadata form with enhanced features."""
    st.markdown("### 📁 Audio File Upload")

    # File upload with additional instructions
    st.info("💡 **New Features:** After uploading, you can analyze and edit your audio before processing!")
    
    uploaded_file = st.file_uploader(
        "Select sermon audio file",
        type=['mp3', 'wav', 'm4a', 'flac', 'ogg'],
        help="Supported formats: MP3, WAV, M4A, FLAC, OGG"
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
            # Estimate duration (rough approximation)
            estimated_duration = uploaded_file.size / (1024 * 16)  # Rough estimate assuming 16KB/s
            st.metric("Est. Duration", f"{estimated_duration/60:.1f} min")

        # Audio preview
        try:
            st.audio(uploaded_file, format=uploaded_file.type)
        except Exception as e:
            st.warning(f"Could not preview audio: {e}")

        # Process and store audio data for editing
        _process_uploaded_audio(uploaded_file)

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


def show_audio_analysis():
    """Audio analysis tab with waveform visualization and Q&A detection."""
    st.markdown("### 🔍 Audio Analysis")
    
    if 'audio_data' not in st.session_state or 'sample_rate' not in st.session_state:
        st.warning("⚠️ Audio data not processed. Please reload the audio file.")
        return

    audio_data = st.session_state.audio_data
    sample_rate = st.session_state.sample_rate

    # Initialize components
    if 'waveform_viewer' not in st.session_state:
        st.session_state.waveform_viewer = AudioWaveformViewer(audio_data, sample_rate)

    waveform_viewer = st.session_state.waveform_viewer

    # Render audio information
    st.subheader("📊 Audio Information")
    waveform_viewer.render_audio_info()

    # Render waveform
    st.subheader("🌊 Waveform Visualization")
    selected_region = waveform_viewer.render_waveform()

    # Analysis tools
    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔍 Analyze Audio Quality", type="primary"):
            with st.spinner("Analyzing audio..."):
                issues = _analyze_audio_issues(audio_data, sample_rate)
                if issues:
                    st.warning("**Potential Issues Detected:**")
                    for issue in issues:
                        st.write(f"• {issue}")
                else:
                    st.success("✅ No significant issues detected!")

    with col2:
        if st.button("❓ Detect Q&A Segments", type="primary"):
            with st.spinner("Detecting question segments..."):
                question_processor = QuestionProcessor({'sample_rate': sample_rate})
                question_segments = question_processor.detect_question_segments(audio_data)

                if question_segments:
                    st.success(f"🎯 Found {len(question_segments)} potential Q&A segments")

                    # Mark segments on waveform
                    waveform_viewer.clear_segments()
                    for start_time, end_time in question_segments:
                        waveform_viewer.add_segment(start_time, end_time, 'question')

                    # Store for later use
                    st.session_state.question_segments = question_segments

                    # Display segment list
                    st.subheader("📋 Detected Q&A Segments")
                    for i, (start, end) in enumerate(question_segments):
                        st.write(f"**Segment {i+1}:** {start:.1f}s - {end:.1f}s ({end-start:.1f}s duration)")
                else:
                    st.info("ℹ️ No Q&A segments automatically detected. You can mark them manually in the editing tab.")

    # Processing recommendations
    if 'question_segments' in st.session_state:
        question_processor = QuestionProcessor({'sample_rate': sample_rate})
        recommendations = question_processor.get_processing_recommendations(st.session_state.question_segments)
        
        st.subheader("💡 Processing Recommendations")
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"**Recommended Mode:** {recommendations['recommended_mode']}")
            st.info(f"**Has Questions:** {'Yes' if recommendations['has_questions'] else 'No'}")
        
        with col2:
            st.info(f"**Noise Reduction:** {recommendations['noise_reduction_strength']:.1f}")
            if recommendations.get('question_preservation'):
                st.info("**Question Preservation:** Enabled")


def show_audio_editing():
    """Audio editing tab with manual controls."""
    st.markdown("### ✂️ Audio Editing")
    
    if 'audio_data' not in st.session_state:
        st.warning("⚠️ Audio data not processed. Please reload the audio file.")
        return

    audio_data = st.session_state.audio_data
    sample_rate = st.session_state.sample_rate

    # Initialize components
    if 'audio_editor' not in st.session_state:
        st.session_state.audio_editor = AudioEditor()
    if 'audio_preview' not in st.session_state:
        st.session_state.audio_preview = AudioPreview()
    if 'waveform_viewer' not in st.session_state:
        st.session_state.waveform_viewer = AudioWaveformViewer(audio_data, sample_rate)

    audio_editor = st.session_state.audio_editor
    audio_preview = st.session_state.audio_preview
    waveform_viewer = st.session_state.waveform_viewer

    # Editing controls
    duration = len(audio_data) / sample_rate
    edit_params = audio_editor.render_controls(duration)

    # Handle segment addition
    if edit_params.get('action') == 'add_segment':
        start_time = edit_params['start_time']
        end_time = edit_params['end_time']
        action = edit_params['segment_action']
        
        waveform_viewer.add_segment(start_time, end_time, action)
        st.success(f"✅ Added {action} segment: {start_time:.1f}s - {end_time:.1f}s")
        st.rerun()

    # Display current segments
    waveform_viewer.render_segment_list()

    # Preview controls
    st.subheader("🔊 Audio Preview")
    preview_controls = audio_preview.render_preview_controls()

    # Handle preview actions
    if preview_controls.get('action') == 'play_original':
        # Create original preview
        original_file = _create_original_preview(audio_data, sample_rate, preview_controls.get('preview_volume', 0.7))
        if original_file:
            audio_preview.render_audio_player(original_file, "Original Audio")

    elif preview_controls.get('action') == 'play_edited':
        # Apply edits and create preview
        segments = waveform_viewer.get_segments()
        if segments:
            edited_file = audio_preview.create_preview_with_edits(
                audio_data, sample_rate, segments, preview_controls.get('preview_volume', 0.7)
            )
            if edited_file:
                audio_preview.render_audio_player(edited_file, "Edited Audio")
        else:
            st.info("ℹ️ No edits applied. Playing original audio.")
            original_file = _create_original_preview(audio_data, sample_rate, preview_controls.get('preview_volume', 0.7))
            if original_file:
                audio_preview.render_audio_player(original_file, "Original Audio")

    elif preview_controls.get('action') == 'compare':
        # Side-by-side comparison
        segments = waveform_viewer.get_segments()
        original_file = _create_original_preview(audio_data, sample_rate, preview_controls.get('preview_volume', 0.7))
        edited_file = audio_preview.create_preview_with_edits(
            audio_data, sample_rate, segments, preview_controls.get('preview_volume', 0.7)
        ) if segments else original_file
        
        if original_file and edited_file:
            audio_preview.render_comparison_player(original_file, edited_file)

    elif preview_controls.get('action') == 'reset':
        waveform_viewer.clear_segments()
        if 'question_segments' in st.session_state:
            del st.session_state.question_segments
        st.success("🔄 All edits cleared!")
        st.rerun()

    # Audio statistics
    segments = waveform_viewer.get_segments()
    if segments:
        st.subheader("📈 Edit Summary")
        summary = audio_editor.get_editing_summary(segments)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Segments", summary['total_segments'])
        with col2:
            st.metric("Edited Duration", f"{summary['total_edited_duration']:.1f}s")
        with col3:
            remaining_duration = duration - sum(
                end - start for start, end, action in segments if action == 'remove'
            )
            st.metric("Final Duration", f"{remaining_duration:.1f}s")

        # Show actions breakdown
        if summary['actions']:
            st.markdown("**Actions Applied:**")
            for action, info in summary['actions'].items():
                st.write(f"• {action.title()}: {info['count']} segments ({info['duration']:.1f}s)")


def show_processing_configuration():
    """Processing configuration with enhanced mode selection."""
    st.markdown("### 🎛️ Processing Configuration")

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
    
    with st.expander("Legacy Processing Options", expanded=False):
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

    # AI Metadata Generation
    st.markdown("### 🤖 AI Metadata Generation")

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
        
        # Show edit summary if any edits were made
        if 'waveform_viewer' in st.session_state:
            segments = st.session_state.waveform_viewer.get_segments()
            if segments:
                st.write(f"• Edits Applied: {len(segments)} segments")

    with col2:
        st.markdown("**Processing Settings:**")
        mode_name = st.session_state.get('selected_mode', 'standard')
        st.write(f"• Mode: {mode_name}")
        st.write(f"• Enhancement: {st.session_state.get('enhancement_method', 'deepfilternet')}")
        st.write(f"• Transcription: {'Enabled' if not st.session_state.get('skip_transcription', False) else 'Disabled'}")
        st.write(f"• Dry Run: {'Yes' if st.session_state.get('dry_run', False) else 'No'}")
        
        # Show question segments if detected
        if 'question_segments' in st.session_state:
            st.write(f"• Q&A Segments: {len(st.session_state.question_segments)}")

    # Processing controls
    st.markdown("#### 🚀 Enhanced Processing")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🎵 Process with Audio Editing", type="primary", use_container_width=True):
            start_enhanced_processing()

    with col2:
        if st.button("📊 Preview Processing", use_container_width=True):
            preview_processing()

    with col3:
        if st.button("🔄 Reset All", use_container_width=True):
            reset_enhanced_form()

    # Show processing status
    _show_enhanced_processing_status()


def _process_uploaded_audio(uploaded_file):
    """Process uploaded audio file for editing."""
    try:
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            temp_file.write(uploaded_file.getvalue())
            temp_file_path = temp_file.name

        # Load audio data
        from pydub import AudioSegment
        audio = AudioSegment.from_file(temp_file_path)

        # Convert to numpy array
        audio_data = np.array(audio.get_array_of_samples(), dtype=np.float32)
        if audio.channels == 2:
            audio_data = audio_data.reshape((-1, 2))
            audio_data = np.mean(audio_data, axis=1)  # Convert to mono

        # Normalize to [-1, 1]
        if audio.sample_width == 2:  # 16-bit
            audio_data = audio_data / 32768.0
        elif audio.sample_width == 4:  # 32-bit
            audio_data = audio_data / 2147483648.0
        else:
            # Auto-normalize based on max value
            max_val = np.max(np.abs(audio_data))
            if max_val > 0:
                audio_data = audio_data / max_val

        # Store in session state
        st.session_state.audio_data = audio_data
        st.session_state.sample_rate = audio.frame_rate
        st.session_state.original_temp_file = temp_file_path

        # Clear any existing components to reinitialize with new audio
        for key in ['waveform_viewer', 'audio_editor', 'audio_preview']:
            if key in st.session_state:
                del st.session_state[key]

    except Exception as e:
        st.error(f"Error processing audio file: {e}")


def _analyze_audio_issues(audio_data, sample_rate):
    """Analyze audio for potential issues."""
    issues = []

    # Check for clipping
    if np.max(np.abs(audio_data)) > 0.95:
        issues.append("Audio may be clipped - consider reducing levels")

    # Check for low volume
    rms = np.sqrt(np.mean(audio_data**2))
    if rms < 0.01:
        issues.append("Audio levels are very low - will be amplified")

    # Check for DC offset
    dc_offset = np.mean(audio_data)
    if abs(dc_offset) > 0.01:
        issues.append("DC offset detected - will be corrected")

    # Check for silence
    silence_threshold = 0.001
    silence_ratio = np.sum(np.abs(audio_data) < silence_threshold) / len(audio_data)
    if silence_ratio > 0.3:
        issues.append(f"High silence ratio ({silence_ratio:.1%}) - consider trimming")

    return issues


def _create_original_preview(audio_data, sample_rate, volume):
    """Create preview of original audio."""
    if 'audio_preview' not in st.session_state:
        st.session_state.audio_preview = AudioPreview()
    
    return st.session_state.audio_preview.create_preview_audio(audio_data, sample_rate, volume=volume)


def _has_uploaded_file():
    """Check if user has uploaded a file."""
    return hasattr(st.session_state, 'uploaded_file') and st.session_state.uploaded_file is not None


def start_enhanced_processing():
    """Start enhanced processing with audio editing support."""
    try:
        # Collect all form data
        form_data = _collect_enhanced_form_data()
        
        # Apply audio edits if any
        processed_audio = _apply_audio_edits()
        
        # Start processing (this would integrate with the job queue)
        st.success("🚀 Enhanced processing started!")
        st.info("Processing will include audio edits and optimized settings for your content.")
        
        # TODO: Integrate with job queue system
        
    except Exception as e:
        st.error(f"❌ Failed to start enhanced processing: {e}")


def preview_processing():
    """Preview what processing will be applied."""
    st.subheader("📊 Processing Preview")
    
    # Show processing steps
    steps = []
    
    # Audio editing steps
    if 'waveform_viewer' in st.session_state:
        segments = st.session_state.waveform_viewer.get_segments()
        if segments:
            steps.append("✂️ Apply audio edits")
    
    # Q&A processing
    if 'question_segments' in st.session_state:
        steps.append("❓ Apply Q&A-aware processing")
    
    # Standard processing steps
    if not st.session_state.get('skip_transcription', False):
        steps.append("🎙️ Generate transcript")
    
    steps.extend([
        "🎵 Enhance audio quality",
        "🤖 Generate metadata",
        "📤 Upload to SermonAudio"
    ])
    
    if steps:
        st.write("**Processing Steps:**")
        for step in steps:
            st.write(step)
    
    # Show estimated time
    base_time = 2.0  # Base processing time multiplier
    if 'question_segments' in st.session_state:
        base_time *= 1.3  # Additional time for Q&A processing
    
    estimated_minutes = base_time * (st.session_state.uploaded_file.size / (1024 * 1024)) / 2
    st.info(f"⏱️ Estimated processing time: {estimated_minutes:.1f} minutes")


def _collect_enhanced_form_data():
    """Collect form data including edits and processing settings."""
    form_data = {}
    
    # Basic metadata
    form_data.update({
        'speaker_name': st.session_state.get('speaker_name'),
        'recorded_date': st.session_state.get('recorded_date'),
        'event_type': st.session_state.get('event_type'),
        'bible_text': st.session_state.get('bible_text'),
        'title': st.session_state.get('sermon_title'),
        'subtitle': st.session_state.get('sermon_subtitle'),
        'description': st.session_state.get('sermon_description'),
        'hashtags': st.session_state.get('sermon_hashtags'),
    })
    
    # Audio edits
    if 'waveform_viewer' in st.session_state:
        form_data['audio_edits'] = st.session_state.waveform_viewer.get_segments()
    
    # Question segments
    if 'question_segments' in st.session_state:
        form_data['question_segments'] = st.session_state.question_segments
    
    # Processing configuration
    form_data['processing_config'] = st.session_state.get('processing_config', {})
    
    return form_data


def _apply_audio_edits():
    """Apply audio edits and return processed audio."""
    if 'audio_data' not in st.session_state or 'waveform_viewer' not in st.session_state:
        return None
    
    audio_data = st.session_state.audio_data.copy()
    segments = st.session_state.waveform_viewer.get_segments()
    
    if not segments:
        return audio_data
    
    # Apply edits in reverse order to maintain sample indices
    segments = sorted(segments, key=lambda x: x[0], reverse=True)
    
    audio_editor = st.session_state.get('audio_editor')
    if not audio_editor:
        return audio_data
    
    sample_rate = st.session_state.sample_rate
    
    for start_time, end_time, action in segments:
        audio_data = audio_editor.apply_edit(
            audio_data, sample_rate, start_time, end_time, action
        )
    
    return audio_data


def reset_enhanced_form():
    """Reset the enhanced form to initial state."""
    # Clear session state variables
    keys_to_clear = [
        'uploaded_file', 'metadata_complete', 'audio_data', 'sample_rate',
        'waveform_viewer', 'audio_editor', 'audio_preview', 'mode_selector',
        'question_segments', 'processing_config', 'selected_mode',
        'speaker_name', 'recorded_date', 'event_type', 'bible_text',
        'sermon_title', 'sermon_subtitle', 'sermon_description', 'sermon_hashtags'
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    st.success("✅ Enhanced form reset successfully!")
    st.rerun()


def _show_enhanced_processing_status():
    """Show enhanced processing status."""
    # This would integrate with the job queue system
    # For now, just show placeholder
    if st.session_state.get('processing_active'):
        st.info("🔄 Processing in progress...")


if __name__ == "__main__":
    show_new_sermon_enhanced()