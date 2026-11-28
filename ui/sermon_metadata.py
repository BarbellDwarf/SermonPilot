"""
SermonAudio Metadata Management

Handles caching and retrieval of pastors, events, and series from the SermonAudio API.
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Add src directory to Python path for imports
ui_dir = Path(__file__).parent
src_dir = ui_dir.parent / 'src'
sys.path.insert(0, str(src_dir))

logger = logging.getLogger(__name__)

# Default empty fallback when API is unavailable
DEFAULT_PASTORS = []

# Authoritative SermonAudio eventType enum. There is no public GET endpoint
# for this list; the values are documented from API validation errors.
# get_broadcaster_event_types() only sees types the church has already used,
# so this enum seeds the picker and every refresh merges with it.
DEFAULT_EVENT_TYPES = [
    "Audiobook",
    "Bible Study",
    "Camp Meeting",
    "Chapel Service",
    "Children",
    "Classic Audio",
    "Conference",
    "Current Events",
    "Debate",
    "Devotional",
    "Funeral Service",
    "Midweek Service",
    "Miscellaneous",
    "Open-Air Ministry",
    "Podcast",
    "Prayer Meeting",
    "Question & Answer",
    "Radio Broadcast",
    "Sermon Clip",
    "Special Meeting",
    "Sunday - AM",
    "Sunday - PM",
    "Sunday School",
    "Sunday Service",
    "Teaching",
    "Testimony",
    "TV Broadcast",
    "Wedding",
    "Youth",
]


def merge_event_types(cached: list | None) -> list[str]:
    """Merge broadcaster-cached types with the authoritative enum.

    Enum order first, then any broadcaster-specific extras sorted. Never
    shrinks: a refresh that finds 4 used types still returns the full enum.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for value in DEFAULT_EVENT_TYPES:
        if value not in seen:
            seen.add(value)
            merged.append(value)
    extras = sorted({str(v) for v in (cached or []) if str(v) not in seen})
    merged.extend(extras)
    return merged

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
    Falls back to the hardcoded defaults if the database is unavailable.

    Returns:
        Dictionary with 'pastors', 'event_types', and 'series' lists, plus
        'last_refresh' (datetime or None) and 'stale' (bool) flags.
    """
    try:
        from ui.database import get_db
        db = get_db()

        infos = {key: db.get_cached_metadata_info(key) for key in _METADATA_KEYS}

        pastors = infos['pastors']['data'] if infos['pastors'] else DEFAULT_PASTORS.copy()
        event_types = merge_event_types(
            infos['event_types']['data'] if infos['event_types'] else None
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
        logger.warning(f"Could not access SQLite cache, falling back to defaults: {e}")

        return {
            'pastors': DEFAULT_PASTORS.copy(),
            'event_types': DEFAULT_EVENT_TYPES.copy(),
            'series': _normalize_series(DEFAULT_SERIES.copy()),
            'last_refresh': None,
            'stale': False,
        }


def needs_metadata_refresh() -> bool:
    """True when any metadata key is missing from the cache or expired."""
    try:
        from ui.database import get_db
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

    Pure function with no UI calls, safe to run from a background thread.
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

    event_types = merge_event_types(event_types)

    if progress_callback:
        progress_callback(1.0, 'Saving to cache...')

    try:
        from ui.database import get_db
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
