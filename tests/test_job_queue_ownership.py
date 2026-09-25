"""One worker owns the queue, and reconciliation respects that ownership.

Two processes over the same database must not both run jobs, and startup
reconciliation must not terminalise a job a live worker still owns.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import ui.database as database_module
from ui.database import SermonDatabase
from ui.job_queue import (
    _JOB_LEASE_TABLE,
    Job,
    JobCancelledError,
    JobQueue,
    JobResult,
    JobStatus,
    JobType,
    _ensure_job_columns,
    _ensure_lease_table,
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

TERMINAL = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


@pytest.fixture(autouse=True)
def _skip_resource_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(JobQueue, "_resources_available", lambda self: True)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "jobs.db"


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema(db_path: Path | str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(JOBS_DDL)
        _ensure_job_columns(conn)
        _ensure_lease_table(conn)
        conn.commit()
    finally:
        conn.close()


def _insert_job(
    db_path: Path | str, job_id: str, *, status: str = "running", owner: str | None = None
) -> None:
    conn = _connect(db_path)
    try:
        _ensure_job_columns(conn)
        conn.execute(
            "INSERT INTO background_jobs"
            " (id, type, title, description, status, progress, parameters, logs, owner_id)"
            " VALUES (?, 'auto_edit_apply', ?, ?, ?, 0, ?, '[]', ?)",
            (
                job_id,
                f"Job {job_id}",
                f"Apply edit for {job_id}",
                status,
                json.dumps({"sermon_id": job_id}),
                owner,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_lease(db_path: Path | str, worker_id: str, heartbeat: datetime) -> None:
    conn = _connect(db_path)
    try:
        _ensure_lease_table(conn)
        conn.execute(
            f"INSERT OR REPLACE INTO {_JOB_LEASE_TABLE}"
            " (id, worker_id, acquired_at, heartbeat_at) VALUES (1, ?, ?, ?)",
            (worker_id, heartbeat.isoformat(), heartbeat.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _read_status(db_path: Path | str, job_id: str) -> str:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT status FROM background_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row["status"] if row else ""
    finally:
        conn.close()


def _wait_for_terminal(queue: JobQueue, job_id: str, timeout: float = 10.0) -> JobStatus:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = queue.get_job(job_id)
        if job and job.status in TERMINAL:
            return job.status
        time.sleep(0.02)
    job = queue.get_job(job_id)
    raise AssertionError(f"job {job_id} did not finish, last status: {job.status if job else None}")


def _wait_for_db_status(db_path: Path | str, job_id: str, status: str,
                        timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _read_status(db_path, job_id) == status:
            return True
        time.sleep(0.02)
    return False


def test_reconciliation_leaves_a_live_job_alone_and_reaps_an_orphan(db_path: Path) -> None:
    _init_schema(db_path)
    _insert_job(db_path, "j-live", owner="live-worker")
    _insert_job(db_path, "j-dead", owner="dead-worker")
    _insert_job(db_path, "j-unowned", owner=None)
    _insert_lease(db_path, "live-worker", datetime.now())

    reconciled = reconcile_interrupted_jobs(db_path=str(db_path))

    assert reconciled == 2
    assert _read_status(db_path, "j-live") == "running"
    assert _read_status(db_path, "j-dead") == "failed"
    assert _read_status(db_path, "j-unowned") == "failed"


def test_reconciliation_never_reaps_an_unstarted_queued_job(db_path: Path) -> None:
    _init_schema(db_path)
    _insert_job(db_path, "j-queued", status="queued", owner=None)
    _insert_lease(db_path, "old-worker", datetime.now() - timedelta(minutes=10))

    reconciled = reconcile_interrupted_jobs(db_path=str(db_path))

    assert reconciled == 0
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT status, started_at, completed_at, result FROM background_jobs"
            " WHERE id = ?",
            ("j-queued",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["status"] == "queued"
    assert row["started_at"] is None
    assert row["completed_at"] is None
    assert row["result"] is None


def test_reconciliation_reaps_a_stale_lease_holder(db_path: Path) -> None:
    _init_schema(db_path)
    _insert_job(db_path, "j-stale", owner="stale-worker")
    _insert_lease(db_path, "stale-worker", datetime.now() - timedelta(minutes=10))

    reconciled = reconcile_interrupted_jobs(db_path=str(db_path))

    assert reconciled == 1
    assert _read_status(db_path, "j-stale") == "failed"


def test_reconciliation_leaves_a_running_job_with_a_fresh_lease(db_path: Path) -> None:
    _init_schema(db_path)
    _insert_job(db_path, "j-live", owner="live-worker")
    _insert_lease(db_path, "live-worker", datetime.now())

    reconciled = reconcile_interrupted_jobs(db_path=str(db_path))

    assert reconciled == 0
    assert _read_status(db_path, "j-live") == "running"


def test_a_fresh_lease_from_a_previous_boot_is_not_live(db_path: Path) -> None:
    _init_schema(db_path)
    _insert_job(db_path, "j-reboot", owner="old-worker")
    _insert_lease(db_path, "old-worker", datetime.now())
    conn = _connect(db_path)
    try:
        conn.execute(
            f"UPDATE {_JOB_LEASE_TABLE} SET boot_id = 'a-previous-boot' WHERE id = 1"
        )
        conn.commit()
    finally:
        conn.close()

    reconciled = reconcile_interrupted_jobs(db_path=str(db_path))

    assert reconciled == 1
    assert _read_status(db_path, "j-reboot") == "failed"


def test_submit_only_queue_runs_no_worker_and_takes_no_lease(db_path: Path) -> None:
    db = SermonDatabase(db_path=str(db_path))
    import ui.database as dm

    dm._db = db
    try:
        queue = JobQueue(run_workers=False)
        queue.start()
        try:
            workers = [
                thread.name
                for thread in threading.enumerate()
                if thread.name.startswith("JobWorker")
            ]
            assert workers == []
            conn = _connect(db_path)
            try:
                row = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {_JOB_LEASE_TABLE}"
                ).fetchone()
                assert row["n"] == 0
            finally:
                conn.close()
        finally:
            queue.stop()
    finally:
        dm._db = None


def test_owner_claims_a_job_enqueued_by_the_submit_queue(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = SermonDatabase(db_path=str(db_path))
    monkeypatch.setattr(database_module, "_db", db)

    submit = JobQueue(run_workers=False)
    submit.start()
    owner = JobQueue(worker_id="owner-1")
    order: list[str] = []

    def fake_executor(job) -> JobResult:
        order.append(job.title)
        return JobResult(success=True, message="done")

    monkeypatch.setattr(owner, "_get_job_executor", lambda job_type: fake_executor)
    try:
        job_id = submit.add_job(JobType.VALIDATION, "from-api", "enqueued by the API")
        owner.start()
        assert _wait_for_terminal(owner, job_id) is JobStatus.COMPLETED
        assert order == ["from-api"]
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT owner_id, status FROM background_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row["owner_id"] == "owner-1"
    finally:
        owner.stop()
        submit.stop()


def test_a_second_live_worker_does_not_start(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = SermonDatabase(db_path=str(db_path))
    monkeypatch.setattr(database_module, "_db", db)

    first = JobQueue(worker_id="owner-1")
    second = JobQueue(worker_id="owner-2")
    first.start()
    try:
        second.start()
        try:
            assert first._owns_lease is True
            assert second._owns_lease is False
            assert second._workers == []
        finally:
            second.stop()
    finally:
        first.stop()


def test_concurrent_lease_claims_have_one_owner(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = SermonDatabase(db_path=str(db_path))
    monkeypatch.setattr(database_module, "_db", db)

    first = JobQueue(worker_id="owner-1")
    second = JobQueue(worker_id="owner-2")
    barrier = threading.Barrier(2)
    results: dict[str, bool] = {}

    def claim(queue: JobQueue) -> None:
        barrier.wait(timeout=5.0)
        results[queue.worker_id] = queue._acquire_worker_lease()

    threads = [
        threading.Thread(target=claim, args=(queue,))
        for queue in (first, second)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results.values()) == [False, True]
    owner_id = next(worker_id for worker_id, acquired in results.items() if acquired)
    owner = first if owner_id == first.worker_id else second
    owner._owns_lease = True
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                f"SELECT worker_id FROM {_JOB_LEASE_TABLE} WHERE id = 1"
            ).fetchone()
        finally:
            conn.close()
        assert row["worker_id"] == owner.worker_id
    finally:
        owner._release_worker_lease()


def test_cancel_status_stays_terminal_until_retry(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = SermonDatabase(db_path=str(db_path))
    monkeypatch.setattr(database_module, "_db", db)
    queue = JobQueue(worker_id="owner-1")
    job = Job(
        id="j-cancel-status",
        type=JobType.VALIDATION,
        title="Cancel status",
        description="Cancel status",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
    )
    queue._jobs[job.id] = job
    queue._save_job_to_db(job)

    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE background_jobs SET status = 'cancelled', cancelled = 1 WHERE id = ?",
            (job.id,),
        )
        conn.commit()
    finally:
        conn.close()

    job.status = JobStatus.RUNNING
    job.cancelled = False
    job.completed_at = None
    queue._save_job_to_db(job)

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT status, cancelled FROM background_jobs WHERE id = ?", (job.id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == "cancelled"
    assert row["cancelled"] == 1

    assert queue.retry_job(job.id) is True
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT status, cancelled FROM background_jobs WHERE id = ?", (job.id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == "queued"
    assert row["cancelled"] == 0


def test_cancel_through_another_process_stops_the_running_worker(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = SermonDatabase(db_path=str(db_path))
    monkeypatch.setattr(database_module, "_db", db)

    owner = JobQueue(worker_id="owner-1")
    submit = JobQueue(run_workers=False, worker_id="api-1")
    submit.start()
    running = threading.Event()

    def fake_executor(job) -> JobResult:
        running.set()
        while True:
            if job.cancelled or job.status == JobStatus.CANCELLED:
                raise JobCancelledError("Job cancelled by user")
            job.update_progress(50, "working")
            time.sleep(0.05)

    monkeypatch.setattr(owner, "_get_job_executor", lambda job_type: fake_executor)
    try:
        job_id = submit.add_job(JobType.VALIDATION, "long", "cancel across processes")
        owner.start()
        assert running.wait(timeout=5.0), "the owner never started the job"

        assert submit.cancel_job(job_id) is True
        assert _wait_for_terminal(owner, job_id) is JobStatus.CANCELLED
        assert _wait_for_db_status(db_path, job_id, "cancelled")
    finally:
        owner.stop()
        submit.stop()
