from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any

import pytest

from server.api.accounts import get_db_path

_JOB_COLUMNS = (
    "id, type, title, description, status, progress, parameters, result, logs,"
    " created_at, started_at, completed_at, can_cancel, can_retry, priority, user_id"
)


def _insert_job(
    job_id: str,
    user_id: str | None,
    status: str = "failed",
    *,
    created_at: str | None = None,
) -> None:
    created_at = created_at or datetime.now().isoformat()
    started_at = created_at if status != "queued" else None
    completed_at = created_at if status in {"completed", "failed", "cancelled"} else None
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        f"INSERT INTO background_jobs ({_JOB_COLUMNS})"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_id,
            "validation",
            f"Job {job_id}",
            f"Description {job_id}",
            status,
            65.0,
            json.dumps({"sermon_id": "s-a", "nested": {"keep": True}}),
            json.dumps({"success": False, "message": "failed", "error": "boom"}),
            json.dumps([f"original log {job_id}"]),
            created_at,
            started_at,
            completed_at,
            True,
            True,
            7,
            user_id,
        ),
    )
    conn.commit()
    conn.close()


def _job_row(job_id: str) -> dict[str, Any]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f"SELECT {_JOB_COLUMNS} FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    return dict(row)


def _job_count() -> int:
    conn = sqlite3.connect(get_db_path())
    count = conn.execute("SELECT COUNT(*) FROM background_jobs").fetchone()[0]
    conn.close()
    return count


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_retry_clones_terminal_job_and_preserves_original(client, scoped_setup, status):
    original_id = "job-retry"
    _insert_job(original_id, scoped_setup["a"]["id"], status)
    before = _job_row(original_id)

    response = client.post(f"/api/jobs/{original_id}/retry", headers=scoped_setup["a"]["headers"])

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    clone_id = body["job_id"]
    assert clone_id != original_id
    assert _job_row(original_id) == before

    clone = _job_row(clone_id)
    for field in ("type", "title", "description", "parameters", "priority", "user_id"):
        assert clone[field] == before[field]
    assert clone["status"] == "queued"
    assert clone["progress"] == 0.0
    assert clone["started_at"] is None
    assert clone["completed_at"] is None
    assert clone["result"] is None
    logs = json.loads(clone["logs"])
    assert any(original_id in line for line in logs)
    assert logs != json.loads(before["logs"])


def test_retry_ownership_matches_job_visibility(client, scoped_setup):
    original_id = "job-owned"
    _insert_job(original_id, scoped_setup["a"]["id"])

    foreign = client.post(f"/api/jobs/{original_id}/retry", headers=scoped_setup["b"]["headers"])
    assert foreign.status_code == 404
    assert _job_count() == 4

    admin = client.post(f"/api/jobs/{original_id}/retry", headers=scoped_setup["admin_headers"])
    assert admin.status_code == 202, admin.text
    assert _job_row(admin.json()["job_id"])["user_id"] == scoped_setup["a"]["id"]
    assert _job_row(original_id)["status"] == "failed"


def test_retry_missing_job_returns_404(client, scoped_setup):
    assert client.post("/api/jobs/missing/retry").status_code == 401
    response = client.post("/api/jobs/missing/retry", headers=scoped_setup["a"]["headers"])
    assert response.status_code == 404
    assert _job_count() == 3


@pytest.mark.parametrize("status", ["queued", "running", "completed"])
def test_retry_rejects_jobs_that_are_not_failed_or_cancelled(client, scoped_setup, status):
    job_id = f"job-{status}"
    _insert_job(job_id, scoped_setup["a"]["id"], status)

    response = client.post(f"/api/jobs/{job_id}/retry", headers=scoped_setup["a"]["headers"])

    assert response.status_code == 409
    assert _job_row(job_id)["status"] == status
    assert _job_count() == 4


def test_retried_job_is_executable(client, scoped_setup, monkeypatch):
    import ui.job_queue as job_queue
    from ui.job_queue import JobQueue, JobResult

    original_id = "job-executable"
    _insert_job(original_id, scoped_setup["a"]["id"], "queued")
    submit = JobQueue(run_workers=False, worker_id="retry-submit")
    submit.start()
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE background_jobs SET status = 'failed', completed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), original_id),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(job_queue, "_submit_queue", submit)

    executed = threading.Event()
    executed_ids: list[str] = []

    def executor(job) -> JobResult:
        executed_ids.append(job.id)
        executed.set()
        return JobResult(success=True, message="done")

    monkeypatch.setattr(JobQueue, "_resources_available", lambda self: True)
    worker = JobQueue(max_workers=1, worker_id="retry-test-worker")
    monkeypatch.setattr(worker, "_get_job_executor", lambda job_type: executor)
    try:
        response = client.post(
            f"/api/jobs/{original_id}/retry", headers=scoped_setup["a"]["headers"]
        )
        assert response.status_code == 202, response.text
        clone_id = response.json()["job_id"]
        assert _job_row(clone_id)["status"] == "queued"

        worker.start()
        assert executed.wait(timeout=5.0), "the retried job was never claimed"
        deadline = time.monotonic() + 5.0
        while _job_row(clone_id)["status"] != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _job_row(clone_id)["status"] == "completed"
    finally:
        worker.stop()
        submit.stop()

    assert executed_ids == [clone_id]
    assert _job_row(original_id)["status"] == "failed"


def test_jobs_offset_and_total_are_scoped_and_stable(client, scoped_setup):
    conn = sqlite3.connect(get_db_path())
    conn.execute("DELETE FROM background_jobs")
    conn.commit()
    conn.close()
    listed_at = datetime.now().isoformat()
    for index in range(5):
        _insert_job(
            f"a-{index}",
            scoped_setup["a"]["id"],
            "failed" if index % 2 == 0 else "completed",
            created_at=listed_at,
        )
    for index in range(3):
        _insert_job(f"b-{index}", scoped_setup["b"]["id"], "failed", created_at=listed_at)

    headers = scoped_setup["a"]["headers"]
    pages = []
    for offset in (0, 2, 4):
        response = client.get("/api/jobs", params={"limit": 2, "offset": offset}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 5
        pages.append([item["id"] for item in body["items"]])
    assert pages == [["a-4", "a-3"], ["a-2", "a-1"], ["a-0"]]

    beyond = client.get("/api/jobs", params={"limit": 2, "offset": 5}, headers=headers)
    assert beyond.json() == {"items": [], "total": 5}

    filtered = client.get(
        "/api/jobs",
        params={"status": "failed", "limit": 1, "offset": 1},
        headers=headers,
    ).json()
    assert filtered["total"] == 3
    assert [item["id"] for item in filtered["items"]] == ["a-2"]

    other = client.get("/api/jobs", headers=scoped_setup["b"]["headers"]).json()
    assert other["total"] == 3
    assert [item["id"] for item in other["items"]] == ["b-2", "b-1", "b-0"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}])
def test_jobs_paging_validation(client, scoped_setup, params):
    response = client.get("/api/jobs", params=params, headers=scoped_setup["a"]["headers"])
    assert response.status_code == 422
