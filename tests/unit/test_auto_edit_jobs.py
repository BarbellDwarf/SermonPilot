from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from job_queue import (  # noqa: E402
    Job,
    JobCancelledError,
    JobStatus,
    JobType,
)

from ui.job_executors import (  # noqa: E402
    execute_auto_edit_apply_job,
    execute_auto_edit_job,
    get_executor,
)


def _job(params: dict[str, Any]) -> Job:
    return Job(
        id="job-1",
        type=JobType.AUTO_EDIT,
        title="Auto edit",
        description="Auto edit job",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=params,
    )


def _form_data() -> dict[str, Any]:
    return {
        "speaker_name": "Test Speaker",
        "recorded_date": "2024-01-01",
        "event_type": "Sunday Service",
        "dry_run": True,
        "skip_audio": True,
    }


AUDIO_FILE = str(_UI_DIR / "job_executors.py")
CONFIG = {"auto_edit": {}, "api_key": "k"}

MUT_UI = _UI_DIR / "job_executors.py"

PENDING_RESULT = {
    "success": True,
    "sermon_id": "draft_123",
    "title": "Original",
    "edit_plan_status": "pending_review",
    "auto_edit_applied": False,
    "transcript": "big transcript body",
    "error": None,
}

APPLY_RESULT = {
    "success": True,
    "sermon_id": "draft_123",
    "edit_plan_status": "auto_applied",
    "auto_edit_applied": True,
    "final_upload_path": "/tmp/edited.mp4",
    "output_dir": "/out/dir",
    "transcript": "big transcript body",
    "error": None,
}


def _stub_repo(monkeypatch, repo) -> None:
    import ui.database as db

    monkeypatch.setattr(db, "SermonRepository", lambda: repo)


def test_auto_edit_job_type_registered() -> None:
    assert get_executor(JobType.AUTO_EDIT) is not None


