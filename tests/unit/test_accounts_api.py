from __future__ import annotations

import datetime
import os
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from server.api.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "accounts.db"
    monkeypatch.setenv("SERMONPILOT_DB", str(db_path))
    # minimal sermons schema so the read router can open the DB; auth runs FIRST
    from ui.database import SermonDatabase
    SermonDatabase(db_path=str(db_path)).init_database()
    monkeypatch.setenv("SERMONPILOT_ADMIN_USER", "test-admin")
    monkeypatch.setenv("SERMONPILOT_ADMIN_PASSWORD", secrets.token_urlsafe(24))
    with TestClient(create_app()) as client:
        yield client


def test_first_boot_and_auth_boundary(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["needs_bootstrap"] is True
    assert client.get("/api/sermons").status_code == 401
    assert client.get("/api/health").status_code == 200
    response = client.post("/api/auth/bootstrap")
    assert response.status_code == 201
    assert response.json()["role"] == "admin"
    assert "token" not in response.json()
    assert client.post("/api/auth/bootstrap").status_code == 400
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["needs_bootstrap"] is False


JOBS_DDL = """
    CREATE TABLE IF NOT EXISTS background_jobs (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL,
        progress REAL DEFAULT 0,
        parameters TEXT,
        result TEXT,
        logs TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        can_cancel BOOLEAN DEFAULT 1,
        can_retry BOOLEAN DEFAULT 1,
        priority INTEGER DEFAULT 5,
        user_id TEXT
    )
"""


@pytest.fixture
def scoped_setup(client):
    from server.api.accounts import migrate

    migrate()
    admin_pw = os.environ["SERMONPILOT_ADMIN_PASSWORD"]
    client.post("/api/auth/bootstrap")
    admin_token = client.post(
        "/api/auth/login", json={"username": "test-admin", "password": admin_pw}
    ).json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = client.get("/api/auth/me", headers=admin_headers).json()["id"]

    def make_user(username: str) -> dict:
        body = {
            "username": username,
            "display_name": username,
            "password": "pw-" + username,
            "role": "user",
        }
        user = client.post("/api/admin/users", json=body, headers=admin_headers).json()
        token = client.post(
            "/api/auth/login", json={"username": username, "password": "pw-" + username}
        ).json()["token"]
        return {"id": user["id"], "headers": {"Authorization": f"Bearer {token}"}}

    user_a = make_user("user-a")
    user_b = make_user("user-b")
    import sqlite3

    from server.api.accounts import get_db_path

    sermon_insert = (
        "INSERT INTO sermons (id, title, speaker, recorded_date, status, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    job_insert = (
        "INSERT INTO background_jobs (id, type, title, status, user_id) VALUES (?, ?, ?, ?, ?)"
    )
    conn = sqlite3.connect(get_db_path())
    conn.execute(JOBS_DDL)
    conn.execute(
        sermon_insert, ("s-a", "Owned A", "Speaker A", "2026-09-01", "processed", user_a["id"])
    )
    conn.execute(
        sermon_insert, ("s-b", "Owned B", "Speaker B", "2026-09-02", "processed", user_b["id"])
    )
    conn.execute(
        sermon_insert, ("s-null", "Legacy", "Speaker C", "2026-09-03", "processed", None)
    )
    for jid, owner in (("j-a", user_a["id"]), ("j-b", user_b["id"]), ("j-null", None)):
        conn.execute(job_insert, (jid, "full_pipeline", jid, "completed", owner))
    conn.commit()
    conn.close()
    return {"admin_headers": admin_headers, "admin_id": admin_id, "a": user_a, "b": user_b}


def _ids(body: dict) -> list[str]:
    return sorted(item["id"] for item in body["items"])


def test_user_sees_only_owned_sermons(client, scoped_setup):
    s = scoped_setup
    assert _ids(client.get("/api/sermons", headers=s["a"]["headers"]).json()) == ["s-a"]
    assert _ids(client.get("/api/sermons", headers=s["b"]["headers"]).json()) == ["s-b"]
    admin_ids = _ids(client.get("/api/sermons", headers=s["admin_headers"]).json())
    assert admin_ids == ["s-a", "s-b", "s-null"]


def test_foreign_and_legacy_sermons_404_for_users(client, scoped_setup):
    s = scoped_setup
    assert client.get("/api/sermons/s-b", headers=s["a"]["headers"]).status_code == 404
    assert client.get("/api/sermons/s-null", headers=s["a"]["headers"]).status_code == 404
    assert client.get("/api/sermons/s-null", headers=s["b"]["headers"]).status_code == 404
    assert client.get("/api/sermons/s-a", headers=s["a"]["headers"]).status_code == 200
    assert client.get("/api/sermons/s-null", headers=s["admin_headers"]).status_code == 200
    assert client.get("/api/sermons/s-b/plan", headers=s["a"]["headers"]).status_code == 404
    assert client.get("/api/sermons/s-a/plan", headers=s["a"]["headers"]).status_code == 200


def test_user_sees_only_owned_jobs(client, scoped_setup):
    s = scoped_setup
    assert _ids(client.get("/api/jobs", headers=s["a"]["headers"]).json()) == ["j-a"]
    assert _ids(client.get("/api/jobs", headers=s["b"]["headers"]).json()) == ["j-b"]
    admin_ids = _ids(client.get("/api/jobs", headers=s["admin_headers"]).json())
    assert admin_ids == ["j-a", "j-b", "j-null"]
    assert client.get("/api/jobs/j-b", headers=s["a"]["headers"]).status_code == 404
    assert client.get("/api/jobs/j-null", headers=s["a"]["headers"]).status_code == 404
    assert client.get("/api/jobs/j-a", headers=s["a"]["headers"]).status_code == 200


def test_search_and_sort_respect_scope(client, scoped_setup):
    s = scoped_setup
    body = client.get("/api/sermons", params={"search": "Owned"}, headers=s["a"]["headers"]).json()
    assert _ids(body) == ["s-a"]
    body = client.get("/api/sermons", params={"sort": "title"}, headers=s["admin_headers"]).json()
    assert body["total"] == 3


def test_attribution_stamps_user_id_on_save(client, scoped_setup):
    s = scoped_setup
    from server.api.accounts import get_db_path
    from ui.database import SermonDatabase, SermonRepository

    repo = SermonRepository(SermonDatabase(db_path=get_db_path()))
    assert repo.save_sermon({
        "id": "s-new", "title": "New", "speaker": "S", "recorded_date": "2026-09-04",
        "status": "draft", "user_id": s["a"]["id"],
    }) is True
    assert client.get("/api/sermons/s-new", headers=s["a"]["headers"]).status_code == 200
    assert client.get("/api/sermons/s-new", headers=s["b"]["headers"]).status_code == 404


def test_stamp_helper_fills_null_never_clobbers(client, scoped_setup, monkeypatch):
    s = scoped_setup
    from server.api.accounts import get_db_path
    from ui.job_executors import _job_user_id, _stamp_sermon_owner
    from ui.job_queue import Job, JobStatus, JobType

    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO sermons (id, title, status) VALUES (?, ?, ?)", ("s-stamp", "T", "draft")
    )
    conn.commit()
    conn.close()
    job = Job(id="x", type=JobType.SERMON_PROCESSING, title="t", description="d",
              status=JobStatus.COMPLETED, progress=100.0, created_at=datetime.datetime.now(),
              parameters={"user_id": s["a"]["id"]})
    assert _job_user_id(job) == s["a"]["id"]
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    _stamp_sermon_owner("s-stamp", _job_user_id(job))
    conn = sqlite3.connect(get_db_path())
    owner = conn.execute("SELECT user_id FROM sermons WHERE id = ?", ("s-stamp",)).fetchone()[0]
    conn.close()
    assert owner == s["a"]["id"]
    _stamp_sermon_owner("s-stamp", s["b"]["id"])
    conn = sqlite3.connect(get_db_path())
    owner = conn.execute("SELECT user_id FROM sermons WHERE id = ?", ("s-stamp",)).fetchone()[0]
    conn.close()
    assert owner == s["a"]["id"]


