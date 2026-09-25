"""Unit coverage for the headless job worker process."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from ui import job_queue, job_worker


class _FakeQueue:
    def __init__(self, **kwargs: object) -> None:
        self.init_kwargs = kwargs
        self._owns_lease = True
        self.started = threading.Event()
        self.stopped = threading.Event()

    def start(self) -> None:
        self.started.set()

    def stop(self) -> None:
        self.stopped.set()


def test_worker_builds_a_worker_enabled_queue(monkeypatch) -> None:
    created: list[_FakeQueue] = []

    def build(**kwargs: object) -> _FakeQueue:
        queue = _FakeQueue(**kwargs)
        created.append(queue)
        return queue

    monkeypatch.setattr(job_worker, "JobQueue", build)

    queue = job_worker.build_worker_queue()

    assert queue.init_kwargs == {"run_workers": True}
    assert created == [queue]


def test_worker_starts_blocks_and_stops_when_shutdown_is_requested(
    caplog,
) -> None:
    caplog.set_level(logging.INFO)
    queue = _FakeQueue()
    shutdown = threading.Event()
    worker_thread = threading.Thread(
        target=job_worker.run_worker,
        args=(queue, shutdown),
    )

    worker_thread.start()
    try:
        assert queue.started.wait(timeout=1.0)
        assert worker_thread.is_alive()
    finally:
        shutdown.set()
        worker_thread.join(timeout=1.0)

    assert not worker_thread.is_alive()
    assert queue.stopped.is_set()
    assert job_worker.WORKER_STARTED_MESSAGE in caplog.text


def test_submit_only_mode_does_not_initialize_a_browser_worker(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setenv("SERMONPILOT_JOB_WORKER_ENABLED", "0")
    monkeypatch.setattr(job_queue, "get_job_queue", lambda: pytest.fail("worker queue initialized"))
    monkeypatch.setattr(job_queue, "get_submit_job_queue", lambda: sentinel)

    assert job_queue.initialize_job_queue() is sentinel


def test_production_entrypoint_starts_the_worker_module() -> None:
    entrypoint = Path(__file__).parents[1] / "docker" / "start_production.sh"

    assert "python -m ui.job_worker" in entrypoint.read_text(encoding="utf-8")
