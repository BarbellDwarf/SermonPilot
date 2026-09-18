from __future__ import annotations

import sqlite3

from server.api.accounts import get_db_path


def test_create_draft_sermon_attributes_and_scopes(client, scoped_setup):
    s = scoped_setup
    body = {"title": "Draft A", "speaker": "Speaker A", "recorded_date": "2026-09-10"}
    r = client.post("/api/sermons", json=body, headers=s["a"]["headers"])
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["title"] == "Draft A"
    assert data["status"] == "draft"
    sermon_id = data["id"]

    assert client.get(f"/api/sermons/{sermon_id}", headers=s["a"]["headers"]).status_code == 200
    assert client.get(f"/api/sermons/{sermon_id}", headers=s["b"]["headers"]).status_code == 404
    assert client.get(f"/api/sermons/{sermon_id}", headers=s["admin_headers"]).status_code == 200

    conn = sqlite3.connect(get_db_path())
    owner = conn.execute("SELECT user_id FROM sermons WHERE id = ?", (sermon_id,)).fetchone()[0]
    conn.close()
    assert owner == s["a"]["id"]

    no_auth = client.post("/api/sermons", json=body)
    assert no_auth.status_code == 401
    missing = client.post("/api/sermons", json={"speaker": "x"}, headers=s["a"]["headers"])
    assert missing.status_code == 422


def test_apply_queues_job_with_attribution_and_guard(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    created = client.post(
        "/api/sermons",
        json={"title": "Apply Me", "speaker": "S", "recorded_date": "2026-09-11"},
        headers=s["a"]["headers"],
    ).json()
    sid = created["id"]

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())

    r = client.post(
        f"/api/sermons/{sid}/plan/apply",
        json={"start": 10.0, "end": 20.0, "render_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT type, status, user_id, parameters FROM background_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "auto_edit_apply"
    assert row[1] in ("queued", "running")
    assert row[2] == s["a"]["id"]

    duplicate = client.post(
        f"/api/sermons/{sid}/plan/apply",
        json={"start": 10.0, "end": 20.0, "render_only": True},
        headers=s["a"]["headers"],
    )
    assert duplicate.status_code == 409

    foreign = client.post(
        f"/api/sermons/{sid}/plan/apply",
        json={"start": 1.0, "end": 2.0},
        headers=s["b"]["headers"],
    )
    assert foreign.status_code == 404


def test_cancel_job_scoped(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod
    from ui.job_queue import JobQueue, JobType

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    queue = JobQueue(max_workers=1)
    jid = queue.add_job(JobType.VALIDATION, "t", "d", parameters={}, user_id=s["a"]["id"])

    r = client.post(f"/api/jobs/{jid}/cancel", headers=s["b"]["headers"])
    assert r.status_code == 404
    r = client.post(f"/api/jobs/{jid}/cancel", headers=s["a"]["headers"])
    assert r.status_code == 200
    assert r.json()["cancelled"] is True
    conn = sqlite3.connect(get_db_path())
    status = conn.execute(
        "SELECT status FROM background_jobs WHERE id = ?", (jid,)
    ).fetchone()[0]
    conn.close()
    assert status == "cancelled"


def test_upload_now_queues_publish_job(client, scoped_setup, monkeypatch):
    import json

    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())

    created = client.post(
        "/api/sermons",
        json={"title": "Push Me", "speaker": "S", "recorded_date": "2026-09-12"},
        headers=s["a"]["headers"],
    ).json()
    sid = created["id"]
    r = client.post(f"/api/sermons/{sid}/upload", headers=s["a"]["headers"])
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT type, user_id, parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "sermon_publish"
    assert row[1] == s["a"]["id"]
    assert json.loads(row[2]).get("sermon_id") == sid


def test_cancel_isolated_queue_fresh_instance(tmp_path, monkeypatch):
    import ui.database as dbmod
    import ui.job_queue as jqmod
    from ui.database import SermonDatabase
    from ui.job_queue import JobQueue, JobType

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "iso.db"))
    SermonDatabase().init_database()
    monkeypatch.setattr(jqmod, "_job_queue", None)

    queue = JobQueue(max_workers=1)
    jid = queue.add_job(JobType.VALIDATION, "t", "d", parameters={}, user_id="u-iso")
    ok = queue.cancel_job(jid)
    assert ok is True
    conn = sqlite3.connect(str(tmp_path / "iso.db"))
    row = conn.execute("SELECT status FROM background_jobs WHERE id = ?", (jid,)).fetchone()
    conn.close()
    assert row == ("cancelled",)


