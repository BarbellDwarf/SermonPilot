from __future__ import annotations

from ui.database import (
    SERMON_LIFECYCLE_STATUSES,
    SermonDatabase,
    SermonRepository,
)


def _repo(tmp_path) -> SermonRepository:
    return SermonRepository(SermonDatabase(db_path=str(tmp_path / "lifecycle.db")))


def test_save_sermon_records_edit_status(tmp_path):
    repo = _repo(tmp_path)
    repo.save_sermon({"id": "draft_a", "title": "A", "edit_status": "pending_review"})
    assert repo.get_sermon_edit_status("draft_a") == "pending_review"


def test_update_edit_status_advances_in_place(tmp_path):
    repo = _repo(tmp_path)
    repo.save_sermon({"id": "draft_a", "title": "A", "edit_status": "pending_review"})

    assert repo.update_sermon_edit_status("draft_a", "applied") is True
    assert repo.update_sermon_edit_status("draft_a", "rendered") is True
    assert repo.update_sermon_edit_status("draft_a", "uploaded") is True
    assert repo.get_sermon_edit_status("draft_a") == "uploaded"
    assert len(repo.get_all_sermons()) == 1


def test_update_edit_status_rejects_unknown_value(tmp_path):
    repo = _repo(tmp_path)
    repo.save_sermon({"id": "draft_a", "title": "A"})
    assert repo.update_sermon_edit_status("draft_a", "made_up") is False
    assert repo.get_sermon_edit_status("draft_a") is None


def test_update_edit_status_missing_row_is_false(tmp_path):
    repo = _repo(tmp_path)
    assert repo.update_sermon_edit_status("nope", "rendered") is False


def test_later_save_does_not_clear_edit_status(tmp_path):
    """A metadata-only save_sermon must not wipe the lifecycle it does not set."""
    repo = _repo(tmp_path)
    repo.save_sermon({"id": "draft_a", "title": "A", "edit_status": "rendered"})
    repo.save_sermon({"id": "draft_a", "title": "A renamed"})
    assert repo.get_sermon_edit_status("draft_a") == "rendered"
    assert repo.get_sermon("draft_a")["title"] == "A renamed"


def test_all_lifecycle_values_are_accepted(tmp_path):
    repo = _repo(tmp_path)
    repo.save_sermon({"id": "draft_a", "title": "A"})
    for status in SERMON_LIFECYCLE_STATUSES:
        assert repo.update_sermon_edit_status("draft_a", status) is True
