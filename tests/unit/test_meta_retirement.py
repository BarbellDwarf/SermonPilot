from __future__ import annotations

import sqlite3

from server.api.accounts import get_db_path


def test_retirement_defaults_false_and_needs_no_auth(client):
    r = client.get("/api/meta/retirement")
    assert r.status_code == 200, r.text
    assert r.json() == {"streamlit_ready": False}


def test_retirement_reads_web_console_ready_key(client, tmp_path, monkeypatch):
    from ui.database import SermonDatabase

    SermonDatabase().save_config({"web_console_ready": True})
    assert client.get("/api/meta/retirement").json() == {"streamlit_ready": True}


def test_detail_files_under_user_dir_are_downloadable(client, scoped_setup, tmp_path):
    from server.api.accounts import set_setting, writable_conn

    s = scoped_setup
    outdir = tmp_path / "processed"
    talk = outdir / "user-a-talk"
    talk.mkdir(parents=True)
    keeper = talk / "keeper.mp3"
    keeper.write_bytes(b"audio-bytes")
    with writable_conn() as conn:
        set_setting(conn, s["a"]["id"], "settings.general", {"output_dir": str(outdir)})

    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO sermon_files (sermon_id, file_type, file_path, file_size)"
        " VALUES (?, ?, ?, ?)",
        ("s-a", "keeper_audio", str(keeper), keeper.stat().st_size),
    )
    conn.commit()
    conn.close()

    detail = client.get("/api/sermons/s-a", headers=s["a"]["headers"]).json()
    assert detail["files"][0]["file_path"] == str(keeper)

    listing = client.get("/api/me/files", headers=s["a"]["headers"]).json()
    assert listing["root"] == str(outdir)

    dl = client.get(
        "/api/me/files/download",
        params={"path": "user-a-talk/keeper.mp3"},
        headers=s["a"]["headers"],
    )
    assert dl.status_code == 200
    assert dl.content == b"audio-bytes"

    assert client.get("/api/sermons/s-a", headers=s["b"]["headers"]).status_code == 404
