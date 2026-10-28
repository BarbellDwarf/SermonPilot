"""Path safety at the upload and server-path boundaries.

Traversal is refused by resolving the candidate first, so a symlink that
points outside the user's roots cannot be used to read a host file. Empty
files are refused before a draft or job is created.
"""

from __future__ import annotations

import os

from server.api.routers.writes import _user_ingest_dir


def _body(path, **overrides):
    body = {
        "container_path": str(path),
        "title": "Path Edge",
        "speaker": "Speaker A",
        "recorded_date": "2026-10-25",
        "event_type": "Sunday Service",
        "dry_run": True,
    }
    body.update(overrides)
    return body


def _source(user_id: str, name: str, payload: bytes):
    path = _user_ingest_dir(user_id) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_stat_and_create_reject_a_symlink_outside_the_roots(
    client, scoped_setup, tmp_path, monkeypatch
):
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "ingest"))
    headers = scoped_setup["a"]["headers"]
    secret = tmp_path / "outside.mp3"
    secret.write_bytes(b"ID3" + bytes(128))
    link = _user_ingest_dir(scoped_setup["a"]["id"]) / "looks-inside.mp3"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(secret, link)

    stat = client.get(
        "/api/sermons/server-path/stat", params={"path": str(link)}, headers=headers
    )
    assert stat.status_code == 403, stat.text

    created = client.post(
        "/api/sermons/server-path", json=_body(link), headers=headers
    )
    assert created.status_code == 403, created.text


def test_absolute_host_path_is_refused(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    response = client.get(
        "/api/sermons/server-path/stat", params={"path": "/etc/passwd"}, headers=headers
    )
    assert response.status_code == 403


def test_zero_byte_server_source_is_refused(client, scoped_setup, tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "ingest"))
    headers = scoped_setup["a"]["headers"]
    empty = _source(scoped_setup["a"]["id"], "empty.mp3", b"")

    response = client.post(
        "/api/sermons/server-path", json=_body(empty), headers=headers
    )
    assert response.status_code == 422, response.text
    assert "empty" in response.json()["detail"]


def test_zero_byte_upload_is_refused(client, scoped_setup, tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "ingest"))
    headers = scoped_setup["a"]["headers"]
    response = client.post(
        "/api/sermons/upload",
        files={"file": ("empty.mp3", b"", "audio/mpeg")},
        data={
            "title": "Empty",
            "speaker": "Speaker A",
            "recorded_date": "2026-10-25",
            "event_type": "Sunday Service",
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    user_dir = _user_ingest_dir(scoped_setup["a"]["id"])
    assert not user_dir.exists() or not any(user_dir.iterdir())


def test_remote_path_with_parent_segments_is_refused(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    for path in (
        "remote:backup:../../etc/passwd",
        "remote:backup:a/../../secret.mp3",
        "remote:..:thing.mp3",
    ):
        response = client.post(
            "/api/sermons/server-path", json=_body(path), headers=headers
        )
        assert response.status_code == 422, (path, response.text)


def test_upload_filename_traversal_is_flattened(client, scoped_setup, tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "ingest"))
    headers = scoped_setup["a"]["headers"]
    response = client.post(
        "/api/sermons/upload",
        files={"file": ("../../escape.mp3", b"ID3" + bytes(256), "audio/mpeg")},
        data={
            "title": "Traversal Name",
            "speaker": "Speaker A",
            "recorded_date": "2026-10-26",
            "event_type": "Sunday Service",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    user_dir = _user_ingest_dir(scoped_setup["a"]["id"])
    stored = [path for path in user_dir.iterdir() if path.is_file()]
    assert len(stored) == 1
    assert stored[0].parent == user_dir
    assert stored[0].name.endswith("escape.mp3")
    assert (tmp_path / "escape.mp3").exists() is False
