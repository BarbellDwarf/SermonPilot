"""Metadata generation must read the edit's kept transcript, not the full source."""

from __future__ import annotations

import json
from pathlib import Path

from src.auto_edit import transcript_for_llm

FULL = "before opening removed sentinel closing after"

SEGMENTS = [
    {"start": 0.0, "end": 5.0, "text": "before"},
    {"start": 11.0, "end": 15.0, "text": "opening"},
    {"start": 21.0, "end": 29.0, "text": "removed sentinel"},
    {"start": 31.0, "end": 35.0, "text": "closing"},
    {"start": 45.0, "end": 50.0, "text": "after"},
]

PLAN_ROW = {
    "proposed_start": 10.0,
    "proposed_end": 40.0,
    "remove_segments": json.dumps([{"start_sec": 20.0, "end_sec": 30.0}]),
}


def _record(tmp_path: Path, **overrides) -> dict:
    timestamps = tmp_path / "transcript_timestamps.json"
    timestamps.write_text(json.dumps(SEGMENTS), encoding="utf-8")
    record = {
        "content": {"transcript_text": FULL},
        "file_paths": {"transcript_timestamps": str(timestamps)},
    }
    record.update(overrides)
    return record


def test_no_plan_returns_the_full_transcript(tmp_path: Path) -> None:
    assert transcript_for_llm(_record(tmp_path)) == FULL


def test_plan_with_removed_ranges_excludes_the_removed_text(tmp_path: Path) -> None:
    text = transcript_for_llm(_record(tmp_path), PLAN_ROW)

    assert "removed sentinel" not in text
    assert text == "opening closing"


def test_a_rejected_plan_falls_back_to_the_full_transcript(tmp_path: Path) -> None:
    plan = dict(PLAN_ROW, status="rejected")

    assert transcript_for_llm(_record(tmp_path), plan) == FULL


def test_a_finalized_transcript_wins_over_the_full_one(tmp_path: Path) -> None:
    record = _record(
        tmp_path,
        content={
            "transcript_text": FULL,
            "finalized_transcript": "finalized text",
        },
    )

    assert transcript_for_llm(record, PLAN_ROW) == "finalized text"
