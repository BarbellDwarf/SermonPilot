"""Write-path actions: apply-plan job queuing, job cancel, upload-now.

P5e. Jobs are created through the real ui.job_queue with the requesting
user stamped as user_id (attribution), and an idempotence guard refuses a
second active job for the same sermon.

A job that reached a terminal state within _ACTIVE_JOB_GRACE_SECONDS still
counts as active, so a fast double-click cannot enqueue a duplicate behind a
job that completed between the two clicks.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from server.api.routers.auth import require_user
from server.api.scoping import visible

router = APIRouter(prefix="/api", tags=["write"])

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("queued", "running")

_ACTIVE_JOB_GRACE_SECONDS = 2.0

_UPLOAD_EXTENSIONS = frozenset(
    {"mkv", "mp4", "mov", "webm", "m4v", "mp3", "wav", "m4a", "flac", "ogg", "mpa"}
)

_BRANDING_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "webp"})

_VIDEO_EXTENSIONS = frozenset({"mkv", "mp4", "mov", "webm", "m4v"})
_AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "m4a", "flac", "ogg", "mpa"})


def _safe_user_segment(user_id: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", user_id or "anon") or "anon"


def _safe_filename(name: str, fallback: str = "file") -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(name).name.strip())
    return safe or fallback


def _human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _kind_for_ext(ext: str) -> str:
    if ext in _VIDEO_EXTENSIONS:
        return "video"
    if ext in _AUDIO_EXTENSIONS:
        return "audio"
    return ext or "unknown"


def _stat_path(path: Path) -> dict[str, Any]:
    try:
        st = path.stat()
    except OSError:
        return {"exists": False, "size": None, "size_human": "—", "ext": "", "kind": "—", "name": path.name}  # noqa: E501
    ext = path.suffix.lower().lstrip(".")
    size = st.st_size
    return {
        "exists": True,
        "is_file": path.is_file(),
        "size": size,
        "size_human": _human_size(size),
        "ext": ext,
        "kind": _kind_for_ext(ext),
        "name": path.name,
    }


def _branding_base() -> Path:
    return Path(os.environ.get("SERMONPILOT_BRANDING_DIR", "/data/branding"))


def _save_draft_sermon(
    *,
    sermon_id: str,
    title: str,
    speaker: str,
    recorded_date: str,
    series_title: str = "",
    description: str = "",
    user_id: str | None,
) -> None:
    from server.api.accounts import get_db_path
    from ui.database import SermonDatabase, SermonRepository

    repo = SermonRepository(SermonDatabase(db_path=get_db_path()))
    ok = repo.save_sermon(
        {
            "id": sermon_id,
            "title": title.strip() or "Untitled",
            "speaker": speaker.strip(),
            "recorded_date": recorded_date.strip(),
            "series_title": series_title.strip(),
            "description": description.strip(),
            "status": "draft",
            "user_id": user_id,
        }
    )
    if not ok:
        raise HTTPException(status_code=500, detail="could not save sermon")


def _output_dir_for(user: dict, requested: str) -> str:
    """Resolve the per-run output override, falling back to the user's default."""
    from server.api.routers.userdata import resolve_user_output_dir, validate_output_dir

    raw = (requested or "").strip()
    if not raw:
        return str(resolve_user_output_dir(user))
    return validate_output_dir(raw, user)


