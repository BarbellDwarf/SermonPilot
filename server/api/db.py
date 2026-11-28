"""Read-only database access for the SermonPilot API bridge.

Reuses ``ui.database.SermonRepository`` / ``SermonDatabase`` without ever
mutating the live database: the connection below opens SQLite with
``mode=ro`` and the schema-init hook is disabled, so even a bug in a
read path cannot write.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ui.database import SermonDatabase, SermonRepository

DEFAULT_DB_PATH = "/data/sermon_processor.db"


def get_db_path() -> str:
    return os.environ.get("SERMONPILOT_DB", DEFAULT_DB_PATH)


class ReadOnlySermonDatabase(SermonDatabase):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or get_db_path())

    def init_database(self) -> None:
        return None

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def get_repository() -> SermonRepository:
    return SermonRepository(ReadOnlySermonDatabase())


def db_is_readable(db_path: str | None = None) -> bool:
    try:
        with ReadOnlySermonDatabase(db_path).get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def _job_query_filters(status: str | None, user_id: str | None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        if status == "active":
            clauses.append("status IN ('queued', 'running')")
        elif status in {"failed", "interrupted"}:
            from ui.job_queue import INTERRUPTED_BY_RESTART_MARKER

            marker = f"%{INTERRUPTED_BY_RESTART_MARKER}%"
            marker_match = "(COALESCE(result, '') LIKE ? OR COALESCE(logs, '') LIKE ?)"
            if status == "failed":
                clauses.append(f"(status IN ('failed', 'cancelled') AND NOT {marker_match})")
            else:
                clauses.append(f"(status IN ('failed', 'cancelled') AND {marker_match})")
            params.extend((marker, marker))
        else:
            clauses.append("status = ?")
            params.append(status)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    return (" WHERE " + " AND ".join(clauses) if clauses else "", params)


def query_jobs(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Read a stable page of background_jobs rows; [] when the table is absent."""
    where, params = _job_query_filters(status, user_id)
    query = (
        "SELECT id, type, title, description, status, progress, parameters,"
        " result, logs, created_at, started_at, completed_at, user_id"
        " FROM background_jobs"
        f"{where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    )
    params.extend((max(1, min(limit, 1000)), max(0, offset)))
    try:
        with ReadOnlySermonDatabase().get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(row) for row in rows]


def query_job_count(status: str | None = None, user_id: str | None = None) -> int:
    """Count background_jobs rows with the same scope and filter as the page."""
    where, params = _job_query_filters(status, user_id)
    try:
        with ReadOnlySermonDatabase().get_connection() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS total FROM background_jobs{where}", params
            ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["total"]) if row else 0


def query_job(job_id: str) -> dict[str, Any] | None:
    try:
        with ReadOnlySermonDatabase().get_connection() as conn:
            row = conn.execute(
                "SELECT id, type, title, description, status, progress, parameters,"
                " result, logs, created_at, started_at, completed_at, user_id"
                " FROM background_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None
