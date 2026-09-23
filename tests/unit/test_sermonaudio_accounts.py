"""Resolution of the per-user SermonAudio connection.

The console stores accounts in ``user_settings``; the pipeline must consult
that store instead of one global credential. These tests pin the resolution
order (own account, then a refusal, then the bootstrap fallback only when no
account exists anywhere) and the secret-free public view.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import pytest

from ui import sermonaudio_accounts as sa


def _enc(key: str) -> str:
    return base64.b64encode(key.encode()).decode()


def _seed(path: Path, user_id: str, items: list[dict], default_id: str | None = None) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_settings ("
        " user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT,"
        " PRIMARY KEY (user_id, key))"
    )
    conn.execute(
        "INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
        (user_id, sa.SETTING_KEY, json.dumps({"items": items, "default_id": default_id})),
    )
    conn.commit()
    conn.close()


def _account(account_id: str, name: str, key: str, broadcaster: str) -> dict:
    return {
        "id": account_id,
        "name": name,
        "broadcasterId": broadcaster,
        "_apiKeyEnc": _enc(key),
    }


def test_user_resolves_to_their_own_account(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")

    conn = sa.resolve_connection("u-a", str(db))

    assert conn.usable is True
    assert conn.api_key == "key-alpha-1111"
    assert conn.broadcaster_id == "alpha"
    assert conn.source == sa.SOURCE_USER
    assert conn.account_name == "Alpha"


def test_two_users_keep_their_own_credentials(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    _seed(db, "u-b", [_account("sa-b", "Beta", "key-beta-2222", "beta")], "sa-b")

    a = sa.resolve_connection("u-a", str(db))
    b = sa.resolve_connection("u-b", str(db))

    assert (a.api_key, a.broadcaster_id) == ("key-alpha-1111", "alpha")
    assert (b.api_key, b.broadcaster_id) == ("key-beta-2222", "beta")


def test_default_account_wins_over_the_first(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(
        db,
        "u-a",
        [
            _account("sa-1", "First", "key-first-1111", "first"),
            _account("sa-2", "Second", "key-second-2222", "second"),
        ],
        "sa-2",
    )

    conn = sa.resolve_connection("u-a", str(db))

    assert conn.account_id == "sa-2"
    assert conn.broadcaster_id == "second"


def test_user_without_account_is_refused_when_others_have_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    fallback = sa.SermonAudioConnection(
        api_key="bootstrap-key", broadcaster_id="bootstrap", source="SERMONAUDIO_API_KEY"
    )
    monkeypatch.setattr(sa, "bootstrap_connection", lambda: fallback)

    conn = sa.resolve_connection("u-b", str(db))

    assert conn.usable is False
    assert conn.source == sa.SOURCE_NONE
    assert conn.api_key == ""


def test_bootstrap_applies_only_when_no_account_exists_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE user_settings (user_id TEXT, key TEXT, value TEXT,"
        " PRIMARY KEY (user_id, key))"
    )
    conn.commit()
    conn.close()
    fallback = sa.SermonAudioConnection(
        api_key="bootstrap-key", broadcaster_id="bootstrap", source="SERMONAUDIO_API_KEY"
    )
    monkeypatch.setattr(sa, "bootstrap_connection", lambda: fallback)

    resolved = sa.resolve_connection("u-new", str(db))

    assert resolved.usable is True
    assert resolved.api_key == "bootstrap-key"
    assert resolved.source == "SERMONAUDIO_API_KEY"


def test_describe_never_returns_the_key(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "sa-live-secret-7890", "alpha")], "sa-a")

    view = sa.describe(sa.resolve_connection("u-a", str(db)))

    assert view["configured"] is True
    assert view["account_name"] == "Alpha"
    assert view["broadcaster_id"] == "alpha"
    assert view["masked_key"].endswith("7890")
    assert "sa-live-secret-7890" not in json.dumps(view)


def test_describe_reports_the_refusal_message_without_an_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    monkeypatch.setattr(sa, "bootstrap_connection", sa.SermonAudioConnection)

    view = sa.describe(sa.resolve_connection("u-b", str(db)))

    assert view["configured"] is False
    assert view["message"] == sa.CONNECT_ACCOUNT_MESSAGE
