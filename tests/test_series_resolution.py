"""Regression tests for series resolution and creation on SermonAudio.

The live API returns series objects with a 'title' field; the fetch used to
read 'displayName'/'name' (both null), which starved every series lookup and
left sermons uploading without a series.
"""

from __future__ import annotations

from unittest.mock import Mock

import sermon_updater


def _api_response(results: list[dict], status: int = 200) -> Mock:
    response = Mock()
    response.status_code = status
    response.json.return_value = {"results": results}
    return response


def test_get_broadcaster_series_reads_title_field(monkeypatch) -> None:
    payload = [{
        "seriesID": 215380,
        "title": "Philippians",
        "displayName": None,
        "name": None,
    }]
    monkeypatch.setattr(
        sermon_updater.requests, "get", lambda *a, **k: _api_response(payload)
    )

    series = sermon_updater.get_broadcaster_series()

    assert series == [{"name": "Philippians", "seriesID": 215380}]
    assert sermon_updater._SERIES_BY_NAME["Philippians"] == 215380


def test_resolve_series_id_finds_cached_series(monkeypatch) -> None:
    monkeypatch.setitem(sermon_updater._SERIES_BY_NAME, "All Things Prayer", 213413)

    assert sermon_updater.resolve_series_id("all things prayer") == 213413


def test_resolve_series_id_creates_missing_when_allowed(monkeypatch) -> None:
    monkeypatch.setattr(
        sermon_updater, "get_broadcaster_series", lambda *a, **k: []
    )
    created = Mock(return_value=221725)
    monkeypatch.setattr(sermon_updater, "create_series_on_api", created)

    result = sermon_updater.resolve_series_id("New Series", create_missing=True)

    assert result == 221725
    created.assert_called_once_with("New Series")
    assert sermon_updater._SERIES_BY_NAME["New Series"] == 221725


def test_resolve_series_id_returns_none_when_missing_and_not_creating(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sermon_updater, "get_broadcaster_series", lambda *a, **k: []
    )
    created = Mock()
    monkeypatch.setattr(sermon_updater, "create_series_on_api", created)

    result = sermon_updater.resolve_series_id("Never Created", create_missing=False)

    assert result is None
    created.assert_not_called()


def test_create_series_on_api_parses_created_id(monkeypatch) -> None:
    response = Mock()
    response.status_code = 201
    response.json.return_value = {
        "seriesID": 221725, "title": "Fresh Series", "broadcasterID": "test"
    }
    monkeypatch.setattr(
        sermon_updater.requests, "post", lambda *a, **k: response
    )

    assert sermon_updater.create_series_on_api("Fresh Series") == 221725


def test_create_series_on_api_returns_none_on_failure(monkeypatch) -> None:
    response = Mock()
    response.status_code = 400
    response.json.return_value = {}
    response.text = '{"detail": "bad"}'
    monkeypatch.setattr(
        sermon_updater.requests, "post", lambda *a, **k: response
    )

    assert sermon_updater.create_series_on_api("Bad Series") is None
