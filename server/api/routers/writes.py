"""Write-path actions: apply-plan job queuing, job cancel, upload-now.

P5e. Jobs are created through the real ui.job_queue with the requesting
user stamped as user_id (attribution), and an idempotence guard refuses a
second active job for the same sermon.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from server.api.routers.auth import require_user
from server.api.scoping import visible

router = APIRouter(prefix="/api", tags=["write"])

_ACTIVE_STATUSES = ("queued", "running")

_UPLOAD_EXTENSIONS = frozenset(
    {"mkv", "mp4", "mov", "webm", "m4v", "mp3", "wav", "m4a", "flac", "ogg", "mpa"}
)


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


def _ingest_base() -> Path:
    return Path(os.environ.get("SERMONPILOT_RAW_INGEST", "/data/raw_ingest"))


def _upload_cap_bytes() -> int:
    try:
        gb = float(os.environ.get("SERMONPILOT_UPLOAD_GB", "30"))
    except ValueError:
        gb = 30.0
    return int(gb * 1024**3)


@router.post("/sermons/upload", status_code=201)
async def upload_sermon(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    speaker: str = Form(default=""),
    recorded_date: str = Form(default=""),
    event_type: str = Form(default=""),
    user=Depends(require_user),
):
    missing = [
        name
        for name, value in (
            ("speaker", speaker),
            ("recorded_date", recorded_date),
            ("event_type", event_type),
        )
        if not value.strip()
    ]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"missing required fields: {', '.join(missing)}"
        )
    original = Path(file.filename or "").name
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in _UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file type: .{ext or '?'} "
            f"(allowed: {', '.join(sorted(_UPLOAD_EXTENSIONS))})",
        )
    user_dir = _ingest_base() / re.sub(r"[^A-Za-z0-9_-]", "_", user.get("id") or "anon")
    user_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", original) or "upload"
    dest = user_dir / f"{int(time.time() * 1000)}_{safe}"
    cap = _upload_cap_bytes()
    written = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > cap:
                    raise HTTPException(
                        status_code=413,
                        detail=f"file exceeds the upload cap of "
                        f"{os.environ.get('SERMONPILOT_UPLOAD_GB', '30')} GB",
                    )
                out.write(chunk)
    except HTTPException:
        try:
            dest.unlink()
        except OSError:
            pass
        raise
    finally:
        await file.close()

    sermon_id = f"s-{secrets.token_hex(8)}"
    from server.api.accounts import get_db_path
    from ui.database import SermonDatabase, SermonRepository

    repo = SermonRepository(SermonDatabase(db_path=get_db_path()))
    ok = repo.save_sermon(
        {
            "id": sermon_id,
            "title": title.strip() or original or "Untitled",
            "speaker": speaker.strip(),
            "recorded_date": recorded_date.strip(),
            "status": "draft",
            "user_id": user.get("id"),
        }
    )
    if not ok:
        try:
            dest.unlink()
        except OSError:
            pass
        raise HTTPException(status_code=500, detail="could not save sermon")

    from ui.job_queue import JobType

    form_data = {
        "speaker_name": speaker.strip(),
        "recorded_date": recorded_date.strip(),
        "event_type": event_type.strip(),
        "title": title.strip() or None,
        "uploaded_file_path": str(dest),
        "original_filename": original,
    }
    job_id = _queue().add_job(
        JobType.SERMON_PROCESSING,
        f"New Sermon: {title.strip() or original}",
        f"Processing new sermon by {speaker.strip()}",
        parameters={
            "sermon_id": sermon_id,
            "form_data": form_data,
            "config": {},
            "processing_type": "new_sermon",
            "uploaded_file_path": str(dest),
        },
        priority=8,
        user_id=user.get("id"),
    )
    return {
        "id": sermon_id,
        "job_id": job_id,
        "status": "queued",
        "filename": dest.name,
    }
