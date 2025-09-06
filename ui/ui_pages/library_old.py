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
import pandas as pd

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

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

    # Search filter
    if search_query:
        search_lower = search_query.lower()
        filtered_sermons = [
            s for s in filtered_sermons
            if search_lower in (s.get('title', '') or '').lower() or
               search_lower in (s.get('speaker', '') or '').lower() or
               search_lower in (s.get('description', '') or '').lower()
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

    # Display sermons
    for sermon in page_sermons:
        with st.container():
            # Create a clickable sermon item
            col1, col2 = st.columns([4, 1])
            
            with col1:
                title = sermon.get('title', 'Untitled')
                speaker = sermon.get('speaker', 'Unknown')
                date = sermon.get('recorded_date', 'Unknown')
                
                if st.button(
                    f"**{title}**\n{speaker} • {date}",
                    key=f"select_{sermon['id']}",
                    use_container_width=True,
                    help="Click to view details"
                ):
                    st.session_state.selected_sermon = sermon
                    st.session_state.editing_sermon = False
                    st.rerun()
            
            with col2:
                # Status indicator
                status = "✅" if sermon.get('status') == 'completed' else "⏳"
                st.markdown(f"<div style='text-align: center; font-size: 20px;'>{status}</div>", 
                           unsafe_allow_html=True)
            
            st.divider()

def display_sermon_details(sermon):
    """Display detailed sermon information"""
    st.markdown("### Sermon Details")
    
    # Header with edit button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"## {sermon.get('title', 'Untitled')}")
    with col2:
        if st.button("✏️ Edit", key=f"edit_{sermon['id']}"):
            st.session_state.editing_sermon = True
            st.rerun()
    
    # Basic information
    st.markdown("### 📋 Information")
    col1, col2 = st.columns(2)
    
    with col1:
        st.text(f"🎤 Speaker: {sermon.get('speaker', 'Unknown')}")
        st.text(f"📅 Date: {sermon.get('recorded_date', 'Unknown')}")
        st.text(f"📍 Church: {sermon.get('church_name', 'Unknown')}")
    
    with col2:
        st.text(f"📚 Series: {sermon.get('series_title', 'None')}")
        st.text(f"🎯 Event: {sermon.get('event_type', 'Unknown')}")
        st.text(f"📖 Scripture: {sermon.get('scripture_reference', 'None')}")
    
    # Description
    if sermon.get('description'):
        st.markdown("### 📝 Description")
        st.markdown(sermon['description'])
    
    # Files and processing info
    st.markdown("### 📁 Files")
    if sermon.get('files'):
        for file_type, file_path in sermon['files'].items():
            st.text(f"{file_type}: {Path(file_path).name}")
    
    # Processing status
    st.markdown("### 🔄 Processing Status")
    status = sermon.get('status', 'unknown')
    if status == 'completed':
        st.success("✅ Processing completed")
    elif status == 'processing':
        st.info("⏳ Processing in progress")
    else:
        st.warning(f"❓ Status: {status}")

def display_sermon_editor(sermon, api_client, repo):
    """Display sermon editor with API-backed dropdowns"""
    st.markdown("### ✏️ Edit Sermon")
    
    # Get API data for dropdowns
    speakers = []
    series = []
    
    if api_client.is_configured():
        try:
            speakers = api_client.get_speakers()
            series = api_client.get_series()
        except Exception as e:
            st.warning(f"Could not load API data: {e}")
    
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

        # Apply filters
        filtered_sermons = _apply_filters(sermons, search_query, speaker_filter, date_filter, status_filter)

        # Main layout: sermon list + detail panel
        if st.session_state.selected_sermon:
            # Two-column layout when sermon is selected
            col_list, col_detail = st.columns([1, 1])
        else:
            # Full width for sermon list when none selected
            col_list = st.container()
            col_detail = None

        with col_list:
            st.markdown("### Sermon List")
            _show_sermon_list(filtered_sermons, repo)

        # Show detail panel if sermon is selected
        if col_detail and st.session_state.selected_sermon:
            with col_detail:
                _show_sermon_detail_panel(st.session_state.selected_sermon, repo, api_client)

    except Exception as e:
        st.error(f"Error loading library: {e}")
        import traceback
        st.code(traceback.format_exc())


def _apply_filters(sermons, search_query, speaker_filter, date_filter, status_filter):
    """Apply search and filter criteria to sermon list"""
    from datetime import datetime, timedelta
    
    filtered = sermons

    # Search filter
    if search_query:
        query_lower = search_query.lower()
        filtered = [
            s for s in filtered
            if (query_lower in s.get('title', '').lower() or
                query_lower in s.get('speaker', '').lower() or
                query_lower in s.get('description', '').lower())
        ]

    # Speaker filter
    if speaker_filter != "All":
        filtered = [s for s in filtered if s.get('speaker') == speaker_filter]

    # Date filter
    if date_filter != "All":
        now = datetime.now()
        if date_filter == "Last Month":
            cutoff = now - timedelta(days=30)
        elif date_filter == "Last 3 Months":
            cutoff = now - timedelta(days=90)
        elif date_filter == "Last Year":
            cutoff = now - timedelta(days=365)
        else:
            cutoff = None

        if cutoff:
            filtered = [
                s for s in filtered
                if s.get('recorded_date') and
                datetime.fromisoformat(s['recorded_date'].replace('Z', '+00:00')) > cutoff
            ]

    # Status filter
    if status_filter != "All":
        status_map = {
            "Processed": "complete",
            "Pending": "processing",
            "Error": "error"
        }
        target_status = status_map.get(status_filter, "complete")
        filtered = [s for s in filtered if s.get('status') == target_status]

    return filtered


def _show_sermon_list(sermons, repo):
    """Show clean sermon list with click-to-select"""
    if not sermons:
        st.info("No sermons match your search criteria.")
        return

    # Show count
    st.caption(f"Found {len(sermons)} sermons")

    # Sermon list container
    list_container = st.container()
    
    with list_container:
        for i, sermon in enumerate(sermons):
            # Create a clean card for each sermon
            with st.container():
                # Check if this sermon is selected
                is_selected = (st.session_state.selected_sermon and 
                             st.session_state.selected_sermon.get('id') == sermon.get('id'))
                
                # Apply selection styling
                card_style = "background-color: #e3f2fd; border-left: 4px solid #2196f3;" if is_selected else "background-color: #f8f9fa; border-left: 4px solid transparent;"
                
                st.markdown(f"""
                <div style="padding: 12px; margin: 8px 0; border-radius: 8px; {card_style} cursor: pointer;">
                    <div style="font-weight: 600; font-size: 16px; color: #1976d2;">
                        {sermon.get('title', 'Untitled Sermon')}
                    </div>
                    <div style="color: #666; font-size: 14px; margin: 4px 0;">
                        👤 {sermon.get('speaker', 'Unknown Speaker')} • 
                        📅 {sermon.get('recorded_date', 'Unknown Date')[:10] if sermon.get('recorded_date') else 'Unknown Date'}
                    </div>
                    <div style="color: #888; font-size: 12px;">
                        🎯 {sermon.get('event_type', 'Service')} • 
                        ⏱️ {sermon.get('duration', 'Unknown')} • 
                        📊 {sermon.get('status', 'Unknown').title()}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Create invisible button for selection
                if st.button(f"Select", key=f"select_sermon_{sermon.get('id')}", 
                           help=f"View details for {sermon.get('title', 'Untitled')}", 
                           type="secondary" if not is_selected else "primary"):
                    st.session_state.selected_sermon = sermon
                    st.session_state.editing_sermon = False
                    st.rerun()


def _show_sermon_detail_panel(sermon, repo, api_client):
    """Show detailed sermon information in slide-in panel"""
    st.markdown("### Sermon Details")
    
    # Close button
    if st.button("✕ Close", key="close_detail_panel"):
        st.session_state.selected_sermon = None
        st.session_state.editing_sermon = False
        st.rerun()
    
    # Edit toggle
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("✏️ Edit Metadata", key="edit_sermon_metadata"):
            st.session_state.editing_sermon = not st.session_state.editing_sermon
            st.rerun()
    
    with col2:
        if st.button("🔄 Refresh from API", key="refresh_sermon_api"):
            if api_client.is_configured():
                # Refresh sermon data from API
                api_data = api_client.get_sermon_details(sermon['id'], force_refresh=True)
                if api_data:
                    st.success("Refreshed sermon data from SermonAudio API")
                    # TODO: Update sermon in database with fresh API data
                else:
                    st.warning("Could not fetch fresh data from API")
            else:
                st.warning("SermonAudio API not configured")

    st.divider()

    # Show sermon information or edit form
    if st.session_state.editing_sermon:
        _show_sermon_edit_form(sermon, repo, api_client)
    else:
        _show_sermon_info(sermon)


def _show_sermon_info(sermon):
    """Show read-only sermon information"""
    
    # Basic info
    st.markdown("#### Basic Information")
    
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Title", value=sermon.get('title', ''), disabled=True, key="info_title")
        st.text_input("Speaker", value=sermon.get('speaker', ''), disabled=True, key="info_speaker")
        st.text_input("Event Type", value=sermon.get('event_type', ''), disabled=True, key="info_event_type")
    
    with col2:
        st.text_input("Date", value=sermon.get('recorded_date', '')[:10] if sermon.get('recorded_date') else '', disabled=True, key="info_date")
        st.text_input("Duration", value=sermon.get('duration', ''), disabled=True, key="info_duration")
        st.text_input("Bible Text", value=sermon.get('bible_text', ''), disabled=True, key="info_bible_text")
    
    # Description
    if sermon.get('description'):
        st.markdown("#### Description")
        st.text_area("", value=sermon.get('description', ''), disabled=True, height=100, key="info_description")
    
    # Processing info
    st.markdown("#### Processing Information")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Status", value=sermon.get('status', '').title(), disabled=True, key="info_status")
        st.text_input("Q&A Segments", value=str(sermon.get('qa_segments_count', 0)), disabled=True, key="info_qa_count")
    
    with col2:
        st.text_input("Enhancement Method", value=sermon.get('enhancement_method', ''), disabled=True, key="info_enhancement")
        st.text_input("Upload Status", value=sermon.get('upload_status', ''), disabled=True, key="info_upload_status")


def _show_sermon_edit_form(sermon, repo, api_client):
    """Show editable sermon form with API-backed dropdowns"""
    
    st.markdown("#### Edit Sermon Metadata")
    
    # Get API data for dropdowns
    speakers = []
    series = []
    
    if api_client.is_configured():
        with st.spinner("Loading speakers and series from SermonAudio..."):
            speakers = api_client.get_speakers()
            series = api_client.get_series()
    
    # Create form
    with st.form("edit_sermon_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Title
            new_title = st.text_input("Title", value=sermon.get('title', ''), key="edit_title")
            
            # Speaker dropdown or text input
            if speakers:
                speaker_names = [s['name'] for s in speakers]
                current_speaker = sermon.get('speaker', '')
                if current_speaker in speaker_names:
                    speaker_index = speaker_names.index(current_speaker)
                else:
                    speaker_names.insert(0, current_speaker)
                    speaker_index = 0
                
                new_speaker = st.selectbox("Speaker", speaker_names, index=speaker_index, key="edit_speaker")
            else:
                new_speaker = st.text_input("Speaker", value=sermon.get('speaker', ''), 
                                          help="SermonAudio API not configured - using text input", key="edit_speaker_text")
            
            # Event Type
            event_types = ["Sunday Service", "Wednesday Service", "Special Event", "Conference", "Other"]
            current_event = sermon.get('event_type', '')
            if current_event and current_event not in event_types:
                event_types.insert(0, current_event)
            event_index = event_types.index(current_event) if current_event in event_types else 0
            new_event_type = st.selectbox("Event Type", event_types, index=event_index, key="edit_event_type")
        
        with col2:
            # Date
            import datetime
            try:
                if sermon.get('recorded_date'):
                    current_date = datetime.datetime.fromisoformat(sermon['recorded_date'].replace('Z', '+00:00')).date()
                else:
                    current_date = datetime.date.today()
            except:
                current_date = datetime.date.today()
            
            new_date = st.date_input("Recorded Date", value=current_date, key="edit_date")
            
            # Series dropdown or text input
            if series:
                series_names = ["None"] + [s['name'] for s in series]
                current_series = sermon.get('series', '')
                if current_series and current_series in series_names:
                    series_index = series_names.index(current_series)
                elif current_series:
                    series_names.insert(1, current_series)
                    series_index = 1
                else:
                    series_index = 0
                
                new_series = st.selectbox("Series", series_names, index=series_index, key="edit_series")
                if new_series == "None":
                    new_series = ""
            else:
                new_series = st.text_input("Series", value=sermon.get('series', ''), 
                                         help="SermonAudio API not configured - using text input", key="edit_series_text")
            
            # Bible Text
            new_bible_text = st.text_input("Bible Text", value=sermon.get('bible_text', ''), key="edit_bible_text")
        
        # Description
        new_description = st.text_area("Description", value=sermon.get('description', ''), height=100, key="edit_description")
        
        # Submit buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            submit = st.form_submit_button("💾 Save Changes", type="primary")
        with col2:
            cancel = st.form_submit_button("❌ Cancel")
        
        if submit:
            # Update sermon in database
            updated_sermon = {
                'id': sermon['id'],
                'title': new_title,
                'speaker': new_speaker,
                'event_type': new_event_type,
                'recorded_date': new_date.isoformat(),
                'series': new_series,
                'bible_text': new_bible_text,
                'description': new_description
            }
            
            try:
                success = repo.update_sermon_metadata(sermon['id'], updated_sermon)
                if success:
                    st.success("Sermon metadata updated successfully!")
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

        # Get unique speakers for filter
        speakers = sorted(set(s.get('speaker', '') for s in sermons if s.get('speaker')))
        
        with col2:
            speaker_filter = st.selectbox(
                "🎤 Speaker",
                options=['All'] + speakers,
                help="Filter by speaker"
            )

        with col3:
            # Get unique event types for filter
            event_types = sorted(set(s.get('event_type', '') for s in sermons if s.get('event_type')))
            event_filter = st.selectbox(
                "📅 Event Type",
                options=['All'] + event_types,
                help="Filter by event type"
            )

        # Apply filters
        filtered_sermons = sermons[:]

        if search_query:
            filtered_sermons = [
                s for s in filtered_sermons
                if search_query.lower() in (
                    s.get('title', '').lower() +
                    s.get('speaker', '').lower() +
                    s.get('description', '').lower()
                )
            ]

        if speaker_filter != 'All':
            filtered_sermons = [
                s for s in filtered_sermons
                if s.get('speaker', '').lower() == speaker_filter.lower()
            ]

        if event_filter != 'All':
            filtered_sermons = [
                s for s in filtered_sermons
                if s.get('event_type', '').lower() == event_filter.lower()
            ]

        # Statistics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Sermons", len(sermons))

        with col2:
            st.metric("Filtered Results", len(filtered_sermons))

        with col3:
            qa_count = sum(1 for s in filtered_sermons if s.get('qa_segments_count', 0) > 0)
            st.metric("With Q&A", qa_count)

        with col4:
            processed_count = sum(1 for s in filtered_sermons if s.get('status') == 'processed')
            st.metric("Processed", processed_count)

        st.divider()

        # Display sermon list
        st.subheader(f"📖 Sermons ({len(filtered_sermons)} found)")

        if not filtered_sermons:
            st.info("No sermons match your search criteria. Try adjusting your filters.")
            return

        # Pagination
        items_per_page = 10
        total_pages = (len(filtered_sermons) + items_per_page - 1) // items_per_page

        if total_pages > 1:
            page = st.selectbox(
                "Page",
                options=list(range(1, total_pages + 1)),
                format_func=lambda x: f"Page {x} of {total_pages}"
            )
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_sermons = filtered_sermons[start_idx:end_idx]
        else:
            page_sermons = filtered_sermons

        # Display sermons
        for sermon in page_sermons:
            with st.expander(
                f"🎵 {sermon.get('title', 'Unknown')} - "
                f"{sermon.get('speaker', 'Unknown')} "
                f"({sermon.get('recorded_date', 'Unknown Date')})"
            ):
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.write(f"**Speaker:** {sermon.get('speaker', 'Unknown')}")

                    if sermon.get('event_type'):
                        st.write(f"**Event Type:** {sermon.get('event_type')}")

                    if sermon.get('bible_text'):
                        st.write(f"**Bible Text:** {sermon.get('bible_text')}")

                    # Duration
                    duration = sermon.get('duration')
                    if duration:
                        hours = int(duration // 3600)
                        minutes = int((duration % 3600) // 60)
                        if hours > 0:
                            duration_str = f"{hours}h {minutes}m"
                        else:
                            duration_str = f"{minutes}m"
                        st.write(f"**Duration:** {duration_str}")

                    # Status
                    status = sermon.get('status', 'unknown')
                    status_emoji_map = {
                        'processed': '✅',
                        'processing': '⏳',
                        'pending': '⏸️',
                        'failed': '❌',
                        'uploaded': '☁️'
                    }
                    status_emoji = status_emoji_map.get(status, '❓')
                    st.write(f"**Status:** {status_emoji} {status.title()}")

                    # Q&A segments
                    qa_count = sermon.get('qa_segments_count', 0)
                    if qa_count > 0:
                        st.write(f"**Q&A Segments:** ✅ {qa_count} detected")

                    # Description preview
                    description = sermon.get('description', '')
                    if description:
                        preview = description[:150] + "..." if len(description) > 150 else description
                        st.write(f"**Description:** {preview}")

                with col2:
                    # Audio player for local files
                    file_paths = sermon.get('file_paths', {})

                    # Show available audio types
                    available_audio = []
                    if file_paths.get('original_audio') and Path(file_paths['original_audio']).exists():
                        available_audio.append("🎙️ Original")
                    if file_paths.get('processed_audio') and Path(file_paths['processed_audio']).exists():
                        available_audio.append("🔧 Processed")
                    if file_paths.get('enhanced_audio') and Path(file_paths['enhanced_audio']).exists():
                        available_audio.append("✨ Enhanced")

                    if available_audio:
                        st.write("**Audio Files:**")
                        for audio_type in available_audio:
                            st.write(f"  {audio_type}")

                    # Audio player (prioritize processed, then original, then enhanced)
                    audio_path = (file_paths.get('processed_audio') or
                                file_paths.get('original_audio') or
                                file_paths.get('enhanced_audio'))

                    if audio_path and Path(audio_path).exists():
                        st.audio(str(audio_path), format='audio/mp3')

                        # Show which audio is being played
                        if audio_path == file_paths.get('processed_audio'):
                            st.caption("🔧 Playing: Processed Audio")
                        elif audio_path == file_paths.get('original_audio'):
                            st.caption("�️ Playing: Original Audio")
                        elif audio_path == file_paths.get('enhanced_audio'):
                            st.caption("✨ Playing: Enhanced Audio")
                    else:
                        st.warning("No audio file available")

                with col3:
                    sermon_id = sermon.get('id', '')

                    if st.button("📖 View Details", key=f"view_{sermon_id}"):
                        st.session_state.selected_sermon = sermon_id
                        st.session_state.current_page = 'viewer'
                        st.rerun()

                    if st.button("✏️ Edit", key=f"edit_{sermon_id}"):
                        st.session_state.selected_sermon = sermon_id
                        st.session_state.edit_mode = True
                        st.session_state.current_page = 'viewer'
                        st.rerun()

                    # Download transcript if available
                    transcript_path = file_paths.get('transcript')
                    if transcript_path and Path(transcript_path).exists():
                        with open(transcript_path, encoding='utf-8') as f:
                            transcript_content = f.read()

                        st.download_button(
                            "📄 Transcript",
                            transcript_content,
                            file_name=f"{sermon.get('title', 'sermon')}_transcript.txt",
                            key=f"download_{sermon_id}"
                        )

    except ImportError as e:
        st.error(f"❌ Database module not found: {e}")
        st.info("Please check that the database module is properly installed.")
    except Exception as e:
        st.error(f"❌ Error loading sermon library: {e}")
        st.info("Please check the database connection and try again.")
