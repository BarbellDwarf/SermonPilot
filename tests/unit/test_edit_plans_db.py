from __future__ import annotations

import sqlite3

import pytest

from ui.database import SermonDatabase, SermonRepository


@pytest.fixture
def repo(tmp_path) -> SermonRepository:
    db = SermonDatabase(db_path=str(tmp_path / "test.db"))
    return SermonRepository(db)


def _insert_sermon(repo: SermonRepository, sermon_id: str) -> None:
    repo.save_sermon({"id": sermon_id, "title": f"Sermon {sermon_id}"})


def _plan(**overrides):
    plan = {
        "proposed_start": 10.0,
        "proposed_end": 20.0,
        "confidence": 0.85,
        "needs_review": True,
        "evidence": "silence gap",
        "qa_judgment": "looks good",
        "reasoning": "trim intro",
        "status": "pending_review",
        "source_path": "audio/clip.wav",
        "notes": "",
    }
    plan.update(overrides)
    return plan


def test_revision_monotonic_across_saves(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    id1 = repo.save_edit_plan_revision("s1", _plan())
    id2 = repo.save_edit_plan_revision("s1", _plan())
    id3 = repo.save_edit_plan_revision("s1", _plan())
    assert (id1, id2, id3) == (1, 2, 3)
    history = repo.get_edit_plan_history("s1")
    assert [row["revision"] for row in history] == [3, 2, 1]


def test_supersede_flips_previous_current_row(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    repo.save_edit_plan_revision("s1", _plan(status="approved"))
    before = repo.get_current_edit_plan("s1")
    assert before["revision"] == 1
    repo.save_edit_plan_revision("s1", _plan())
    history = repo.get_edit_plan_history("s1")
    by_rev = {row["revision"]: row for row in history}
    assert by_rev[1]["status"] == "superseded"
    assert by_rev[2]["status"] == "pending_review"
    assert before["id"] != by_rev[2]["id"]


def test_get_current_returns_latest_non_superseded(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    rev1 = repo.save_edit_plan_revision("s1", _plan(status="reverted"))
    rev2 = repo.save_edit_plan_revision("s1", _plan())
    repo.update_edit_plan_status(rev2, "superseded")
    current = repo.get_current_edit_plan("s1")
    assert current["id"] == rev1
    assert current["revision"] == 1
    assert rev1 != rev2
    assert repo.get_edit_plan_history("s1")[0]["status"] == "superseded"


def test_status_round_trip_with_final_values(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    plan_id = repo.save_edit_plan_revision("s1", _plan())
    assert repo.update_edit_plan_status(
        plan_id,
        "approved",
        notes="looks fine",
        final_start=11.0,
        final_end=19.5,
        applied_media_id="media-123",
    )
    current = repo.get_current_edit_plan("s1")
    assert current["status"] == "approved"
    assert current["final_start"] == 11.0
    assert current["final_end"] == 19.5
    assert current["applied_media_id"] == "media-123"
    assert current["notes"] == "looks fine"
    assert current["reviewed_at"] is not None


def test_invalid_status_rejected(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    plan_id = repo.save_edit_plan_revision("s1", _plan())
    assert not repo.update_edit_plan_status(plan_id, "banana")
    current = repo.get_current_edit_plan("s1")
    assert current["status"] == "pending_review"


def test_unique_sermon_revision_enforced(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    repo.save_edit_plan_revision("s1", _plan())
    with repo.db.get_connection() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO edit_plans (sermon_id, revision) VALUES (?, ?)", ("s1", 1)
        )
        conn.commit()


def test_needs_review_bool_coerced_to_int(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    repo.save_edit_plan_revision("s1", _plan(needs_review=False))
    current = repo.get_current_edit_plan("s1")
    assert current["needs_review"] == 0


def test_detection_status_defaults_to_ok(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    repo.save_edit_plan_revision("s1", _plan())
    assert repo.get_current_edit_plan("s1")["detection_status"] == "ok"


def test_detection_status_unavailable_round_trips(repo: SermonRepository):
    _insert_sermon(repo, "s1")
    repo.save_edit_plan_revision("s1", _plan(detection_status="unavailable"))
    assert repo.get_current_edit_plan("s1")["detection_status"] == "unavailable"
