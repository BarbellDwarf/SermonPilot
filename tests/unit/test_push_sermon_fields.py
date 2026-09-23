"""The full metadata push sends every API-supported field and reports skips.

The SermonAudio ``SermonParamsPatch`` schema accepts fullTitle, displayTitle,
subtitle, bibleText, eventType, keywords, and moreInfoText. The push must send
all of them and name any field it could not send, with a reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sermon_updater as su  # noqa: E402


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _stub_api(monkeypatch):
    monkeypatch.setattr(su, "get_api_headers", lambda: {})
    monkeypatch.setattr(su, "validate_event_type_for_api", lambda value: None)


def _capture_patch(monkeypatch, status_code: int = 204) -> list[dict]:
    calls: list[dict] = []

    def fake_patch(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        return _Resp(status_code)

    monkeypatch.setattr(su.requests, "patch", fake_patch)
    return calls


def test_full_push_sends_every_supported_field(monkeypatch) -> None:
    calls = _capture_patch(monkeypatch)

    result = su.push_sermon_fields(
        "123",
        {
            "title": "A Title",
            "display_title": "A Title",
            "subtitle": "A Subtitle",
            "bible_text": "John 3:16",
            "event_type": "Sunday Service",
            "hashtags": "#one #two",
            "description": "A description.",
        },
    )

    assert result["success"] is True
    assert set(result["pushed"]) == {
        "title",
        "display_title",
        "subtitle",
        "bible_text",
        "event_type",
        "hashtags",
        "description",
    }
    assert calls[0]["json"] == {
        "fullTitle": "A Title",
        "displayTitle": "A Title",
        "subtitle": "A Subtitle",
        "bibleText": "John 3:16",
        "eventType": "Sunday Service",
        "keywords": "#one #two",
        "moreInfoText": "A description.",
    }


def test_push_reports_skipped_fields_with_reasons(monkeypatch) -> None:
    _capture_patch(monkeypatch)

    def reject_bad_event(value: str) -> None:
        if value == "Nope":
            raise ValueError("Invalid event_type 'Nope'")

    monkeypatch.setattr(su, "validate_event_type_for_api", reject_bad_event)

    result = su.push_sermon_fields(
        "123",
        {
            "title": "x" * 90,
            "subtitle": "   ",
            "speaker": "Someone",
            "event_type": "Nope",
            "description": "kept",
        },
    )

    assert result["success"] is True
    assert result["pushed"] == ["description"]
    assert "exceeds 85 characters" in result["skipped"]["title"]
    assert result["skipped"]["subtitle"] == "empty value"
    assert "not updatable" in result["skipped"]["speaker"]
    assert "Nope" in result["skipped"]["event_type"]


def test_no_updatable_fields_is_a_failure(monkeypatch) -> None:
    calls = _capture_patch(monkeypatch)

    result = su.push_sermon_fields("123", {"subtitle": "", "speaker": "Someone"})

    assert result["success"] is False
    assert result["pushed"] == []
    assert calls == []


def test_full_metadata_push_gathers_stored_fields(monkeypatch) -> None:
    calls = _capture_patch(monkeypatch)

    result = su.push_sermon_metadata(
        "123",
        {
            "title": "Stored Title",
            "subtitle": "Stored Subtitle",
            "bible_text": "Romans 8",
            "event_type": "Sunday Service",
            "hashtags": "#stored",
            "description": "Stored description.",
        },
        full_push=True,
    )

    assert result["success"] is True
    assert "title" in result["pushed"]
    assert calls[0]["json"]["fullTitle"] == "Stored Title"
    assert calls[0]["json"]["keywords"] == "#stored"


def test_default_push_stays_description_only(monkeypatch) -> None:
    captured: dict = {}

    def fake_update(sermon_id, description, hashtags, series_title=None):
        captured.update(
            {
                "sermon_id": sermon_id,
                "description": description,
                "hashtags": hashtags,
                "series_title": series_title,
            }
        )
        return True

    monkeypatch.setattr(su, "update_sermon_metadata", fake_update)

    result = su.push_sermon_metadata(
        "123",
        {"title": "T", "description": "D", "hashtags": "#h"},
    )

    assert result["success"] is True
    assert captured["description"] == "D"
    assert captured["hashtags"] == ["#h"]
    assert result["pushed"] == ["description", "hashtags"]
