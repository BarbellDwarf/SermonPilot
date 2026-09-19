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


def query_jobs(
    status: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Read background_jobs rows directly; [] when the table is absent."""
    query = (
        "SELECT id, type, title, description, status, progress, parameters,"
        " result, logs, created_at, started_at, completed_at, user_id"
        " FROM background_jobs"
    )
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 1000)))
    try:
        with ReadOnlySermonDatabase().get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(row) for row in rows]


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
