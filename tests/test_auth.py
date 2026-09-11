"""Tests for the signed persistent-auth tokens."""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from ui.auth import make_token, valid_token  # noqa: E402


def test_round_trip(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "test-password")

    assert valid_token(make_token(int(time.time()) + 3600))


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "test-password")

    assert not valid_token(make_token(int(time.time()) - 1))


def test_tampered_signature_rejected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "test-password")

    expiry, signature = make_token(int(time.time()) + 3600).split(".", 1)

    assert not valid_token(f"{expiry}.{'0' * len(signature)}")


def test_password_change_revokes_tokens(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "old-password")
    token = make_token(int(time.time()) + 3600)
    monkeypatch.setenv("APP_PASSWORD", "new-password")

    assert not valid_token(token)


def test_garbage_rejected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "test-password")

    assert not valid_token("")
    assert not valid_token("not-a-token")
    assert not valid_token("abc.def")
