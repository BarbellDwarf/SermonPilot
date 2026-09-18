from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from server.api import mapping
from server.api.db import query_job, query_jobs
from server.api.schemas import JobDetailOut, JobListItem, JobListOut
from server.api.scoping import ownership_map, request_user, scope_rows, visible

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _row_to_list_item(row: dict) -> JobListItem:
    return JobListItem(
        id=str(row.get("id") or ""),
        type=str(row.get("type") or ""),
        title=str(row.get("title") or ""),
        description=row.get("description"),
        status=str(row.get("status") or ""),
        created_at=str(row.get("created_at")) if row.get("created_at") else None,
        completed_at=str(row.get("completed_at")) if row.get("completed_at") else None,
        duration=mapping.job_duration(row.get("created_at"), row.get("completed_at")),
        error=mapping.job_error(row.get("result")),
    )


@router.get("", response_model=JobListOut)
def list_jobs(
    request: Request,
    status: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
) -> JobListOut:
    rows = scope_rows(
        query_jobs(status=status or None, limit=limit), request_user(request), "background_jobs"
    )
    items = [_row_to_list_item(row) for row in rows]
    return JobListOut(items=items, total=len(items))


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job(request: Request, job_id: str) -> JobDetailOut:
    row = query_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    owner = row.get("user_id")
    if owner is None and "user_id" not in row:
        owner = ownership_map("background_jobs").get(job_id)
    if not visible(owner, request_user(request)):
        raise HTTPException(status_code=404, detail="job not found")
    base = _row_to_list_item(row)
    logs = mapping.parse_json(row.get("logs"), [])
    parameters = mapping.parse_json(row.get("parameters"), {})
    result = mapping.parse_json(row.get("result"), None)
    return JobDetailOut(
        **base.model_dump(),
        logs=[str(line) for line in logs] if isinstance(logs, list) else [],
        parameters=parameters if isinstance(parameters, dict) else {},
        result=result if isinstance(result, dict) else None,
    )
