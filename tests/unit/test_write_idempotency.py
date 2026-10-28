"""Idempotency: two intents that arrive together create one job.

The guard reads the store, then writes through the job queue. Those two steps
used to be separate, so two parallel requests could both read "no active job"
and each queue one. These tests widen that window and require exactly one job
per intent, plus a 409 that names the job already running.
"""

from __future__ import annotations

import sqlite3
import threading
import time

from fastapi import HTTPException

from server.api.accounts import get_db_path
from server.api.routers import writes


class _SlowQueue:
    """Stand-in queue whose insert pauses after the guard has passed."""

    def __init__(self) -> None:
        self.jobs: list[str] = []
        self._lock = threading.Lock()

    def add_job(self, job_type, title, description, parameters=None, priority=5, user_id=None):
        time.sleep(0.15)
        with self._lock:
            job_id = f"job-{len(self.jobs) + 1}"
            self.jobs.append(job_id)
        return job_id


def _draft(client, headers, title="Concurrent Talk"):
    created = client.post(
        "/api/sermons",
        json={"title": title, "speaker": "Speaker A", "recorded_date": "2026-10-20"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sermon_id = created.json()["id"]
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE sermons SET duration = ? WHERE id = ?", (3600.0, sermon_id))
    conn.commit()
    conn.close()
    return sermon_id


def _run_pair(call):
    results: list[object] = [None, None]
    barrier = threading.Barrier(2)

    def worker(index: int) -> None:
        barrier.wait()
        try:
            results[index] = call()
        except HTTPException as exc:
            results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _wire_queue(monkeypatch, queue: _SlowQueue) -> None:
    monkeypatch.setattr(writes, "_queue", lambda: queue)
    monkeypatch.setattr(
        writes,
        "_active_job_for",
        lambda _sid: {"id": queue.jobs[0]} if queue.jobs else None,
    )


def test_parallel_apply_creates_one_job(client, scoped_setup, monkeypatch):
    user = {"id": scoped_setup["a"]["id"], "role": "user"}
    sermon_id = _draft(client, scoped_setup["a"]["headers"])
    queue = _SlowQueue()
    _wire_queue(monkeypatch, queue)

    body = writes.ApplyBody(start=10.0, end=20.0, render_only=True)
    results = _run_pair(lambda: writes.apply_plan(sermon_id, body, None, user))

    statuses = sorted(
        result.status_code if isinstance(result, HTTPException) else 202
        for result in results
    )
    assert statuses == [202, 409], results
    assert len(queue.jobs) == 1
    conflict = next(result for result in results if isinstance(result, HTTPException))
    assert conflict.detail["code"] == "job_active"
    assert conflict.detail["job_id"] == queue.jobs[0]


def test_parallel_upload_creates_one_job(client, scoped_setup, monkeypatch):
    user = {"id": scoped_setup["a"]["id"], "role": "user"}
    sermon_id = _draft(client, scoped_setup["a"]["headers"])
    queue = _SlowQueue()
    _wire_queue(monkeypatch, queue)
    monkeypatch.setattr(writes, "_require_sermonaudio_connection", lambda _uid: None)

    results = _run_pair(lambda: writes.upload_now(sermon_id, user=user))
    statuses = sorted(
        result.status_code if isinstance(result, HTTPException) else 202
        for result in results
    )
    assert statuses == [202, 409], results
    assert len(queue.jobs) == 1


def test_uploading_the_same_file_twice_does_not_queue_twice(
    client, scoped_setup, tmp_path, monkeypatch
):
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "ingest"))
    monkeypatch.setattr(writes, "_require_sermonaudio_connection", lambda _uid: None)
    headers = scoped_setup["a"]["headers"]
    data = {
        "title": "Same Bytes",
        "speaker": "Speaker A",
        "recorded_date": "2026-10-21",
        "event_type": "Sunday Service",
    }
    payload = b"ID3" + bytes(4096)

    first = client.post(
        "/api/sermons/upload",
        files={"file": ("talk.mp3", payload, "audio/mpeg")},
        data=data,
        headers=headers,
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/sermons/upload",
        files={"file": ("talk.mp3", payload, "audio/mpeg")},
        data=data,
        headers=headers,
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "job_active"
    assert second.json()["detail"]["job_id"] == first.json()["job_id"]

    sermon_id = first.json()["id"]
    conn = sqlite3.connect(get_db_path())
    jobs = conn.execute(
        "SELECT id FROM background_jobs WHERE parameters LIKE ?", (f"%{sermon_id}%",)
    ).fetchall()
    conn.close()
    assert len(jobs) == 1
