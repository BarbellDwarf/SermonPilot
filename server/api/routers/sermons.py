from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from server.api import mapping
from server.api.db import get_repository
from server.api.schemas import (
    EditPlanOut,
    SermonDetailOut,
    SermonListItem,
    SermonListOut,
    SermonPlanOut,
)
from server.api.scoping import request_user, scope_rows, visible

router = APIRouter(prefix="/api/sermons", tags=["sermons"])

_SORT_KEYS = {"date", "title", "duration"}


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
    items = [_row_to_list_item(row) for row in rows]
    return SermonListOut(items=items, total=len(items))


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
