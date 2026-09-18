from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from server.api import mapping
from server.api.db import get_repository
from server.api.routers.auth import require_user
from server.api.schemas import (
    EditPlanOut,
    SermonDetailOut,
    SermonListItem,
    SermonListOut,
    SermonPlanOut,
    TranscriptOut,
)
from server.api.scoping import request_user, scope_rows, visible

router = APIRouter(prefix="/api/sermons", tags=["sermons"])

logger = logging.getLogger(__name__)

_TRANSCRIPT_LIMIT = 50_000

_SORT_KEYS = {"date", "title", "duration"}


class SermonCreateBody(BaseModel):
    title: str
    speaker: str = ""
    recorded_date: str = ""
    series_title: str = ""
    description: str = ""


@router.post("", status_code=201)
def create_draft_sermon(request: Request, body: SermonCreateBody) -> dict:
    user = request_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    sermon_id = f"s-{secrets.token_hex(8)}"
    from ui.database import SermonDatabase, SermonRepository
    from server.api.accounts import get_db_path

    repo = SermonRepository(SermonDatabase(db_path=get_db_path()))
    ok = repo.save_sermon(
        {
            "id": sermon_id,
            "title": body.title.strip() or "Untitled",
            "speaker": body.speaker.strip(),
            "recorded_date": body.recorded_date.strip(),
            "series_title": body.series_title.strip(),
            "description": body.description.strip(),
            "status": "draft",
            "user_id": user.get("id"),
        }
    )
    if not ok:
        raise HTTPException(status_code=500, detail="could not save sermon")
    return {
        "id": sermon_id,
        "title": body.title.strip(),
        "speaker": body.speaker.strip(),
        "recorded_date": body.recorded_date.strip(),
        "series_title": body.series_title.strip(),
        "status": "draft",
    }


def _row_to_list_item(row: dict) -> SermonListItem:
    return SermonListItem(
        id=str(row.get("id") or ""),
        title=str(row.get("title") or ""),
        speaker=str(row.get("speaker") or ""),
        date=str(row.get("recorded_date") or ""),
        duration=mapping.format_duration(row.get("duration")),
        series=str(row.get("series_title") or ""),
        status=str(row.get("status") or ""),
    )


def _row_to_plan(sermon_id: str, row: dict, revisions_total: int) -> EditPlanOut:
    start = row.get("proposed_start")
    if start is None:
        start = row.get("final_start")
    end = row.get("proposed_end")
    if end is None:
        end = row.get("final_end")
    return EditPlanOut(
        sermon_id=sermon_id,
        status=str(row.get("status") or ""),
        revision=int(row.get("revision") or 0),
        revisions_total=revisions_total,
        confidence=mapping.confidence_percent(row.get("confidence")),
        qa_judgment=str(row.get("qa_judgment") or ""),
        evidence=str(row.get("evidence") or ""),
        start_sec=float(start) if start is not None else None,
        end_sec=float(end) if end is not None else None,
        offset_sec=float(row.get("audio_offset") or 0.0),
    )


@router.get("", response_model=SermonListOut)
def list_sermons(
    request: Request,
    search: str = Query(default=""),
    sort: str = Query(default="date"),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> SermonListOut:
    repo = get_repository()
    rows = scope_rows(repo.get_all_sermons(), request_user(request), "sermons")
    needle = search.strip().lower()
    if needle:
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                str(row.get(key) or "")
                for key in ("title", "speaker", "series_title")
            ).lower()
        ]
    key = sort if sort in _SORT_KEYS else "date"
    if key == "title":
        rows.sort(key=lambda row: str(row.get("title") or "").lower())
    elif key == "duration":
        rows.sort(key=lambda row: -(float(row.get("duration") or 0.0)))
    else:
        rows.sort(key=lambda row: str(row.get("recorded_date") or ""), reverse=True)
    total = len(rows)
    if limit is not None:
        rows = rows[offset : offset + limit]
    elif offset:
        rows = rows[offset:]
    items = [_row_to_list_item(row) for row in rows]
    return SermonListOut(items=items, total=total)


