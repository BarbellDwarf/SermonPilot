from __future__ import annotations

from datetime import datetime

from ui.job_executors import execute_metadata_update_job
from ui.job_queue import Job, JobStatus, JobType


def _job(job_type: JobType, **parameters) -> Job:
    return Job(
        id="job-1",
        type=job_type,
        title="metadata",
        description="metadata update",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=parameters,
    )


def test_metadata_update_fails_when_every_sermon_raises(monkeypatch):
    import sermon_updater

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(sermon_updater, "process_single_sermon", boom)
    job = _job(
        JobType.METADATA_UPDATE,
        sermon_ids=["s-1", "s-2"],
        actions={"generate_description": True},
    )

    result = execute_metadata_update_job(job)

    assert result.success is False
    assert result.data is not None
    assert result.data["failed"] == 2
    assert result.data["completed"] == 0
