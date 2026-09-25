from __future__ import annotations

import json
import os
import sqlite3

import pytest

from server.api.accounts import get_db_path
from server.api.routers.writes import _user_ingest_dir


def _ingest_source(user_id: str, name: str, payload: bytes):
    path = _user_ingest_dir(user_id) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.fixture(autouse=True)
def _allow_tmp_as_ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path))


def _server_path_body(path, **overrides):
    body = {
        "container_path": str(path),
        "title": "Server Talk",
        "speaker": "Speaker A",
        "recorded_date": "2026-09-14",
        "event_type": "Sunday Service",
        "series_title": "Series X",
        "scripture": "Psalm 23",
        "auto_edit_enabled": True,
        "auto_edit_mode": "interactive",
        "logo_path": "user/card.png",
        "fade_to_black": True,
    }
    body.update(overrides)
    return body


def test_server_path_creates_draft_and_queues_job(client, scoped_setup, tmp_path):
    s = scoped_setup
    src = _ingest_source(s["a"]["id"], "talk.mp3", b"ID3" + bytes(2048))

    r = client.post(
        "/api/sermons/server-path", json=_server_path_body(src), headers=s["a"]["headers"]
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["job_id"]
    assert body["filename"] == "talk.mp3"
    assert body["size"] == 2051
    assert body["ext"] == "mp3"
    assert body["kind"] == "audio"
    sermon_id = body["id"]

    conn = sqlite3.connect(get_db_path())
    sermon = conn.execute(
        "SELECT title, speaker, recorded_date, series_title, status, user_id"
        " FROM sermons WHERE id = ?",
        (sermon_id,),
    ).fetchone()
    job = conn.execute(
        "SELECT type, user_id, parameters FROM background_jobs WHERE id = ?",
        (body["job_id"],),
    ).fetchone()
    conn.close()
    assert sermon[:5] == ("Server Talk", "Speaker A", "2026-09-14", "Series X", "draft")
    assert sermon[5] == s["a"]["id"]
    assert job[0] == "sermon_processing"
    assert job[1] == s["a"]["id"]
    params = json.loads(job[2])
    assert params["uploaded_file_path"] == str(src)
    assert params["auto_edit_enabled"] is True
    assert params["auto_edit_mode"] == "interactive"
    form = params["form_data"]
    assert form["speaker_name"] == "Speaker A"
    assert form["bible_text"] == "Psalm 23"
    assert form["series_title"] == "Series X"
    assert form["logo_path"] == "user/card.png"
    assert form["fade_to_black"] is True

    assert client.get(f"/api/sermons/{sermon_id}", headers=s["a"]["headers"]).status_code == 200
    assert client.get(f"/api/sermons/{sermon_id}", headers=s["b"]["headers"]).status_code == 404


def test_server_path_rejects_bad_extension(client, scoped_setup, tmp_path):
    s = scoped_setup
    src = _ingest_source(s["a"]["id"], "notes.txt", b"hello")
    r = client.post(
        "/api/sermons/server-path", json=_server_path_body(src), headers=s["a"]["headers"]
    )
    assert r.status_code == 415


def test_server_path_requires_fields(client, scoped_setup, tmp_path):
    s = scoped_setup
    src = _ingest_source(s["a"]["id"], "talk.mp3", b"ID3")
    for drop in ("container_path", "title", "speaker", "recorded_date"):
        payload = _server_path_body(src)
        payload[drop] = ""
        r = client.post("/api/sermons/server-path", json=payload, headers=s["a"]["headers"])
        assert r.status_code == 422, drop
    missing = _user_ingest_dir(s["a"]["id"]) / "gone.mp3"
    r = client.post(
        "/api/sermons/server-path", json=_server_path_body(missing), headers=s["a"]["headers"]
    )
    assert r.status_code == 422
    assert client.post("/api/sermons/server-path", json=_server_path_body(src)).status_code == 401


def test_server_path_stat_reports_real_file(client, scoped_setup, tmp_path):
    s = scoped_setup
    src = _ingest_source(s["a"]["id"], "clip.mp4", b"\x00" * 4096)
    r = client.get(
        "/api/sermons/server-path/stat", params={"path": str(src)}, headers=s["a"]["headers"]
    )
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["exists"] is True
    assert info["size"] == 4096
    assert info["ext"] == "mp4"
    assert info["kind"] == "video"
    gone = client.get(
        "/api/sermons/server-path/stat",
        params={"path": str(_user_ingest_dir(s["a"]["id"]) / "nope.mp3")},
        headers=s["a"]["headers"],
    ).json()
    assert gone["exists"] is False
    assert client.get("/api/sermons/server-path/stat", params={"path": str(src)}).status_code == 401


def test_server_path_rejects_sources_outside_allowed_roots(
    client, scoped_setup, tmp_path
):
    s = scoped_setup
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    src = outside / "talk.mp3"
    src.write_bytes(b"ID3")

    r = client.post(
        "/api/sermons/server-path", json=_server_path_body(src), headers=s["a"]["headers"]
    )
    assert r.status_code == 403, r.text

    stat = client.get(
        "/api/sermons/server-path/stat",
        params={"path": str(src)},
        headers=s["a"]["headers"],
    )
    assert stat.status_code == 403

    traversal = client.post(
        "/api/sermons/server-path",
        json=_server_path_body(
            str(tmp_path / ".." / f"{tmp_path.name}-outside" / "talk.mp3")
        ),
        headers=s["a"]["headers"],
    )
    assert traversal.status_code == 403


def test_server_path_refuses_another_users_ingest_file(client, scoped_setup):
    s = scoped_setup
    src = _ingest_source(s["a"]["id"], "private.mp3", b"ID3" + bytes(128))
    body = _server_path_body(src)

    denied = client.post(
        "/api/sermons/server-path", json=body, headers=s["b"]["headers"]
    )
    assert denied.status_code == 403, denied.text

    stat = client.get(
        "/api/sermons/server-path/stat",
        params={"path": str(src)},
        headers=s["b"]["headers"],
    )
    assert stat.status_code == 403

    allowed = client.post(
        "/api/sermons/server-path", json=body, headers=s["a"]["headers"]
    )
    assert allowed.status_code == 201, allowed.text


def test_branding_upload_stores_per_user_with_tight_perms(
    client, scoped_setup, tmp_path, monkeypatch
):
    s = scoped_setup
    base = tmp_path / "branding"
    monkeypatch.setenv("SERMONPILOT_BRANDING_DIR", str(base))
    png = b"\x89PNG\r\n\x1a\n" + bytes(64)

    r = client.post(
        "/api/branding",
        files={"file": ("card.png", png, "image/png")},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201, r.text
    rel = r.json()["path"]
    assert rel.startswith(s["a"]["id"][:1]) or "/" in rel
    stored = base / rel
    assert stored.is_file()
    assert stored.read_bytes() == png
    assert oct(os.stat(stored).st_mode & 0o777) == "0o600"

    mine = client.get("/api/branding", headers=s["a"]["headers"]).json()["items"]
    assert [i["name"] for i in mine] == [stored.name]
    theirs = client.get("/api/branding", headers=s["b"]["headers"]).json()["items"]
    assert theirs == []

    bad = client.post(
        "/api/branding",
        files={"file": ("evil.txt", b"hi", "text/plain")},
        headers=s["a"]["headers"],
    )
    assert bad.status_code == 415
    assert client.get("/api/branding").status_code == 401
