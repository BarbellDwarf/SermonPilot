"""Library apply updates one sermon row in place, reusing retained artifacts.

The review pass retains the full-length source, keeper, enhanced audio,
transcript and generated metadata. Applying an approved edit must advance the
same row through the lifecycle and must not re-run the LLM, the keeper
transcode, or audio enhancement while those artifacts still exist.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

import sermon_updater as su
import ui.auto_edit_apply as core
from ui.database import SermonDatabase, SermonRepository

SID = "draft_reuse_0001"
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
    db_path = tmp_path / "apply.db"
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.setattr("ui.database._db", None)
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
    (directory / "review_media.json").write_text("{}", encoding="utf-8")
    metadata = {
        "sermon_id": SID,
        "title": "Stored Title",
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
    description: str | None = "Stored description",
    hashtags: str | None = "#stored",
) -> int:
    repo.save_sermon({
        "id": SID,
        "title": "Stored Title",
        "speaker": "Test Speaker",
        "recorded_date": "2024-01-01",
        "status": "draft",
        "edit_status": "pending_review",
        "description": description or "",
        "file_paths": {
            "audio": str(review["keeper"]),
            "metadata": str(review["metadata"]),
        },
        "content": {
            "transcript_text": "hello transcript",
            "description": description or "",
            "hashtags": hashtags or "",
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
    """Count every stage that must not run, and record each render source."""
    calls: dict = {
        "keeper": 0,
        "enhance": 0,
        "title": 0,
        "summary": 0,
        "hashtags": 0,
        "apply_sources": [],
    }

    import src.auto_edit as auto_edit_mod

    def _transcode(source, *_args, **_kwargs):
        calls["keeper"] += 1
        return source

    monkeypatch.setattr(auto_edit_mod, "transcode_to_keeper", Mock(side_effect=_transcode))

    fake_audio = types.ModuleType("src.audio_processing")

    class _FakeProcessor:
        enhancement_method = "deepfilternet"

        def __init__(self, *_args, **_kwargs):
            pass

        def process_sermon_audio(self, _source, out):
            calls["enhance"] += 1
            Path(out).write_bytes(b"wav")
            return True, {}

        def release_gpu(self):
            pass

    fake_audio.AudioProcessor = _FakeProcessor
    monkeypatch.setitem(sys.modules, "src.audio_processing", fake_audio)

    def _count(name: str, value: str):
        def _call(*_args, **_kwargs):
            calls[name] += 1
            return value

        return Mock(side_effect=_call)

    monkeypatch.setattr(su, "generate_title", _count("title", "Generated Title"))
    monkeypatch.setattr(su, "generate_summary", _count("summary", "Generated description"))
    monkeypatch.setattr(su, "generate_hashtags", _count("hashtags", "#generated"))
    monkeypatch.setattr(su, "_reuse_existing_transcript", Mock(return_value=""))
    monkeypatch.setattr(su, "_reuse_existing_transcript_segments", Mock(return_value=[]))

    def _fake_apply(source, _plan, out, **_kwargs):
        calls["apply_sources"].append(str(source))
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"edited")
        return out

    monkeypatch.setattr(su, "apply_edit", Mock(side_effect=_fake_apply))
    return calls


def _apply(repo: SermonRepository, plan_id: int, tmp_path: Path, **kwargs) -> dict:
    return core.run_library_apply(
        repo,
        SID,
        PLAN_START,
        PLAN_END,
        render_only=True,
        plan_id=plan_id,
        config=_config(tmp_path),
        **kwargs,
    )


def test_apply_reuses_stored_metadata_without_llm_calls(
    repo, review, pipeline, tmp_path
) -> None:
    plan_id = _seed(repo, review)

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert pipeline["title"] == 0
    assert pipeline["summary"] == 0
    assert pipeline["hashtags"] == 0
    assert result["title"] == "Stored Title"
    assert result["description"] == "Stored description"
    assert result["hashtags"] == "#stored"


def test_apply_generates_only_the_empty_fields(repo, review, pipeline, tmp_path) -> None:
    plan_id = _seed(repo, review, description=None, hashtags=None)

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert pipeline["title"] == 0
    assert pipeline["summary"] == 1
    assert pipeline["hashtags"] == 1


def test_apply_skips_keeper_transcode_and_enhancement(repo, review, pipeline, tmp_path) -> None:
    plan_id = _seed(repo, review)

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert pipeline["keeper"] == 0
    assert pipeline["enhance"] == 0
    assert pipeline["apply_sources"] == [str(review["keeper"])]


def test_apply_keeps_one_record_and_advances_lifecycle(
    repo, review, pipeline, tmp_path, monkeypatch
) -> None:
    plan_id = _seed(repo, review)

    seen: list[str] = []
    update = repo.update_sermon_edit_status

    def _record(sermon_id: str, status: str) -> bool:
        seen.append(status)
        return update(sermon_id, status)

    monkeypatch.setattr(repo, "update_sermon_edit_status", _record)

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert [row["id"] for row in repo.get_all_sermons()] == [SID]
    assert repo.get_sermon_edit_status(SID) == "rendered"
    assert "applied" in seen
    assert "rendered" in seen
    assert seen.index("applied") < seen.index("rendered")


def test_re_edit_renders_from_retained_full_length_source(
    repo, review, pipeline, tmp_path, monkeypatch
) -> None:
    plan_id = _seed(repo, review)

    first = _apply(repo, plan_id, tmp_path)
    assert first["success"] is True
    assert pipeline["apply_sources"] == [str(review["keeper"])]

    def _duration(path):
        name = Path(str(path)).name
        trimmed = name.endswith("_edited.mp4") or " - Processed" in name
        return 2918.0 if trimmed else 3600.0

    monkeypatch.setattr(core, "_source_duration", _duration)
    pipeline["apply_sources"].clear()

    second = _apply(repo, plan_id, tmp_path)

    assert second["success"] is True
    assert pipeline["apply_sources"] == [str(review["keeper"])]
    assert len(repo.get_all_sermons()) == 1
    assert pipeline["keeper"] == 0
    assert pipeline["enhance"] == 0
