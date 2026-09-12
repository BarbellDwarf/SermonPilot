"""Tests for the SermonAudio publish-state helper."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import sermon_updater as su  # noqa: E402


class _Resp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_publish_sends_publish_now(monkeypatch):
    captured: dict = {}

    def fake_patch(url, headers=None, json=None, timeout=None):
        captured.update(url=url, payload=json)
        return _Resp(204)

    monkeypatch.setattr(su.requests, "patch", fake_patch)

    assert su.set_sermon_published("123", True) is True
    assert captured["payload"] == {"publishNow": True}
    assert captured["url"].endswith("node/sermons/123")


def test_unpublish_clears_timestamp(monkeypatch):
    captured: dict = {}

    def fake_patch(url, headers=None, json=None, timeout=None):
        captured.update(payload=json)
        return _Resp(204)

    monkeypatch.setattr(su.requests, "patch", fake_patch)

    assert su.set_sermon_published("123", False) is True
    assert captured["payload"] == {"publishTimestamp": None}


def test_failure_returns_false(monkeypatch):
    monkeypatch.setattr(su.requests, "patch", lambda *a, **k: _Resp(401, "nope"))

    assert su.set_sermon_published("123", True) is False