def _enqueue_sermon_processing(
    *,
    sermon_id: str,
    source_path: str,
    original_name: str,
    title: str,
    speaker: str,
    recorded_date: str,
    event_type: str,
    series_title: str = "",
    bible_text: str = "",
    skip_audio: bool = False,
    skip_transcription: bool = False,
    skip_ai_generation: bool = False,
    dry_run: bool = False,
    auto_edit_enabled: bool = False,
    auto_edit_mode: str | None = None,
    logo_path: str = "",
    fade_to_black: bool = True,
    output_dir: str | None = None,
    user_id: str | None,
) -> str:
    from ui.job_queue import JobType

    if auto_edit_enabled and auto_edit_mode not in ("interactive", "auto"):
        auto_edit_mode = "interactive"
    if not auto_edit_enabled:
        auto_edit_mode = None
    form_data = {
        "speaker_name": speaker.strip(),
        "recorded_date": recorded_date.strip(),
        "event_type": event_type.strip() or "Sunday Service",
        "bible_text": bible_text.strip() or None,
        "title": title.strip() or None,
        "series_title": series_title.strip() or None,
        "skip_audio": bool(skip_audio),
        "skip_transcription": bool(skip_transcription),
        "skip_ai_generation": bool(skip_ai_generation),
        "dry_run": bool(dry_run),
        "auto_edit_enabled": bool(auto_edit_enabled),
        "auto_edit_mode": auto_edit_mode,
        "auto_edit_logo_path": logo_path.strip(),
        "logo_path": logo_path.strip(),
        "auto_edit_fade_to_black": bool(fade_to_black),
        "fade_to_black": bool(fade_to_black),
        "uploaded_file_path": source_path,
        "original_filename": original_name,
    }
    return _queue().add_job(
        JobType.SERMON_PROCESSING,
        f"New Sermon: {title.strip() or original_name}",
        f"Processing new sermon by {speaker.strip()}",
        parameters={
            "sermon_id": sermon_id,
            "form_data": form_data,
            "config": {},
            "processing_type": "new_sermon",
            "uploaded_file_path": source_path,
            "auto_edit_enabled": bool(auto_edit_enabled),
            "auto_edit_mode": auto_edit_mode,
            "output_dir": output_dir,
            "user_id": user_id,
        },
        priority=8,
        user_id=user_id,
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

        cutoff = (datetime.now() - timedelta(seconds=_ACTIVE_JOB_GRACE_SECONDS)).isoformat()
        with ReadOnlySermonDatabase().get_connection() as conn:
            row = conn.execute(
                "SELECT id, type, status FROM background_jobs"
                " WHERE (status IN (?, ?)"
                "        OR (status IN ('completed', 'failed')"
                "            AND completed_at IS NOT NULL"
                "            AND datetime(completed_at) >= datetime(?)))"
                " AND (parameters LIKE ? OR parameters LIKE ?)"
                " ORDER BY created_at DESC LIMIT 1",
                (
                    *_ACTIVE_STATUSES,
                    cutoff,
                    f'%"{sermon_id}"%',
                    f"%{sermon_id}%",
                ),
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
    series_title: str = Form(default=""),
    bible_text: str = Form(default=""),
    scripture: str = Form(default=""),
    skip_audio: bool = Form(default=False),
    skip_transcription: bool = Form(default=False),
    skip_ai_generation: bool = Form(default=False),
    dry_run: bool = Form(default=False),
    auto_edit_enabled: bool = Form(default=False),
    auto_edit_mode: str | None = Form(default=None),
    logo_path: str = Form(default=""),
    auto_edit_logo_path: str = Form(default=""),
    fade_to_black: bool = Form(default=True),
    output_dir: str = Form(default=""),
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
    try:
        _save_draft_sermon(
            sermon_id=sermon_id,
            title=title.strip() or original or "Untitled",
            speaker=speaker.strip(),
            recorded_date=recorded_date.strip(),
            series_title=series_title.strip(),
            user_id=user.get("id"),
        )
    except HTTPException:
        try:
            dest.unlink()
        except OSError:
            pass
        raise

    resolved_logo = (logo_path or auto_edit_logo_path).strip()
    resolved_bible = (bible_text or scripture).strip()
    if auto_edit_mode not in (None, "interactive", "auto"):
        raise HTTPException(status_code=422, detail="auto_edit_mode must be interactive or auto")
    job_id = _enqueue_sermon_processing(
        sermon_id=sermon_id,
        source_path=str(dest),
        original_name=original,
        title=title.strip() or original or "Untitled",
        speaker=speaker.strip(),
        recorded_date=recorded_date.strip(),
        event_type=event_type.strip() or "Sunday Service",
        series_title=series_title.strip(),
        bible_text=resolved_bible,
        skip_audio=skip_audio,
        skip_transcription=skip_transcription,
        skip_ai_generation=skip_ai_generation,
        dry_run=dry_run,
        auto_edit_enabled=auto_edit_enabled,
        auto_edit_mode=auto_edit_mode,
        logo_path=resolved_logo,
        fade_to_black=fade_to_black,
        output_dir=_output_dir_for(user, output_dir),
        user_id=user.get("id"),
    )
    return {
        "id": sermon_id,
        "job_id": job_id,
        "status": "queued",
        "filename": dest.name,
    }


class ServerPathBody(BaseModel):
    container_path: str = ""
    title: str = ""
    speaker: str = ""
    recorded_date: str = ""
    event_type: str = "Sunday Service"
    series_title: str = ""
    bible_text: str = ""
    scripture: str = ""
    skip_audio: bool = False
    skip_transcription: bool = False
    skip_ai_generation: bool = False
    dry_run: bool = False
    auto_edit_enabled: bool = False
    auto_edit_mode: str | None = None
    logo_path: str = ""
    auto_edit_logo_path: str = ""
    fade_to_black: bool = True
    output_dir: str = ""


@router.get("/sermons/server-path/stat")
def server_path_stat(path: str = "", user=Depends(require_user)) -> dict[str, Any]:
    candidate = Path(path.strip()).expanduser() if path.strip() else None
    if candidate is None or not path.strip().startswith("/"):
        return {"exists": False, "size": None, "size_human": "—", "ext": "", "kind": "—", "name": ""}  # noqa: E501
    return _stat_path(candidate)


@router.post("/sermons/server-path", status_code=201)
def create_sermon_from_server_path(body: ServerPathBody, user=Depends(require_user)):
    missing = [
        name
        for name, value in (
            ("container_path", body.container_path),
            ("title", body.title),
            ("speaker", body.speaker),
            ("recorded_date", body.recorded_date),
        )
        if not (value or "").strip()
    ]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"missing required fields: {', '.join(missing)}"
        )
    if body.container_path.strip().startswith("remote:"):
        from server.api.routers.cloud import resolve_remote_uri

        resolved = resolve_remote_uri(user.get("id"), body.container_path.strip())
        if not resolved:
            raise HTTPException(status_code=422, detail="invalid remote path")
        source_path = resolved
        original_name = body.container_path.strip().rstrip("/").rsplit("/", 1)[-1]
        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
        info = {"size": None, "size_human": "—", "ext": ext, "kind": _kind_for_ext(ext)}
    else:
        if not body.container_path.strip().startswith("/"):
            raise HTTPException(status_code=422, detail="container_path must be absolute")
        source = Path(body.container_path.strip()).expanduser()
        info = _stat_path(source)
        if not info["exists"] or not source.is_file():
            raise HTTPException(status_code=422, detail="container_path does not exist")
        ext = info["ext"]
        source_path = str(source)
        original_name = source.name
    if ext not in _UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file type: .{ext or '?'} "
            f"(allowed: {', '.join(sorted(_UPLOAD_EXTENSIONS))})",
        )
    if body.auto_edit_mode not in (None, "interactive", "auto"):
        raise HTTPException(status_code=422, detail="auto_edit_mode must be interactive or auto")

    sermon_id = f"s-{secrets.token_hex(8)}"
    _save_draft_sermon(
        sermon_id=sermon_id,
        title=body.title,
        speaker=body.speaker,
        recorded_date=body.recorded_date,
        series_title=body.series_title,
        user_id=user.get("id"),
    )
    resolved_logo = (body.logo_path or body.auto_edit_logo_path).strip()
    resolved_bible = (body.bible_text or body.scripture).strip()
    job_id = _enqueue_sermon_processing(
        sermon_id=sermon_id,
        source_path=source_path,
        original_name=original_name,
        title=body.title,
        speaker=body.speaker,
        recorded_date=body.recorded_date,
        event_type=body.event_type or "Sunday Service",
        series_title=body.series_title,
        bible_text=resolved_bible,
        skip_audio=body.skip_audio,
        skip_transcription=body.skip_transcription,
        skip_ai_generation=body.skip_ai_generation,
        dry_run=body.dry_run,
        auto_edit_enabled=body.auto_edit_enabled,
        auto_edit_mode=body.auto_edit_mode,
        logo_path=resolved_logo,
        fade_to_black=body.fade_to_black,
        output_dir=_output_dir_for(user, body.output_dir),
        user_id=user.get("id"),
    )
    return {
        "id": sermon_id,
        "job_id": job_id,
        "status": "queued",
        "filename": original_name,
        "size": info["size"],
        "size_human": info["size_human"],
        "ext": ext,
        "kind": info["kind"],
    }


