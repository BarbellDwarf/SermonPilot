from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

import auto_edit_apply as core  # noqa: E402
from job_queue import Job, JobStatus, JobType  # noqa: E402


class _StubRepo:
    def __init__(self, sermon: dict, plan: dict):
        self._sermon = sermon
        self._plan = plan
        self.status_updates: list[tuple] = []

    def get_sermon(self, _sermon_id):
        return dict(self._sermon)

    def get_edit_plan_history(self, _sermon_id):
        return [dict(self._plan)]

    def get_current_edit_plan(self, _sermon_id):
        return dict(self._plan)

    def update_edit_plan_status(self, plan_id, status, notes="", applied_media_id=None):
        self.status_updates.append((plan_id, status, notes, applied_media_id))
        return True


def _plan(plan_id: int = 7) -> dict:
    return {
        "id": plan_id,
        "revision": 3,
        "proposed_start": 40.0,
        "proposed_end": 2958.0,
        "confidence": 1.0,
        "needs_review": False,
        "evidence": "approved in Library",
        "qa_judgment": "approved",
        "reasoning": "",
        "status": "approved",
        "notes": "",
    }


def _sermon_with_metadata(tmp_path: Path, trimmed: Path, full: Path | None) -> dict:
    metadata = tmp_path / "metadata.json"
    payload = {"processed_file": str(trimmed)}
    if full is not None:
        payload["original_file"] = str(full)
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "id": "sermon-1",
        "speaker": "Spk",
        "recorded_date": "2024-01-01",
        "event_type": "Sunday Service",
        "title": "T",
        "file_paths": {"audio": str(trimmed), "metadata": str(metadata)},
    }


def test_approved_plan_exceeding_source_fails_loud_without_render(tmp_path, monkeypatch):
    trimmed = tmp_path / "Sermon_Processed.mkv"
    trimmed.write_bytes(b"x")
    sermon = _sermon_with_metadata(tmp_path, trimmed, None)
    repo = _StubRepo(sermon, _plan())

    monkeypatch.setattr(core, "_source_duration", lambda _p: 2918.0)
    process = Mock()
    monkeypatch.setitem(sys.modules, "sermon_updater", Mock(process_new_sermon=process))
    import sermon_updater  # noqa: F401

    result = core.run_library_apply(repo, "sermon-1", 40.0, 2958.0, render_only=True, plan_id=7)

    assert result["success"] is False
    assert "2958" in (result.get("error") or "")
    assert "2918" in (result.get("error") or "")
    assert "nothing was rendered" in (result.get("error") or "").lower()
    process.assert_not_called()
    assert repo.status_updates == []


def test_pending_review_pipeline_result_is_not_marked_applied(tmp_path, monkeypatch):
    full = tmp_path / "Sermon_Original.mkv"
    full.write_bytes(b"x")
    trimmed = tmp_path / "Sermon_Processed.mkv"
    trimmed.write_bytes(b"x")
    sermon = _sermon_with_metadata(tmp_path, trimmed, full)
    repo = _StubRepo(sermon, _plan())

    monkeypatch.setattr(core, "_source_duration", lambda _p: 3600.0)
    pending = {
        "success": True,
        "sermon_id": "draft_junk_1",
        "edit_plan_status": "pending_review",
        "auto_edit_applied": False,
    }
    process = Mock(return_value=dict(pending))
    monkeypatch.setitem(sys.modules, "sermon_updater", Mock(process_new_sermon=process))

    result = core.run_library_apply(repo, "sermon-1", 40.0, 2958.0, render_only=True, plan_id=7)

    assert result["success"] is False
    assert "pending_review" in (result.get("error") or "").lower()
    assert repo.status_updates == []


def test_resolve_apply_source_skips_trimmed_shorter_than_plan(tmp_path, monkeypatch):
    trimmed = tmp_path / "Sermon_Processed.mkv"
    trimmed.write_bytes(b"x")
    full = tmp_path / "Sermon_Original.mkv"
    full.write_bytes(b"x")
    sermon = _sermon_with_metadata(tmp_path, trimmed, full)
    repo = _StubRepo(sermon, _plan())

    def _duration(path):
        return 2918.0 if Path(str(path)).name == trimmed.name else 3600.0

    monkeypatch.setattr(core, "_source_duration", _duration)

    source, _enhanced = core._resolve_apply_source(sermon, repo, min_duration=2958.0)
    assert source == str(full)


def test_executor_reports_failure_not_rendered_on_pending_review(monkeypatch):
    pending = {
        "success": True,
        "sermon_id": "draft_junk_1",
        "edit_plan_status": "pending_review",
        "auto_edit_applied": False,
    }
    monkeypatch.setattr(core, "run_library_apply", lambda *a, **k: dict(pending))

    from ui.job_executors import execute_library_auto_edit_apply_job

    job = Job(
        id="job-pending-1",
        type=JobType.AUTO_EDIT_APPLY,
        title="Apply edit",
        description="Library apply",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters={
            "sermon_id": "sermon-1",
            "start": 40.0,
            "end": 2958.0,
            "audio_offset": 0.0,
            "render_only": True,
            "mode": "render_only",
            "plan_id": 7,
            "plan_revision": 3,
            "re_detect": False,
            "config": {},
        },
    )
    result = execute_library_auto_edit_apply_job(job)

    assert result.success is False
    assert "rendered locally" not in (result.message or "").lower()
