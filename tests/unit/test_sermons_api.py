from __future__ import annotations

import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from server.api.app import create_app
from server.api.routers.sermons import _lifecycle_state
from ui.database import SermonDatabase, SermonRepository

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"

try:  # noqa: E402 - package path (same module identity as ui.job_executors)
    from ui.job_queue import Job, JobStatus, JobType
except ImportError:  # top-level import entrypoint
    from job_queue import Job, JobStatus, JobType  # type: ignore[no-redef]

from ui.job_executors import execute_auto_edit_job  # noqa: E402

LIFECYCLE_KEYS = {
    "draft",
    "review",
    "processing",
    "ready",
    "published",
    "failed",
}


@pytest.fixture
def fixture_db(tmp_path, monkeypatch) -> str:
    db_path = str(tmp_path / "sermons-api.db")
    monkeypatch.setenv("SERMONPILOT_DB", db_path)
    repo = SermonRepository(SermonDatabase(db_path=db_path))
    rows: list[dict[str, Any]] = [
        {"id": "s-error", "title": "Error", "status": "error"},
        {
            "id": "s-upload-failed",
            "title": "Upload failed",
            "status": "draft",
            "upload_info": {"upload_status": "failed"},
        },
        {
            "id": "s-applied",
            "title": "Applied",
            "status": "draft",
            "edit_status": "applied",
        },
        {
            "id": "s-rendered",
            "title": "Rendered",
            "status": "draft",
            "edit_status": "rendered",
        },
        {"id": "s-review", "title": "Review", "status": "draft"},
        {
            "id": "s-published",
            "title": "Published",
            "status": "processed",
            "upload_info": {"upload_status": "success"},
        },
        {"id": "s-draft", "title": "Draft", "status": "draft"},
        {"id": "s-unknown", "title": "Unknown", "status": "mystery"},
        {"id": "s-latest-approved", "title": "Latest approved", "status": "draft"},
    ]
    for index, row in enumerate(rows):
        row.setdefault("speaker", "Speaker A")
        row.setdefault("recorded_date", f"2026-09-{index + 1:02d}")
        assert repo.save_sermon(row) is True
    repo.save_edit_plan_revision("s-review", {"status": "approved", "confidence": 0.4})
    repo.save_edit_plan_revision("s-review", {"status": "pending_review", "confidence": 0.8})
    repo.save_edit_plan_revision(
        "s-latest-approved", {"status": "pending_review", "confidence": 0.5}
    )
    repo.save_edit_plan_revision("s-latest-approved", {"status": "approved", "confidence": 0.9})
    return db_path


@pytest.fixture
def auth_token(fixture_db, monkeypatch) -> str:
    monkeypatch.setenv("SERMONPILOT_ADMIN_USER", "fixture-admin")
    monkeypatch.setenv("SERMONPILOT_ADMIN_PASSWORD", secrets.token_urlsafe(24))
    with TestClient(create_app()) as client:
        assert client.post("/api/auth/bootstrap").status_code == 201
        response = client.post(
            "/api/auth/login",
            json={
                "username": "fixture-admin",
                "password": os.environ["SERMONPILOT_ADMIN_PASSWORD"],
            },
        )
        assert response.status_code == 200
        return response.json()["token"]


@pytest.fixture
def client(fixture_db, auth_token) -> TestClient:
    return TestClient(create_app(), headers={"Authorization": f"Bearer {auth_token}"})


def test_list_items_expose_lifecycle_fields(client: TestClient) -> None:
    body = client.get("/api/sermons").json()
    items = {item["id"]: item for item in body["items"]}

    assert items["s-rendered"]["edit_status"] == "rendered"
    assert items["s-rendered"]["upload_status"] is None
    assert items["s-rendered"]["plan_status"] is None
    assert items["s-published"]["upload_status"] == "success"
    assert items["s-review"]["edit_status"] is None
    assert items["s-review"]["plan_status"] == "pending_review"
    assert set(items["s-draft"]) == {
        "id",
        "title",
        "speaker",
        "date",
        "duration",
        "series",
        "status",
        "edit_status",
        "upload_status",
        "plan_status",
    }