@router.get("/branding")
def list_branding(user=Depends(require_user)) -> dict[str, Any]:
    base = _branding_base()
    user_dir = base / _safe_user_segment(user.get("id"))
    user_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(user_dir, 0o700)
    except OSError:
        pass
    _adopt_legacy_branding(base, user_dir)
    items: list[dict[str, Any]] = []
    if user_dir.is_dir():
        for entry in sorted(user_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower().lstrip(".") in _BRANDING_EXTENSIONS:
                items.append({"name": entry.name, "path": f"{user_dir.name}/{entry.name}"})
    return {"items": items}


def _adopt_legacy_branding(base: Path, user_dir: Path) -> None:
    """One-time, idempotent move of flat-root cards into the listing user's dir."""
    if not base.is_dir():
        return
    adopted = 0
    for entry in sorted(base.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower().lstrip(".") not in _BRANDING_EXTENSIONS:
            continue
        dest = user_dir / entry.name
        if dest.exists():
            stem, suffix = entry.stem, entry.suffix
            counter = 1
            while (user_dir / f"{stem}-{counter}{suffix}").exists():
                counter += 1
            dest = user_dir / f"{stem}-{counter}{suffix}"
        try:
            shutil.move(str(entry), str(dest))
        except OSError as exc:
            logger.warning("Could not adopt legacy branding file %s: %s", entry.name, exc)
            continue
        adopted += 1
    if adopted:
        logger.info("Adopted %d legacy branding file(s) into %s", adopted, user_dir.name)


@router.post("/branding", status_code=201)
async def upload_branding(file: UploadFile = File(...), user=Depends(require_user)):
    original = _safe_filename(file.filename or "", "card")
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in _BRANDING_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported image type: .{ext or '?'} "
            f"(allowed: {', '.join(sorted(_BRANDING_EXTENSIONS))})",
        )
    user_dir = _branding_base() / _safe_user_segment(user.get("id"))
    user_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(user_dir, 0o700)
    except OSError:
        pass
    dest = user_dir / f"{int(time.time() * 1000)}_{original}"
    data = await file.read()
    await file.close()
    if not data:
        raise HTTPException(status_code=422, detail="empty file")
    dest.write_bytes(data)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    return {"path": f"{user_dir.name}/{dest.name}", "filename": dest.name}
