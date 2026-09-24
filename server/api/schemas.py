"""Pydantic schemas mirroring web/src/mock/data.ts shapes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    ok: bool
    version: str
    db_path_ok: bool


class SermonListItem(BaseModel):
    id: str
    title: str
    speaker: str
    date: str
    duration: str
    series: str
    status: str


class SermonListOut(BaseModel):
    items: list[SermonListItem]
    total: int


class SermonFileOut(BaseModel):
    file_type: str
    file_path: str
    file_size: int | None = None


class SermonDetailOut(BaseModel):
    id: str
    title: str
    speaker: str
    date: str
    duration: str
    duration_seconds: float | None = None
    series: str
    status: str
    description: str | None = None
    description_needs_review: bool = False
    files: list[SermonFileOut] = []
    transcript_available: bool = False
    transcript_length: int = 0
    sermonaudio_id: str | None = None
    upload_date: str | None = None
    upload_status: str | None = None
    bible_text: str | None = None
    scripture_reference: str | None = None


class RemoveSegmentOut(BaseModel):
    start_sec: float
    end_sec: float


class EditPlanOut(BaseModel):
    sermon_id: str
    status: str
    revision: int
    revisions_total: int
    confidence: float
    qa_judgment: str
    evidence: str
    start_sec: float | None = None
    end_sec: float | None = None
    remove_segments: list[RemoveSegmentOut] = Field(default_factory=list)
    offset_sec: float = 0.0
    detection_status: str = "ok"
    reasoning: str = ""
    notes: str = ""


class SermonPlanOut(BaseModel):
    plan: EditPlanOut | None = None
    history: list[EditPlanOut] = []


class TranscriptOut(BaseModel):
    id: str
    transcript: str
    truncated: bool = False
    total_length: int = 0


class JobListItem(BaseModel):
    id: str
    type: str
    title: str
    description: str | None = None
    status: str
    created_at: str | None = None
    completed_at: str | None = None
    duration: str
    error: str | None = None


class JobListOut(BaseModel):
    items: list[JobListItem]
    total: int


class JobDetailOut(JobListItem):
    logs: list[str] = []
    parameters: dict[str, Any] = {}
    result: dict[str, Any] | None = None


class StatusOut(BaseModel):
    status: dict[str, Any]
    checked_at: str
