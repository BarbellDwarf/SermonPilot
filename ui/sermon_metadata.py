"""
SermonAudio Metadata Management for Streamlit UI

Handles caching and retrieval of pastors, events, and series from the SermonAudio API
to populate dynamic dropdowns in the UI.
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

# Add src directory to Python path for imports
ui_dir = Path(__file__).parent
src_dir = ui_dir.parent / 'src'
sys.path.insert(0, str(src_dir))

logger = logging.getLogger(__name__)

# Default empty fallback when API is unavailable
DEFAULT_PASTORS = []

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

_METADATA_KEYS = ('pastors', 'event_types', 'series')


def _normalize_series(data) -> list[dict[str, Any]]:
    """Normalize cached series data to [{'name': str, 'seriesID': int | None}]."""
    normalized = []
    for item in data or []:
        if isinstance(item, dict):
            normalized.append({
                'name': item.get('name') or str(item),
                'seriesID': item.get('seriesID'),
            })
        else:
            normalized.append({'name': str(item), 'seriesID': None})
    return normalized


def get_cached_metadata() -> dict[str, list[str]]:
    """
    Get cached sermon metadata (pastors, events, series) from SQLite database.
    Expired rows are still returned so the last-known data survives the 24h TTL;
    hardcoded defaults are used only when the cache has never been populated.
    Falls back to session state and defaults if database is unavailable.

    Returns:
        Dictionary with 'pastors', 'event_types', and 'series' lists, plus
        'last_refresh' (datetime or None) and 'stale' (bool) flags.
    """
    try:
        from database import get_db
        db = get_db()

        infos = {key: db.get_cached_metadata_info(key) for key in _METADATA_KEYS}

        pastors = infos['pastors']['data'] if infos['pastors'] else DEFAULT_PASTORS.copy()
        event_types = (
            infos['event_types']['data'] if infos['event_types'] else DEFAULT_EVENT_TYPES.copy()
        )
        series = _normalize_series(
            infos['series']['data'] if infos['series'] else DEFAULT_SERIES.copy()
        )

        result = {
            'pastors': pastors,
            'event_types': event_types,
            'series': series,
            'last_refresh': None,
            'stale': False,
        }

        refreshed_at = [
            info['last_updated'] for info in infos.values() if info and info['last_updated']
        ]
        if refreshed_at:
            result['last_refresh'] = max(refreshed_at)
        result['stale'] = any(
            info and info['is_stale'] for info in infos.values()
        )

        return result

    except Exception as e:
        logger.warning(f"Could not access SQLite cache, falling back to session state: {e}")

        # Fallback to session state if database fails
        if 'sermon_metadata' not in st.session_state:
            st.session_state.sermon_metadata = {
                'pastors': DEFAULT_PASTORS.copy(),
                'event_types': DEFAULT_EVENT_TYPES.copy(),
                'series': _normalize_series(DEFAULT_SERIES.copy()),
                'last_refresh': None,
                'stale': False,
            }

        return st.session_state.sermon_metadata


def needs_metadata_refresh() -> bool:
    """True when any metadata key is missing from the cache or expired."""
    try:
        from database import get_db
        db = get_db()
        for key in _METADATA_KEYS:
            info = db.get_cached_metadata_info(key)
            if info is None or info['is_stale']:
                return True
        return False
    except Exception as e:
        logger.warning(f"Could not check metadata cache: {e}")
        return True


def fetch_and_cache_metadata(
    api_key: str | None = None,
    broadcaster_id: str | None = None,
    limit: int = 200,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, list[str]]:
    """Fetch pastors, event types and series from the SermonAudio API and cache them.

    Pure function with no Streamlit calls, safe to run from a background thread.
    Credentials fall back to the SERMONAUDIO_API_KEY / SERMONAUDIO_BROADCASTER_ID
    environment variables when not passed explicitly.

    Returns:
        Dictionary with 'pastors', 'event_types', and 'series' lists
    """
    import sermon_updater

    api_key = api_key or os.environ.get('SERMONAUDIO_API_KEY')
    broadcaster_id = broadcaster_id or os.environ.get('SERMONAUDIO_BROADCASTER_ID')

    if not api_key or not broadcaster_id:
        logger.warning(
            "SermonAudio API credentials not configured - "
            f"api_key: {'present' if api_key else 'missing'}, "
            f"broadcaster_id: {'present' if broadcaster_id else 'missing'}"
        )
        return {'pastors': [], 'event_types': [], 'series': []}

    if progress_callback:
        progress_callback(0.1, 'Fetching pastors...')
    pastors = sermon_updater.get_broadcaster_pastors(limit=limit)
    logger.info(f"Fetched {len(pastors)} pastors")

    if progress_callback:
        progress_callback(0.5, 'Fetching event types...')
    event_types = sermon_updater.get_broadcaster_event_types(limit=limit)
    logger.info(f"Fetched {len(event_types)} event types")

    if progress_callback:
        progress_callback(0.8, 'Fetching series...')
    series = sermon_updater.get_broadcaster_series(limit=limit)
    logger.info(f"Fetched {len(series)} series")

    if progress_callback:
        progress_callback(1.0, 'Saving to cache...')

    try:
        from database import get_db
        db = get_db()

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

    return {'pastors': pastors, 'event_types': event_types, 'series': series}


def refresh_metadata_in_background() -> None:
    """Start a non-blocking background refresh of the cached metadata."""
    import threading

    def _run() -> None:
        try:
            fetch_and_cache_metadata()
        except Exception as e:
            logger.warning(f"Background metadata refresh failed: {e}")

    threading.Thread(target=_run, name='sermon-metadata-refresh', daemon=True).start()


def _resolve_api_credentials() -> tuple[str | None, str | None]:
    """Resolve SermonAudio credentials from session config or environment."""
    api_key = None
    broadcaster_id = None
    try:
        config = st.session_state.get('config') or {}
        api_key = config.get('api_key')
        broadcaster_id = config.get('broadcaster_id')
    except Exception:
        pass
    api_key = api_key or os.environ.get('SERMONAUDIO_API_KEY')
    broadcaster_id = broadcaster_id or os.environ.get('SERMONAUDIO_BROADCASTER_ID')
    return api_key or None, broadcaster_id or None


def refresh_metadata_from_api() -> bool:
    """
    Refresh metadata by fetching fresh data from SermonAudio API.
    Stores results in SQLite cache for persistence across sessions.

    Returns:
        True if successful, False if failed (will use cached/default data)
    """
    try:
        api_key, broadcaster_id = _resolve_api_credentials()

        if not api_key or not broadcaster_id:
            logger.warning(
                "SermonAudio API credentials not configured - "
                f"api_key: {'present' if api_key else 'missing'}, "
                f"broadcaster_id: {'present' if broadcaster_id else 'missing'}"
            )
            return False

        with st.spinner('Refreshing metadata from SermonAudio API...'):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def _progress(pct: float, message: str) -> None:
                progress_bar.progress(pct)
                status_text.text(message)

            result = fetch_and_cache_metadata(
                api_key=api_key,
                broadcaster_id=broadcaster_id,
                progress_callback=_progress,
            )

            progress_bar.empty()
            status_text.empty()

            metadata = get_cached_metadata()

            if result['pastors']:
                metadata['pastors'] = result['pastors']
                logger.info(f"Refreshed {len(result['pastors'])} pastors from API")
            else:
                logger.warning("No pastors found from API, keeping defaults")
                st.warning("No pastors found - keeping default list")

            if result['event_types']:
                metadata['event_types'] = result['event_types']
                logger.info(f"Refreshed {len(result['event_types'])} event types from API")
            else:
                logger.warning("No event types found from API, keeping defaults")
                st.warning("No event types found - keeping default list")

            if result['series']:
                metadata['series'] = result['series']
                logger.info(f"Refreshed {len(result['series'])} series from API")
            else:
                logger.warning("No series found from API, keeping defaults")
                st.warning("No series found - keeping default list")

            metadata['last_refresh'] = datetime.datetime.now()

            # Update session state
            st.session_state.sermon_metadata = metadata

            # Stash feedback so it survives the page rerun
            success_msg = 'Metadata refreshed successfully!\n'
            success_msg += f'Pastors: {len(metadata["pastors"])}\n'
            success_msg += f'Event Types: {len(metadata["event_types"])}\n'
            success_msg += f'Series: {len(metadata["series"])}'
            st.session_state.metadata_refresh_feedback = success_msg
            return True

    except ImportError as e:
        logger.error(f"Could not import sermon_updater: {e}")
        st.error("Could not load sermon processing modules")
        return False
    except Exception as e:
        logger.error(f"Error refreshing metadata: {e}")
        st.error(f"Error refreshing metadata: {str(e)}")
        return False


def get_pastors() -> list[str]:
    """Get list of pastors/speakers."""
    metadata = get_cached_metadata()
    return metadata['pastors']


def get_event_types() -> list[str]:
    """Get list of event types."""
    metadata = get_cached_metadata()
    return metadata['event_types']


def get_series() -> list[str]:
    """Get list of sermon series names."""
    metadata = get_cached_metadata()
    return [s['name'] for s in metadata['series']]


def get_series_map() -> dict[str, int]:
    """Map series names to their numeric SermonAudio seriesID."""
    metadata = get_cached_metadata()
    return {
        s['name']: s['seriesID']
        for s in metadata['series']
        if s.get('seriesID') is not None
    }


def show_metadata_refresh_section():
    """
    Show a collapsible section for refreshing metadata from API.
    Call this in UI pages that use the metadata dropdowns.
    """
    with st.expander("Refresh Metadata from SermonAudio"):
        feedback = st.session_state.pop('metadata_refresh_feedback', None)
        if feedback:
            st.success(feedback)

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

        if metadata.get('stale'):
            st.caption(
                "Showing cached data past its 24h freshness window - click refresh to update"
            )

        # Refresh button
        if st.button("Refresh from SermonAudio API", width='stretch'):
            refreshed = refresh_metadata_from_api()
            if refreshed:
                st.rerun()


def create_pastor_selectbox(
    label: str = "Speaker Name", key: str = "speaker_name", **kwargs
) -> str | None:
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

    if not pastors:
        return st.text_input(
            label,
            key=f"{key}_custom",
            placeholder="Enter pastor name"
        ) or None

    options = ["[Select Pastor]"] + pastors + ["[Add New Pastor]"]
    selected = st.selectbox(label, options, key=f"{key}_select", **kwargs)

    if selected == "[Add New Pastor]":
        custom_pastor = st.text_input(
            "Enter pastor name:",
            key=f"{key}_custom",
            placeholder="Enter pastor name"
        )
        return custom_pastor if custom_pastor else None
    elif selected == "[Select Pastor]":
        return None
    else:
        return selected


def create_event_type_selectbox(
    label: str = "Event Type", key: str = "event_type", **kwargs
) -> str | None:
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


def create_series_selectbox(
    label: str = "Series (optional)", key: str = "series", **kwargs
) -> str | None:
    """
    Create a selectbox for series selection with option to add new series.

    Returns the selected series name for display; the matching numeric
    seriesID is stored in st.session_state[f"{key}_id"] for uploads.
    """
    series = get_series()
    series_map = get_series_map()

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
        st.session_state[f"{key}_id"] = None
        return custom_series if custom_series else None
    elif selected == "[No Series]":
        st.session_state[f"{key}_id"] = None
        return None
    else:
        st.session_state[f"{key}_id"] = series_map.get(selected)
        return selected


_FILENAME_DATE_FORMATS = ('%Y-%m-%d', '%Y_%m_%d', '%m-%d-%Y', '%m_%d_%Y', '%d.%m.%Y')


def parse_sermon_filename(filename: str) -> dict[str, str | datetime.date | None]:
    """Parse 'Title - Series - Speaker - date.ext' style filenames.

    The stem is split on the literal ' - ' separator: position 0 is the title,
    1 the series, 2 the speaker and 3 a date candidate. Segments past the
    fourth are ignored and missing ones come back as None.
    """
    stem = Path(filename).stem
    segments = [segment.strip() for segment in stem.split(' - ')]

    def segment(index: int) -> str | None:
        return segments[index] if index < len(segments) else None

    raw_date = segment(3)
    return {
        'title': segment(0) or None,
        'series': segment(1) or None,
        'speaker': segment(2) or None,
        'date': _parse_filename_date(raw_date) if raw_date else None,
    }


def _parse_filename_date(value: str) -> datetime.date | None:
    for date_format in _FILENAME_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _match_option(options: list[str], value: str) -> str | None:
    for option in options:
        if option == value:
            return option
    folded = value.casefold()
    for option in options:
        if option.casefold() == folded:
            return option
    return None


def _speaker_field_set() -> bool:
    selected = st.session_state.get('speaker_name_select')
    if selected and selected not in ('[Select Pastor]', '[Add New Pastor]'):
        return True
    return bool(st.session_state.get('speaker_name_custom'))


def _series_field_set() -> bool:
    selected = st.session_state.get('sermon_series_select')
    if selected and selected not in ('[No Series]', '[Add New Series]'):
        return True
    return bool(st.session_state.get('sermon_series_custom'))


def apply_filename_autodetect(filename: str) -> bool:
    """Pre-fill metadata fields from an uploaded filename.

    Call before the metadata widgets render. Only fields the user has not set
    are touched. Returns True when any field was pre-filled.
    """
    parsed = parse_sermon_filename(filename)
    applied = False

    title = parsed['title']
    if title and not st.session_state.get('sermon_title'):
        st.session_state['sermon_title'] = title
        applied = True

    speaker = parsed['speaker']
    if speaker and not _speaker_field_set():
        match = _match_option(get_pastors(), speaker)
        if match is not None:
            st.session_state['speaker_name_select'] = match
        else:
            st.session_state['speaker_name_select'] = '[Add New Pastor]'
            st.session_state['speaker_name_custom'] = speaker
        applied = True

    series = parsed['series']
    if series and not _series_field_set():
        match = _match_option(get_series(), series)
        if match is not None:
            st.session_state['sermon_series_select'] = match
            st.session_state['sermon_series_id'] = get_series_map().get(match)
        else:
            st.session_state['sermon_series_select'] = '[Add New Series]'
            st.session_state['sermon_series_custom'] = series
            st.session_state['sermon_series_id'] = None
        applied = True

    parsed_date = parsed['date']
    if parsed_date is not None:
        current_date = st.session_state.get('recorded_date')
        if current_date is None or current_date == datetime.date.today():
            st.session_state['recorded_date'] = parsed_date
            applied = True

    return applied
