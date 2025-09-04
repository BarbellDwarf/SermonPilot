"""
SermonAudio Metadata Management for Streamlit UI

Handles caching and retrieval of pastors, events, and series from the SermonAudio API
to populate dynamic dropdowns in the UI.
"""

import streamlit as st
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add src directory to Python path for imports
ui_dir = Path(__file__).parent
src_dir = ui_dir.parent / 'src'
sys.path.insert(0, str(src_dir))

logger = logging.getLogger(__name__)

# Default fallback lists if API calls fail
DEFAULT_PASTORS = [
    "Pastor John Smith",
    "Pastor Mary Johnson", 
    "Pastor David Wilson",
    "Pastor Sarah Brown",
    "Pastor Michael Davis"
]

DEFAULT_EVENT_TYPES = [
    "Sunday Service",
    "Sunday - AM",
    "Sunday - PM", 
    "Wednesday Service",
    "Bible Study",
    "Prayer Meeting",
    "Special Event",
    "Conference",
    "Other"
]

DEFAULT_SERIES = [
    "Book of John",
    "Psalms Study",
    "Gospel of Matthew",
    "Romans Study",
    "Genesis Series",
    "Advent Series",
    "Easter Series"
]


def get_cached_metadata() -> Dict[str, List[str]]:
    """
    Get cached sermon metadata (pastors, events, series) from SQLite database.
    Falls back to session state and defaults if database is unavailable.
    
    Returns:
        Dictionary with 'pastors', 'event_types', and 'series' lists
    """
    try:
        from database import get_db
        db = get_db()
        
        # Try to get from SQLite cache first
        pastors = db.get_cached_metadata('pastors')
        event_types = db.get_cached_metadata('event_types')
        series = db.get_cached_metadata('series')
        
        # Use cached data if available, otherwise use defaults
        result = {
            'pastors': pastors if pastors is not None else DEFAULT_PASTORS.copy(),
            'event_types': event_types if event_types is not None else DEFAULT_EVENT_TYPES.copy(),
            'series': series if series is not None else DEFAULT_SERIES.copy(),
            'last_refresh': None  # TODO: Track refresh time in database
        }
        
        return result
        
    except Exception as e:
        logger.warning(f"Could not access SQLite cache, falling back to session state: {e}")
        
        # Fallback to session state if database fails
        if 'sermon_metadata' not in st.session_state:
            st.session_state.sermon_metadata = {
                'pastors': DEFAULT_PASTORS.copy(),
                'event_types': DEFAULT_EVENT_TYPES.copy(),  
                'series': DEFAULT_SERIES.copy(),
                'last_refresh': None
            }
        
        return st.session_state.sermon_metadata


def refresh_metadata_from_api() -> bool:
    """
    Refresh metadata by fetching fresh data from SermonAudio API.
    Stores results in SQLite cache for persistence across sessions.
    
    Returns:
        True if successful, False if failed (will use cached/default data)
    """
    try:
        # Import sermon_updater functions - only when needed to avoid startup delays
        import sermon_updater
        
        # Check if we have API configuration
        if not hasattr(st.session_state, 'config') or not st.session_state.config:
            logger.warning("No configuration available for API calls")
            return False
            
        # Test if we can make API calls by checking if API key is configured
        api_key = st.session_state.config.get('api_key')
        broadcaster_id = st.session_state.config.get('broadcaster_id')
        
        if not api_key or not broadcaster_id:
            logger.warning(f"SermonAudio API credentials not configured - api_key: {'present' if api_key else 'missing'}, broadcaster_id: {'present' if broadcaster_id else 'missing'}")
            return False
        
        with st.spinner('🔄 Refreshing metadata from SermonAudio API...'):
            # Fetch data from API with progress indicators
            progress_bar = st.progress(0)
            
            # Fetch pastors
            st.text('📋 Fetching pastors...')
            progress_bar.progress(0.1)
            pastors = sermon_updater.get_broadcaster_pastors(limit=200)
            progress_bar.progress(0.4)
            logger.info(f"Fetched {len(pastors) if pastors else 0} pastors")
            
            # Fetch event types  
            st.text('📅 Fetching event types...')
            progress_bar.progress(0.5)
            event_types = sermon_updater.get_broadcaster_event_types(limit=200)
            progress_bar.progress(0.7)
            logger.info(f"Fetched {len(event_types) if event_types else 0} event types")
            
            # Fetch series
            st.text('📚 Fetching series...')
            progress_bar.progress(0.8)
            series = sermon_updater.get_broadcaster_series(limit=200)
            progress_bar.progress(1.0)
            logger.info(f"Fetched {len(series) if series else 0} series")
            
            # Clear progress indicators
            progress_bar.empty()
            
            # Store in SQLite cache for persistence
            try:
                from database import get_db
                db = get_db()
                
                # Cache with 24-hour expiration
                if pastors:
                    db.cache_metadata('pastors', pastors, expires_hours=24)
                    logger.info(f"Cached {len(pastors)} pastors to SQLite")
                    
                if event_types:
                    db.cache_metadata('event_types', event_types, expires_hours=24)
                    logger.info(f"Cached {len(event_types)} event types to SQLite")
                    
                if series:
                    db.cache_metadata('series', series, expires_hours=24)
                    logger.info(f"Cached {len(series)} series to SQLite")
                    
            except Exception as db_error:
                logger.warning(f"Could not cache to SQLite, using session state: {db_error}")
            
            # Also update session state for immediate use
            metadata = get_cached_metadata()
            
            # Use fetched data if available, otherwise keep defaults
            if pastors:
                metadata['pastors'] = pastors
                logger.info(f"Refreshed {len(pastors)} pastors from API")
            else:
                logger.warning("No pastors found from API, keeping defaults")
                st.warning("⚠️ No pastors found - keeping default list")
                
            if event_types:
                metadata['event_types'] = event_types
                logger.info(f"Refreshed {len(event_types)} event types from API")
            else:
                logger.warning("No event types found from API, keeping defaults")
                st.warning("⚠️ No event types found - keeping default list")
                
            if series:
                metadata['series'] = series
                logger.info(f"Refreshed {len(series)} series from API")
            else:
                logger.warning("No series found from API, keeping defaults")
                st.warning("⚠️ No series found - keeping default list")
            
            import datetime
            metadata['last_refresh'] = datetime.datetime.now()
            
            # Update session state
            st.session_state.sermon_metadata = metadata
            
            # Show detailed success message
            success_msg = f'✅ Metadata refreshed successfully!\n'
            success_msg += f'📋 Pastors: {len(metadata["pastors"])}\n'
            success_msg += f'📅 Event Types: {len(metadata["event_types"])}\n'
            success_msg += f'📚 Series: {len(metadata["series"])}'
            st.success(success_msg)
            return True
            
    except ImportError as e:
        logger.error(f"Could not import sermon_updater: {e}")
        st.error("❌ Could not load sermon processing modules")
        return False
    except Exception as e:
        logger.error(f"Error refreshing metadata: {e}")
        st.error(f"❌ Error refreshing metadata: {str(e)}")
        return False


