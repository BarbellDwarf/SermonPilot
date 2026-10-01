"""SermonAudio vocabulary and its local cache.

The authoritative eventType enum, the pastor and series lists, the SQLite
metadata cache, and filename parsing. This module has no UI dependency, so the
processing pipeline, the API bridge, and the console all read the same values.

The Streamlit page that used to own this imported ``streamlit`` at module scope
and mixed its pickers in with the data. The pickers are gone; what is left is
here.
"""

from __future__ import annotations

import datetime
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PASTORS: list[str] = []

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
    "Easter Series",
]

METADATA_KEYS = ("pastors", "event_types", "series")


def _normalize_series(data: Any) -> list[dict[str, Any]]:
    """Normalize cached series data to [{'name': str, 'seriesID': int | None}]."""
    normalized = []
    for item in data or []:
        if isinstance(item, dict):
            normalized.append(
                {
                    "name": item.get("name") or str(item),
                    "seriesID": item.get("seriesID"),
                }
            )
        else:
            normalized.append({"name": str(item), "seriesID": None})
    return normalized


def get_cached_metadata() -> dict[str, Any]:
    """Pastors, event types, and series from the SQLite cache.

    Expired rows are still returned so the last-known data survives the 24h TTL;
    the hardcoded defaults are used only when the cache has never been
    populated. When the cache cannot be read at all the defaults are returned
    rather than raising, because callers are display surfaces.
    """
    try:
        from ui.database import get_db

        db = get_db()
    except Exception as exc:
        logger.warning("Could not open the metadata cache, using defaults: %s", exc)
        return {
            "pastors": DEFAULT_PASTORS.copy(),
            "event_types": DEFAULT_EVENT_TYPES.copy(),
            "series": _normalize_series(DEFAULT_SERIES.copy()),
            "last_refresh": None,
            "stale": False,
        }

    try:
        infos = {key: db.get_cached_metadata_info(key) for key in METADATA_KEYS}
    except Exception as exc:
        logger.warning("Could not read the metadata cache, using defaults: %s", exc)
        return {
            "pastors": DEFAULT_PASTORS.copy(),
            "event_types": DEFAULT_EVENT_TYPES.copy(),
            "series": _normalize_series(DEFAULT_SERIES.copy()),
            "last_refresh": None,
            "stale": False,
        }

    result: dict[str, Any] = {
        "pastors": infos["pastors"]["data"] if infos["pastors"] else DEFAULT_PASTORS.copy(),
        "event_types": merge_event_types(
            infos["event_types"]["data"] if infos["event_types"] else None
        ),
        "series": _normalize_series(
            infos["series"]["data"] if infos["series"] else DEFAULT_SERIES.copy()
        ),
        "last_refresh": None,
        "stale": False,
    }
    refreshed_at = [
        info["last_updated"] for info in infos.values() if info and info["last_updated"]
    ]
    if refreshed_at:
        result["last_refresh"] = max(refreshed_at)
    result["stale"] = any(info and info["is_stale"] for info in infos.values())
    return result


def needs_metadata_refresh() -> bool:
    """True when any metadata key is missing from the cache or expired."""
    try:
        from ui.database import get_db

        db = get_db()
        for key in METADATA_KEYS:
            info = db.get_cached_metadata_info(key)
            if info is None or info["is_stale"]:
                return True
        return False
    except Exception as exc:
        logger.warning("Could not check metadata cache: %s", exc)
        return True


def fetch_and_cache_metadata(
    api_key: str | None = None,
    broadcaster_id: str | None = None,
    limit: int = 200,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, list[str]]:
    """Fetch pastors, event types and series from the SermonAudio API and cache them.

    Credentials fall back to the SERMONAUDIO_API_KEY /
    SERMONAUDIO_BROADCASTER_ID environment variables when not passed
    explicitly. Safe to run from a background thread.
    """
    import sermon_updater

    api_key = api_key or os.environ.get("SERMONAUDIO_API_KEY")
    broadcaster_id = broadcaster_id or os.environ.get("SERMONAUDIO_BROADCASTER_ID")

    if not api_key or not broadcaster_id:
        logger.warning(
            "SermonAudio API credentials not configured - "
            f"api_key: {'present' if api_key else 'missing'}, "
            f"broadcaster_id: {'present' if broadcaster_id else 'missing'}"
        )
        return {"pastors": [], "event_types": [], "series": []}

    if progress_callback:
        progress_callback(0.1, "Fetching pastors...")
    pastors = sermon_updater.get_broadcaster_pastors(limit=limit)
    logger.info("Fetched %d pastors", len(pastors))

    if progress_callback:
        progress_callback(0.5, "Fetching event types...")
    event_types = sermon_updater.get_broadcaster_event_types(limit=limit)
    logger.info("Fetched %d event types", len(event_types))

    if progress_callback:
        progress_callback(0.8, "Fetching series...")
    series = sermon_updater.get_broadcaster_series(limit=limit)
    logger.info("Fetched %d series", len(series))

    event_types = merge_event_types(event_types)

    if progress_callback:
        progress_callback(1.0, "Saving to cache...")

    try:
        from ui.database import get_db

        db = get_db()
        if pastors:
            db.cache_metadata("pastors", pastors, expires_hours=24)
            logger.info("Cached %d pastors to SQLite", len(pastors))
        if event_types:
            db.cache_metadata("event_types", event_types, expires_hours=24)
            logger.info("Cached %d event types to SQLite", len(event_types))
        if series:
            db.cache_metadata("series", series, expires_hours=24)
            logger.info("Cached %d series to SQLite", len(series))
    except Exception as exc:
        logger.warning("Could not cache to SQLite: %s", exc)

    return {"pastors": pastors, "event_types": event_types, "series": series}


def get_pastors() -> list[str]:
    """List of pastors/speakers."""
    return get_cached_metadata()["pastors"]


def get_event_types() -> list[str]:
    """List of event types."""
    return get_cached_metadata()["event_types"]


def get_series() -> list[str]:
    """List of sermon series names."""
    return [s["name"] for s in get_cached_metadata()["series"]]


def get_series_map() -> dict[str, int]:
    """Map series names to their numeric SermonAudio seriesID."""
    return {
        s["name"]: s["seriesID"]
        for s in get_cached_metadata()["series"]
        if s.get("seriesID") is not None
    }


FILENAME_DATE_FORMATS = ("%Y-%m-%d", "%Y_%m_%d", "%m-%d-%Y", "%m_%d_%Y", "%d.%m.%Y")


def parse_sermon_filename(filename: str) -> dict[str, str | datetime.date | None]:
    """Parse 'Title - Series - Speaker - date.ext' style filenames.

    The stem is split on the literal ' - ' separator: position 0 is the title,
    1 the series, 2 the speaker and 3 a date candidate. Segments past the
    fourth are ignored and missing ones come back as None.
    """
    stem = Path(filename).stem
    segments = [segment.strip() for segment in stem.split(" - ")]

    def segment(index: int) -> str | None:
        return segments[index] if index < len(segments) else None

    raw_date = segment(3)
    return {
        "title": segment(0) or None,
        "series": segment(1) or None,
        "speaker": segment(2) or None,
        "date": _parse_filename_date(raw_date) if raw_date else None,
    }


def _parse_filename_date(value: str) -> datetime.date | None:
    for date_format in FILENAME_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None
