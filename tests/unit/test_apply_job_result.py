from __future__ import annotations

import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from job_queue import _coerce_job_result  # noqa: E402

from ui.database import SermonDatabase, SermonRepository  # noqa: E402


def test_apply_result_shape_with_render_only_parses() -> None:
    result = _coerce_job_result({"success": True, "render_only": True, "elapsed_seconds": 123.4})
    assert result.success is True
    assert result.data["render_only"] is True
    assert result.data["elapsed_seconds"] == 123.4


def test_error_result_without_success_defaults_false() -> None:
    result = _coerce_job_result({"error": "boom", "elapsed_seconds": 1.2, "render_only": True})
    assert result.success is False
    assert result.error == "boom"
    assert result.data["render_only"] is True


def test_standard_result_passes_through() -> None:
    result = _coerce_job_result({"success": True, "message": "ok", "data": {"a": 1}, "error": None})
    assert result.success is True
    assert result.message == "ok"
    assert result.data == {"a": 1}


def test_start_apply_job_round_trips(tmp_path) -> None:
    db = SermonDatabase(db_path=str(tmp_path / "apply.db"))
    with db.get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS background_jobs ("
            "id TEXT PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL, "
            "description TEXT, status TEXT NOT NULL, progress REAL DEFAULT 0, "
            "parameters TEXT, result TEXT, logs TEXT, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, started_at TIMESTAMP, "
            "completed_at TIMESTAMP, can_cancel BOOLEAN DEFAULT 1, "
            "can_retry BOOLEAN DEFAULT 1, priority INTEGER DEFAULT 5)"
        )
        conn.commit()
    repo = SermonRepository(db)
    sermon_id = "sermon-123"
    job_id = "job-abc"
    assert repo.start_apply_job(job_id, sermon_id, "Title", {"sermon_id": sermon_id}) is True
    row = repo.get_latest_apply_job(sermon_id)
    assert row is not None
    assert row["id"] == job_id
    assert row["status"] == "running"
    with db.get_connection() as conn:
        stored = conn.execute(
            "SELECT type FROM background_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    assert stored["type"] == "auto_edit_apply"
