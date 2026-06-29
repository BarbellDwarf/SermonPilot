"""
Sermon Viewer Page - Detailed sermon viewing
"""

import sys
from pathlib import Path

import streamlit as st
from ui.pages import library

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))


def show_viewer():
    """Main sermon viewer interface"""
    st.markdown('<div class="main-header">📖 Sermon Viewer</div>', unsafe_allow_html=True)

    # Check if a sermon is selected
    if 'selected_sermon' not in st.session_state:
        st.info("No sermon selected. Please select a sermon from the Library page.")

        # Show recent sermons for selection
        st.subheader("Recent Sermons")
        try:
            from database import SermonRepository
            repo = SermonRepository()
            recent_sermons = repo.get_all_sermons(limit=10)

            if recent_sermons:
                for sermon in recent_sermons:
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        title = sermon.get('title', 'Untitled Sermon')
                        speaker = sermon.get('speaker', 'Unknown Speaker')
                        date = sermon.get('recorded_date', 'Unknown Date')
                        st.write(f"**{title}** by {speaker} ({date})")

                    with col2:
                        if st.button("📖 View", key=f"select_{sermon.get('id')}"):
                            st.session_state.selected_sermon = sermon.get('id')
                            st.rerun()
            else:
                st.write("No sermons available.")
        except ImportError:
            st.error("❌ Database module not found")
        except Exception as e:
            st.error(f"❌ Error loading sermons: {e}")

        return

    sermon_id = st.session_state.selected_sermon
    edit_mode = st.session_state.get('edit_mode', False)

    # Navigation
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("⬅️ Back to Library"):
            if 'selected_sermon' in st.session_state:
                del st.session_state.selected_sermon
            st.switch_page(library)

    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    # Load sermon details
    try:
        from database import SermonRepository
        repo = SermonRepository()
        sermon = repo.get_sermon(sermon_id)

        if not sermon:
            st.error(f"❌ Sermon {sermon_id} not found")
            if st.button("🔄 Clear Selection"):
                if 'selected_sermon' in st.session_state:
                    del st.session_state.selected_sermon
                st.rerun()
            return

        # Header with sermon info
        st.title(f"📖 {sermon.get('title', 'Unknown Title')}")
        st.subheader(f"by {sermon.get('speaker', 'Unknown')} • {sermon.get('recorded_date', 'Unknown Date')}")

        # Status and info
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            status = sermon.get('status', 'unknown')
            status_emoji_map = {
                'processed': '✅',
                'processing': '⏳',
                'pending': '⏸️',
                'failed': '❌',
                'uploaded': '☁️'
            }
            status_emoji = status_emoji_map.get(status, '❓')
            st.metric("Status", f"{status_emoji} {status.title()}")

        with col2:
            qa_count = sermon.get('qa_segments_count', 0)
            st.metric("Q&A Segments", qa_count)

        with col3:
            duration = sermon.get('duration', 0)
            if duration:
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                if hours > 0:
                    duration_str = f"{hours}h {minutes}m"
                else:
                    duration_str = f"{minutes}m"
                st.metric("Duration", duration_str)
            else:
                st.metric("Duration", "Unknown")

        with col4:
            if sermon.get('event_type'):
                st.metric("Event Type", sermon.get('event_type'))

        # Edit mode toggle
        if st.button("✏️ Toggle Edit Mode", type="secondary"):
            st.session_state.edit_mode = not edit_mode
            st.rerun()

        st.divider()

        # Content tabs
        if edit_mode:
            tabs = st.tabs(["🎵 Audio", "📄 Edit Transcript", "📝 Edit Metadata", "🔧 Processing Info"])
        else:
            tabs = st.tabs(["🎵 Audio", "📄 Transcript", "📝 Description", "🔧 Processing Info"])

        # Tab 1: Audio
        with tabs[0]:
            st.subheader("🎵 Audio Player")

            file_paths = sermon.get('file_paths', {})

            # Show all available audio files
            available_audio = {}
            if file_paths.get('original_audio') and Path(file_paths['original_audio']).exists():
                available_audio['🎙️ Original Audio'] = file_paths['original_audio']
            if file_paths.get('processed_audio') and Path(file_paths['processed_audio']).exists():
                available_audio['🔧 Processed Audio'] = file_paths['processed_audio']
            if file_paths.get('enhanced_audio') and Path(file_paths['enhanced_audio']).exists():
                available_audio['✨ Enhanced Audio'] = file_paths['enhanced_audio']

            if available_audio:
                # Audio file selector
                if len(available_audio) > 1:
                    selected_audio_type = st.selectbox(
                        "Select Audio Type:",
                        list(available_audio.keys()),
                        index=0
                    )
                    audio_path = available_audio[selected_audio_type]
                else:
                    audio_path = list(available_audio.values())[0]
                    selected_audio_type = list(available_audio.keys())[0]

                # Display audio player
                st.audio(str(audio_path), format='audio/mp3')

                # File info
                file_size = Path(audio_path).stat().st_size / (1024 * 1024)  # MB
                st.caption(f"Playing: {selected_audio_type}")
                st.caption(f"File: {Path(audio_path).name} ({file_size:.1f} MB)")

                # Show all available files as info
                if len(available_audio) > 1:
                    st.info(f"Available audio files: {', '.join(available_audio.keys())}")

                # Q&A segments
                qa_segments = sermon.get('qa_segments', [])
                if qa_segments:
                    st.subheader("🗣️ Q&A Segments")

                    for i, segment in enumerate(qa_segments, 1):
                        col1, col2, col3 = st.columns([2, 1, 1])

                        with col1:
                            start_time = segment.get('start_time', 0)
                            end_time = segment.get('end_time', 0)
                            start_min = int(start_time // 60)
                            start_sec = int(start_time % 60)
                            end_min = int(end_time // 60)
                            end_sec = int(end_time % 60)
                            st.write(f"**Q&A {i}:** {start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}")

                        with col2:
                            gain = segment.get('gain_applied', 0)
                            st.write(f"Boost: +{gain:.1f}dB")

                        with col3:
                            confidence = segment.get('confidence', 0)
                            st.write(f"Confidence: {confidence:.1%}")
            else:
                st.warning("Audio file not found")
                st.info("No audio files are available for this sermon.")

        # Tab 2: Transcript
        with tabs[1]:
            if edit_mode:
                st.subheader("📄 Edit Transcript")

                current_transcript = sermon.get('transcript', '')

                transcript = st.text_area(
                    "Transcript Content",
                    value=current_transcript,
                    height=400,
                    help="Edit the sermon transcript"
                )

                if transcript != current_transcript:
                    col1, col2 = st.columns(2)

                    with col1:
                        if st.button("💾 Save Changes", type="primary"):
                            try:
                                repo.update_sermon(sermon_id, {'transcript': transcript})
                                st.success("Transcript saved successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving transcript: {e}")

                    with col2:
                        if st.button("↩️ Revert Changes", type="secondary"):
                            st.rerun()

                # Download options
                if transcript:
                    st.download_button(
                        "📄 Download Transcript",
                        transcript,
                        file_name=f"transcript_{sermon_id}.txt",
                        mime="text/plain"
                    )
            else:
                st.subheader("📄 Transcript")

                transcript = sermon.get('transcript', '')
                if transcript:
                    st.markdown(transcript)

                    # Download option
                    st.download_button(
                        "📥 Download Transcript",
                        transcript,
                        file_name=f"{sermon.get('title', 'sermon')}_transcript.txt",
                        mime="text/plain"
                    )
                else:
                    st.info("No transcript available")

        # Tab 3: Metadata/Description
        with tabs[2]:
            if edit_mode:
                st.subheader("📝 Edit Metadata")

                with st.form("metadata_form"):
                    col1, col2 = st.columns(2)

                    with col1:
                        title = st.text_input("Title", value=sermon.get('title', ''))
                        speaker = st.text_input("Speaker", value=sermon.get('speaker', ''))
                        event_type = st.text_input("Event Type", value=sermon.get('event_type', ''))
                        bible_text = st.text_input("Bible Text", value=sermon.get('bible_text', ''))

                    with col2:
                        status_options = ['processed', 'processing', 'pending', 'failed', 'uploaded']
                        current_status = sermon.get('status', 'processed')
                        if current_status not in status_options:
                            current_status = 'processed'
                        status = st.selectbox("Status", options=status_options, index=status_options.index(current_status))

                    description = st.text_area(
                        "Description",
                        value=sermon.get('description', ''),
                        height=150
                    )

                    hashtags_list = sermon.get('hashtags', [])
                    hashtags_text = ', '.join(hashtags_list) if isinstance(hashtags_list, list) else str(hashtags_list)
                    hashtags = st.text_input("Hashtags", value=hashtags_text, help="Comma-separated hashtags")

                    if st.form_submit_button("💾 Save All Changes", type="primary"):
                        try:
                            hashtag_list = [tag.strip() for tag in hashtags.split(',') if tag.strip()]

                            updates = {
                                'title': title,
                                'speaker': speaker,
                                'event_type': event_type,
                                'bible_text': bible_text,
                                'status': status,
                                'description': description,
                                'hashtags': hashtag_list
                            }

                            repo.update_sermon(sermon_id, updates)
                            st.success("Metadata saved successfully!")
                            st.session_state.edit_mode = False
                            st.rerun()

                        except Exception as e:
                            st.error(f"Error saving metadata: {e}")
            else:
                st.subheader("📝 Description")

                description = sermon.get('description', '')
                if description:
                    st.markdown(description)
                else:
                    st.info("No description available")

                # Hashtags
                hashtags = sermon.get('hashtags', [])
                if hashtags:
                    st.subheader("🏷️ Hashtags")
                    if isinstance(hashtags, list):
                        for tag in hashtags:
                            st.write(f"#{tag}")
                    else:
                        st.write(str(hashtags))

                # Summary if available
                summary = sermon.get('summary', '')
                if summary:
                    st.subheader("📋 Summary")
                    st.markdown(summary)

        # Tab 4: Processing Info
        with tabs[3]:
            st.subheader("🔧 Processing Information")

            processing_info = sermon.get('processing_info', {})

            if processing_info:
                col1, col2 = st.columns(2)

                with col1:
                    st.write("**Audio Processing:**")
                    enhancement = processing_info.get('enhancement_method', 'Unknown')
                    st.write(f"• Enhancement: {enhancement}")

                    if processing_info.get('noise_reduction_applied'):
                        st.write("• ✅ Noise Reduction Applied")

                    if processing_info.get('normalization_applied'):
                        st.write("• ✅ Normalization Applied")

                with col2:
                    st.write("**Q&A Processing:**")
                    if processing_info.get('qa_normalization_applied'):
                        st.write("• ✅ Q&A Normalization Applied")

                    qa_count = processing_info.get('qa_segments_count', 0)
                    if qa_count > 0:
                        st.write(f"• {qa_count} Q&A segments detected")

                # Processing details
                if processing_info.get('processing_duration'):
                    st.write(f"**Processing Time:** {processing_info['processing_duration']:.1f}s")

                if processing_info.get('quality_score'):
                    st.write(f"**Quality Score:** {processing_info['quality_score']:.1f}/10")

                # Raw data
                with st.expander("🔍 Raw Processing Data"):
                    st.json(processing_info)
            else:
                st.info("No processing information available")

    except ImportError:
        st.error("❌ Database module not found")
    except Exception as e:
        st.error(f"❌ Error loading sermon: {e}")