def get_pastors() -> List[str]:
    """Get list of pastors/speakers."""
    metadata = get_cached_metadata()
    return metadata['pastors']


def get_event_types() -> List[str]:
    """Get list of event types."""
    metadata = get_cached_metadata()
    return metadata['event_types']


def get_series() -> List[str]:
    """Get list of sermon series."""
    metadata = get_cached_metadata()
    return metadata['series']


def show_metadata_refresh_section():
    """
    Show a collapsible section for refreshing metadata from API.
    Call this in UI pages that use the metadata dropdowns.
    """
    with st.expander("🔄 Refresh Metadata from SermonAudio"):
        metadata = get_cached_metadata()
        
        # Show current counts
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Pastors", len(metadata['pastors']))
        with col2:
            st.metric("Event Types", len(metadata['event_types']))
        with col3:
            st.metric("Series", len(metadata['series']))
        
        # Show last refresh time
        if metadata.get('last_refresh'):
            st.caption(f"Last refreshed: {metadata['last_refresh'].strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.caption("Using default data - click refresh to load from API")
        
        # Refresh button
        if st.button("🔄 Refresh from SermonAudio API", width='stretch'):
            refresh_metadata_from_api()
            st.rerun()


def create_pastor_selectbox(label: str = "Speaker Name", key: str = "speaker_name", **kwargs) -> Optional[str]:
    """
    Create a selectbox for pastor selection with option to add new pastor.
    
    Args:
        label: Label for the selectbox
        key: Unique key for the widget
        **kwargs: Additional arguments passed to selectbox
        
    Returns:
        Selected pastor name or None
    """
    pastors = get_pastors()
    
    # Add option for custom pastor
    options = ["[Select Pastor]"] + pastors + ["[Add New Pastor]"]
    
    selected = st.selectbox(label, options, key=f"{key}_select", **kwargs)
    
    if selected == "[Add New Pastor]":
        # Show text input for custom pastor
        custom_pastor = st.text_input(
            "Enter pastor name:",
            key=f"{key}_custom",
            placeholder="Pastor John Smith"
        )
        return custom_pastor if custom_pastor else None
    elif selected == "[Select Pastor]":
        return None
    else:
        return selected


def create_event_type_selectbox(label: str = "Event Type", key: str = "event_type", **kwargs) -> Optional[str]:
    """
    Create a selectbox for event type selection with option to add new type.
    
    Args:
        label: Label for the selectbox
        key: Unique key for the widget
        **kwargs: Additional arguments passed to selectbox
        
    Returns:
        Selected event type or None
    """
    event_types = get_event_types()
    
    # Add option for custom event type
    options = ["[Select Event Type]"] + event_types + ["[Add New Event Type]"]
    
    selected = st.selectbox(label, options, key=f"{key}_select", **kwargs)
    
    if selected == "[Add New Event Type]":
        # Show text input for custom event type
        custom_event = st.text_input(
            "Enter event type:",
            key=f"{key}_custom",
            placeholder="Special Service"
        )
        return custom_event if custom_event else None
    elif selected == "[Select Event Type]":
        return None
    else:
        return selected


def create_series_selectbox(label: str = "Series (optional)", key: str = "series", **kwargs) -> Optional[str]:
    """
    Create a selectbox for series selection with option to add new series.
    
    Args:
        label: Label for the selectbox
        key: Unique key for the widget
        **kwargs: Additional arguments passed to selectbox
        
    Returns:
        Selected series name or None
    """
    series = get_series()
    
    # Add option for custom series and no series
    options = ["[No Series]"] + series + ["[Add New Series]"]
    
    selected = st.selectbox(label, options, key=f"{key}_select", **kwargs)
    
    if selected == "[Add New Series]":
        # Show text input for custom series
        custom_series = st.text_input(
            "Enter series name:",
            key=f"{key}_custom",
            placeholder="Book of Romans"
        )
        return custom_series if custom_series else None
    elif selected == "[No Series]":
        return None
    else:
        return selected