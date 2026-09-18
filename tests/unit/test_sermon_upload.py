from __future__ import annotations

import json
import sqlite3

from server.api.accounts import get_db_path

TINY_MP3 = b"ID3" + bytes(1024)


def _post_upload(client, headers, filename="sample-talk.mp3", content=TINY_MP3, **fields):
    data = {
        "title": "Uploaded Talk",
        "speaker": "Speaker A",
        "recorded_date": "2026-09-13",
        "event_type": "Sunday Service",
    }
    data.update(fields)
    return client.post(
        "/api/sermons/upload",
        files={"file": (filename, content, "audio/mpeg")},
        data=data,
        headers=headers,
    )


def test_upload_streams_to_user_dir_and_queues_job(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    ingest = tmp_path / "raw_ingest"
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(ingest))

    r = _post_upload(client, s["a"]["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["job_id"]
    sermon_id = body["id"]

    user_dir = ingest / s["a"]["id"]
    stored = list(user_dir.iterdir())
    assert len(stored) == 1
    assert stored[0].name == body["filename"]
    assert stored[0].stat().st_size == len(TINY_MP3)

    conn = sqlite3.connect(get_db_path())
    owner = conn.execute(
        "SELECT user_id, status FROM sermons WHERE id = ?", (sermon_id,)
    ).fetchone()
    job = conn.execute(
        "SELECT type, user_id, parameters FROM background_jobs WHERE id = ?",
        (body["job_id"],),
    ).fetchone()
    conn.close()
    assert owner[0] == s["a"]["id"]
    assert owner[1] == "draft"
    assert job[0] == "sermon_processing"
    assert job[1] == s["a"]["id"]
    assert json.loads(job[2])["uploaded_file_path"] == str(stored[0])

    assert client.get(f"/api/sermons/{sermon_id}", headers=s["a"]["headers"]).status_code == 200
    assert client.get(f"/api/sermons/{sermon_id}", headers=s["b"]["headers"]).status_code == 404


def test_upload_rejects_bad_extension(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    r = _post_upload(client, s["a"]["headers"], filename="notes.txt", content=b"hello")
    assert r.status_code == 415


def test_upload_enforces_size_cap(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    monkeypatch.setenv("SERMONPILOT_UPLOAD_GB", "0.000001")
    r = _post_upload(client, s["a"]["headers"], content=b"x" * 4096)
    assert r.status_code == 413


def test_upload_requires_metadata(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    r = _post_upload(client, s["a"]["headers"], speaker="")
    assert r.status_code == 422


def test_upload_needs_auth(client, scoped_setup, tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    r = _post_upload(client, {})
    assert r.status_code == 401
