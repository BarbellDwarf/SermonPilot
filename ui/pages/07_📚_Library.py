"""
Sermon Library Page - Browse and search processed sermons with local/remote data

Provides comprehensive sermon browsing with:
- Hybrid local/remote sermon data integration
- Local/remote status indicators  
- Search and filtering capabilities
- Q&A segment information
- Processing status display
- Quick access to sermon details and editing
"""

import streamlit as st
import pandas as pd
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sys
from pathlib import Path

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

from database import SermonRepository, get_db
from sermon_metadata import get_pastors, get_event_types
from sermon_manager import get_sermon_manager
from analytics_manager import get_analytics_manager

# Import enhanced search engine
try:
    from search_engine import get_search_engine
    search_engine_available = True
except ImportError:
    search_engine_available = False
    get_search_engine = None

# Page configuration
st.set_page_config(page_title="Sermon Library", page_icon="📚", layout="wide")

# Load configuration
try:
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    config = {}

# Initialize managers
@st.cache_resource
def get_managers():
    sermon_mgr = get_sermon_manager(config)
    analytics_mgr = get_analytics_manager(config)
    return sermon_mgr, analytics_mgr

def get_filter_options():
    """Get options for filter dropdowns with hybrid data"""
    repo = SermonRepository()
    
    # Get all sermons for filter options
    all_sermons = repo.get_all_sermons()
    
    speakers = sorted(set(s.get('speaker', '') for s in all_sermons if s.get('speaker')))
    event_types = sorted(set(s.get('event_type', '') for s in all_sermons if s.get('event_type')))
    
    # Fallback to cached metadata if no sermons yet
    if not speakers:
        speakers = get_pastors()
    if not event_types:
        event_types = get_event_types()
    
    return speakers, event_types

def get_availability_status(sermon):
    """Get availability status with appropriate emoji and text"""
    local = sermon.get('local_available', False)
    remote = sermon.get('remote_available', False)
    
    if local and remote:
        return "🔄", "Local + Remote"
    elif local:
        return "💾", "Local Only"
    elif remote:
        return "☁️", "Remote Only"
    else:
        return "❓", "Unknown"