@router.get("/{sermon_id}", response_model=SermonDetailOut)
def get_sermon(request: Request, sermon_id: str) -> SermonDetailOut:
    repo = get_repository()
    sermon = repo.get_sermon(sermon_id)
    if sermon is None or not visible(sermon.get("user_id"), request_user(request)):
        raise HTTPException(status_code=404, detail="sermon not found")
    files = repo.get_sermon_files(sermon_id)
    content = sermon.get("content") or {}
    transcript = content.get("transcript_text") or ""
    description = content.get("description") or sermon.get("description")
    try:
        duration_seconds = (
            float(sermon["duration"]) if sermon.get("duration") is not None else None
        )
    except (TypeError, ValueError):
        duration_seconds = None
    return SermonDetailOut(
        id=str(sermon.get("id") or sermon_id),
        title=str(sermon.get("title") or ""),
        speaker=str(sermon.get("speaker") or ""),
        date=str(sermon.get("recorded_date") or ""),
        duration=mapping.format_duration(duration_seconds),
        duration_seconds=duration_seconds,
        series=str(sermon.get("series_title") or ""),
        status=str(sermon.get("status") or ""),
        description=str(description) if description else None,
        files=[
            {
                "file_type": str(item.get("file_type") or ""),
                "file_path": str(item.get("file_path") or ""),
                "file_size": item.get("file_size"),
            }
            for item in files
        ],
        transcript_available=bool(transcript.strip()),
        transcript_length=len(transcript),
    )


@router.get("/{sermon_id}/plan", response_model=SermonPlanOut)
def get_sermon_plan(request: Request, sermon_id: str) -> SermonPlanOut:
    repo = get_repository()
    sermon = repo.get_sermon(sermon_id)
    if sermon is None or not visible(sermon.get("user_id"), request_user(request)):
        raise HTTPException(status_code=404, detail="sermon not found")
    history_rows = repo.get_edit_plan_history(sermon_id)
    history = [
        _row_to_plan(sermon_id, row, len(history_rows)) for row in history_rows
    ]
    current = repo.get_current_edit_plan(sermon_id)
    plan = _row_to_plan(sermon_id, current, len(history_rows)) if current else None
    return SermonPlanOut(plan=plan, history=history)


@router.get("/{sermon_id}/transcript", response_model=TranscriptOut)
def get_sermon_transcript(request: Request, sermon_id: str) -> TranscriptOut:
    repo = get_repository()
    sermon = repo.get_sermon(sermon_id)
    if sermon is None or not visible(sermon.get("user_id"), request_user(request)):
        raise HTTPException(status_code=404, detail="sermon not found")
    content = sermon.get("content") or {}
    full = content.get("transcript_text") or ""
    if len(full) > _TRANSCRIPT_LIMIT:
        marker = f"\n…[truncated at {_TRANSCRIPT_LIMIT} of {len(full)} characters]"
        return TranscriptOut(
            id=str(sermon.get("id") or sermon_id),
            transcript=full[:_TRANSCRIPT_LIMIT] + marker,
            truncated=True,
            total_length=len(full),
        )
    return TranscriptOut(
        id=str(sermon.get("id") or sermon_id),
        transcript=full,
        truncated=False,
        total_length=len(full),
    )


def _remove_sermon_dirs(sermon_id: str, file_paths: list[str]) -> None:
    from pathlib import Path

    try:
        base = Path(__file__).resolve().parent.parent.parent
        root = base / "processed_sermons"
        try:
            import yaml

            cfg_path = base / "config.yaml"
            if cfg_path.exists():
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                configured = str(cfg.get("output_directory") or "").strip()
                if configured:
                    candidate = Path(configured)
                    root = candidate if candidate.is_absolute() else base / candidate
        except Exception as exc:
            logger.warning("Could not resolve output_directory for %s: %s", sermon_id, exc)
        root = root.resolve()
        seen: set[str] = set()
        for raw in file_paths:
            try:
                parent = Path(raw).expanduser().resolve().parent
            except (OSError, RuntimeError):
                continue
            if str(parent) in seen or parent == root or root not in parent.parents:
                continue
            seen.add(str(parent))
            try:
                import shutil

                shutil.rmtree(parent)
                logger.info("Removed sermon directory %s for %s", parent, sermon_id)
            except OSError as exc:
                logger.warning("Could not remove sermon directory %s: %s", parent, exc)
    except Exception as exc:
        logger.warning("Sermon directory cleanup failed for %s: %s", sermon_id, exc)


@router.delete("/{sermon_id}")
def delete_sermon(sermon_id: str, user=Depends(require_user)) -> dict:
    from server.api.accounts import get_db_path
    from ui.database import SermonDatabase, SermonRepository

    repo = SermonRepository(SermonDatabase(db_path=get_db_path()))
    sermon = repo.get_sermon(sermon_id)
    if sermon is None or not visible(sermon.get("user_id"), user):
        raise HTTPException(status_code=404, detail="sermon not found")
    files = repo.get_sermon_files(sermon_id)
    if not repo.delete_sermon(sermon_id):
        raise HTTPException(status_code=500, detail="could not delete sermon")
    _remove_sermon_dirs(
        sermon_id, [str(item.get("file_path") or "") for item in files if item.get("file_path")]
    )
    return {"deleted": True, "id": sermon_id}
