"""Fast tests for the default serialized job queue.

The module singleton constructs JobQueue with no arguments, so the default
worker count must keep submitted jobs strictly sequential.
"""

from __future__ import annotations

import threading
import time

import pytest

import ui.database as database_module
from ui.job_queue import Job, JobQueue, JobResult, JobStatus, JobType

JOB_WAIT_TIMEOUT = 10.0
_TERMINAL_STATUSES = (
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
)


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> JobQueue:
    def _no_database(*args: object, **kwargs: object) -> None:
        raise RuntimeError("persistence stubbed")

    monkeypatch.setattr(database_module, "get_db", _no_database)
    return JobQueue()


def _wait_for_terminal_status(queue: JobQueue, job_id: str) -> JobStatus:
    deadline = time.monotonic() + JOB_WAIT_TIMEOUT
    job = queue.get_job(job_id)
    while time.monotonic() < deadline:
        if job and job.status in _TERMINAL_STATUSES:
            return job.status
        time.sleep(0.01)
        job = queue.get_job(job_id)
    status = job.status if job else None
    raise AssertionError(f"job {job_id} did not finish, last status: {status}")


def test_default_queue_spawns_single_worker(queue: JobQueue) -> None:
    assert queue.max_workers == 1
    assert JobQueue(max_workers=2).max_workers == 2

    queue.start()
    try:
        worker_names = [
            worker.name for worker in threading.enumerate() if worker.name.startswith("JobWorker")
        ]
    finally:
        queue.stop()

    assert worker_names == ["JobWorker-1"]


def test_back_to_back_jobs_do_not_overlap(queue: JobQueue, monkeypatch: pytest.MonkeyPatch) -> None:
    timeline: list[str] = []
    timeline_lock = threading.Lock()

    def fake_executor(job: Job) -> JobResult:
        with timeline_lock:
            timeline.append(f"start:{job.title}")
        time.sleep(0.2)
        with timeline_lock:
            timeline.append(f"stop:{job.title}")
        return JobResult(success=True, message="done")

    monkeypatch.setattr(queue, "_get_job_executor", lambda job_type: fake_executor)

    first_id = queue.add_job(JobType.VALIDATION, "first", "first fake job")
    second_id = queue.add_job(JobType.VALIDATION, "second", "second fake job")

    queue.start()
    try:
        assert _wait_for_terminal_status(queue, first_id) is JobStatus.COMPLETED
        assert _wait_for_terminal_status(queue, second_id) is JobStatus.COMPLETED
    finally:
        queue.stop()

    assert timeline == [
        "start:first",
        "stop:first",
        "start:second",
        "stop:second",
    ]