def test_detail_exposes_lifecycle_fields(client: TestClient) -> None:
    detail = client.get("/api/sermons/s-rendered").json()
    assert detail["edit_status"] == "rendered"
    assert detail["plan_status"] is None
    assert detail["upload_status"] is None

    published = client.get("/api/sermons/s-published").json()
    assert published["upload_status"] == "success"

    review = client.get("/api/sermons/s-review").json()
    assert review["edit_status"] is None
    assert review["plan_status"] == "pending_review"


def test_plan_status_comes_from_latest_revision(client: TestClient) -> None:
    body = client.get("/api/sermons").json()
    items = {item["id"]: item for item in body["items"]}
    assert items["s-review"]["plan_status"] == "pending_review"
    assert items["s-latest-approved"]["plan_status"] == "approved"


def test_counts_cover_every_lifecycle_state(client: TestClient) -> None:
    body = client.get("/api/sermons").json()
    assert body["total"] == 9
    assert set(body["counts"]) == LIFECYCLE_KEYS
    assert body["counts"] == {
        "draft": 3,
        "review": 1,
        "processing": 1,
        "ready": 1,
        "published": 1,
        "failed": 2,
    }
    assert sum(body["counts"].values()) == body["total"]


def test_counts_ignores_limit_and_offset(client: TestClient) -> None:
    body = client.get("/api/sermons", params={"limit": 1, "offset": 2}).json()
    assert len(body["items"]) == 1
    assert body["total"] == 9
    assert sum(body["counts"].values()) == 9


def test_counts_follow_search_scope(client: TestClient) -> None:
    body = client.get("/api/sermons", params={"search": "Review"}).json()
    assert body["total"] == 1
    assert body["counts"]["review"] == 1
    assert body["counts"]["draft"] == 0


def test_search_matches_every_token_in_any_order(client: TestClient) -> None:
    body = client.get("/api/sermons", params={"search": "review speaker"}).json()
    assert [item["id"] for item in body["items"]] == ["s-review"]


def test_search_requires_every_token_to_match(client: TestClient) -> None:
    body = client.get("/api/sermons", params={"search": "review missing"}).json()
    assert body["total"] == 0


def test_unknown_status_falls_back_to_draft() -> None:
    assert _lifecycle_state({"status": "mystery"}) == "draft"
    assert _lifecycle_state({"status": "mystery", "edit_status": "rendered"}) == "ready"
    assert _lifecycle_state({"status": "mystery", "upload_status": "failed"}) == "failed"


def test_park_point_writes_pending_review(monkeypatch) -> None:
    repo = Mock()
    repo.update_sermon_edit_status.return_value = True
    import ui.database as database

    monkeypatch.setattr(database, "SermonRepository", lambda: repo)
    monkeypatch.setattr(
        "sermon_updater.process_new_sermon",
        Mock(
            return_value={
                "success": True,
                "sermon_id": "draft_123",
                "edit_plan_status": "pending_review",
                "auto_edit_applied": False,
            }
        ),
    )
    job = Job(
        id="job-1",
        type=JobType.AUTO_EDIT,
        title="Auto edit",
        description="Auto edit job",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters={
            "audio_file": str(_UI_DIR / "job_executors.py"),
            "form_data": {
                "speaker_name": "Test Speaker",
                "recorded_date": "2024-01-01",
                "dry_run": True,
                "skip_audio": True,
            },
            "config": {"auto_edit": {}, "api_key": "k"},
            "auto_edit_mode": "interactive",
            "auto_edit_enabled": True,
        },
    )
    result = execute_auto_edit_job(job)

    assert result.success is True
    assert "awaiting manual review" in result.message
    repo.update_sermon_edit_status.assert_called_once_with("draft_123", "pending_review")
