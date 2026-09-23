"""An operator-edited description must survive the next apply render.

The review pass writes a metadata.json snapshot and the operator may edit the
title or description in the console after that. The apply render must read the
operator's live values (stamped by ``sermons.metadata_edited_at``) instead of
writing its own stale snapshot back over the record. The record's review flag
must survive with the edit.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import sermon_updater as su
import ui.auto_edit_apply as core
from ui.database import SermonDatabase, SermonRepository

SID = "draft_authority_0001"
PLAN_START = 40.0
PLAN_END = 2958.0


def _plan_dict() -> dict:
    return {
        "proposed_start": PLAN_START,
        "proposed_end": PLAN_END,
        "confidence": 1.0,
        "needs_review": False,
        "evidence": "approved",
        "qa_judgment": "approved",
        "reasoning": "",
        "status": "pending_review",
        "source_path": "keeper.mp4",
        "notes": "",
    }


@pytest.fixture
def repo(tmp_path, monkeypatch) -> SermonRepository:
    db_path = tmp_path / "authority.db"
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.setattr("ui.database._db", None)
    monkeypatch.setattr("database._db", None)
    return SermonRepository(SermonDatabase(db_path=str(db_path)))


@pytest.fixture
def review(tmp_path) -> dict:
    directory = tmp_path / "review"
    directory.mkdir()
    files = {
        "original": directory / "Original.mp4",
        "keeper": directory / "Keeper.mp4",
        "enhanced": directory / "Enhanced.wav",
        "transcript": directory / "transcript.txt",
    }
    files["original"].write_bytes(b"orig")
    files["keeper"].write_bytes(b"keep")
    files["enhanced"].write_bytes(b"enh")
    files["transcript"].write_text("hello transcript", encoding="utf-8")
    metadata = {
        "sermon_id": SID,
        "title": "Snapshot Title",
        "description": "Snapshot description",
        "hashtags": "#snapshot",
        "original_file": str(files["original"]),
        "keeper_file": str(files["keeper"]),
        "enhanced_file": str(files["enhanced"]),
        "transcript_file": str(files["transcript"]),
        "is_video": True,
    }
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    files["review"] = directory
    files["metadata"] = directory / "metadata.json"
    return files


def _seed(
    repo: SermonRepository,
    review: dict,
    *,
    description: str = "Snapshot description",
    review_flag: bool = True,
) -> int:
    repo.save_sermon({
        "id": SID,
        "title": "Snapshot Title",
        "speaker": "Test Speaker",
        "recorded_date": "2024-01-01",
        "status": "draft",
        "edit_status": "pending_review",
        "description": description,
        "description_needs_review": review_flag,
        "file_paths": {
            "audio": str(review["keeper"]),
            "metadata": str(review["metadata"]),
        },
        "content": {
            "transcript_text": "hello transcript",
            "description": description,
            "hashtags": "#snapshot",
        },
    })
    return repo.save_edit_plan_revision(SID, _plan_dict())


def _config(tmp_path: Path) -> dict:
    return {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {"enabled": False, "min_sermon_seconds": 1},
    }


@pytest.fixture
def pipeline(monkeypatch) -> dict:
    calls = {"title": 0, "summary": 0, "hashtags": 0}

    def _count(name: str, value: str):
        def _call(*_args, **_kwargs):
            calls[name] += 1
            return value

        return Mock(side_effect=_call)

    monkeypatch.setattr(su, "generate_title", _count("title", "Generated Title"))
    monkeypatch.setattr(su, "generate_summary", _count("summary", "Generated description"))
    monkeypatch.setattr(su, "generate_hashtags", _count("hashtags", "#generated"))
    monkeypatch.setattr(su, "_reuse_existing_transcript", Mock(return_value="hello transcript"))
    monkeypatch.setattr(su, "_reuse_existing_transcript_segments", Mock(return_value=[]))

    def _fake_apply(source, _plan, out, **_kwargs):
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"edited")
        return out

    monkeypatch.setattr(su, "apply_edit", Mock(side_effect=_fake_apply))
    return calls


def _apply(repo: SermonRepository, plan_id: int, tmp_path: Path) -> dict:
    return core.run_library_apply(
        repo,
        SID,
        PLAN_START,
        PLAN_END,
        render_only=True,
        plan_id=plan_id,
        config=_config(tmp_path),
    )


def test_operator_edited_description_survives_apply_render(
    repo, review, pipeline, tmp_path
) -> None:
    plan_id = _seed(repo, review)
    assert repo.update_sermon_metadata(SID, {"description": "Operator edited description"})

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert pipeline["summary"] == 0
    assert result["description"] == "Operator edited description"
    stored = repo.get_sermon(SID)
    assert stored["description"] == "Operator edited description"
    assert stored["content"]["description"] == "Operator edited description"


def test_operator_review_flag_survives_apply_render(repo, review, pipeline, tmp_path) -> None:
    plan_id = _seed(repo, review, review_flag=True)
    assert repo.update_sermon_metadata(SID, {"description": "Operator edited description"})

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert result["description_needs_review"] is True
    assert bool(repo.get_sermon(SID)["description_needs_review"]) is True


def test_genuine_description_replaces_older_one_without_operator_edit(
    repo, review, pipeline, tmp_path
) -> None:
    plan_id = _seed(repo, review, description="Older snapshot description")
    # No console save: metadata_edited_at stays unset, so the review snapshot
    # remains authoritative and the render reuses it verbatim.
    assert not repo.get_sermon(SID).get("metadata_edited_at")

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert result["description"] == "Snapshot description"
    assert repo.get_sermon(SID)["description"] == "Snapshot description"