def format_duration(duration_seconds):
    """Format duration in seconds to readable string"""
    if not duration_seconds:
        return "Unknown"
    
    hours = int(duration_seconds // 3600)
    minutes = int((duration_seconds % 3600) // 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

def format_qa_info(sermon):
    """Format Q&A information for display"""
    qa_count = sermon.get('qa_segments_count', 0)
    qa_applied = sermon.get('qa_normalization_applied', False)
    
    if qa_count > 0:
        status = "✅ Applied" if qa_applied else "🔍 Detected"
        return f"{status} ({qa_count} segments)"
    else:
        return "None detected"

def get_status_emoji(status):
    """Get emoji for processing status"""
    status_map = {
        'processed': '✅',
        'processing': '⏳',
        'pending': '⏸️',
        'failed': '❌',
        'uploaded': '☁️'
    }
    return status_map.get(status, '❓')

def show_sermon_library():
    """Main sermon library interface with hybrid local/remote data"""
    st.title("📚 Sermon Library")
    st.markdown("Browse and search all sermons with local/remote data integration")
    
    # Initialize managers
    sermon_manager, analytics_manager = get_managers()
    repo = SermonRepository()
    
    # Show loading spinner while fetching data
    with st.spinner("Loading sermon library..."):
        try:
            # Get sermon list with hybrid data
            filters = {}
            sermons = asyncio.run(sermon_manager.get_sermon_list(filters))
        except Exception as e:
            st.error(f"Error loading sermons: {e}")
            # Fallback to database-only data
            sermons = []
            db_sermons = repo.get_all_sermons()
            for db_sermon in db_sermons:
                sermon_dict = {
                    'id': db_sermon.get('id'),
                    'title': db_sermon.get('title', 'Unknown'),
                    'speaker': db_sermon.get('speaker', 'Unknown'),
                    'recorded_date': db_sermon.get('recorded_date'),
                    'event_type': db_sermon.get('event_type'),
                    'status': db_sermon.get('status', 'unknown'),
                    'local_available': True,
                    'remote_available': False,
                    'qa_segments_count': len(db_sermon.get('qa_segments', [])),
                    'duration': db_sermon.get('duration')
                }
                sermons.append(sermon_dict)
    
    # Statistics summary
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_sermons = len(sermons)
        st.metric("Total Sermons", total_sermons)
    
    with col2:
        local_count = sum(1 for s in sermons if isinstance(s, dict) and s.get('local_available') or hasattr(s, 'local_available') and s.local_available)
        st.metric("Local Sermons", local_count)
    
    with col3:
        remote_count = sum(1 for s in sermons if isinstance(s, dict) and s.get('remote_available') or hasattr(s, 'remote_available') and s.remote_available)
        st.metric("Remote Sermons", remote_count)
    
    with col4:
        qa_count = sum(1 for s in sermons if (isinstance(s, dict) and s.get('qa_segments_count', 0) > 0) or (hasattr(s, 'qa_segments') and s.qa_segments and len(s.qa_segments) > 0))
        st.metric("Q&A Sessions", qa_count)
    
    st.divider()
    
    # Search and filter controls
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        search_query = st.text_input(
            "🔍 Search sermons", 
            placeholder="Search titles, speakers, content...",
            help="Search across sermon titles, speakers, and descriptions"
        )
    
    with col2:
        # Get filter options
        speakers, event_types = get_filter_options()
        speaker_filter = st.selectbox(
            "🎤 Speaker", 
            options=['All'] + speakers,
            help="Filter by speaker"
        )
        if speaker_filter == 'All':
            speaker_filter = None
    
    with col3:
        event_type_filter = st.selectbox(
            "📅 Event Type",
            options=['All'] + event_types,
            help="Filter by event type"
        )
        if event_type_filter == 'All':
            event_type_filter = None
    
    with col4:
        availability_filter = st.selectbox(
            "💾 Availability",
            options=['All', 'Local Only', 'Remote Only', 'Both Local & Remote'],
            help="Filter by data availability"
        )
    
    # Advanced filters in expander
    with st.expander("📊 Advanced Filters"):
        col1, col2 = st.columns(2)
        
        with col1:
            date_range = st.date_input(
                "Date Range",
                value=None,
                help="Filter by sermon date range"
            )
            
            status_filter = st.multiselect(
                "Processing Status",
                options=['processed', 'processing', 'pending', 'failed', 'uploaded'],
                help="Filter by processing status"
            )
        
        with col2:
            qa_filter = st.checkbox(
                "Has Q&A Segments",
                help="Show only sermons with Q&A segments"
            )
            
            sort_by = st.selectbox(
                "Sort By",
                options=['Date (Newest)', 'Date (Oldest)', 'Title', 'Speaker', 'Duration'],
                help="Sort order for results"
            )
    
    # Apply filters
    filtered_sermons = sermons[:]
    
    # Text search
    if search_query:
        filtered_sermons = [
            s for s in filtered_sermons 
            if search_query.lower() in (
                (s.title if hasattr(s, 'title') else s.get('title', '')).lower() +
                (s.speaker if hasattr(s, 'speaker') else s.get('speaker', '')).lower() +
                (s.description if hasattr(s, 'description') else s.get('description', '')).lower()
            )
        ]
    
    # Speaker filter
    if speaker_filter:
        filtered_sermons = [
            s for s in filtered_sermons 
            if speaker_filter.lower() in (s.speaker if hasattr(s, 'speaker') else s.get('speaker', '')).lower()
        ]
    
    # Event type filter
    if event_type_filter:
        filtered_sermons = [
            s for s in filtered_sermons 
            if event_type_filter.lower() in (s.event_type if hasattr(s, 'event_type') else s.get('event_type', '')).lower()
        ]
    
    # Availability filter
    if availability_filter != 'All':
        if availability_filter == 'Local Only':
            filtered_sermons = [
                s for s in filtered_sermons 
                if (s.local_available if hasattr(s, 'local_available') else s.get('local_available', False)) and 
                not (s.remote_available if hasattr(s, 'remote_available') else s.get('remote_available', False))
            ]
        elif availability_filter == 'Remote Only':
            filtered_sermons = [
                s for s in filtered_sermons 
                if (s.remote_available if hasattr(s, 'remote_available') else s.get('remote_available', False)) and 
                not (s.local_available if hasattr(s, 'local_available') else s.get('local_available', False))
            ]
        elif availability_filter == 'Both Local & Remote':
            filtered_sermons = [
                s for s in filtered_sermons 
                if (s.local_available if hasattr(s, 'local_available') else s.get('local_available', False)) and 
                (s.remote_available if hasattr(s, 'remote_available') else s.get('remote_available', False))
            ]
    
    # Status filter
    if status_filter:
        filtered_sermons = [
            s for s in filtered_sermons 
            if (s.status if hasattr(s, 'status') else s.get('status', 'unknown')) in status_filter
        ]
    
    # Q&A filter
    if qa_filter:
        filtered_sermons = [
            s for s in filtered_sermons 
            if (hasattr(s, 'qa_segments') and s.qa_segments and len(s.qa_segments) > 0) or 
            (isinstance(s, dict) and s.get('qa_segments_count', 0) > 0)
        ]
    
    # Sort sermons
    def get_sort_key(sermon):
        if sort_by.startswith('Date'):
            date_str = sermon.date.isoformat() if hasattr(sermon, 'date') else sermon.get('recorded_date', '')
            return date_str
        elif sort_by == 'Title':
            return sermon.title if hasattr(sermon, 'title') else sermon.get('title', '')
        elif sort_by == 'Speaker':
            return sermon.speaker if hasattr(sermon, 'speaker') else sermon.get('speaker', '')
        elif sort_by == 'Duration':
            return sermon.audio_files.duration if hasattr(sermon, 'audio_files') and sermon.audio_files.duration else sermon.get('duration', 0) or 0
        return ''
    
    try:
        filtered_sermons.sort(key=get_sort_key, reverse=sort_by == 'Date (Newest)')
    except Exception as e:
        st.warning(f"Could not sort sermons: {e}")
    
    # Display results
    st.subheader(f"📖 Sermon Results ({len(filtered_sermons)} of {len(sermons)})")
    
    if not filtered_sermons:
        st.info("No sermons found matching your criteria. Try adjusting your filters.")
        return
    
    # Pagination
    items_per_page = config.get('web_ui', {}).get('items_per_page', 20)
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
    
    # Display sermon cards
    for sermon in page_sermons:
        # Convert dataclass to dict-like access if needed
        sermon_data = sermon.__dict__ if hasattr(sermon, '__dict__') else sermon
        
        with st.expander(
            f"🎵 {sermon_data.get('title', 'Unknown')} - "
            f"{sermon_data.get('speaker', 'Unknown')} "
            f"({sermon_data.get('recorded_date', sermon_data.get('date', 'Unknown Date'))})"
        ):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"**Speaker:** {sermon_data.get('speaker', 'Unknown')}")
                if sermon_data.get('event_type'):
                    st.write(f"**Event Type:** {sermon_data.get('event_type')}")
                if sermon_data.get('bible_text'):
                    st.write(f"**Bible Text:** {sermon_data.get('bible_text')}")
                
                # Duration
                duration = sermon_data.get('duration')
                if hasattr(sermon, 'audio_files') and sermon.audio_files.duration:
                    duration = sermon.audio_files.duration
                if duration:
                    st.write(f"**Duration:** {format_duration(duration)}")
                
                # Status and availability
                status_emoji = get_status_emoji(sermon_data.get('status', 'unknown'))
                st.write(f"**Status:** {status_emoji} {sermon_data.get('status', 'Unknown').title()}")
                
                # Get availability status
                if hasattr(sermon, 'local_available'):
                    avail_emoji, avail_text = get_availability_status({
                        'local_available': sermon.local_available,
                        'remote_available': sermon.remote_available
                    })
                else:
                    avail_emoji, avail_text = get_availability_status(sermon_data)
                st.write(f"**Availability:** {avail_emoji} {avail_text}")
                
                # Q&A segments info
                qa_count = 0
                if hasattr(sermon, 'qa_segments') and sermon.qa_segments:
                    qa_count = len(sermon.qa_segments)
                elif isinstance(sermon_data, dict):
                    qa_count = sermon_data.get('qa_segments_count', 0)
                
                if qa_count > 0:
                    st.write(f"**Q&A Segments:** ✅ {qa_count} detected")
                
                # Description preview
                description = sermon_data.get('description', '')
                if description:
                    st.write(f"**Description:** {description[:150]}{'...' if len(description) > 150 else ''}")
            
            with col2:
                # Audio player for local files
                if hasattr(sermon, 'audio_files'):
                    if sermon.audio_files.processed and Path(sermon.audio_files.processed).exists():
                        st.audio(sermon.audio_files.processed, format='audio/mp3')
                        st.caption("🎵 Enhanced Audio")
                    elif sermon.audio_files.original and Path(sermon.audio_files.original).exists():
                        st.audio(sermon.audio_files.original, format='audio/mp3')
                        st.caption("🎵 Original Audio")
                elif sermon_data.get('local_available'):
                    # Try to find audio files
                    output_dir = Path(config.get('output_directory', 'processed_sermons'))
                    sermon_dir = output_dir / sermon_data.get('id', '')
                    if sermon_dir.exists():
                        for audio_file in sermon_dir.glob("*.mp3"):
                            st.audio(str(audio_file), format='audio/mp3')
                            st.caption("🎵 Local Audio")
                            break
            
            with col3:
                sermon_id = sermon_data.get('id', '')
                
                if st.button(f"📖 View Details", key=f"view_{sermon_id}"):
                    st.session_state.selected_sermon = sermon_id
                    st.switch_page("ui_pages/08_📖_Viewer.py")
                
                if st.button(f"✏️ Edit", key=f"edit_{sermon_id}"):
                    st.session_state.selected_sermon = sermon_id
                    st.session_state.edit_mode = True
                    st.switch_page("ui_pages/08_📖_Viewer.py")
                
                # Download options
                if sermon_data.get('local_available'):
                    with st.popover("📥 Download"):
                        if st.button("Transcript", key=f"dl_transcript_{sermon_id}"):
                            # Handle transcript download
                            pass
                        if st.button("Audio", key=f"dl_audio_{sermon_id}"):
                            # Handle audio download
                            pass
    
    # Search and filter controls
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    
    with col1:
        search_query = st.text_input(
            "🔍 Search sermons",
            placeholder="Search titles, content, speakers...",
            help="Full-text search across sermon titles, descriptions, and transcripts"
        )
        
        # Show search suggestions if enhanced search is available
        if search_engine_available and search_query and len(search_query) >= 2:
            try:
                search_engine = get_search_engine()
                suggestions = search_engine.get_search_suggestions(search_query, limit=5)
                if suggestions:
                    suggestion_text = " • ".join(suggestions[:3])
                    st.caption(f"💡 Suggestions: {suggestion_text}")
            except Exception:
                pass  # Silently ignore suggestion errors
    
    with col2:
        speaker_filter = st.selectbox(
            "🎤 Speaker",
            options=["All"] + speakers,
            index=0
        )
    
    with col3:
        event_filter = st.selectbox(
            "📅 Event Type",
            options=["All"] + event_types,
            index=0
        )
    
    with col4:
        status_filter = st.selectbox(
            "📊 Status",
            options=["All", "processed", "pending", "uploaded", "failed"],
            index=0
        )
    
    # Additional filters
    col5, col6, col7 = st.columns(3)
    
    with col5:
        show_qa_only = st.checkbox("🗣️ Q&A Segments Only", help="Show only sermons with detected Q&A segments")
    
    with col6:
        date_range = st.selectbox(
            "📆 Date Range",
            options=["All Time", "Last 7 days", "Last 30 days", "Last 90 days", "Last year"],
            index=0
        )
    
    with col7:
        results_per_page = st.selectbox(
            "📄 Results per page",
            options=[10, 20, 50, 100],
            index=1
        )
    
    # Build filters dictionary
    filters = {}
    
    if speaker_filter != "All":
        filters['speaker'] = speaker_filter
    
    if event_filter != "All":
        filters['event_type'] = event_filter
    
    if status_filter != "All":
        filters['status'] = status_filter
    
    if show_qa_only:
        filters['has_qa_segments'] = True
    
    # Date range filtering
    if date_range != "All Time":
        days_map = {
            "Last 7 days": 7,
            "Last 30 days": 30,
            "Last 90 days": 90,
            "Last year": 365
        }
        days_back = days_map[date_range]
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        filters['date_from'] = cutoff_date
    
    # Pagination state
    if 'page_number' not in st.session_state:
        st.session_state.page_number = 0
    
    # Get sermons
    if search_query.strip():
        # Use enhanced search engine if available
        if search_engine_available:
            try:
                search_engine = get_search_engine()
                search_results = search_engine.search(search_query.strip(), filters=filters)
                
                # Convert search results to sermon format
                sermons = []
                for result in search_results:
                    sermon = result.sermon_data
                    sermon['search_snippet'] = result.snippet
                    sermon['search_rank'] = result.relevance_score
                    sermon['match_type'] = result.match_type
                    sermons.append(sermon)
                
                st.info(f"🔍 Found {len(sermons)} sermons matching '{search_query}' (relevance-ranked)")
                
            except Exception as e:
                st.warning(f"Enhanced search failed, using fallback: {e}")
                # Fallback to repository search
                sermons = repo.search_sermons(search_query.strip(), limit=results_per_page * 10)
                
                # Apply additional filters to search results
                if filters:
                    filtered_sermons = []
                    for sermon in sermons:
                        include = True
                        
                        if 'speaker' in filters and filters['speaker'] not in sermon.get('speaker', ''):
                            include = False
                        if 'event_type' in filters and sermon.get('event_type') != filters['event_type']:
                            include = False
                        if 'status' in filters and sermon.get('status') != filters['status']:
                            include = False
                        if 'has_qa_segments' in filters and sermon.get('qa_segments_count', 0) == 0:
                            include = False
                        
                        if include:
                            filtered_sermons.append(sermon)
                    
                    sermons = filtered_sermons
                
                st.info(f"🔍 Found {len(sermons)} sermons matching '{search_query}'")
        else:
            # Use repository search
            sermons = repo.search_sermons(search_query.strip(), limit=results_per_page * 10)
            
            # Apply additional filters to search results
            if filters:
                filtered_sermons = []
                for sermon in sermons:
                    include = True
                    
                    if 'speaker' in filters and filters['speaker'] not in sermon.get('speaker', ''):
                        include = False
                    if 'event_type' in filters and sermon.get('event_type') != filters['event_type']:
                        include = False
                    if 'status' in filters and sermon.get('status') != filters['status']:
                        include = False
                    if 'has_qa_segments' in filters and sermon.get('qa_segments_count', 0) == 0:
                        include = False
                    
                    if include:
                        filtered_sermons.append(sermon)
                
                sermons = filtered_sermons
            
            st.info(f"🔍 Found {len(sermons)} sermons matching '{search_query}'")
    else:
        # Get all sermons with filters
        offset = st.session_state.page_number * results_per_page
        sermons = repo.get_all_sermons(filters=filters, limit=results_per_page, offset=offset)
    
    # Show results count and pagination controls
    total_results = len(sermons)
    
    if total_results > 0:
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.write(f"Showing {min(total_results, results_per_page)} of {total_results} sermons")
        
        with col2:
            if st.session_state.page_number > 0:
                if st.button("◀ Previous"):
                    st.session_state.page_number -= 1
                    st.rerun()
        
        with col3:
            if not search_query and total_results == results_per_page:  # Might be more pages
                if st.button("Next ▶"):
                    st.session_state.page_number += 1
                    st.rerun()
        
        st.divider()
        
        # Display sermons
        for sermon in sermons:
            with st.container():
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Sermon title and basic info
                    title = sermon.get('title', 'Untitled Sermon')
                    speaker = sermon.get('speaker', 'Unknown Speaker')
                    date = sermon.get('recorded_date', 'Unknown Date')
                    
                    st.subheader(f"{title}")
                    st.write(f"**Speaker:** {speaker} | **Date:** {date}")
                    
                    # Event type and duration
                    event_type = sermon.get('event_type', 'Unknown Event')
                    duration = format_duration(sermon.get('duration'))
                    status = sermon.get('status', 'unknown')
                    
                    col_info1, col_info2, col_info3 = st.columns(3)
                    
                    with col_info1:
                        st.write(f"**Event:** {event_type}")
                    
                    with col_info2:
                        st.write(f"**Duration:** {duration}")
                    
                    with col_info3:
                        status_emoji = get_status_emoji(status)
                        st.write(f"**Status:** {status_emoji} {status.title()}")
                    
                    # Q&A information
                    qa_info = format_qa_info(sermon)
                    st.write(f"**Q&A Segments:** {qa_info}")
                    
                    # Enhancement method
                    enhancement = sermon.get('enhancement_method', 'Unknown')
                    if enhancement != 'Unknown':
                        st.write(f"**Enhancement:** {enhancement}")
                    
                    # Search snippet if available
                    if 'search_snippet' in sermon:
                        snippet = sermon['search_snippet']
                        match_type = sermon.get('match_type', 'content')
                        st.markdown(f"**{match_type.title()} match:** {snippet}", unsafe_allow_html=True)
                        
                        # Show relevance score for enhanced search
                        if 'search_rank' in sermon:
                            st.caption(f"Relevance: {sermon['search_rank']:.2f}")
                
                with col2:
                    # Action buttons
                    sermon_id = sermon.get('id')
                    
                    if st.button(f"📖 View Details", key=f"view_{sermon_id}"):
                        st.session_state.selected_sermon = sermon_id
                        # Navigate to viewer page (would need page routing)
                        st.info(f"Selected sermon: {title}")
                        st.info("Note: Sermon viewer page will be implemented next")
                    
                    # Download transcript if available
                    transcript_path = sermon.get('file_paths', {}).get('transcript')
                    if transcript_path and Path(transcript_path).exists():
                        with open(transcript_path, 'r') as f:
                            transcript_content = f.read()
                        
                        st.download_button(
                            "📄 Download Transcript",
                            transcript_content,
                            file_name=f"{sermon.get('title', 'sermon')}_transcript.txt",
                            key=f"download_{sermon_id}"
                        )
                    
                    # Show processing details
                    if st.button(f"🔧 Processing Info", key=f"info_{sermon_id}"):
                        st.session_state[f"show_info_{sermon_id}"] = not st.session_state.get(f"show_info_{sermon_id}", False)
                
                # Processing details (expandable)
                if st.session_state.get(f"show_info_{sermon_id}", False):
                    with st.expander("🔧 Processing Details", expanded=True):
                        processing_info = sermon.get('processing_info', {})
                        
                        col_p1, col_p2, col_p3 = st.columns(3)
                        
                        with col_p1:
                            st.write("**Audio Processing:**")
                            st.write(f"• Enhancement: {processing_info.get('enhancement_method', 'N/A')}")
                            st.write(f"• Noise Reduction: {'✅' if processing_info.get('noise_reduction_applied') else '❌'}")
                            st.write(f"• Normalization: {'✅' if processing_info.get('normalization_applied') else '❌'}")
                        
                        with col_p2:
                            st.write("**Q&A Processing:**")
                            qa_applied = processing_info.get('qa_normalization_applied', False)
                            qa_count = processing_info.get('qa_segments_count', 0)
                            st.write(f"• Q&A Normalization: {'✅' if qa_applied else '❌'}")
                            st.write(f"• Segments Detected: {qa_count}")
                            
                            if qa_count > 0:
                                # Show Q&A segment details
                                qa_segments = processing_info.get('qa_segments', [])
                                for i, segment in enumerate(qa_segments[:3], 1):  # Show first 3
                                    start = segment.get('start_time', 0)
                                    end = segment.get('end_time', 0)
                                    gain = segment.get('gain_applied', 0)
                                    st.write(f"  • Segment {i}: {start:.1f}-{end:.1f}s (+{gain:.1f}dB)")
                                
                                if len(qa_segments) > 3:
                                    st.write(f"  • ... and {len(qa_segments) - 3} more")
                        
                        with col_p3:
                            st.write("**Quality Metrics:**")
                            duration = processing_info.get('processing_duration')
                            if duration:
                                st.write(f"• Processing Time: {duration:.1f}s")
                            
                            quality = processing_info.get('quality_score')
                            if quality:
                                st.write(f"• Quality Score: {quality:.1f}/10")
                            
                            # File sizes
                            file_paths = sermon.get('file_paths', {})
                            for file_type, file_path in file_paths.items():
                                if file_path and Path(file_path).exists():
                                    size_mb = Path(file_path).stat().st_size / (1024 * 1024)
                                    st.write(f"• {file_type.title()}: {size_mb:.1f}MB")
                
                st.divider()
    
    else:
        # No results
        st.info("No sermons found matching your criteria.")
        
        if filters or search_query:
            st.write("Try:")
            st.write("• Broadening your search terms")
            st.write("• Removing some filters")
            st.write("• Checking the date range")
        else:
            st.write("No sermons have been processed yet.")
            st.write("Use the 'New Sermon' page to process your first sermon!")
    
    # Library statistics
    with st.sidebar:
        st.subheader("📊 Library Statistics")
        
        try:
            stats = repo.get_processing_stats()
            
            st.metric("Total Sermons", stats['total_sermons'])
            st.metric("With Q&A Segments", stats['qa_sermons'])
            st.metric("Total Q&A Segments", stats['total_qa_segments'])
            st.metric("Total Duration", f"{stats['total_duration_hours']:.1f} hours")
            
            if stats['total_sermons'] > 0:
                st.metric("Avg Q&A per Sermon", f"{stats['avg_qa_segments_per_sermon']:.1f}")
                
                if stats['avg_processing_time'] > 0:
                    st.metric("Avg Processing Time", f"{stats['avg_processing_time']:.1f}s")
                
                if stats['avg_quality_score'] > 0:
                    st.metric("Avg Quality Score", f"{stats['avg_quality_score']:.1f}/10")
        
        except Exception as e:
            st.error(f"Error loading statistics: {e}")
        
        # Quick actions
        st.subheader("🚀 Quick Actions")
        
        if st.button("🔄 Refresh Library"):
            st.cache_data.clear()
            st.rerun()
        
        if st.button("📈 View Analytics"):
            st.info("Analytics page coming soon!")
        
        if st.button("⚙️ Library Settings"):
            st.info("Settings page coming soon!")

if __name__ == "__main__":
    show_sermon_library()
else:
    # When imported as a page
    show_sermon_library()