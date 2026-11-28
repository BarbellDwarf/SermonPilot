from __future__ import annotations

import pytest

from ui.auto_edit_apply import _build_apply_kwargs
from ui.database import SermonDatabase, SermonRepository


@pytest.fixture
def repo(tmp_path) -> SermonRepository:
    db = SermonDatabase(db_path=str(tmp_path / "test.db"))
    return SermonRepository(db)


def _plan() -> dict:
    return {
        "proposed_start": 10.0,
        "proposed_end": 20.0,
        "confidence": 0.8,
        "needs_review": True,
        "evidence": "x",
        "qa_judgment": "cut",
        "reasoning": "y",
        "status": "pending_review",
        "source_path": "a.mp4",
        "notes": "",
    }


def test_render_only_kwargs_use_dry_run():
    kwargs = _build_apply_kwargs({"speaker": "A"}, "/tmp/m.mp4", "/tmp/p.json", True, 0.5)
    assert kwargs["dry_run"] is True
    assert kwargs["audio_offset"] == 0.5
    assert kwargs["auto_edit_mode"] == "auto"


def test_upload_kwargs_do_not_use_dry_run():
    kwargs = _build_apply_kwargs({"speaker": "A"}, "/tmp/m.mp4", "/tmp/p.json", False, 0.0)
    assert kwargs["dry_run"] is False


def test_applied_local_status_persists_render_link(repo: SermonRepository):
    repo.save_sermon({"id": "s1", "title": "S1"})
    plan_id = repo.save_edit_plan_revision("s1", _plan())
    assert repo.update_edit_plan_status(
        plan_id,
        "applied_local",
        notes="rendered locally, not uploaded",
        applied_media_id="draft_local_1",
    )
    current = repo.get_current_edit_plan("s1")
    assert current["status"] == "applied_local"
    assert current["applied_media_id"] == "draft_local_1"
