from __future__ import annotations

import pytest

from ui.database import SermonDatabase, SermonRepository
from ui.ui_pages.library import (
    _allow_apply_upload,
    _build_apply_kwargs,
    _default_apply_mode,
    _edit_status_badge,
    _sermon_has_upload,
)


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


def test_default_apply_mode_draft_is_render_only():
    assert _default_apply_mode("draft_mark_20260913_x_ab12") == "render_only"


def test_default_apply_mode_uploaded_is_upload():
    assert _default_apply_mode("922607137246") == "upload"
    assert _default_apply_mode("") == "upload"


def test_render_only_kwargs_use_dry_run():
    kwargs = _build_apply_kwargs(
        {"speaker": "A"}, "/tmp/m.mp4", "/tmp/p.json", True, 0.5
    )
    assert kwargs["dry_run"] is True
    assert kwargs["audio_offset"] == 0.5
    assert kwargs["auto_edit_mode"] == "auto"


def test_upload_kwargs_do_not_use_dry_run():
    kwargs = _build_apply_kwargs(
        {"speaker": "A"}, "/tmp/m.mp4", "/tmp/p.json", False, 0.0
    )
    assert kwargs["dry_run"] is False


def test_badge_for_applied_local():
    assert _edit_status_badge("applied_local") == "Rendered, not uploaded"


def test_plan_working_values_reset_and_full_reset():
    from ui.ui_pages.library import _plan_working_values

    plan = {"proposed_start": 40.0, "proposed_end": 2958.0, "audio_offset": 0.4}
    assert _plan_working_values(plan) == (40.0, 2958.0, 0.4)
    assert _plan_working_values(plan, full_reset=True) == (40.0, 2958.0, 0.0)


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


def test_unuploaded_applied_local_disallows_upload_target():
    assert _allow_apply_upload("applied_local", False) is False


def test_uploaded_applied_local_keeps_upload_choice():
    assert _allow_apply_upload("applied_local", True) is True


def test_other_statuses_keep_upload_choice():
    assert _allow_apply_upload("applied", False) is True
    assert _allow_apply_upload("auto_applied", False) is True
    assert _allow_apply_upload("reverted", False) is True
    assert _allow_apply_upload("pending_review", False) is True


def test_sermon_has_upload_false_before_any_upload(repo: SermonRepository):
    repo.save_sermon({"id": "draft_src_1", "title": "S"})
    assert _sermon_has_upload(repo, {"id": "draft_src_1"}, "draft_rendered_9") is False


def test_sermon_has_upload_true_for_rendered_record_row(repo: SermonRepository):
    repo.save_sermon({"id": "draft_src_1", "title": "S"})
    repo.save_sermon({"id": "draft_rendered_9", "title": "R"})
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO upload_info "
            "(sermon_id, sermonaudio_id, upload_status) VALUES (?, ?, ?)",
            ("draft_rendered_9", "123456", "completed"),
        )
        conn.commit()
    assert _sermon_has_upload(repo, {"id": "draft_src_1"}, "draft_rendered_9") is True


def test_sermon_has_upload_true_for_sermon_row(repo: SermonRepository):
    repo.save_sermon({"id": "922607137246", "title": "S"})
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO upload_info "
            "(sermon_id, sermonaudio_id, upload_status) VALUES (?, ?, ?)",
            ("922607137246", "922607137246", "completed"),
        )
        conn.commit()
    assert _sermon_has_upload(repo, {"id": "922607137246"}, None) is True
