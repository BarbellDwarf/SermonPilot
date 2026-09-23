"""A metadata regenerate must do real work or fail, never report success.

The web console's "Regenerate description" queues a METADATA_UPDATE job.
A skipped record or unusable model output previously counted as completed
and the job reported success; these tests pin the failure.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from ui.job_executors import execute_metadata_update_job  # noqa: E402
from ui.job_queue import Job, JobStatus, JobType  # noqa: E402


def _job(params: dict[str, Any]) -> Job:
    return Job(
        id="job-meta-1",
        type=JobType.METADATA_UPDATE,
        title="Regenerate description",
        description="Regenerate description",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=params,
    )


def _params() -> dict[str, Any]:
    return {
        "sermon_ids": ["sermon-1"],
        "actions": {"generate_description": True},
        "config": {"api_key": "k"},
    }


def test_skipped_regenerate_reports_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "sermon_updater.process_single_sermon",
        Mock(
            return_value={
                "action": "skipped",
                "reason": "No updates needed - adequate content exists",
            }
        ),
    )

    result = execute_metadata_update_job(_job(_params()))

    assert result.success is False
    assert "No updates needed" in (result.error or "")


def test_unusable_description_output_reports_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "sermon_updater.process_single_sermon",
        Mock(
            return_value={
                "action": "processed",
                "completed": [],
                "skipped": ["description"],
                "description_needs_review": True,
                "description_error": (
                    "description generation produced no usable text after cleanup"
                ),
            }
        ),
    )

    result = execute_metadata_update_job(_job(_params()))

    assert result.success is False
    assert "no usable text" in (result.error or "")


def test_missing_requested_description_reports_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "sermon_updater.process_single_sermon",
        Mock(return_value={"action": "processed", "completed": [], "skipped": ["description"]}),
    )

    result = execute_metadata_update_job(_job(_params()))

    assert result.success is False
    assert "description was not generated" in (result.error or "")


def test_real_regenerate_reports_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "sermon_updater.process_single_sermon",
        Mock(return_value={"action": "processed", "completed": ["description"], "skipped": []}),
    )

    result = execute_metadata_update_job(_job(_params()))

    assert result.success is True
    assert result.error is None
