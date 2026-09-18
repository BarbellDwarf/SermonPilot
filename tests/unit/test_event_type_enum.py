"""SermonAudio eventType enum completeness and merge-on-refresh.

Seams under test (public boundaries):
- ui.sermon_metadata.DEFAULT_EVENT_TYPES (authoritative enum seam)
- ui.sermon_metadata.get_event_types (picker consumer seam)
- ui.sermon_metadata.fetch_and_cache_metadata (refresh seam)

Spec: the picker must show the full SermonAudio eventType enum even with an
empty cache, and a refresh must merge (enum + broadcaster extras) rather
than replace.
"""

from __future__ import annotations

EXPECTED_ENUM = [
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

NARROW_CACHE = ["Midweek Service", "Sunday - PM", "Sunday School", "Sunday Service"]


class _FakeDB:
    def __init__(self, event_data=None) -> None:
        self.event_data = event_data
        self.cached: dict = {}

    def get_cached_metadata_info(self, key: str):
        if key == "event_types":
            if self.event_data is None:
                return None
            return {
                "data": list(self.event_data),
                "last_updated": None,
                "expires_at": None,
                "is_stale": False,
            }
        return None

    def cache_metadata(self, key: str, data, expires_hours: int = 24) -> None:
        self.cached[key] = list(data)


def _patch_db(monkeypatch, db) -> None:
    import ui.database as database

    monkeypatch.setattr(database, "get_db", lambda: db)


def test_enum_constant_has_all_values() -> None:
    import ui.sermon_metadata as metadata

    for value in EXPECTED_ENUM:
        assert value in metadata.DEFAULT_EVENT_TYPES
    assert len(metadata.DEFAULT_EVENT_TYPES) >= 28


def test_get_event_types_with_empty_cache_returns_full_enum(monkeypatch) -> None:
    import ui.sermon_metadata as metadata

    _patch_db(monkeypatch, _FakeDB(event_data=None))

    result = metadata.get_event_types()
    for value in EXPECTED_ENUM:
        assert value in result
    assert len(result) >= 28


def test_get_event_types_upgrades_narrow_cache(monkeypatch) -> None:
    import ui.sermon_metadata as metadata

    _patch_db(monkeypatch, _FakeDB(event_data=list(NARROW_CACHE)))

    result = metadata.get_event_types()
    for value in EXPECTED_ENUM:
        assert value in result
    assert len(result) >= 28


def test_fetch_and_cache_merges_rather_than_replaces(monkeypatch) -> None:
    import sermon_updater as su
    import ui.sermon_metadata as metadata

    db = _FakeDB(event_data=None)
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(su, "get_broadcaster_pastors", lambda limit=200: ["Pastor"])
    monkeypatch.setattr(su, "get_broadcaster_event_types", lambda limit=200: list(NARROW_CACHE))
    monkeypatch.setattr(su, "get_broadcaster_series", lambda limit=200: [])

    result = metadata.fetch_and_cache_metadata(api_key="k", broadcaster_id="b")

    for value in EXPECTED_ENUM:
        assert value in result["event_types"]
    for value in NARROW_CACHE:
        assert value in result["event_types"]
    cached = db.cached.get("event_types", [])
    for value in EXPECTED_ENUM:
        assert value in cached
    assert len(cached) >= 28


def test_broadcaster_extra_preserved_on_merge(monkeypatch) -> None:
    import sermon_updater as su
    import ui.sermon_metadata as metadata

    db = _FakeDB(event_data=None)
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(su, "get_broadcaster_pastors", lambda limit=200: [])
    monkeypatch.setattr(
        su, "get_broadcaster_event_types", lambda limit=200: ["Revival Service"]
    )
    monkeypatch.setattr(su, "get_broadcaster_series", lambda limit=200: [])

    result = metadata.fetch_and_cache_metadata(api_key="k", broadcaster_id="b")

    assert "Revival Service" in result["event_types"]
    for value in EXPECTED_ENUM:
        assert value in result["event_types"]
