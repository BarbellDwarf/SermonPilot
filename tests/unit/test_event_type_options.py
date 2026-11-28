"""Event type must come from actual options, never free text.

Covers the pre-create guard in ``sermon_updater`` that fails loudly instead of
firing a create the SermonAudio API would reject with 422.
"""

from __future__ import annotations

import pytest

import sermon_updater as su
import ui.sermon_metadata as metadata

ALLOWED = ["Sunday Service", "Bible Study"]
BAD_VALUE = "Sunday School class"


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
