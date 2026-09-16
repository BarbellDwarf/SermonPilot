from __future__ import annotations

import datetime
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from server.api.app import create_app
from ui.database import SermonDatabase, SermonRepository

BACKGROUND_JOBS_DDL = """
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
        priority INTEGER DEFAULT 5
    )
"""


@pytest.fixture
def fixture_db(tmp_path, monkeypatch) -> str:
    db_path = str(tmp_path / "fixture.db")
    monkeypatch.setenv("SERMONPILOT_DB", db_path)
    db = SermonDatabase(db_path=db_path)
    repo = SermonRepository(db)
    repo.save_sermon(
        {
            "id": "s-01",
            "title": "Sample Teaching 2",
            "speaker": "Speaker A",
            "recorded_date": "2026-09-05",
            "series_title": "Sample Series A",
            "duration": 2530.0,
            "status": "processed",
            "content": {"transcript_text": "amen " * 200, "description": "A sample"},
        }
    )
    repo.save_sermon(
        {
            "id": "s-02",
            "title": "Sample Teaching 1",
            "speaker": "Speaker B",
            "recorded_date": "2026-09-06",
            "series_title": "Sample Series A",
            "duration": 2324.0,
            "status": "draft",
        }
    )
    repo.save_edit_plan_revision(
        "s-01",
        {
            "proposed_start": 8.5,
            "proposed_end": 2512.3,
            "audio_offset": 0.4,
            "confidence": 0.87,
            "evidence": "Silence gate at both ends.",
            "qa_judgment": "Pass",
            "status": "pending_review",
        },
    )
    conn = sqlite3.connect(db_path)
    conn.execute(BACKGROUND_JOBS_DDL)
    conn.execute(
        "INSERT INTO background_jobs (id, type, title, description, status, progress,"
        " parameters, result, logs, created_at, started_at, completed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "job-1039",
            "full_pipeline",
            "Full pipeline",
            "Sample Teaching 1",
            "completed",
            100.0,
            json.dumps({"sermon_id": "s-01"}),
            json.dumps({"success": True, "message": "upload done"}),
            json.dumps(["16:02 job accepted", "16:41 upload done"]),
            "2026-09-06T16:02:00",
            "2026-09-06T16:02:00",
            "2026-09-06T16:41:00",
        ),
    )
    conn.execute(
        "INSERT INTO background_jobs (id, type, title, description, status, progress,"
        " parameters, result, logs, created_at, started_at, completed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "job-1037",
            "full_pipeline",
            "Full pipeline",
            "Sample Teaching 2",
            "failed",
            60.0,
            json.dumps({"sermon_id": "s-02"}),
            json.dumps({"success": False, "error": "upload rejected: gateway timeout"}),
            json.dumps(["15:03 job accepted", "15:19 upload rejected"]),
            "2026-09-06T15:03:00",
            "2026-09-06T15:03:00",
            "2026-09-06T15:19:00",
        ),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(fixture_db) -> TestClient:
    return TestClient(create_app())


def test_read_only_get_routes(client: TestClient) -> None:
    allowed = {"GET", "HEAD", "OPTIONS"}
    for route in client.app.routes:
        methods = getattr(route, "methods", None) or set()
        assert set(methods) <= allowed, f"{route.path} allows {methods}"


