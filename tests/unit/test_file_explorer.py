from __future__ import annotations

import json
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
def _allow_tmp_roots(tmp_path, monkeypatch):
    raw = tmp_path.parent / f"{tmp_path.name}-raw"
    raw.mkdir()
    monkeypatch.setenv("OUTPUT_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(raw))


def _seed_output_dir(user_id: str, path) -> None:
    from server.api.accounts import set_setting, writable_conn

    with writable_conn() as conn:
        set_setting(conn, user_id, "settings.general", {"output_dir": str(path)})


def test_explore_default_root_lists_items(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "processed"
    (outdir / "sub").mkdir(parents=True)
    (outdir / "talk.mp3").write_bytes(b"ID3" + bytes(100))
    _seed_output_dir(s["a"]["id"], outdir)

    r = client.get("/api/files/explore", headers=s["a"]["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == str(outdir.resolve())
    assert body["parent"] is None
    assert body["root"] == str(outdir.resolve())
    names = {item["name"]: item for item in body["items"]}
    assert names["sub"]["type"] == "dir"
    assert names["sub"]["size"] is None
    assert names["talk.mp3"]["type"] == "file"
    assert names["talk.mp3"]["size"] == 103
    assert names["talk.mp3"]["modified"]
    assert names["sub"]["modified"]
    assert names["talk.mp3"]["path"] == str((outdir / "talk.mp3").resolve())

    child = client.get(
        "/api/files/explore",
        params={"path": str(outdir / "sub")},
        headers=s["a"]["headers"],
    )
    assert child.status_code == 200
    assert child.json()["parent"] == str(outdir.resolve())
    assert child.json()["items"] == []


def test_explore_confines_to_roots(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    outdir = tmp_path / "processed"
    outdir.mkdir()
    ingest = tmp_path.parent / f"{tmp_path.name}-confined-raw"
    own_ingest = ingest / s["a"]["id"]
    foreign_ingest = ingest / s["b"]["id"]
    own_ingest.mkdir(parents=True)
    foreign_ingest.mkdir(parents=True)
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(ingest))
    _seed_output_dir(s["a"]["id"], outdir)

    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "keys.txt").write_bytes(b"nope")

    roots = client.get("/api/files/explore", headers=s["a"]["headers"]).json()["roots"]
    assert {r["path"] for r in roots} == {str(outdir.resolve()), str(own_ingest.resolve())}
    assert client.get(
        "/api/files/explore",
        params={"path": str(own_ingest)},
        headers=s["a"]["headers"],
    ).status_code == 200
    assert client.get(
        "/api/files/explore",
        params={"path": str(own_ingest)},
        headers=s["b"]["headers"],
    ).status_code == 403

    escape = client.get(
        "/api/files/explore", params={"path": str(secret)}, headers=s["a"]["headers"]
    )
    assert escape.status_code == 403
    traversal = client.get(
        "/api/files/explore",
        params={"path": str(outdir / ".." / ".." / ".." / "etc")},
        headers=s["a"]["headers"],
    )
    assert traversal.status_code == 403
    missing = client.get(
        "/api/files/explore", params={"path": str(outdir / "gone")}, headers=s["a"]["headers"]
    )
    assert missing.status_code == 404
    assert client.get("/api/files/explore").status_code == 401


def test_output_dir_get_put_per_user(client, scoped_setup, tmp_path):
    s = scoped_setup
    initial = client.get("/api/me/output-dir", headers=s["a"]["headers"]).json()
    assert initial == {"output_dir": "processed_sermons", "source": "default"}
    assert client.get("/api/me/output-dir", headers=s["b"]["headers"]).json()["source"] == "default"

    target = tmp_path / "my-output"
    target.mkdir()
    put = client.put(
        "/api/me/output-dir", json={"output_dir": str(target)}, headers=s["a"]["headers"]
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"output_dir": str(target), "source": "user"}

    assert client.get("/api/me/output-dir", headers=s["a"]["headers"]).json() == {
        "output_dir": str(target),
        "source": "user",
    }
    assert client.get("/api/me/output-dir", headers=s["b"]["headers"]).json()["source"] == "default"

    created_parent = tmp_path / "makes" / "this"
    ok = client.put(
        "/api/me/output-dir",
        json={"output_dir": str(created_parent)},
        headers=s["a"]["headers"],
    )
    assert ok.status_code == 200, ok.text

    assert (
        client.put(
            "/api/me/output-dir", json={"output_dir": "/"}, headers=s["a"]["headers"]
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/me/output-dir", json={"output_dir": "  "}, headers=s["a"]["headers"]
        ).status_code
        == 422
    )
    a_file = tmp_path / "not-a-dir.txt"
    a_file.write_bytes(b"x")
    assert (
        client.put(
            "/api/me/output-dir", json={"output_dir": str(a_file)}, headers=s["a"]["headers"]
        ).status_code
        == 422
    )
    assert client.get("/api/me/output-dir").status_code == 401


def _job_params(client, job_id):
    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    return json.loads(row[0])


def test_upload_output_dir_override_threads_to_job(
    client, scoped_setup, tmp_path, monkeypatch
):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))
    override = tmp_path / "override-out"
    override.mkdir()
    r = client.post(
        "/api/sermons/upload",
        files={"file": ("talk.mp3", b"ID3" + bytes(64), "audio/mpeg")},
        data={
            "title": "Talk",
            "speaker": "Speaker A",
            "recorded_date": "2026-09-13",
            "event_type": "Sunday Service",
            "output_dir": str(override),
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201, r.text
    assert _job_params(client, r.json()["job_id"])["output_dir"] == str(override.resolve())

    default_upload = client.post(
        "/api/sermons/upload",
        files={"file": ("talk2.mp3", b"ID3" + bytes(64), "audio/mpeg")},
        data={
            "title": "Talk 2",
            "speaker": "Speaker A",
            "recorded_date": "2026-09-13",
            "event_type": "Sunday Service",
        },
        headers=s["a"]["headers"],
    )
    assert default_upload.status_code == 201
    sampled = _job_params(client, default_upload.json()["job_id"])["output_dir"]
    assert sampled.endswith("processed_sermons")


def test_server_path_output_dir_override_threads_to_job(client, scoped_setup, tmp_path):
    s = scoped_setup
    src = _ingest_source(s["a"]["id"], "talk.mp3", b"ID3" + bytes(128))
    override = tmp_path / "server-out"
    override.mkdir()
    r = client.post(
        "/api/sermons/server-path",
        json={
            "container_path": str(src),
            "title": "Server Talk",
            "speaker": "Speaker A",
            "recorded_date": "2026-09-14",
            "event_type": "Sunday Service",
            "output_dir": str(override),
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201, r.text
    assert _job_params(client, r.json()["job_id"])["output_dir"] == str(override.resolve())


def test_output_dir_default_is_used_when_override_absent(client, scoped_setup, tmp_path):
    s = scoped_setup
    target = tmp_path / "user-default"
    target.mkdir()
    _seed_output_dir(s["a"]["id"], target)
    src = _ingest_source(s["a"]["id"], "talk.mp3", b"ID3" + bytes(128))
    r = client.post(
        "/api/sermons/server-path",
        json={
            "container_path": str(src),
            "title": "Server Talk",
            "speaker": "Speaker A",
            "recorded_date": "2026-09-14",
            "event_type": "Sunday Service",
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201, r.text
    assert _job_params(client, r.json()["job_id"])["output_dir"] == str(target.resolve())