def test_sermons_pagination_limit_offset(client, scoped_setup):
    s = scoped_setup
    full = client.get("/api/sermons", headers=s["admin_headers"]).json()
    assert full["total"] == 3
    assert len(full["items"]) == 3

    page = client.get(
        "/api/sermons", params={"limit": 2}, headers=s["admin_headers"]
    ).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert [item["id"] for item in page["items"]] == [
        item["id"] for item in full["items"][:2]
    ]

    rest = client.get(
        "/api/sermons", params={"limit": 2, "offset": 2}, headers=s["admin_headers"]
    ).json()
    assert rest["total"] == 3
    assert [item["id"] for item in rest["items"]] == [full["items"][2]["id"]]

    bad = client.get(
        "/api/sermons", params={"limit": 0}, headers=s["admin_headers"]
    )
    assert bad.status_code == 422


def test_delete_sermon_owner_admin_and_foreign(client, scoped_setup):
    s = scoped_setup
    assert client.delete("/api/sermons/s-a").status_code == 401
    assert (
        client.delete("/api/sermons/s-a", headers=s["b"]["headers"]).status_code == 404
    )
    assert (
        client.delete("/api/sermons/nope", headers=s["admin_headers"]).status_code
        == 404
    )
    r = client.delete("/api/sermons/s-a", headers=s["a"]["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": True, "id": "s-a"}
    assert (
        client.get("/api/sermons/s-a", headers=s["a"]["headers"]).status_code == 404
    )
    conn = sqlite3.connect(get_db_path())
    row = conn.execute("SELECT id FROM sermons WHERE id = 's-a'").fetchone()
    conn.close()
    assert row is None
    legacy = client.delete("/api/sermons/s-null", headers=s["a"]["headers"])
    assert legacy.status_code == 404
    admin = client.delete("/api/sermons/s-null", headers=s["admin_headers"])
    assert admin.status_code == 200, admin.text


def test_sermon_transcript_and_truncation(client, scoped_setup):
    s = scoped_setup
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO sermon_content (sermon_id, transcript_text) VALUES (?, ?)",
        ("s-a", "word " * 100),
    )
    long_text = "x" * 50100
    conn.execute(
        "INSERT INTO sermon_content (sermon_id, transcript_text) VALUES (?, ?)",
        ("s-b", long_text),
    )
    conn.commit()
    conn.close()

    assert client.get("/api/sermons/s-a/transcript").status_code == 401
    assert (
        client.get("/api/sermons/s-a/transcript", headers=s["b"]["headers"]).status_code
        == 404
    )
    short = client.get(
        "/api/sermons/s-a/transcript", headers=s["a"]["headers"]
    ).json()
    assert short["id"] == "s-a"
    assert short["truncated"] is False
    assert short["total_length"] == 500
    assert short["transcript"] == "word " * 100

    cut = client.get("/api/sermons/s-b/transcript", headers=s["admin_headers"]).json()
    assert cut["truncated"] is True
    assert cut["total_length"] == 50100
    assert len(cut["transcript"]) > 50000
    assert "truncated at 50000 of 50100" in cut["transcript"]

    missing = client.get(
        "/api/sermons/nope/transcript", headers=s["admin_headers"]
    )
    assert missing.status_code == 404
