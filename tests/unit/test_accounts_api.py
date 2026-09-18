from __future__ import annotations

import datetime
import sqlite3
import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))



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


def test_connections_crud_roundtrip_and_isolation(client, scoped_setup):
    s = scoped_setup
    body = {"name": "Conn", "provider": "Ollama", "apiKey": "sk-secret-99aa"}
    r = client.post("/api/me/connections/llm", json=body, headers=s["a"]["headers"])
    assert r.status_code == 201
    saved = r.json()
    assert saved["has_key"] is True
    assert "99aa" in saved["masked_key"]
    assert "sk-secret-99aa" not in r.text
    conn_id = saved["id"]

    listed = client.get("/api/me/connections/llm", headers=s["a"]["headers"]).json()["items"]
    assert [c["id"] for c in listed] == [conn_id]
    assert "sk-secret-99aa" not in client.get(
        "/api/me/connections/llm", headers=s["a"]["headers"]
    ).text

    r = client.put(
        f"/api/me/connections/llm/{conn_id}",
        json={"name": "Conn2", "apiKey": "sk-rotated-77bb"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200
    assert r.json()["masked_key"].endswith("77bb")
    assert "sk-rotated-77bb" not in r.text

    r = client.post("/api/me/connections/llm", json=body, headers=s["b"]["headers"])
    assert r.status_code == 201
    assert client.get("/api/me/connections/llm", headers=s["b"]["headers"]).json()["total"] == 1
    foreign = client.put(
        f"/api/me/connections/llm/{conn_id}", json={"name": "steal"}, headers=s["b"]["headers"]
    )
    assert foreign.status_code == 404
    assert client.delete(f"/api/me/connections/llm/{conn_id}",
        headers=s["b"]["headers"]).status_code == 404
    assert client.get("/api/me/connections/llm", headers=s["a"]["headers"]).json()["total"] == 1

    assert client.delete(f"/api/me/connections/llm/{conn_id}",
        headers=s["a"]["headers"]).status_code == 204
    assert client.get("/api/me/connections/llm", headers=s["a"]["headers"]).json()["total"] == 0


def test_sa_connections_and_role_gating(client, scoped_setup):
    s = scoped_setup
    no_auth = client.post("/api/me/connections/llm", json={"name": "x"})
    assert no_auth.status_code == 401
    r = client.post(
        "/api/me/connections/sermonaudio",
        json={"name": "SA", "broadcasterId": "b-1", "apiKey": "sa-key-1234"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201
    assert r.json()["masked_key"].endswith("1234")
    default = client.put("/api/me/connections/sermonaudio/default", json={"id": r.json()["id"]},
        headers=s["a"]["headers"])
    assert default.status_code == 200
    assert client.get("/api/me/connections/sermonaudio",
        headers=s["a"]["headers"]).json()["default_id"] == r.json()["id"]
    assert client.get("/api/me/connections/sermonaudio",
        headers=s["b"]["headers"]).json()["default_id"] is None
    admin_forbidden = client.post(
        "/api/me/connections/llm",
        json={"name": "x"},
        headers=s["admin_headers"],
    )
    assert admin_forbidden.status_code == 201


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
