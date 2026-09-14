from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from job_queue import Job, JobStatus, JobType  # noqa: E402

from ui.database import SermonDatabase, SermonRepository  # noqa: E402


def _ensure_jobs_table(db: SermonDatabase) -> None:
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


def _repo_with_sermon(tmp_path: Path) -> tuple[SermonRepository, str, int, str]:
    db = SermonDatabase(db_path=str(tmp_path / "apply_q.db"))
    _ensure_jobs_table(db)
    repo = SermonRepository(db)
    media = tmp_path / "Sermon_Original.mp4"
    media.write_bytes(b"x")
    sermon_id = "draft_qt1"
    repo.save_sermon(
        {
            "id": sermon_id,
            "title": "QT",
            "speaker": "Spk",
            "recorded_date": "2024-01-01",
            "event_type": "Sunday Service",
            "file_paths": {"audio": str(media)},
        }
    )
    plan_id = repo.save_edit_plan_revision(
        sermon_id,
        {
            "proposed_start": 10.0,
            "proposed_end": 60.0,
            "confidence": 0.9,
            "needs_review": False,
            "evidence": "e",
            "qa_judgment": "cut",
            "reasoning": "r",
            "status": "approved",
            "notes": "",
        },
    )
    return repo, sermon_id, plan_id, str(media)


def _apply_job(sermon_id: str, plan_id: int, revision: int) -> Job:
    try:
        import auto_edit_apply as core
    except ImportError:
        from ui import auto_edit_apply as core
    params = core.build_apply_job_params(
        sermon_id, plan_id, revision, 10.0, 60.0, 0.0, True, False, {}
    )
    return Job(
        id="job-apply-1",
        type=JobType.AUTO_EDIT_APPLY,
        title="Apply edit",
        description="Library apply",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=params,
    )


def test_apply_executor_registered() -> None:
    from ui.job_executors import get_executor

    assert get_executor(JobType.AUTO_EDIT_APPLY) is not None


def test_apply_params_carry_required_fields() -> None:
    try:
        import auto_edit_apply as core
    except ImportError:
        from ui import auto_edit_apply as core
    params = core.build_apply_job_params("s1", 3, 2, 5.0, 50.0, 0.4, True, False, {})
    for key in ("sermon_id", "start", "end", "audio_offset", "render_only", "mode"):
        assert key in params
    assert params["mode"] == "render_only"
    assert params["render_only"] is True
    upload = core.build_apply_job_params("s1", 3, 2, 5.0, 50.0, 0.0, False, False, {})
    assert upload["mode"] == "upload"


def test_executor_render_only_marks_applied_local(tmp_path, monkeypatch) -> None:
    repo, sermon_id, plan_id, _media = _repo_with_sermon(tmp_path)
    revision = repo.get_current_edit_plan(sermon_id)["revision"]

    rendered = {
        "success": True,
        "sermon_id": "draft_rendered_1",
        "edit_plan_status": "applied_local",
        "transcript": "big body",
        "error": None,
    }
    process = Mock(return_value=dict(rendered))
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    import ui.database as db

    monkeypatch.setattr(db, "SermonRepository", lambda *a, **k: repo)

    from ui.job_executors import execute_library_auto_edit_apply_job

    job = _apply_job(sermon_id, plan_id, revision)
    result = execute_library_auto_edit_apply_job(job)

    assert result.success is True
    assert "nothing was uploaded" in result.message
    assert "transcript" not in (result.data or {})
    kwargs = process.call_args.kwargs
    assert kwargs["dry_run"] is True
    assert kwargs["auto_edit_mode"] == "auto"
    current = repo.get_current_edit_plan(sermon_id)
    assert current["status"] == "applied_local"
    assert current["applied_media_id"] == "draft_rendered_1"


def test_dedupe_blocks_second_enqueue_for_same_revision(tmp_path) -> None:
    repo, sermon_id, _plan_id, _media = _repo_with_sermon(tmp_path)
    revision = repo.get_current_edit_plan(sermon_id)["revision"]
    try:
        import auto_edit_apply as core
    except ImportError:
        from ui import auto_edit_apply as core
    params = core.build_apply_job_params(sermon_id, 1, revision, 10.0, 60.0, 0.0, True, False, {})
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT INTO background_jobs (id, type, title, description, status, "
            "progress, parameters) VALUES (?, 'auto_edit_apply', ?, ?, "
            "'running', 10, ?)",
            ("job-active-1", "Apply edit", "desc", json.dumps(params)),
        )
        conn.commit()

    active = core.get_active_apply_job(repo, sermon_id, revision)
    assert active is not None
    assert active["id"] == "job-active-1"
    assert repo.get_active_apply_job(sermon_id, revision)["id"] == "job-active-1"

    other = core.get_active_apply_job(repo, "no-such-sermon", revision)
    assert other is None


def test_latest_apply_sees_queue_row(tmp_path) -> None:
    repo, sermon_id, _plan_id, _media = _repo_with_sermon(tmp_path)
    revision = repo.get_current_edit_plan(sermon_id)["revision"]
    try:
        import auto_edit_apply as core
    except ImportError:
        from ui import auto_edit_apply as core
    params = core.build_apply_job_params(sermon_id, 1, revision, 10.0, 60.0, 0.0, True, False, {})
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT INTO background_jobs (id, type, title, description, status, "
            "progress, parameters) VALUES (?, 'auto_edit_apply', ?, ?, "
            "'queued', 0, ?)",
            ("job-q-1", "Apply edit", "desc", json.dumps(params)),
        )
        conn.commit()
    latest = repo.get_latest_apply_job(sermon_id)
    assert latest is not None
    assert latest["id"] == "job-q-1"
    assert latest["status"] == "queued"
