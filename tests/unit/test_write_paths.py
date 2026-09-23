from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

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


def test_create_draft_cannot_overwrite_another_users_sermon(client, scoped_setup):
    s = scoped_setup
    body = {"title": "Shared Title", "speaker": "Speaker X", "recorded_date": "2026-09-20"}
    first = client.post("/api/sermons", json=body, headers=s["a"]["headers"])
    assert first.status_code == 201, first.text
    sermon_id = first.json()["id"]

    hijack = client.post(
        "/api/sermons",
        json={**body, "description": "hijacked"},
        headers=s["b"]["headers"],
    )
    assert hijack.status_code == 403, hijack.text

    detail = client.get(f"/api/sermons/{sermon_id}", headers=s["a"]["headers"])
    assert detail.status_code == 200
    assert detail.json()["description"] in (None, "")
    assert client.get(f"/api/sermons/{sermon_id}", headers=s["b"]["headers"]).status_code == 404

    again = client.post(
        "/api/sermons",
        json={**body, "description": "mine now"},
        headers=s["a"]["headers"],
    )
    assert again.status_code == 201, again.text


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
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

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


def test_apply_request_carries_enhance_audio_to_job_parameters(
    client, scoped_setup, monkeypatch
):
    s = scoped_setup
    import ui.database as dbmod

    created = client.post(
        "/api/sermons",
        json={"title": "Enhance Me", "speaker": "S", "recorded_date": "2026-09-13"},
        headers=s["a"]["headers"],
    ).json()
    sid = created["id"]

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

    r = client.post(
        f"/api/sermons/{sid}/plan/apply",
        json={"start": 10.0, "end": 20.0, "render_only": True, "enhance_audio": False},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    params = json.loads(row[0])
    assert params["enhance_audio"] is False


def _insert_completed_apply(sermon_id: str, user_id: str, completed_at: datetime) -> str:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO background_jobs (id, type, title, status, parameters, user_id, completed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "j-just-completed",
            "auto_edit_apply",
            f"Apply edit: {sermon_id}",
            "completed",
            json.dumps({"sermon_id": sermon_id, "render_only": True}),
            user_id,
            completed_at.isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return "j-just-completed"


def test_apply_blocks_reapply_within_grace_window(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    _insert_completed_apply("s-a", s["a"]["id"], datetime.now())

    r = client.post(
        "/api/sermons/s-a/plan/apply",
        json={"start": 10.0, "end": 20.0, "render_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["job_id"] == "j-just-completed"


def test_apply_allows_reapply_after_grace_window(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    _insert_completed_apply("s-a", s["a"]["id"], datetime.now() - timedelta(seconds=30))

    r = client.post(
        "/api/sermons/s-a/plan/apply",
        json={"start": 10.0, "end": 20.0, "render_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text


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


def test_regenerate_description_queues_metadata_job(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

    r = client.post("/api/sermons/s-a/description/regenerate", headers=s["a"]["headers"])
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT type, user_id, parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "metadata_update"
    assert row[1] == s["a"]["id"]
    params = json.loads(row[2])
    assert params["sermon_ids"] == ["s-a"]
    assert params["actions"]["generate_description"] is True

    duplicate = client.post(
        "/api/sermons/s-a/description/regenerate", headers=s["a"]["headers"]
    )
    assert duplicate.status_code == 409

    foreign = client.post(
        "/api/sermons/s-a/description/regenerate", headers=s["b"]["headers"]
    )
    assert foreign.status_code == 404


def test_push_metadata_queues_full_push_job(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

    r = client.post(
        "/api/sermons/s-a/metadata/push",
        json={"full_push": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text
    assert r.json()["full_push"] is True
    job_id = r.json()["job_id"]

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT type, user_id, parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "metadata_update"
    assert row[1] == s["a"]["id"]
    params = json.loads(row[2])
    assert params["sermon_ids"] == ["s-a"]
    assert params["actions"]["push_metadata"] is True
    assert params["actions"]["full_push"] is True

    foreign = client.post(
        "/api/sermons/s-a/metadata/push", json={}, headers=s["b"]["headers"]
    )
    assert foreign.status_code == 404


def test_sermon_detail_surfaces_description_needs_review(client, scoped_setup):
    s = scoped_setup
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE sermons SET description_needs_review = 1 WHERE id = 's-a'")
    conn.commit()
    conn.close()

    body = client.get("/api/sermons/s-a", headers=s["a"]["headers"]).json()
    assert body["description_needs_review"] is True

    other = client.get("/api/sermons/s-b", headers=s["b"]["headers"]).json()
    assert other["description_needs_review"] is False


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
    body = r.json()
    assert body["deleted"] is True
    assert body["id"] == "s-a"
    assert body["recoverable"] is True
    assert body["trash"] == []
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


def test_delete_sermon_moves_local_media_to_trash_and_keeps_cloud(
    client, scoped_setup, tmp_path, monkeypatch
):
    from server.api.routers import sermons as sermons_router

    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    output_root = tmp_path / "output"
    monkeypatch.setattr(sermons_router, "_resolve_output_root", lambda: output_root)
    s = scoped_setup

    local_dir = output_root / "Speaker A" / "No Series" / "Talk - No Series - Speaker A"
    local_dir.mkdir(parents=True)
    local_file = local_dir / "audio.mp3"
    local_file.write_bytes(b"audio bytes")

    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO sermon_files (sermon_id, file_type, file_path) VALUES (?, ?, ?)",
        ("s-a", "audio", str(local_file)),
    )
    conn.execute(
        "INSERT INTO sermon_files (sermon_id, file_type, file_path) VALUES (?, ?, ?)",
        ("s-a", "original", "remote:gdrive:talks/example/service.mp4"),
    )
    conn.commit()
    conn.close()

    r = client.delete("/api/sermons/s-a", headers=s["a"]["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recoverable"] is True
    modes = {record["mode"] for record in body["trash"]}
    assert "local" in modes
    assert "remote-kept" in modes
    assert not local_file.exists()
    moved = list((tmp_path / "trash").rglob("audio.mp3"))
    assert len(moved) == 1
    assert moved[0].read_bytes() == b"audio bytes"
    kept = next(record for record in body["trash"] if record["mode"] == "remote-kept")
    assert kept["destination"] == "remote:gdrive:talks/example/service.mp4"
    assert kept["recoverable"] is True


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


def test_refine_queues_auto_edit_job_with_notes(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

    r = client.post(
        "/api/sermons/s-a/plan/refine",
        json={"notes": "Only the second class"},
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
    assert row[0] == "auto_edit"
    assert row[1] in ("queued", "running")
    assert row[2] == s["a"]["id"]
    params = json.loads(row[3])
    assert params["refine"] is True
    assert params["re_detect"] is False
    assert params["notes"] == "Only the second class"
    assert params["sermon_id"] == "s-a"
    assert params["config"]

    duplicate = client.post(
        "/api/sermons/s-a/plan/refine",
        json={"notes": "again"},
        headers=s["a"]["headers"],
    )
    assert duplicate.status_code == 409

    foreign = client.post(
        "/api/sermons/s-a/plan/refine",
        json={"notes": "notes"},
        headers=s["b"]["headers"],
    )
    assert foreign.status_code == 404


def test_refine_requires_notes(client, scoped_setup):
    s = scoped_setup
    assert (
        client.post(
            "/api/sermons/s-a/plan/refine",
            json={"notes": "   "},
            headers=s["a"]["headers"],
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/sermons/s-a/plan/refine",
            json={},
            headers=s["a"]["headers"],
        ).status_code
        == 422
    )


def test_re_detect_queues_fresh_job_without_notes(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

    r = client.post("/api/sermons/s-a/plan/re-detect", headers=s["a"]["headers"])
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT type, parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "auto_edit"
    params = json.loads(row[1])
    assert params["refine"] is True
    assert params["re_detect"] is True
    assert params["notes"] == ""

    foreign = client.post("/api/sermons/s-b/plan/re-detect", headers=s["a"]["headers"])
    assert foreign.status_code == 404


def test_plan_endpoint_carries_reasoning_and_notes(client, scoped_setup):
    s = scoped_setup
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO edit_plans (sermon_id, revision, status, proposed_start,"
        " proposed_end, confidence, reasoning, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("s-a", 2, "pending_review", 10.0, 20.0, 0.8, "second class only", "Keep only the second"),
    )
    conn.commit()
    conn.close()

    got = client.get("/api/sermons/s-a/plan", headers=s["a"]["headers"])
    assert got.status_code == 200, got.text
    plan = got.json()["plan"]
    assert plan["reasoning"] == "second class only"
    assert plan["notes"] == "Keep only the second"
