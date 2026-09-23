"""Startup reconciliation: a restart cannot strand a job at ``running``.

A worker thread is a daemon and dies with its process, but the job row it owned
stays in the store. Reconciliation marks those rows terminal at startup, so the
operator sees an honest outcome and the sermon's queue is usable again without
touching the database by hand.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

import ui.database as database_module
from ui.database import SermonDatabase, SermonRepository
from ui.job_queue import (
    INTERRUPTED_BY_RESTART_MARKER,
    Job,
    JobQueue,
    JobStatus,
    JobType,
    _ensure_job_columns,
    reconcile_interrupted_jobs,
)

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
        priority INTEGER DEFAULT 5
    )
"""


@pytest.fixture(autouse=True)
def _skip_resource_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(JobQueue, "_resources_available", lambda self: True)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "jobs.db"


@pytest.fixture
def queue(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobQueue:
    db = SermonDatabase(db_path=str(db_path))
    monkeypatch.setattr(database_module, "_db", db)
    return JobQueue()


def _create_jobs_table(db_path: Path | str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(JOBS_DDL)
        conn.commit()
    finally:
        conn.close()


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _read_row(db_path: Path | str, job_id: str) -> sqlite3.Row | None:
    conn = _connect(db_path)
    try:
        return conn.execute(
            "SELECT * FROM background_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()


def _insert_job(
    db_path: Path | str,
    job_id: str,
    *,
    status: str = "running",
    logs: list[str] | None = None,
    cancelled: int = 0,
    job_type: str = "auto_edit_apply",
    parameters: dict | None = None,
) -> None:
    conn = _connect(db_path)
    try:
        _ensure_job_columns(conn)
        conn.execute(
            "INSERT INTO background_jobs (id, type, title, description, status,"
            " progress, parameters, logs, cancelled)"
            " VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (
                job_id,
                job_type,
                "Interrupted apply",
                "Apply edit for s-1",
                status,
                json.dumps(parameters if parameters is not None else {"sermon_id": "s-1"}),
                json.dumps(logs or []),
                cancelled,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_start_reconciles_running_job_and_appends_log(
    queue: JobQueue, db_path: Path
) -> None:
    existing_logs = ["[10:00:00] Job started", "[10:01:00] Enhancing audio"]
    _insert_job(db_path, "j-run", status="running", logs=existing_logs)

    queue.start()
    try:
        job = queue.get_job("j-run")
        assert job is not None
        assert job.status is JobStatus.FAILED
        assert job.completed_at is not None
        assert job.result is not None and job.result.success is False
        assert INTERRUPTED_BY_RESTART_MARKER in (job.result.message or "").lower()
        assert INTERRUPTED_BY_RESTART_MARKER in (job.result.error or "").lower()
        # No artifact is registered on the interrupted record.
        assert job.result.data is None
        # Existing logs survive and the interruption line is appended last.
        assert job.logs[:2] == existing_logs
        assert len(job.logs) == 3
        assert "Job interrupted by app restart" in job.logs[-1]
    finally:
        queue.stop()

    row = _read_row(db_path, "j-run")
    assert row is not None
    assert row["status"] == "failed"
    assert row["completed_at"] is not None
    stored_logs = json.loads(row["logs"])
    assert stored_logs[:2] == existing_logs
    assert "Job interrupted by app restart" in stored_logs[-1]
    stored_result = json.loads(row["result"])
    assert stored_result["success"] is False
    assert INTERRUPTED_BY_RESTART_MARKER in json.dumps(stored_result).lower()


def test_running_job_with_cancel_flag_reconciles_to_cancelled(
    queue: JobQueue, db_path: Path
) -> None:
    _insert_job(db_path, "j-cancel", status="running", cancelled=1)

    queue.start()
    try:
        job = queue.get_job("j-cancel")
        assert job is not None
        assert job.status is JobStatus.CANCELLED
        assert job.cancelled is True
        assert job.result is not None and job.result.success is False
    finally:
        queue.stop()

    row = _read_row(db_path, "j-cancel")
    assert row is not None and row["status"] == "cancelled"


def test_terminal_jobs_untouched_and_reconciliation_is_idempotent(db_path: Path) -> None:
    _create_jobs_table(db_path)

    _insert_job(db_path, "j-run", status="running", logs=["[10:00:00] Job started"])
    _insert_job(db_path, "j-done", status="completed", logs=["[09:00:00] done"])
    _insert_job(db_path, "j-paused", status="paused", logs=["[10:02:00] paused"])

    first = reconcile_interrupted_jobs(db_path=str(db_path))
    assert first == 2

    failed_row = _read_row(db_path, "j-run")
    assert failed_row is not None and failed_row["status"] == "failed"
    paused_row = _read_row(db_path, "j-paused")
    assert paused_row is not None and paused_row["status"] == "failed"
    done_row = _read_row(db_path, "j-done")
    assert done_row is not None and done_row["status"] == "completed"

    first_logs = json.loads(failed_row["logs"])
    first_result = json.loads(failed_row["result"])

    # A second run finds nothing in flight and changes nothing.
    second = reconcile_interrupted_jobs(db_path=str(db_path))
    assert second == 0

    failed_again = _read_row(db_path, "j-run")
    assert failed_again is not None
    assert failed_again["status"] == "failed"
    assert json.loads(failed_again["logs"]) == first_logs
    assert json.loads(failed_again["result"]) == first_result
    assert _read_row(db_path, "j-done")["status"] == "completed"
    assert _read_row(db_path, "j-paused")["status"] == "failed"


def test_cancel_flag_round_trips_through_the_store(
    queue: JobQueue, db_path: Path
) -> None:
    job = Job(
        id="j-flag",
        type=JobType.VALIDATION,
        title="t",
        description="d",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        cancelled=True,
    )
    queue._save_job_to_db(job)

    row = _read_row(db_path, "j-flag")
    assert row is not None and row["cancelled"] == 1
    loaded = queue._job_from_row(row)
    assert loaded is not None and loaded.cancelled is True


def test_library_guard_accepts_new_job_immediately_after_reconciliation(
    queue: JobQueue, db_path: Path
) -> None:
    repo = SermonRepository(SermonDatabase(db_path=str(db_path)))
    _insert_job(db_path, "j-apply", status="running")
    assert repo.get_active_apply_job("s-1") is not None

    reconcile_interrupted_jobs(db_path=str(db_path))

    assert repo.get_active_apply_job("s-1") is None


def test_api_guard_ignores_reconciled_job_immediately(
    queue: JobQueue, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERMONPILOT_DB", str(db_path))
    from server.api.routers.writes import _active_job_for

    _insert_job(db_path, "j-apply", status="running")
    assert _active_job_for("s-1") is not None

    reconcile_interrupted_jobs(db_path=str(db_path))

    # A restart-reconciled job must not count as a fresh completion in the
    # double-click grace window, or the operator stays blocked for seconds.
    assert _active_job_for("s-1") is None


def test_reconciliation_skips_a_missing_store(tmp_path: Path) -> None:
    missing = tmp_path / "absent.db"
    assert reconcile_interrupted_jobs(db_path=str(missing)) == 0
    assert not missing.exists()


def test_api_startup_reconciles_running_job(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERMONPILOT_DB", str(db_path))
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    _create_jobs_table(db_path)
    _insert_job(db_path, "j-boot", status="running", logs=["[10:00:00] Job started"])

    from fastapi.testclient import TestClient

    from server.api.app import create_app

    with TestClient(create_app()):
        pass

    row = _read_row(db_path, "j-boot")
    assert row is not None
    assert row["status"] == "failed"
    stored_logs = json.loads(row["logs"])
    assert stored_logs[0] == "[10:00:00] Job started"
    assert "Job interrupted by app restart" in stored_logs[-1]
