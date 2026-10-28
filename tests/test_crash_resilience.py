"""Crash resilience: WAL survives kill -9 and a restarted worker resumes.

The probes use a scratch database in a temp directory. A child process is
killed by its own PID, never matched by pattern, and the parent then verifies
the store opens cleanly and only committed rows survive.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import ui.database as database_module
from ui.database import SermonDatabase
from ui.job_queue import (
    INTERRUPTED_BY_RESTART_MARKER,
    Job,
    JobQueue,
    JobResult,
    _ensure_job_columns,
    _ensure_lease_table,
    reconcile_interrupted_jobs,
)

_CHILD = """
import os, sqlite3, sys
path = sys.argv[1]
conn = sqlite3.connect(path)
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("CREATE TABLE evidence (value TEXT)")
conn.execute("INSERT INTO evidence VALUES ('committed')")
conn.commit()
conn.execute("INSERT INTO evidence VALUES ('uncommitted')")
os.kill(os.getpid(), 9)
"""


def test_kill_9_mid_transaction_leaves_a_clean_wal_store(tmp_path: Path) -> None:
    db_path = tmp_path / "crash.db"
    proc = subprocess.Popen([sys.executable, "-c", _CHILD, str(db_path)])
    assert proc.wait(timeout=30) != 0

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        rows = [row[0] for row in conn.execute("SELECT value FROM evidence")]
    finally:
        conn.close()
    assert rows == ["committed"]


def _seed_store(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> SermonDatabase:
    db = SermonDatabase(db_path=str(db_path))
    monkeypatch.setattr(database_module, "_db", db)
    bootstrap = JobQueue(run_workers=False)
    bootstrap.start()
    bootstrap.stop()
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        _ensure_job_columns(conn)
        _ensure_lease_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO job_worker_lease"
            " (id, worker_id, acquired_at, heartbeat_at)"
            " VALUES (1, 'dead-worker', ?, ?)",
            (
                (datetime.now() - timedelta(minutes=10)).isoformat(),
                (datetime.now() - timedelta(minutes=10)).isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO background_jobs"
            " (id, type, title, description, status, progress, parameters, logs, owner_id)"
            " VALUES (?, ?, ?, ?, 'running', 40, ?, ?, 'dead-worker')",
            (
                "j-interrupted",
                "validation",
                "Interrupted run",
                "started before the kill",
                json.dumps({"sermon_id": "s-1"}),
                json.dumps(["[10:00:00] Job started"]),
            ),
        )
        conn.execute(
            "INSERT INTO background_jobs"
            " (id, type, title, description, status, progress, parameters, logs)"
            " VALUES (?, ?, ?, ?, 'queued', 0, ?, '[]')",
            (
                "j-queued",
                "validation",
                "Resume me",
                "queued behind the interrupted run",
                json.dumps({"sermon_id": "s-2"}),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _read(db_path: Path, job_id: str) -> sqlite3.Row:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT status, result FROM background_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row


def test_restarted_worker_reconciles_the_dead_run_and_resumes_the_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "worker.db"
    _seed_store(db_path, monkeypatch)
    assert reconcile_interrupted_jobs(db_path=str(db_path)) == 1

    queue = JobQueue(worker_id="replacement")
    ran: list[str] = []

    def fake_executor(job: Job) -> JobResult:
        ran.append(job.id)
        return JobResult(success=True, message="resumed")

    monkeypatch.setattr(queue, "_get_job_executor", lambda _job_type: fake_executor)
    queue.start()
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if _read(db_path, "j-queued")["status"] == "completed":
                break
            time.sleep(0.05)
        assert _read(db_path, "j-queued")["status"] == "completed"
        assert ran == ["j-queued"]
    finally:
        queue.stop()

    interrupted = _read(db_path, "j-interrupted")
    assert interrupted["status"] == "failed"
    assert INTERRUPTED_BY_RESTART_MARKER in interrupted["result"]
