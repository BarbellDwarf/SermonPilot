"""Publishing is gated on the requesting user's own SermonAudio account.

The console refuses a publish before a job exists when the user has no account,
shows which account an upload will use, and never returns or stores the key.
"""

from __future__ import annotations

import json
import sqlite3

from server.api.accounts import get_db_path
from ui.sermonaudio_accounts import CONNECT_ACCOUNT_MESSAGE

TINY_MP3 = b"ID3" + bytes(1024)


def _create_account(client, headers, key: str = "sa-key-4321") -> str:
    r = client.post(
        "/api/me/connections/sermonaudio",
        json={"name": "Alpha", "broadcasterId": "alpha", "apiKey": key},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload(client, headers, **fields):
    data = {
        "title": "Uploaded Talk",
        "speaker": "Speaker A",
        "recorded_date": "2026-09-13",
        "event_type": "Sunday Service",
    }
    data.update(fields)
    return client.post(
        "/api/sermons/upload",
        files={"file": ("sample-talk.mp3", TINY_MP3, "audio/mpeg")},
        data=data,
        headers=headers,
    )


def _jobs() -> list[tuple]:
    conn = sqlite3.connect(get_db_path())
    rows = conn.execute("SELECT id, parameters FROM background_jobs").fetchall()
    conn.close()
    return rows


def test_effective_view_reports_the_bootstrap_fallback(client, scoped_setup):
    s = scoped_setup
    r = client.get("/api/me/sermonaudio-connection", headers=s["a"]["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["source"] in ("db", "default", "SERMONAUDIO_API_KEY")
    assert "test-api-key" not in r.text


def test_effective_view_reports_the_users_own_account(client, scoped_setup):
    s = scoped_setup
    _create_account(client, s["a"]["headers"], key="sa-live-secret-7890")
    r = client.get("/api/me/sermonaudio-connection", headers=s["a"]["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["source"] == "user"
    assert body["account_name"] == "Alpha"
    assert body["broadcaster_id"] == "alpha"
    assert body["masked_key"].endswith("7890")
    assert "sa-live-secret-7890" not in r.text
    assert "sa-live-secret-7890" not in json.dumps(body)


def test_publish_is_refused_when_the_user_has_no_account(
    client, scoped_setup, tmp_path, monkeypatch
):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    _create_account(client, s["a"]["headers"])
    before = len(_jobs())

    r = _upload(client, s["b"]["headers"])

    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "no_sermonaudio_account"
    assert r.json()["detail"]["message"] == CONNECT_ACCOUNT_MESSAGE
    assert "sa-key-4321" not in r.text
    assert len(_jobs()) == before


def test_publish_is_allowed_for_the_user_with_an_account(
    client, scoped_setup, tmp_path, monkeypatch
):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    _create_account(client, s["a"]["headers"])

    r = _upload(client, s["a"]["headers"])

    assert r.status_code == 201, r.text
    assert r.json()["job_id"]


def test_upload_now_is_refused_when_the_user_has_no_account(client, scoped_setup):
    s = scoped_setup
    _create_account(client, s["a"]["headers"])

    r = client.post("/api/sermons/s-b/upload", headers=s["b"]["headers"])

    assert r.status_code == 422, r.text
    assert r.json()["detail"]["message"] == CONNECT_ACCOUNT_MESSAGE


def test_dry_run_upload_is_allowed_without_an_account(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    _create_account(client, s["a"]["headers"])

    r = _upload(client, s["b"]["headers"], dry_run=True)

    assert r.status_code == 201, r.text


def test_interactive_auto_edit_is_allowed_without_an_account(
    client, scoped_setup, tmp_path, monkeypatch
):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    _create_account(client, s["a"]["headers"])

    r = _upload(
        client,
        s["b"]["headers"],
        auto_edit_enabled=True,
        auto_edit_mode="interactive",
    )

    assert r.status_code == 201, r.text


def test_stored_job_parameters_never_contain_the_key(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    _create_account(client, s["a"]["headers"], key="sa-live-secret-7890")

    r = _upload(client, s["a"]["headers"])
    assert r.status_code == 201, r.text

    stored = json.dumps(_jobs())
    assert "sa-live-secret-7890" not in stored
