"""A hung stage must not wedge the single worker.

The watchdog only gives up when a job reports no progress for the bound, so a
legitimately long stage that keeps logging is left alone.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import ui.database as database_module
from ui.database import SermonDatabase
from ui.job_queue import Job, JobQueue, JobResult, JobStatus, JobType

TERMINAL = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


@pytest.fixture(autouse=True)
def _skip_resource_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(JobQueue, "_resources_available", lambda self: True)


@pytest.fixture
def queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobQueue:
    db = SermonDatabase(db_path=str(tmp_path / "jobs.db"))
    monkeypatch.setattr(database_module, "_db", db)
    return JobQueue()


def _wait_for_terminal(queue: JobQueue, job_id: str, timeout: float = 10.0) -> JobStatus:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = queue.get_job(job_id)
        if job and job.status in TERMINAL:
            return job.status
        time.sleep(0.02)
    job = queue.get_job(job_id)
    raise AssertionError(f"job {job_id} did not finish, last status: {job.status if job else None}")


def _patch_stall_bound(monkeypatch: pytest.MonkeyPatch, seconds: float = 0.3) -> None:
    monkeypatch.setattr(
        "ui.config_utils.resolve_config",
        lambda db=None: {"job_queue": {"stall_timeout_seconds": seconds}},
    )


def test_hung_stage_fails_with_the_stage_named_and_queue_moves_on(
    queue: JobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    next_started = threading.Event()
    cancel_seen = threading.Event()

    def fake_executor(job: Job) -> JobResult:
        if job.title == "hung":
            job.update_progress(30, "Enhancing audio")
            while not job.cancelled:
                time.sleep(0.05)
            cancel_seen.set()
            return JobResult(success=False, message="cancelled")
        next_started.set()
        return JobResult(success=True, message="done")

    _patch_stall_bound(monkeypatch)
    monkeypatch.setattr(queue, "_get_job_executor", lambda job_type: fake_executor)

    hung_id = queue.add_job(JobType.VALIDATION, "hung", "stage hangs")
    next_id = queue.add_job(JobType.VALIDATION, "next", "runs after the stall")

    queue.start()
    try:
        assert _wait_for_terminal(queue, hung_id) is JobStatus.FAILED
        assert cancel_seen.wait(timeout=2.0), "the stalled executor did not see cancellation"
        assert next_started.wait(timeout=5.0), "the next job never started"
        assert _wait_for_terminal(queue, next_id) is JobStatus.COMPLETED
    finally:
        queue.stop()

    job = queue.get_job(hung_id)
    assert job is not None and job.result is not None
    assert "Enhancing audio" in (job.result.message or "")
    assert "Enhancing audio" in (job.result.error or "")
    assert any("stalled at stage" in line for line in job.logs)


def test_a_progressing_job_is_never_stalled(
    queue: JobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_executor(job: Job) -> JobResult:
        for index in range(6):
            job.update_progress(10 + index, f"chunk-{index}")
            time.sleep(0.1)
        return JobResult(success=True, message="done")

    _patch_stall_bound(monkeypatch)
    monkeypatch.setattr(queue, "_get_job_executor", lambda job_type: fake_executor)

    job_id = queue.add_job(JobType.VALIDATION, "progressing", "keeps logging")
    queue.start()
    try:
        assert _wait_for_terminal(queue, job_id) is JobStatus.COMPLETED
    finally:
        queue.stop()