def test_add_job_records_user_id(client, scoped_setup, tmp_path, monkeypatch):
    import ui.database as dbmod
    from ui.job_queue import JobQueue, JobType

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    queue = JobQueue(max_workers=1)
    job_id = queue.add_job(JobType.VALIDATION, "t", "d", parameters={}, user_id="u-xyz")
    conn = sqlite3.connect(str(db_path))
    owner = conn.execute(
        "SELECT user_id FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()[0]
    conn.close()
    assert owner == "u-xyz"
    job = queue.get_job(job_id)
    assert job is not None and job.user_id == "u-xyz"


def test_backfill_reassigns_null_to_admin(client, scoped_setup):
    s = scoped_setup
    from server.api import backfill

    counts = backfill.backfill()
    assert counts["sermons"] >= 1 and counts["background_jobs"] >= 1
    assert client.get("/api/sermons/s-null", headers=s["a"]["headers"]).status_code == 404
    assert client.get("/api/sermons/s-null", headers=s["admin_headers"]).status_code == 200
    assert client.get("/api/jobs/j-null", headers=s["a"]["headers"]).status_code == 404
    assert client.get("/api/jobs/j-null", headers=s["admin_headers"]).status_code == 200
    assert backfill.backfill() == {"sermons": 0, "background_jobs": 0}
