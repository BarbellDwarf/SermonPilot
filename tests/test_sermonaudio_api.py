"""Mocked tests for the SermonAudio analytics client.

The original file was a live debug script that read real credentials from
config.yaml and hit the real API.  These tests never touch the network or
real credentials.
"""

from __future__ import annotations

from unittest.mock import Mock

from ui.sermonaudio_analytics import SermonAudioAnalytics


def test_mock_mode_without_credentials_returns_empty() -> None:
    analytics = SermonAudioAnalytics()
    assert analytics.mock_mode is True
    assert analytics.get_all_sermon_analytics() == []


def test_real_mode_parses_api_response(monkeypatch) -> None:
    response = Mock()
    response.json.return_value = {
        "results": [
            {
                "sermonID": "123",
                "displayTitle": "Test Sermon",
                "speaker": {"displayName": "Test Speaker"},
                "broadcaster": {"displayName": "Test Church"},
                "preachDate": "2024-01-01",
                "bibleText": "John 3:16",
            }
        ]
    }
    monkeypatch.setattr("ui.sermonaudio_analytics.requests.get", lambda *args, **kwargs: response)

    analytics = SermonAudioAnalytics(api_key="test-key", broadcaster_id="test-broadcaster")
    assert analytics.mock_mode is False
    sermons = analytics.get_all_sermon_analytics()
    assert len(sermons) == 1
    assert sermons[0]["sermon_id"] == "123"
    assert sermons[0]["title"] == "Test Sermon"
    assert sermons[0]["speaker"] == "Test Speaker"
    assert sermons[0]["church_name"] == "Test Church"


def test_real_mode_falls_back_to_mock_on_api_error(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("ui.sermonaudio_analytics.requests.get", boom)

    analytics = SermonAudioAnalytics(api_key="test-key", broadcaster_id="test-broadcaster")
    assert analytics.get_all_sermon_analytics() == []
