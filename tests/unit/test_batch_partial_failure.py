"""A batch with a failed item must never report plain success.

The per-item failures used to be counted into the summary and then dropped: the
job ended COMPLETED, so the console showed a green result for work that partly
did not happen. The failed item names are now part of the outcome.
"""

from __future__ import annotations

from datetime import datetime

from ui.job_executors import execute_batch_processing_job
from ui.job_queue import Job, JobStatus, JobType

CONFIG = {
    "api_key": "test-api-key",
    "broadcaster_id": "test-broadcaster",
    "output_directory": "test_output",
}


def _job(sermon_ids: list[str]) -> Job:
    return Job(
        id="job-batch",
        type=JobType.BATCH_PROCESSING,
        title="Batch",
        description="Batch processing",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters={
            "sermon_ids": sermon_ids,
            "actions": {"generate_description": True},
            "config": {},
        },
    )


def _patch(monkeypatch, outcomes: dict[str, str]) -> None:
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: CONFIG)

    import sermon_updater

    def fake_process(sermon_id, **kwargs):
        outcome = outcomes.get(sermon_id, "ok")
        if outcome == "fail":
            raise RuntimeError(f"per-item failure for {sermon_id}")
        if outcome == "metadata-fail":
            return {
                "action": "processed",
                "completed": [],
                "description_needs_review": True,
                "description_error": "description generation failed",
            }
        return {"action": "processed", "completed": ["description"]}

    monkeypatch.setattr(sermon_updater, "process_single_sermon", fake_process)


def test_batch_with_a_failed_item_is_not_plain_success(monkeypatch) -> None:
    _patch(monkeypatch, {"s-good": "ok", "s-bad": "fail"})

    result = execute_batch_processing_job(_job(["s-good", "s-bad"]))

    assert result.success is False
    assert "s-bad" in (result.message or "")
    assert result.data is not None
    assert result.data["failed"] == 1
    assert any(
        detail.get("sermon_id") == "s-bad" and detail.get("status") == "error"
        for detail in result.data["details"]
    )


def test_batch_with_a_failed_metadata_result_is_not_plain_success(monkeypatch) -> None:
    _patch(monkeypatch, {"s-good": "ok", "s-bad": "metadata-fail"})

    result = execute_batch_processing_job(_job(["s-good", "s-bad"]))

    assert result.success is False
    assert "s-bad" in (result.message or "")
    assert result.data is not None
    assert result.data["failed"] == 1


def test_batch_without_failures_still_reports_success(monkeypatch) -> None:
    _patch(monkeypatch, {"s-good": "ok", "s-better": "ok"})

    result = execute_batch_processing_job(_job(["s-good", "s-better"]))

    assert result.success is True
    assert result.data is not None and result.data["failed"] == 0
