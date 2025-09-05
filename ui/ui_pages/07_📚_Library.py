"""
Sermon Library Page - Browse and search processed sermons

Provides comprehensive sermon browsing with:
- Search and filtering capabilities
- Q&A segment information
- Processing status display
- Quick access to sermon details
"""

import streamlit as st
import pandas as pd
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
from sermon_metadata import get_cached_pastors, get_cached_event_types

# Import enhanced search engine
try:
    from search_engine import get_search_engine
    search_engine_available = True
except ImportError:
    search_engine_available = False
    get_search_engine = None

# Page configuration
st.set_page_config(page_title="Sermon Library", page_icon="📚", layout="wide")

def get_filter_options():
    """Get options for filter dropdowns"""
    repo = SermonRepository()
    
    # Get all sermons for filter options
    all_sermons = repo.get_all_sermons()
    
    speakers = sorted(set(s.get('speaker', '') for s in all_sermons if s.get('speaker')))
    event_types = sorted(set(s.get('event_type', '') for s in all_sermons if s.get('event_type')))
    
    # Fallback to cached metadata if no sermons yet
    if not speakers:
        speakers = get_cached_pastors()
    if not event_types:
        event_types = get_cached_event_types()
    
    return speakers, event_types

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
    """Main sermon library interface"""
    st.title("📚 Sermon Library")
    st.markdown("Browse and search all processed sermons with Q&A information")
    
    # Initialize repository
    repo = SermonRepository()
    
    # Get filter options
    speakers, event_types = get_filter_options()
    
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