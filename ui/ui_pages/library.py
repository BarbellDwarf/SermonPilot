"""
Sermon Library Page - Browse and search processed sermons

Provides comprehensive sermon browsing with:
- Clean list view with search and filtering
- Slide-in panel for detailed sermon information
- Quick access to sermon editing with API-backed dropdowns
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

def push_sermon_metadata_to_api(sermon):
    """Push sermon metadata updates to SermonAudio API"""
    try:
        # Import the sermon updater module for API updates
        import sermon_updater
        
        sermon_id = sermon.get('id') or sermon.get('sermon_id')
        if not sermon_id:
            st.error("❌ No sermon ID found")
            return
            
        with st.spinner("📤 Pushing metadata to SermonAudio..."):
            # Get description and hashtags for the existing API function
            description = (sermon.get('description') or 
                          sermon.get('ai_description') or 
                          sermon.get('moreInfoText') or '')
            
            hashtags = sermon.get('hashtags') or sermon.get('keywords') or []
            
            # Convert hashtags to proper format
            if isinstance(hashtags, str):
                if ' ' in hashtags and ',' not in hashtags:
                    # Space-separated keywords like "ChristianLiving FaithAndWorks"
                    hashtags = hashtags.split()
                else:
                    # Comma-separated
                    hashtags = [tag.strip() for tag in hashtags.split(',') if tag.strip()]
            
            # Use the existing sermon_updater function
            success = sermon_updater.update_sermon_metadata(sermon_id, description, hashtags)
            
            if success:
                st.success("✅ Metadata successfully updated on SermonAudio!")
                # Optionally refresh the sermon data
                st.info("🔄 Refresh the page to see updated data from SermonAudio")
            else:
                st.error("❌ Failed to update metadata on SermonAudio. Check your API credentials and try again.")
                
    except ImportError:
        st.error("❌ Sermon updater module not available")
    except Exception as e:
        st.error(f"❌ Error updating metadata: {e}")
        if st.checkbox("Show Error Details", key=f"error_details_{sermon_id}"):
            st.exception(e)


def show_library():
    """Main sermon library interface"""
    st.markdown('<div class="main-header">📚 Sermon Library</div>', unsafe_allow_html=True)
    st.markdown("Browse and search all processed sermons")

    try:
        from database import SermonRepository
        from sermonaudio_api import SermonAudioAPI
        
        repo = SermonRepository()
        api_client = SermonAudioAPI()

        # Initialize session state for selected sermon
        if 'selected_sermon' not in st.session_state:
            st.session_state.selected_sermon = None
        if 'editing_sermon' not in st.session_state:
            st.session_state.editing_sermon = False

        # Get sermons
        sermons = repo.get_all_sermons(limit=1000)

        if not sermons:
            st.info("No sermons found. Process some sermons first using the 'New Sermon' page.")
            return

        # Search and filter controls
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

        with col1:
            search_query = st.text_input(
                "🔍 Search sermons",
                placeholder="Search titles, speakers, content...",
                help="Search across sermon titles, speakers, and descriptions",
                key="library_search"
            )

        with col2:
            # Get unique speakers for filter
            speakers = sorted(set(s.get('speaker', '') for s in sermons if s.get('speaker')))
            speaker_filter = st.selectbox(
                "👤 Speaker",
                ["All"] + speakers,
                key="library_speaker_filter"
            )

        with col3:
            # Date range filter
            date_filter = st.selectbox(
                "📅 Date Range",
                ["All", "Last Month", "Last 3 Months", "Last Year"],
                key="library_date_filter"
            )

        with col4:
            # Processing status filter
            status_filter = st.selectbox(
                "🔄 Status",
                ["All", "Processed", "Pending", "Error"],
                key="library_status_filter"
            )

        # Apply filters
        filtered_sermons = apply_filters(sermons, search_query, speaker_filter, date_filter, status_filter)

        # Main layout with two columns
        col_list, col_detail = st.columns([2, 3])

        with col_list:
            st.markdown("### Sermons")
            display_sermon_list(filtered_sermons, sermons)

        with col_detail:
            if st.session_state.selected_sermon:
                if st.session_state.editing_sermon:
                    display_sermon_editor(st.session_state.selected_sermon, api_client, repo)
                else:
                    display_sermon_details(st.session_state.selected_sermon)
            else:
                st.markdown("### Select a Sermon")
                st.info("👈 Select a sermon from the list to view details")

    except ImportError as e:
        st.error(f"❌ Import error: {e}")
        st.error("Please ensure all required modules are available.")
    except Exception as e:
        st.error(f"❌ Error loading sermon library: {e}")
        import traceback
        st.code(traceback.format_exc())

def apply_filters(sermons, search_query, speaker_filter, date_filter, status_filter):
    """Apply search and filter criteria to sermons"""
    filtered_sermons = sermons[:]

    # Enhanced search filter - search across more fields
    if search_query:
        search_lower = search_query.lower()
        filtered_sermons = [
            s for s in filtered_sermons
            if search_lower in (s.get('title', '') or '').lower() or
               search_lower in (s.get('speaker', '') or '').lower() or
               search_lower in (s.get('description', '') or '').lower() or
               search_lower in (s.get('ai_description', '') or '').lower() or
               search_lower in (s.get('scripture_reference', '') or '').lower() or
               search_lower in (s.get('series_title', '') or '').lower() or
               search_lower in str(s.get('hashtags', '') or '').lower() or
               search_lower in str(s.get('key_topics', '') or '').lower() or
               (s.get('content') and search_lower in str(s['content'].get('key_topics', '') or '').lower())
        ]

    # Speaker filter
    if speaker_filter != "All":
        filtered_sermons = [s for s in filtered_sermons if s.get('speaker') == speaker_filter]

    # Date filter
    if date_filter != "All":
        cutoff_date = datetime.now()
        if date_filter == "Last Month":
            cutoff_date -= timedelta(days=30)
        elif date_filter == "Last 3 Months":
            cutoff_date -= timedelta(days=90)
        elif date_filter == "Last Year":
            cutoff_date -= timedelta(days=365)

        filtered_sermons = [
            s for s in filtered_sermons
            if s.get('recorded_date') and 
            datetime.fromisoformat(s['recorded_date'].replace('Z', '+00:00')) >= cutoff_date
        ]

    # Status filter
    if status_filter != "All":
        status_map = {
            "Processed": ["completed", "processed"],  # Handle both status values
            "Pending": ["processing"], 
            "Error": ["failed"]
        }
        target_statuses = status_map.get(status_filter, [status_filter.lower()])
        filtered_sermons = [s for s in filtered_sermons if s.get('status') in target_statuses]

    return filtered_sermons

def display_sermon_list(filtered_sermons, all_sermons):
    """Display the sermon list with selection"""
    
    # Statistics
    st.markdown(f"**{len(filtered_sermons)}** sermons shown (of {len(all_sermons)} total)")
    
    # Pagination
    items_per_page = 20
    total_pages = (len(filtered_sermons) + items_per_page - 1) // items_per_page
    
    if total_pages > 1:
        page = st.selectbox("Page", range(1, total_pages + 1), key="library_page") - 1
    else:
        page = 0
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_sermons))
    page_sermons = filtered_sermons[start_idx:end_idx]

    # Display sermons with clean formatting
    for sermon in page_sermons:
        with st.container():
            # Create a clickable sermon item with clean layout
            col1, col2, col3 = st.columns([6, 1, 1])
            
            with col1:
                title = sermon.get('title', 'Untitled')
                speaker = sermon.get('speaker', 'Unknown')
                date = sermon.get('recorded_date', 'Unknown')
                
                # Format date better
                try:
                    if date and date != 'Unknown':
                        from datetime import datetime
                        date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                        date = date_obj.strftime('%Y-%m-%d')
                except:
                    pass  # Keep original date format if parsing fails
                
                # Build a clean subtitle
                subtitle_parts = []
                if speaker and speaker != 'Unknown':
                    subtitle_parts.append(f"🎤 {speaker}")
                if sermon.get('scripture_reference'):
                    subtitle_parts.append(f"📖 {sermon['scripture_reference']}")
                if sermon.get('series_title'):
                    subtitle_parts.append(f"📚 {sermon['series_title']}")
                
                subtitle = " • ".join(subtitle_parts) if subtitle_parts else "No additional info"
                
                if st.button(
                    f"**{title}**\n{subtitle}\n📅 {date}",
                    key=f"select_{sermon['id']}",
                    use_container_width=True,
                    help="Click to view details"
                ):
                    st.session_state.selected_sermon = sermon
                    st.session_state.editing_sermon = False
                    st.rerun()
            
            with col2:
                # Show duration if available
                if sermon.get('duration'):
                    st.caption(f"⏱️ {sermon['duration']}")
                else:
                    st.caption("⏱️ --:--")
            
            with col3:
                # Clean status indicator
                status = sermon.get('status', 'unknown')
                if status in ['completed', 'processed']:
                    st.markdown("<div style='text-align: center; font-size: 20px;'>✅</div>", 
                               unsafe_allow_html=True)
                elif status == 'processing':
                    st.markdown("<div style='text-align: center; font-size: 20px;'>⏳</div>", 
                               unsafe_allow_html=True)
                elif status == 'failed':
                    st.markdown("<div style='text-align: center; font-size: 20px;'>❌</div>", 
                               unsafe_allow_html=True)
                else:
                    st.markdown("<div style='text-align: center; font-size: 20px;'>❓</div>", 
                               unsafe_allow_html=True)
            
            st.divider()

def display_sermon_details(sermon):
    """Display detailed sermon information with API data"""
    st.markdown("### Sermon Details")
    
    # Header with edit and push buttons
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"## {sermon.get('title', 'Untitled')}")
    with col2:
        if st.button("✏️ Edit", key=f"edit_{sermon['id']}", use_container_width=True):
            st.session_state.editing_sermon = True
            st.rerun()
    with col3:
        if st.button("📤 Push to SermonAudio", key=f"push_{sermon['id']}", 
                    help="Update this sermon's metadata on SermonAudio", 
                    use_container_width=True):
            push_sermon_metadata_to_api(sermon)
            st.rerun()
    
    # Try to get enhanced API data
    sermon_id = sermon.get('id') or sermon.get('sermon_id')
    api_sermon_data = None
    
    if sermon_id:
        # Debug info
        if st.checkbox("🔍 Show Debug Info", key=f"debug_{sermon_id}"):
            st.json({
                "sermon_id": sermon_id,
                "sermon_keys": list(sermon.keys()),
                "has_title": bool(sermon.get('title')),
                "has_speaker": bool(sermon.get('speaker')),
                "has_description": bool(sermon.get('description'))
            })
        
        try:
            from sermonaudio_api import SermonAudioAPI
            api_client = SermonAudioAPI()
            if api_client.is_configured():
                with st.spinner("🔄 Loading enhanced sermon data..."):
                    api_response = api_client.get_sermon_details(sermon_id)
                    # Extract the sermon data from the API response
                    if api_response and isinstance(api_response, dict):
                        if 'sermon' in api_response:
                            api_sermon_data = api_response['sermon']
                        else:
                            api_sermon_data = api_response
                            
                    # Debug: Show API response
                    if st.checkbox("📡 Show API Response", key=f"api_debug_{sermon_id}"):
                        st.json({
                            "api_response_type": type(api_response).__name__,
                            "api_response_keys": list(api_response.keys()) if isinstance(api_response, dict) else "Not a dict",
                            "has_sermon_key": 'sermon' in api_response if isinstance(api_response, dict) else False,
                            "api_sermon_data_keys": list(api_sermon_data.keys()) if api_sermon_data else "No API data"
                        })
        except Exception as e:
            st.warning(f"Could not load enhanced sermon data: {e}")
            if st.checkbox("🚨 Show API Error Details", key=f"api_error_{sermon_id}"):
                st.exception(e)
    
    # Merge API data with database data, mapping API fields to display fields
    display_data = sermon.copy()
    
    if api_sermon_data:
        # Map API fields to our expected field names
        field_mapping = {
            'fullTitle': 'title',
            'displayTitle': 'title',
            'moreInfoText': 'ai_description',
            'bibleText': 'scripture_reference',
            'speaker': 'speaker_obj',
            'keywords': 'hashtags',
            'audioDurationSeconds': 'duration_seconds',
            'preachDate': 'recorded_date',
            'eventType': 'event_type',
            'displayEventType': 'event_type'
        }
        
        # Apply the mapping
        for api_field, display_field in field_mapping.items():
            if api_field in api_sermon_data:
                display_data[display_field] = api_sermon_data[api_field]
        
        # Handle speaker information
        if 'speaker' in api_sermon_data and isinstance(api_sermon_data['speaker'], dict):
            display_data['speaker'] = api_sermon_data['speaker'].get('displayName', display_data.get('speaker', 'Unknown'))
        
        # Handle series information
        if 'series' in api_sermon_data and isinstance(api_sermon_data['series'], dict):
            display_data['series_title'] = api_sermon_data['series'].get('title', display_data.get('series_title', ''))
        
        # Handle broadcaster/church information
        if 'broadcaster' in api_sermon_data and isinstance(api_sermon_data['broadcaster'], dict):
            display_data['church_name'] = api_sermon_data['broadcaster'].get('displayName', display_data.get('church_name', ''))
        
        # Handle audio URL
        if 'media' in api_sermon_data and 'audio' in api_sermon_data['media']:
            audio_files = api_sermon_data['media']['audio']
            if audio_files and len(audio_files) > 0:
                # Use the first audio file
                display_data['audio_url'] = audio_files[0].get('streamURL')
        
        # Convert duration from seconds to readable format
        if 'duration_seconds' in display_data:
            seconds = display_data['duration_seconds']
            if seconds:
                hours, remainder = divmod(seconds, 3600)
                minutes, secs = divmod(remainder, 60)
                if hours > 0:
                    display_data['duration'] = f"{hours}:{minutes:02d}:{secs:02d}"
                else:
                    display_data['duration'] = f"{minutes}:{secs:02d}"
    
    # Basic information with better error handling
    st.markdown("### 📋 Information")
    col1, col2 = st.columns(2)
    
    with col1:
        speaker_name = display_data.get('speaker', 'Unknown')
        # Handle case where speaker is still an object
        if isinstance(speaker_name, dict):
            speaker_name = speaker_name.get('displayName', 'Unknown')
        
        st.text(f"🎤 Speaker: {speaker_name}")
        st.text(f"📅 Date: {display_data.get('recorded_date', 'Unknown')}")
        st.text(f"📍 Church: {display_data.get('church_name', 'Unknown')}")
        st.text(f"⏱️ Duration: {display_data.get('duration', 'Unknown')}")
    
    with col2:
        series_title = display_data.get('series_title', 'None')
        # Handle case where series is still an object
        if isinstance(series_title, dict):
            series_title = series_title.get('title', 'None')
            
        st.text(f"📚 Series: {series_title}")
        st.text(f"🎯 Event: {display_data.get('event_type', 'Unknown')}")
        st.text(f"📖 Scripture: {display_data.get('scripture_reference', 'None')}")
        if display_data.get('language'):
            st.text(f"🌐 Language: {display_data.get('language')}")
    
    # SermonAudio link and audio player
    if sermon_id:
        st.markdown("### 🔗 Links & Audio")
        col1, col2 = st.columns(2)
        
        with col1:
            sermon_url = f"https://www.sermonaudio.com/sermoninfo.asp?SID={sermon_id}"
            st.markdown(f"[🎧 View on SermonAudio]({sermon_url})")
        
        with col2:
            # Try to show audio player if audio URL is available
            audio_url = display_data.get('audio_url')
            if audio_url:
                try:
                    st.audio(audio_url)
                except Exception as e:
                    st.caption(f"Audio: {audio_url}")
                    st.caption("(Direct link - click to play in browser)")
            else:
                # Try local audio file if available
                file_paths = display_data.get('file_paths', display_data.get('files', {}))
                if file_paths and file_paths.get('audio'):
                    audio_path = file_paths['audio']
                    if Path(audio_path).exists():
                        st.audio(audio_path)
                    else:
                        st.caption("Audio file not found locally")
                else:
                    st.caption("No audio available")
    
    # Enhanced description section
    st.markdown("### 📝 Description")
    description = display_data.get('description', '')
    ai_description = display_data.get('ai_description', '')
    
    if ai_description and ai_description != description:
        # Show both original and AI-generated descriptions
        tab1, tab2 = st.tabs(["🤖 AI Generated", "📄 Original"])
        
        with tab1:
            if ai_description:
                st.markdown(ai_description)
            else:
                st.info("No AI-generated description available")
        
        with tab2:
            if description:
                st.markdown(description)
            else:
                st.info("No original description available")
    else:
        # Show single description
        if description:
            st.markdown(description)
        elif ai_description:
            st.markdown(ai_description)
        else:
            st.info("No description available")
    
    # Hashtags section
    hashtags_to_display = None
    
    # Try to get hashtags from various sources
    if display_data.get('hashtags'):
        hashtags_source = display_data['hashtags']
        if isinstance(hashtags_source, str):
            # Handle keywords format like "ChristianLiving FaithAndWorks FirstPeter"
            if ' ' in hashtags_source and ',' not in hashtags_source:
                # Space-separated keywords
                hashtags_to_display = hashtags_source.split()
            else:
                # Comma-separated hashtags
                hashtags_to_display = [tag.strip() for tag in hashtags_source.split(',') if tag.strip()]
        elif isinstance(hashtags_source, list):
            hashtags_to_display = hashtags_source
    
    if hashtags_to_display:
        st.markdown("### 🏷️ Keywords & Topics")
        # Display hashtags as clickable badges in a grid
        cols_per_row = 5
        for i in range(0, len(hashtags_to_display), cols_per_row):
            row_tags = hashtags_to_display[i:i + cols_per_row]
            hashtag_cols = st.columns(len(row_tags))
            for j, tag in enumerate(row_tags):
                with hashtag_cols[j]:
                    # Clean up tag format
                    tag_clean = tag.replace('#', '').strip()
                    if tag_clean:
                        # Add spaces before capital letters for better readability
                        import re
                        tag_display = re.sub(r'([a-z])([A-Z])', r'\1 \2', tag_clean)
                        st.markdown(f"`{tag_display}`")
    
    # Scripture and verses section
    scripture_ref = display_data.get('scripture_reference')
    verses = display_data.get('verses', display_data.get('scripture_text'))
    
    if scripture_ref or verses:
        st.markdown("### � Scripture")
        
        if scripture_ref:
            st.markdown(f"**Reference:** {scripture_ref}")
        
        if verses:
            with st.expander("📜 Scripture Text", expanded=True):
                st.markdown(verses)
    
    # Key topics and themes
    if display_data.get('key_topics') or display_data.get('content', {}).get('key_topics'):
        st.markdown("### 🔑 Key Topics")
        topics = display_data.get('key_topics') or display_data.get('content', {}).get('key_topics', [])
        
        if isinstance(topics, str):
            topics = [topic.strip() for topic in topics.split(',') if topic.strip()]
        
        if topics:
            topic_cols = st.columns(min(len(topics), 4))
            for i, topic in enumerate(topics):
                with topic_cols[i % 4]:
                    st.markdown(f"• {topic}")
    
    # Files and processing info
    st.markdown("### 📁 Files & Processing")
    
    # Show available files
    files = display_data.get('files', display_data.get('file_paths', {}))
    if files:
        st.markdown("**Available Files:**")
        file_cols = st.columns(len(files))
        for i, (file_type, file_path) in enumerate(files.items()):
            with file_cols[i]:
                file_name = Path(file_path).name if file_path else "Not available"
                st.text(f"{file_type.title()}: {file_name}")
    
    # Processing status and info
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Processing Status:**")
        status = display_data.get('status', 'unknown')
        if status in ['completed', 'processed']:
            st.success("✅ Processing completed")
        elif status == 'processing':
            st.info("⏳ Processing in progress")
        elif status == 'failed':
            st.error("❌ Processing failed")
        elif status == 'unknown':
            st.info("❓ Status unknown")
        else:
            st.info(f"ℹ️ Status: {status.title()}")
    
    with col2:
        # Processing info and upload status
        processing_info = display_data.get('processing_info', {})
        upload_info = display_data.get('upload_info', {})
        
        if processing_info.get('processed_at'):
            st.text(f"Processed: {processing_info['processed_at']}")
        
        if upload_info.get('uploaded_at'):
            st.text(f"Uploaded: {upload_info['uploaded_at']}")
        
        if processing_info.get('enhancement_method'):
            st.text(f"Enhancement: {processing_info['enhancement_method']}")
    
    # Advanced information in expandable sections
    if processing_info or api_sermon_data:
        with st.expander("🔬 Advanced Information", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                if processing_info:
                    st.markdown("**Processing Details:**")
                    for key, value in processing_info.items():
                        if key not in ['processed_at', 'enhancement_method'] and value:
                            display_key = key.replace('_', ' ').title()
                            if isinstance(value, (dict, list)):
                                st.json({display_key: value})
                            else:
                                st.text(f"{display_key}: {value}")
            
            with col2:
                if api_sermon_data:
                    st.markdown("**API Metadata:**")
                    api_keys = ['broadcaster_id', 'speaker_id', 'series_id', 'event_type_id']
                    for key in api_keys:
                        if key in api_sermon_data and api_sermon_data[key]:
                            display_key = key.replace('_', ' ').title()
                            st.text(f"{display_key}: {api_sermon_data[key]}")
    
    # Refresh data button
    if api_sermon_data:
        st.markdown("---")
        if st.button("🔄 Refresh from SermonAudio", help="Fetch the latest data from SermonAudio API"):
            try:
                from sermonaudio_api import SermonAudioAPI
                api_client = SermonAudioAPI()
                fresh_data = api_client.get_sermon_details(sermon_id, force_refresh=True)
                if fresh_data:
                    st.success("✅ Data refreshed successfully!")
                    st.rerun()
                else:
                    st.error("❌ Failed to refresh data")
            except Exception as e:
                st.error(f"❌ Error refreshing data: {e}")

def display_sermon_editor(sermon, api_client, repo):
    """Display sermon editor with API-backed dropdowns"""
    st.markdown("### ✏️ Edit Sermon")
    
    # Get API data for dropdowns
    speakers = []
    series = []
    
    if api_client.is_configured():
        try:
            # Get speakers and extract names from dictionary format
            speaker_data = api_client.get_speakers()
            speakers = [s.get('name', str(s)) for s in speaker_data] if speaker_data else []
            
            # Get series and extract names from dictionary format
            series_data = api_client.get_series()
            series = [s.get('name', str(s)) for s in series_data] if series_data else []
            
        except Exception as e:
            st.warning(f"Could not load API data: {e}")
            # Fallback to empty lists
            speakers = []
            series = []
    
    # Edit form
    with st.form(f"edit_sermon_{sermon['id']}"):
        col1, col2 = st.columns(2)
        
        with col1:
            title = st.text_input("Title", value=sermon.get('title', ''))
            
            # Speaker dropdown or text input
            if speakers:
                current_speaker = sermon.get('speaker', '')
                speaker_options = [''] + speakers
                speaker_idx = 0
                if current_speaker in speaker_options:
                    speaker_idx = speaker_options.index(current_speaker)
                speaker = st.selectbox("Speaker", speaker_options, index=speaker_idx)
            else:
                speaker = st.text_input("Speaker", value=sermon.get('speaker', ''))
            
            recorded_date = st.date_input("Recorded Date", 
                                        value=datetime.fromisoformat(sermon.get('recorded_date', '2024-01-01').replace('Z', '+00:00')).date() if sermon.get('recorded_date') else datetime.now().date())
        
        with col2:
            # Series dropdown or text input
            if series:
                current_series = sermon.get('series_title', '')
                series_options = [''] + series
                series_idx = 0
                if current_series in series_options:
                    series_idx = series_options.index(current_series)
                series_title = st.selectbox("Series", series_options, index=series_idx)
            else:
                series_title = st.text_input("Series", value=sermon.get('series_title', ''))
            
            scripture_reference = st.text_input("Scripture Reference", value=sermon.get('scripture_reference', ''))
            event_type = st.text_input("Event Type", value=sermon.get('event_type', ''))
        
        description = st.text_area("Description", value=sermon.get('description', ''), height=100)
        
        # Form buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            save = st.form_submit_button("💾 Save", type="primary")
        with col2:
            cancel = st.form_submit_button("❌ Cancel")
        
        # Handle form submission
        if save:
            try:
                updated_data = {
                    'title': title,
                    'speaker': speaker,
                    'series_title': series_title,
                    'recorded_date': recorded_date.isoformat(),
                    'scripture_reference': scripture_reference,
                    'event_type': event_type,
                    'description': description
                }
                
                success = repo.update_sermon_metadata(sermon['id'], updated_data)
                if success:
                    st.success("✅ Sermon updated successfully!")
                    st.session_state.editing_sermon = False
                    # Refresh the selected sermon data
                    st.session_state.selected_sermon = repo.get_sermon(sermon['id'])
                    st.rerun()
                else:
                    st.error("Failed to update sermon metadata")
            except Exception as e:
                st.error(f"Error updating sermon: {e}")
        
        if cancel:
            st.session_state.editing_sermon = False
            st.rerun()
