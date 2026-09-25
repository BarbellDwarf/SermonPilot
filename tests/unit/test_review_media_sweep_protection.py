"""The review-media sweep must not touch a review that is still live.

A review is live while a user is deciding on it (edit plan ``pending_review``)
and while a non-terminal job still references its artifacts. Retention may
only discard reviews that have reached a terminal outcome.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.review_media import MARKER_FILENAME, sweep_abandoned_reviews, write_review_marker
from ui.database import SermonDatabase, SermonRepository

JOBS_DDL = """
    CREATE TABLE IF NOT EXISTS background_jobs (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL,
        progress REAL DEFAULT 0,
        parameters TEXT,
        result TEXT,
        logs TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        can_cancel BOOLEAN DEFAULT 1,
        can_retry BOOLEAN DEFAULT 1,
        priority INTEGER DEFAULT 5
    )
"""


def _seed_review(root: Path, name: str) -> Path:
    review_dir = root / "speaker" / "series" / name
    review_dir.mkdir(parents=True, exist_ok=True)
    write_review_marker(review_dir, name)
    (review_dir / "Sermon - Original.mp4").write_bytes(b"original")
    (review_dir / "metadata.json").write_text("{}", encoding="utf-8")
    return review_dir


def _make_repo(tmp_path: Path) -> SermonRepository:
    db = SermonDatabase(db_path=str(tmp_path / "sweep.db"))
    db.init_database()
    with db.get_connection() as conn:
        conn.execute(JOBS_DDL)
        conn.commit()
    return SermonRepository(db)


def _link_review(repo: SermonRepository, sermon_id: str, review_dir: Path) -> None:
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT INTO sermons (id, title, speaker, recorded_date, status)"
            " VALUES (?, ?, 'Speaker', '2024-01-01', 'draft')",
            (sermon_id, sermon_id),
        )
        conn.execute(
            "INSERT INTO sermon_files (sermon_id, file_type, file_path)"
            " VALUES (?, 'metadata', ?)",
            (sermon_id, str(review_dir / "metadata.json")),
        )
        conn.commit()


def _add_pending_plan(repo: SermonRepository, sermon_id: str) -> None:
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT INTO edit_plans (sermon_id, revision, status) VALUES (?, 1, 'pending_review')",
            (sermon_id,),
        )
        conn.commit()


def _add_job(repo: SermonRepository, job_id: str, status: str, parameters: dict) -> None:
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT INTO background_jobs (id, type, title, description, status, parameters)"
            " VALUES (?, 'sermon_processing', ?, 'test job', ?, ?)",
            (job_id, job_id, status, json.dumps(parameters)),
        )
        conn.commit()


def _age(review_dir: Path, seconds: float) -> None:
    os.utime(review_dir / MARKER_FILENAME, (seconds, seconds))


def test_sweep_keeps_a_review_whose_plan_is_still_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "1")
    monkeypatch.delenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", raising=False)

    repo = _make_repo(tmp_path)
    in_progress = _seed_review(tmp_path / "reviews", "in-progress")
    abandoned = _seed_review(tmp_path / "reviews", "abandoned")
    _link_review(repo, "s-in-progress", in_progress)
    _add_pending_plan(repo, "s-in-progress")
    _age(in_progress, 1)
    _age(abandoned, 1)

    result = sweep_abandoned_reviews({"output_directory": str(tmp_path / "out")}, repo=repo)

    assert in_progress.is_dir()
    assert str(in_progress) not in result["removed"]
    assert not abandoned.exists()
    assert str(abandoned) in result["removed"]


@pytest.mark.parametrize("status", ["queued", "running", "paused"])
def test_sweep_keeps_artifacts_referenced_by_a_non_terminal_job(
    tmp_path, monkeypatch, status
):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "1")
    monkeypatch.delenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", raising=False)

    repo = _make_repo(tmp_path)
    busy = _seed_review(tmp_path / "reviews", "busy-job")
    idle = _seed_review(tmp_path / "reviews", "idle-job")
    _add_job(repo, "j-busy", status, {"output_dir": str(busy)})
    _add_job(repo, "j-idle", "completed", {"output_dir": str(idle)})
    _age(busy, 1)
    _age(idle, 1)

    result = sweep_abandoned_reviews({"output_directory": str(tmp_path / "out")}, repo=repo)

    assert busy.is_dir()
    assert str(busy) not in result["removed"]
    assert not idle.exists()
    assert str(idle) in result["removed"]
