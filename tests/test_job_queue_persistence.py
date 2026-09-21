"""Regression tests for live job persistence, terminal states, and cancellation.

These cover the bug where a running job's progress and logs lived only in
memory until a queue transition, so the Jobs page showed "Job started" for the
whole run, and where a cancelled job could leave the single worker busy.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

import ui.database as database_module
from ui.database import SermonDatabase
from ui.job_queue import (
    JOB_CANCEL_POLL_INTERVAL_SECONDS,
    Job,
    JobCancelledError,
    JobQueue,
    JobResult,
    JobStatus,
    JobType,
)

TERMINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
# The fake chunked executors below poll at CHUNK_SECONDS; the queue's documented
# cancel bound is JOB_CANCEL_POLL_INTERVAL_SECONDS. The test asserts the worker
# releases the queue within that bound plus a small scheduling margin.
CHUNK_SECONDS = 0.05
CANCEL_RELEASE_BOUND_SECONDS = JOB_CANCEL_POLL_INTERVAL_SECONDS + 1.0


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


def _read_row(db_path: Path, job_id: str) -> sqlite3.Row | None:
    """Read a job row from a brand new sqlite connection."""
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM background_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()


def _wait_for(predicate, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    return None


def _wait_for_terminal(queue: JobQueue, job_id: str, timeout: float = 10.0) -> JobStatus:
    def _terminal():
        job = queue.get_job(job_id)
        if job and job.status in TERMINAL_STATUSES:
            return job.status
        return None

    status = _wait_for(_terminal, timeout)
    if status is None:
        job = queue.get_job(job_id)
        raise AssertionError(
            f"job {job_id} did not finish, last status: {job.status if job else None}"
        )
    return status


def test_progress_and_logs_visible_from_second_connection_while_running(
    queue: JobQueue, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression test for the invisibility bug.

    A separate sqlite connection must see progress and log lines while the
    executor is still running, not only at the terminal transition.
    """
    finished = threading.Event()
    release = threading.Event()

    def fake_executor(job: Job) -> JobResult:
        try:
            index = 0
            while not release.is_set():
                index += 1
                job.update_progress(min(90, 10 + index), f"chunk-{index}")
                time.sleep(CHUNK_SECONDS)
            return JobResult(success=True, message="done")
        finally:
            finished.set()

    monkeypatch.setattr(queue, "_get_job_executor", lambda job_type: fake_executor)
    job_id = queue.add_job(JobType.VALIDATION, "chunked", "runs in chunks")

    queue.start()
    try:
        def _marker_visible():
            job = queue.get_job(job_id)
            row = _read_row(db_path, job_id)
            if row is None:
                return None
            logs = json.loads(row["logs"] or "[]")
            if any("chunk-5" in line for line in logs) and (row["progress"] or 0) > 10:
                return (row, job)
            return None

        observed = _wait_for(_marker_visible, 5.0)
        assert observed is not None, "progress/logs never became visible while running"
        row, job = observed
        assert row["status"] == "running"
        assert not finished.is_set(), "job had already finished when state was observed"
        assert job is not None and job.status == JobStatus.RUNNING
    finally:
        release.set()
        _wait_for_terminal(queue, job_id)
        queue.stop()


def test_executor_exception_marks_job_failed_with_error(
    queue: JobQueue, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_executor(job: Job) -> JobResult:
        job.update_progress(25, "about to raise")
        raise RuntimeError("boom-placeholder-error")

    monkeypatch.setattr(queue, "_get_job_executor", lambda job_type: fake_executor)
    job_id = queue.add_job(JobType.VALIDATION, "explodes", "raises")

    queue.start()
    try:
        assert _wait_for_terminal(queue, job_id) is JobStatus.FAILED
    finally:
        queue.stop()

    job = queue.get_job(job_id)
    assert job is not None
    assert job.status is JobStatus.FAILED
    assert job.result is not None and job.result.success is False
    assert "boom-placeholder-error" in (job.result.error or "")

    row = _read_row(db_path, job_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["completed_at"] is not None
    stored_result = json.loads(row["result"] or "{}")
    assert "boom-placeholder-error" in json.dumps(stored_result)


class _EscapingStage(BaseException):
    """Stand-in for a BaseException a stage could raise past the normal guard."""


def test_escaped_base_exception_still_reaches_failed_and_queue_continues(
    queue: JobQueue, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defensive wrapper must not strand the worker on a fatal stage."""
    order: list[str] = []

    def fake_executor(job: Job) -> JobResult:
        order.append(job.title)
        if job.title == "fatal":
            raise _EscapingStage("stage escaped")
        return JobResult(success=True, message="done")

    monkeypatch.setattr(queue, "_get_job_executor", lambda job_type: fake_executor)
    fatal_id = queue.add_job(JobType.VALIDATION, "fatal", "escapes")
    next_id = queue.add_job(JobType.VALIDATION, "next", "should still run")

    queue.start()
    try:
        assert _wait_for_terminal(queue, fatal_id) is JobStatus.FAILED
        assert _wait_for_terminal(queue, next_id) is JobStatus.COMPLETED
    finally:
        queue.stop()

    assert order == ["fatal", "next"]
    row = _read_row(db_path, fatal_id)
    assert row is not None and row["status"] == "failed"


def test_cancel_releases_queue_and_starts_next_job_within_bound(
    queue: JobQueue, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running = threading.Event()
    next_started = threading.Event()

    def fake_executor(job: Job) -> JobResult:
        if job.title == "long":
            running.set()
            while True:
                if job.cancelled or job.status == JobStatus.CANCELLED:
                    raise JobCancelledError("Job cancelled by user")
                job.update_progress(50, "working")
                time.sleep(CHUNK_SECONDS)
        next_started.set()
        return JobResult(success=True, message="done")

    monkeypatch.setattr(queue, "_get_job_executor", lambda job_type: fake_executor)
    long_id = queue.add_job(JobType.VALIDATION, "long", "cancel me")
    next_id = queue.add_job(JobType.VALIDATION, "next", "follow-up")

    queue.start()
    try:
        assert running.wait(timeout=5.0), "long job never started"
        assert queue.cancel_job(long_id) is True

        started_at = time.monotonic()
        assert next_started.wait(timeout=CANCEL_RELEASE_BOUND_SECONDS), (
            "queue did not start the next job within the cancel bound"
        )
        elapsed = time.monotonic() - started_at
        assert elapsed <= CANCEL_RELEASE_BOUND_SECONDS, (
            f"cancel took {elapsed:.2f}s, bound is {CANCEL_RELEASE_BOUND_SECONDS:.2f}s"
        )

        assert _wait_for_terminal(queue, long_id) is JobStatus.CANCELLED
        assert _wait_for_terminal(queue, next_id) is JobStatus.COMPLETED
    finally:
        queue.stop()

    row = _read_row(db_path, long_id)
    assert row is not None and row["status"] == "cancelled"