def test_pending_review_completes_successfully_with_note(monkeypatch) -> None:
    process = Mock(return_value=PENDING_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    job = _job({
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
        "auto_edit_mode": "interactive",
        "auto_edit_enabled": True,
        "edit_plan_file": None,
    })
    result = execute_auto_edit_job(job)

    assert result.success is True
    assert "awaiting manual review" in result.message
    assert result.error is None
    assert result.data["edit_plan_status"] == "pending_review"
    assert result.data["auto_edit_applied"] is False
    assert result.data["sermon_id"] == "draft_123"
    assert "transcript" not in result.data

    kwargs = process.call_args.kwargs
    assert kwargs["auto_edit_mode"] == "interactive"
    assert kwargs["edit_plan_file"] is None
    assert kwargs["audio_file"] == AUDIO_FILE
    assert kwargs["dry_run"] is True
    assert kwargs["speaker_name"] == "Test Speaker"


def test_auto_applied_result_is_success(monkeypatch) -> None:
    result_dict = dict(PENDING_RESULT, edit_plan_status="auto_applied",
                       auto_edit_applied=True)
    process = Mock(return_value=result_dict)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    job = _job({
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
        "auto_edit_mode": "auto",
        "auto_edit_enabled": True,
        "edit_plan_file": None,
    })
    result = execute_auto_edit_job(job)

    assert result.success is True
    assert result.error is None
    assert result.data["edit_plan_status"] == "auto_applied"
    assert result.data["auto_edit_applied"] is True
    assert process.call_args.kwargs["auto_edit_mode"] == "auto"


def test_auto_edit_job_defaults_mode_when_only_enabled(monkeypatch) -> None:
    process = Mock(return_value=PENDING_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    job = _job({
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
        "auto_edit_enabled": True,
    })
    execute_auto_edit_job(job)
    assert process.call_args.kwargs["auto_edit_mode"] == "interactive"


def test_disabled_job_passes_no_auto_edit_mode(monkeypatch) -> None:
    process = Mock(return_value=PENDING_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    job = _job({
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
        "auto_edit_enabled": False,
    })
    execute_auto_edit_job(job)
    assert process.call_args.kwargs["auto_edit_mode"] is None


def test_auto_edit_job_requires_fields() -> None:
    job = _job({"audio_file": None, "form_data": {}, "config": CONFIG})
    result = execute_auto_edit_job(job)
    assert result.success is False
    assert "audio_file" in result.error

    not_found = str(_UI_DIR / "does_not_exist.m4a")
    job2 = _job({"audio_file": not_found, "form_data": _form_data(),
                 "config": CONFIG})
    result = execute_auto_edit_job(job2)
    assert result.success is False
    assert not_found in result.message

    job3 = _job({"audio_file": AUDIO_FILE, "form_data": {"speaker_name": "S"},
                 "config": CONFIG})
    result = execute_auto_edit_job(job3)
    assert result.success is False
    assert "recorded_date" in result.error


def test_job_cancellation_honored(monkeypatch) -> None:
    job = _job({
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
        "auto_edit_enabled": True,
    })
    job.cancelled = True
    with pytest.raises(JobCancelledError):
        execute_auto_edit_job(job)

    job2 = _job({
        "sermon_id": "draft_123", "plan_id": 1,
        "final_start": 1.0, "final_end": 2.0,
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(), "config": CONFIG,
    })
    job2.cancelled = True
    with pytest.raises(JobCancelledError):
        execute_auto_edit_apply_job(job2)


def test_apply_job_writes_approved_numbers_and_marks_applied(monkeypatch) -> None:
    process = Mock(return_value=APPLY_RESULT)
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> dict[str, Any]:
        captured['kwargs'] = kwargs
        captured['plan'] = json.loads(Path(kwargs['edit_plan_file']).read_text())
        return APPLY_RESULT

    process.side_effect = capture
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    repo = Mock()
    repo.update_edit_plan_status.side_effect = [True, True]
    _stub_repo(monkeypatch, repo)

    job = _job({
        "sermon_id": "draft_123",
        "plan_id": 7,
        "final_start": 45.5,
        "final_end": 610.0,
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
    })
    result = execute_auto_edit_apply_job(job)

    assert result.success is True
    assert result.error is None
    assert result.data["edit_plan_status"] == "auto_applied"
    assert "transcript" not in result.data

    calls = repo.update_edit_plan_status.call_args_list
    assert calls[0].args == (7, "approved")
    assert calls[0].kwargs["final_start"] == 45.5
    assert calls[0].kwargs["final_end"] == 610.0
    assert calls[1].args == (7, "applied")
    assert calls[1].kwargs["applied_media_id"] == "/tmp/edited.mp4"

    kwargs = captured['kwargs']
    assert kwargs["auto_edit_mode"] == "auto"
    written = captured['plan']
    assert written["start"] == 45.5
    assert written["end"] == 610.0
    assert written["needs_review"] is False
    assert written["confidence"] == 1.0
    assert not Path(kwargs["edit_plan_file"]).exists()


def test_apply_job_re_edit_and_logo_override(monkeypatch) -> None:
    process = Mock(return_value=APPLY_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    repo = Mock()
    repo.update_edit_plan_status.return_value = True
    _stub_repo(monkeypatch, repo)

    job = _job({
        "sermon_id": "draft_123",
        "plan_id": 8,
        "final_start": 50.0,
        "final_end": 700.0,
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
        "logo_path": "/tmp/logo.png",
        "re_edit": True,
    })
    result = execute_auto_edit_apply_job(job)

    assert result.success is True
    assert "revision" in result.message
    assert "approved" in repo.update_edit_plan_status.call_args_list[0].kwargs["notes"]
    run_config = process.call_args.kwargs["config"]
    assert run_config["auto_edit"]["logo_path"] == "/tmp/logo.png"


def test_apply_job_pipeline_error_keeps_plan_unapplied(monkeypatch) -> None:
    result_dict = dict(PENDING_RESULT)
    process = Mock(return_value={**result_dict, "success": False,
                                 "error": "boom"})
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    repo = Mock()
    repo.update_edit_plan_status.return_value = True
    _stub_repo(monkeypatch, repo)
    job = _job({
        "sermon_id": "draft_123", "plan_id": 9,
        "final_start": 1.0, "final_end": 2.0,
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
    })
    result = execute_auto_edit_apply_job(job)
    assert result.success is False
    assert result.error == "boom"
    statuses = [call.args[1] for call in repo.update_edit_plan_status.call_args_list]
    assert statuses == ["approved"]


def test_apply_job_pending_review_returns_error(monkeypatch) -> None:
    result_dict = dict(PENDING_RESULT, success=True)
    process = Mock(return_value=result_dict)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    repo = Mock()
    repo.update_edit_plan_status.return_value = True
    _stub_repo(monkeypatch, repo)
    job = _job({
        "sermon_id": "draft_123", "plan_id": 11,
        "final_start": 1.0, "final_end": 2.0,
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
    })
    result = execute_auto_edit_apply_job(job)
    assert result.success is False
    assert "pending_review" in result.message
    statuses = [call.args[1] for call in repo.update_edit_plan_status.call_args_list]
    assert statuses == ["approved"]


def test_apply_job_requires_plan_and_numbers() -> None:
    job = _job({"sermon_id": "s", "final_start": 1.0, "final_end": 2.0})
    result = execute_auto_edit_apply_job(job)
    assert result.success is False
    assert result.error is not None and "plan_id" in result.error

    job2 = _job({
        "sermon_id": "s", "plan_id": 1,
        "final_start": "1.0", "final_end": "2.0",
        "audio_file": AUDIO_FILE, "form_data": _form_data(), "config": CONFIG,
    })
    result = execute_auto_edit_apply_job(job2)
    assert result.success is False
    assert "final_start" in result.error


def test_apply_job_missing_plan_row_fails_before_pipeline(monkeypatch) -> None:
    process = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    repo = Mock()
    repo.update_edit_plan_status.return_value = False
    _stub_repo(monkeypatch, repo)
    job = _job({
        "sermon_id": "draft_123", "plan_id": 12,
        "final_start": 1.0, "final_end": 2.0,
        "audio_file": AUDIO_FILE,
        "form_data": _form_data(),
        "config": CONFIG,
    })
    result = execute_auto_edit_apply_job(job)
    assert result.success is False
    assert "draft_123" in result.message
    process.assert_not_called()


def test_refine_job_calls_refine_with_notes(monkeypatch) -> None:
    from ui.job_executors import execute_auto_edit_refine_job

    refine = Mock(return_value={
        "success": True,
        "sermon_id": "draft_123",
        "start": 120.0,
        "end": 900.0,
        "confidence": 0.9,
        "needs_review": False,
        "evidence": "fresh quote",
        "qa_judgment": "cut",
        "reasoning": "second class only",
    })
    monkeypatch.setattr("sermon_updater.refine_edit_plan", refine)
    job = _job({
        "refine": True,
        "sermon_id": "draft_123",
        "notes": "Keep only the second class",
        "config": CONFIG,
    })
    result = execute_auto_edit_refine_job(job)
    assert result.success is True
    assert result.data["start"] == 120.0
    assert refine.call_args.kwargs["notes"] == "Keep only the second class"
    assert refine.call_args.args[0] == "draft_123"


def test_refine_dispatch_routes_refine_jobs(monkeypatch) -> None:
    refine = Mock(return_value={"success": True, "confidence": 0.8})
    process = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr("sermon_updater.refine_edit_plan", refine)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    job = _job({"refine": True, "sermon_id": "draft_123", "notes": "n", "config": CONFIG})
    result = get_executor(JobType.AUTO_EDIT)(job)
    assert result.success is True
    refine.assert_called_once()
    process.assert_not_called()


def test_refine_job_requires_sermon_id() -> None:
    from ui.job_executors import execute_auto_edit_refine_job

    result = execute_auto_edit_refine_job(_job({"refine": True, "config": CONFIG}))
    assert result.success is False
    assert "sermon_id" in result.error


def test_refine_job_failure_reports_error(monkeypatch) -> None:
    from ui.job_executors import execute_auto_edit_refine_job

    monkeypatch.setattr(
        "sermon_updater.refine_edit_plan",
        Mock(return_value={"success": False, "error": "no timestamped transcript"}),
    )
    job = _job({"refine": True, "sermon_id": "draft_123", "notes": "", "config": CONFIG})
    result = execute_auto_edit_refine_job(job)
    assert result.success is False
    assert "no timestamped transcript" in result.error