def test_health_shape(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert isinstance(body["version"], str) and body["version"]
    assert body["db_path_ok"] is True


def test_health_db_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SERMONPILOT_DB", str(tmp_path / "absent.db"))
    body = TestClient(create_app()).get("/api/health").json()
    assert body["ok"] is True
    assert body["db_path_ok"] is False


def test_sermons_list_shape_and_default_sort(client: TestClient) -> None:
    body = client.get("/api/sermons").json()
    assert body["total"] == 2
    first, second = body["items"]
    assert first["id"] == "s-02"
    assert set(first) == {"id", "title", "speaker", "date", "duration", "series", "status"}
    assert "transcript" not in json.dumps(body).lower()
    assert first["duration"] == "38:44"
    assert second["duration"] == "42:10"


def test_sermons_search_param(client: TestClient) -> None:
    body = client.get("/api/sermons", params={"search": "Teaching 1"}).json()
    assert [item["id"] for item in body["items"]] == ["s-02"]
    body = client.get("/api/sermons", params={"search": "speaker a"}).json()
    assert [item["id"] for item in body["items"]] == ["s-01"]


def test_sermons_sort_params(client: TestClient) -> None:
    by_title = client.get("/api/sermons", params={"sort": "title"}).json()
    assert [item["id"] for item in by_title["items"]] == ["s-02", "s-01"]
    by_duration = client.get("/api/sermons", params={"sort": "duration"}).json()
    assert [item["id"] for item in by_duration["items"]] == ["s-01", "s-02"]


def test_sermon_detail_flags(client: TestClient) -> None:
    body = client.get("/api/sermons/s-01").json()
    assert body["series"] == "Sample Series A"
    assert body["status"] == "processed"
    assert body["files"] == []
    assert body["transcript_available"] is True
    assert body["transcript_length"] == len("amen " * 200)
    assert "transcript_text" not in body
    plain = client.get("/api/sermons/s-02").json()
    assert plain["transcript_available"] is False
    assert plain["transcript_length"] == 0


def test_sermon_detail_404(client: TestClient) -> None:
    assert client.get("/api/sermons/nope").status_code == 404


def test_sermon_plan_shape(client: TestClient) -> None:
    body = client.get("/api/sermons/s-01/plan").json()
    plan = body["plan"]
    assert plan["status"] == "pending_review"
    assert plan["revision"] == 1
    assert plan["confidence"] == 87.0
    assert plan["qa_judgment"] == "Pass"
    assert plan["start_sec"] == 8.5
    assert plan["end_sec"] == 2512.3
    assert plan["offset_sec"] == 0.4
    assert plan["evidence"] == "Silence gate at both ends."
    assert len(body["history"]) == 1
    empty = client.get("/api/sermons/s-02/plan").json()
    assert empty["plan"] is None
    assert empty["history"] == []


def test_jobs_list_shape(client: TestClient) -> None:
    body = client.get("/api/jobs").json()
    assert body["total"] == 2
    assert body["items"][0]["id"] == "job-1039"
    failed = next(item for item in body["items"] if item["id"] == "job-1037")
    assert failed["duration"] == "16m"
    assert failed["error"] == "upload rejected: gateway timeout"
    assert "logs" not in failed


def test_jobs_status_and_limit_params(client: TestClient) -> None:
    body = client.get("/api/jobs", params={"status": "failed"}).json()
    assert [item["id"] for item in body["items"]] == ["job-1037"]
    body = client.get("/api/jobs", params={"limit": 1}).json()
    assert body["total"] == 1


def test_job_detail_logs(client: TestClient) -> None:
    body = client.get("/api/jobs/job-1039").json()
    assert body["logs"] == ["16:02 job accepted", "16:41 upload done"]
    assert body["parameters"] == {"sermon_id": "s-01"}
    assert body["duration"] == "39m"
    assert client.get("/api/jobs/nope").status_code == 404


def test_status_uses_manager_logic(client: TestClient, monkeypatch) -> None:
    from ui import system_status

    seen: dict = {}

    def fake_status(self):
        seen["called"] = True
        return {"database": {"status": "ok", "timestamp": datetime.datetime(2026, 9, 6, 12, 0, 0)}}

    monkeypatch.setattr(
        system_status.SystemStatusManager, "get_comprehensive_status", fake_status
    )
    body = client.get("/api/status").json()
    assert seen.get("called") is True
    assert body["status"]["database"]["status"] == "ok"
    assert body["status"]["database"]["timestamp"] == "2026-09-06T12:00:00"
    assert body["checked_at"]


def test_gets_do_not_mutate_db(client: TestClient, fixture_db: str) -> None:
    def counts() -> dict:
        conn = sqlite3.connect(f"file:{fixture_db}?mode=ro", uri=True)
        out = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("sermons", "sermon_content", "edit_plans", "background_jobs")
        }
        conn.close()
        return out

    before = counts()
    client.get("/api/health")
    client.get("/api/sermons")
    client.get("/api/sermons", params={"search": "Sample", "sort": "title"})
    client.get("/api/sermons/s-01")
    client.get("/api/sermons/s-01/plan")
    client.get("/api/jobs")
    client.get("/api/jobs/job-1039")
    assert counts() == before


def test_spa_fallback_serves_index(client: TestClient) -> None:
    for path in ("/", "/library", "/library/s-01", "/jobs"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"], path
