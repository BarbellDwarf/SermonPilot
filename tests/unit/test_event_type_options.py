"""Event type must come from actual options everywhere, never free text.

Covers the picker contract in ``ui.sermon_metadata`` and the pre-create
guard in ``sermon_updater`` that fails loudly instead of firing a create
the SermonAudio API would reject with 422.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import sermon_updater as su
import ui.sermon_metadata as metadata

ALLOWED = ["Sunday Service", "Bible Study"]
BAD_VALUE = "Sunday School class"


class _FakeSt:
    """Minimal streamlit stand-in recording widget calls."""

    def __init__(self, selection: str) -> None:
        self.selection = selection
        self.selectbox_calls: list[dict] = []
        self.text_input_calls = 0
        self.captions: list[str] = []

    def selectbox(self, label, options, **kwargs):
        self.selectbox_calls.append({"label": label, "options": list(options), "kwargs": kwargs})
        return self.selection

    def text_input(self, *args, **kwargs):
        self.text_input_calls += 1
        raise AssertionError("event type must not use free-text input")

    def caption(self, message):
        self.captions.append(message)


def _patch_picker(monkeypatch, selection, allowed=None, **kwargs):
    fake = _FakeSt(selection)
    monkeypatch.setattr(metadata, "st", fake)
    monkeypatch.setattr(
        metadata, "get_event_types", lambda: list(allowed if allowed is not None else ALLOWED)
    )
    return fake


def test_picker_offers_only_actual_options(monkeypatch) -> None:
    fake = _patch_picker(monkeypatch, "[Select Event Type]")

    assert metadata.create_event_type_selectbox() is None

    assert len(fake.selectbox_calls) == 1
    options = fake.selectbox_calls[0]["options"]
    assert options == ["[Select Event Type]", *ALLOWED]
    assert "[Add New Event Type]" not in options
    assert fake.text_input_calls == 0


def test_picker_returns_selected_option(monkeypatch) -> None:
    fake = _patch_picker(monkeypatch, "Bible Study")

    assert metadata.create_event_type_selectbox() == "Bible Study"
    assert fake.text_input_calls == 0


def test_picker_preselects_current_value(monkeypatch) -> None:
    fake = _patch_picker(monkeypatch, "Bible Study", value="Bible Study")

    assert metadata.create_event_type_selectbox(value="Bible Study") == "Bible Study"
    assert fake.selectbox_calls[0]["kwargs"]["index"] == 2


def test_picker_stale_value_falls_back_to_placeholder(monkeypatch) -> None:
    fake = _patch_picker(monkeypatch, "[Select Event Type]", value=BAD_VALUE)

    assert metadata.create_event_type_selectbox(value=BAD_VALUE) is None
    assert fake.selectbox_calls[0]["kwargs"]["index"] == 0
    assert any(BAD_VALUE in caption for caption in fake.captions)
    assert fake.text_input_calls == 0


def test_picker_with_no_known_options_still_has_no_free_text(monkeypatch) -> None:
    fake = _patch_picker(monkeypatch, "[Select Event Type]", allowed=[])

    assert metadata.create_event_type_selectbox() is None
    assert fake.selectbox_calls[0]["options"] == ["[Select Event Type]"]
    assert fake.text_input_calls == 0


def _patch_allowed(monkeypatch, allowed):
    monkeypatch.setattr(metadata, "get_event_types", lambda: list(allowed))


def test_guard_rejects_invalid_event_type(monkeypatch) -> None:
    _patch_allowed(monkeypatch, ALLOWED)

    with pytest.raises(ValueError, match="Sunday School class"):
        su.validate_event_type_for_api(BAD_VALUE)


def test_guard_error_names_allowed_options(monkeypatch) -> None:
    _patch_allowed(monkeypatch, ALLOWED)

    with pytest.raises(ValueError) as exc_info:
        su.validate_event_type_for_api(BAD_VALUE)

    assert "Bible Study" in str(exc_info.value)
    assert "Sunday Service" in str(exc_info.value)


def test_guard_accepts_valid_event_type(monkeypatch) -> None:
    _patch_allowed(monkeypatch, ALLOWED)

    assert su.validate_event_type_for_api("Bible Study") is None


def test_guard_skips_when_allowed_list_empty(monkeypatch) -> None:
    _patch_allowed(monkeypatch, [])

    assert su.validate_event_type_for_api("Anything At All") is None


def test_create_never_posts_invalid_event_type(monkeypatch) -> None:
    _patch_allowed(monkeypatch, ALLOWED)
    post = Mock(side_effect=AssertionError("must not fire the create"))
    monkeypatch.setattr(su.requests, "post", post)

    with pytest.raises(ValueError, match="Sunday School class"):
        su.create_new_sermon_api(
            title="Title",
            speaker_name="Speaker",
            recorded_date="2024-01-01",
            event_type=BAD_VALUE,
        )

    post.assert_not_called()


def test_publish_dry_run_rejects_invalid_event_type_without_creating(tmp_path, monkeypatch) -> None:
    import ui.database as db

    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")

    class BadEventRepo:
        def get_sermon(self, sermon_id: str) -> dict:
            return {
                "title": "Test Title",
                "speaker": "Test Speaker",
                "recorded_date": "2024-01-01",
                "event_type": BAD_VALUE,
                "content": {"description": "d", "hashtags": "#t", "transcript_text": "t"},
                "file_paths": {"audio": str(audio_file), "metadata": ""},
                "duration": 0,
            }

    _patch_allowed(monkeypatch, ALLOWED)
    create = Mock(side_effect=AssertionError("must not fire the create"))
    monkeypatch.setattr(db, "SermonRepository", lambda: BadEventRepo())
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})

    result = su.publish_dry_run_sermon("draft_bad_event")

    assert result["success"] is False
    assert BAD_VALUE in result["error"]
    assert "Bible Study" in result["error"]
    create.assert_not_called()
