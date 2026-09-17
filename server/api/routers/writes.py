"""Write-path actions: apply-plan job queuing, job cancel, upload-now.

P5e. Jobs are created through the real ui.job_queue with the requesting
user stamped as user_id (attribution), and an idempotence guard refuses a
second active job for the same sermon.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.api.routers.auth import require_user
from server.api.scoping import visible

router = APIRouter(prefix="/api", tags=["write"])

_ACTIVE_STATUSES = ("queued", "running")


def _sermon_owner(sermon_id: str) -> str | None:
    from server.api.db import ReadOnlySermonDatabase

    try:
        with ReadOnlySermonDatabase().get_connection() as conn:
            row = conn.execute("SELECT user_id FROM sermons WHERE id = ?", (sermon_id,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["user_id"] if row else None


def _queue():
    from ui.job_queue import get_job_queue

    return get_job_queue()


def _active_job_for(sermon_id: str) -> dict[str, Any] | None:
    try:
        from server.api.db import ReadOnlySermonDatabase

        with ReadOnlySermonDatabase().get_connection() as conn:
            row = conn.execute(
                "SELECT id, type, status FROM background_jobs"
                " WHERE status IN ('queued', 'running')"
                " AND (parameters LIKE ? OR parameters LIKE ?)"
                " ORDER BY created_at DESC LIMIT 1",
                (f'%"{sermon_id}"%', f"%{sermon_id}%"),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None


class ApplyBody(BaseModel):
    start: float
    end: float
    audio_offset: float = 0.0
    render_only: bool = True
    re_detect: bool = False
    plan_id: str | None = None


@router.post("/sermons/{sermon_id}/plan/apply", status_code=202)
def apply_plan(sermon_id: str, body: ApplyBody, request: Request, user=Depends(require_user)):
    owner = _sermon_owner(sermon_id)
    if owner is None or not visible(owner, user):
        raise HTTPException(status_code=404, detail="sermon not found")
    if body.end <= body.start:
        raise HTTPException(status_code=422, detail="end must be greater than start")
    active = _active_job_for(sermon_id)
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "an active job already exists for this sermon",
                "job_id": active["id"],
            },
        )
    from ui.job_queue import JobType

    job_id = _queue().add_job(
        JobType.AUTO_EDIT_APPLY,
        f"Apply edit: {sermon_id}",
        f"Library apply for {sermon_id}",
        parameters={
            "sermon_id": sermon_id,
            "start": body.start,
            "end": body.end,
            "audio_offset": body.audio_offset,
            "render_only": body.render_only,
            "re_detect": body.re_detect,
            "plan_id": body.plan_id,
        },
        user_id=user.get("id"),
    )
    return {"job_id": job_id, "status": "queued"}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user=Depends(require_user)):
    from server.api.db import query_job

    row = query_job(job_id)
    if row is None or not visible(row.get("user_id"), user):
        raise HTTPException(status_code=404, detail="job not found")
    cancelled = _queue().cancel_job(job_id)
    return {"cancelled": cancelled, "job_id": job_id}


@router.post("/sermons/{sermon_id}/upload", status_code=202)
def upload_now(sermon_id: str, user=Depends(require_user)):
    owner = _sermon_owner(sermon_id)
    if owner is None or not visible(owner, user):
        raise HTTPException(status_code=404, detail="sermon not found")
    active = _active_job_for(sermon_id)
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "an active job already exists for this sermon",
                "job_id": active["id"],
            },
        )
    from ui.job_queue import JobType

    job_id = _queue().add_job(
        JobType.SERMON_PUBLISH,
        f"Publish: {sermon_id}",
        f"Upload draft to SermonAudio for {sermon_id}",
        parameters={"sermon_id": sermon_id},
        user_id=user.get("id"),
    )
    return {"job_id": job_id, "status": "queued"}
