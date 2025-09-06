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
