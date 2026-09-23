"""An apply resolves audio enhancement from the request, the plan, or settings.

Silence is never consent to skip: with no explicit flag anywhere the app config
decides, and its default is on. A retained enhancement is reused only when it
exists, covers the approved cut, and came from the same source; otherwise the
enhancer runs. If a requested enhancement fails, the apply fails loudly rather
than shipping an un-enhanced render labelled enhanced.
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

SID = "draft_enh_0001"
PLAN_START = 40.0
PLAN_END = 2958.0


def _plan(actions: dict | None = None) -> dict:
    plan = {
        "proposed_start": PLAN_START,
        "proposed_end": PLAN_END,
        "confidence": 1.0,
        "needs_review": False,
        "evidence": "approved",
        "qa_judgment": "approved",
        "reasoning": "",
        "status": "pending_review",
        "source_path": "Keeper.mp4",
        "notes": "",
    }
    if actions is not None:
        plan["actions"] = actions
    return plan


@pytest.fixture
def repo(tmp_path, monkeypatch) -> SermonRepository:
    db_path = tmp_path / "enh.db"
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
    files["metadata"] = directory / "metadata.json"
    files["dir"] = directory
    return files


def _drop_enhanced_artifact(review: dict) -> None:
    metadata = json.loads(Path(review["metadata"]).read_text(encoding="utf-8"))
    metadata.pop("enhanced_file", None)
    Path(review["metadata"]).write_text(json.dumps(metadata), encoding="utf-8")


def _seed(repo: SermonRepository, review: dict, plan: dict | None = None) -> int:
    repo.save_sermon(
        {
            "id": SID,
            "title": "Stored Title",
            "speaker": "Sample Speaker",
            "recorded_date": "2024-01-01",
            "status": "draft",
            "edit_status": "pending_review",
            "description": "Stored description",
            "file_paths": {
                "audio": str(review["keeper"]),
                "metadata": str(review["metadata"]),
            },
            "content": {
                "transcript_text": "hello transcript",
                "description": "Stored description",
                "hashtags": "#stored",
            },
        }
    )
    return repo.save_edit_plan_revision(SID, plan or _plan())


@pytest.fixture
def pipeline(monkeypatch) -> dict:
    calls: dict = {"enhance": 0, "enhance_inputs": [], "apply_sources": [], "apply_kwargs": []}

    import src.auto_edit as auto_edit_mod

    monkeypatch.setattr(
        auto_edit_mod,
        "transcode_to_keeper",
        Mock(side_effect=lambda source, *_a, **_k: source),
    )

    real_process = su.process_new_sermon

    def _spy_process(**kwargs):
        calls["apply_kwargs"].append(dict(kwargs))
        return real_process(**kwargs)

    monkeypatch.setattr(su, "process_new_sermon", _spy_process)

    fake_audio = types.ModuleType("src.audio_processing")

    class _FakeProcessor:
        enhancement_method = "deepfilternet"

        def __init__(self, *_args, **_kwargs):
            pass

        def process_sermon_audio(self, source, out):
            calls["enhance"] += 1
            calls["enhance_inputs"].append(str(source))
            Path(out).write_bytes(b"wav")
            return True, {}

        def release_gpu(self):
            pass

    fake_audio.AudioProcessor = _FakeProcessor
    monkeypatch.setitem(sys.modules, "src.audio_processing", fake_audio)

    monkeypatch.setattr(su, "generate_title", Mock(return_value="Generated Title"))
    monkeypatch.setattr(su, "generate_summary", Mock(return_value="Generated description"))
    monkeypatch.setattr(su, "generate_hashtags", Mock(return_value="#generated"))
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


def _config(tmp_path: Path) -> dict:
    return {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {"enabled": False, "min_sermon_seconds": 1},
    }


def _apply(repo: SermonRepository, plan_id: int, tmp_path: Path, **kwargs) -> dict:
    messages = kwargs.pop("messages", None)
    if messages is not None:
        kwargs["progress_callback"] = lambda _pct, msg: messages.append(msg)
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


def test_resolve_enhancement_prefers_request_then_plan_then_settings() -> None:
    config = {"metadata_processing": {"process_audio": False}}
    assert core.resolve_enhancement(config, request_value=True) == (True, "request")
    assert core.resolve_enhancement({}, plan={"actions": {"enhance_audio": False}}) == (
        False,
        "plan",
    )
    assert core.resolve_enhancement({}) == (True, "settings")
    assert core.resolve_enhancement(config) == (False, "settings")
    assert core.resolve_enhancement({"audio_enhancement_method": "none"}) == (
        False,
        "settings",
    )


def test_plan_actions_round_trip_through_the_database(repo: SermonRepository) -> None:
    repo.save_sermon({"id": "s-actions", "title": "S"})
    repo.save_edit_plan_revision(
        "s-actions", {**_plan(), "actions": {"enhance_audio": False}}
    )
    current = repo.get_current_edit_plan("s-actions")
    assert json.loads(current["actions"]) == {"enhance_audio": False}


def test_requested_enhancement_runs_when_no_retained_artifact(
    repo, review, pipeline, tmp_path
) -> None:
    _drop_enhanced_artifact(review)
    plan_id = _seed(repo, review)

    result = _apply(repo, plan_id, tmp_path, enhance_audio=True)

    assert result["success"] is True
    assert pipeline["enhance"] == 1
    assert pipeline["enhance_inputs"] == [str(review["keeper"])]
    assert pipeline["apply_sources"] == [str(review["keeper"])]
    kwargs = pipeline["apply_kwargs"][-1]
    assert kwargs["skip_audio"] is False
    assert kwargs["require_enhancement"] is True
    assert "enhanced_audio_file" not in kwargs


def test_current_retained_enhancement_is_reused(repo, review, pipeline, tmp_path) -> None:
    plan_id = _seed(repo, review)

    result = _apply(repo, plan_id, tmp_path, enhance_audio=True)

    assert result["success"] is True
    assert pipeline["enhance"] == 0
    assert pipeline["apply_sources"] == [str(review["keeper"])]
    kwargs = pipeline["apply_kwargs"][-1]
    assert kwargs["enhanced_audio_file"] == str(review["enhanced"])
    assert kwargs["skip_audio"] is True
    assert "require_enhancement" not in kwargs


def test_explicit_off_skips_and_logs_the_reason(repo, review, pipeline, tmp_path) -> None:
    plan_id = _seed(repo, review)
    messages: list[str] = []

    result = _apply(repo, plan_id, tmp_path, enhance_audio=False, messages=messages)

    assert result["success"] is True
    assert pipeline["enhance"] == 0
    assert any(
        "Skipping audio enhancement (not requested; request turned it off)" in m
        for m in messages
    )


def test_settings_only_enhancement_on_runs(repo, review, pipeline, tmp_path) -> None:
    _drop_enhanced_artifact(review)
    plan_id = _seed(repo, review)
    config = _config(tmp_path)
    config["metadata_processing"] = {"process_audio": True}

    result = core.run_library_apply(
        repo,
        SID,
        PLAN_START,
        PLAN_END,
        render_only=True,
        plan_id=plan_id,
        config=config,
    )

    assert result["success"] is True
    assert pipeline["enhance"] == 1
    kwargs = pipeline["apply_kwargs"][-1]
    assert kwargs["skip_audio"] is False
    assert kwargs["require_enhancement"] is True


def test_plan_action_off_skips_and_names_the_plan(repo, review, pipeline, tmp_path) -> None:
    plan_id = _seed(repo, review, plan=_plan(actions={"enhance_audio": False}))
    messages: list[str] = []

    result = _apply(repo, plan_id, tmp_path, messages=messages)

    assert result["success"] is True
    assert pipeline["enhance"] == 0
    assert any("not requested; plan turned it off" in m for m in messages)


def test_plan_action_on_runs_without_a_retained_artifact(
    repo, review, pipeline, tmp_path
) -> None:
    _drop_enhanced_artifact(review)
    plan_id = _seed(repo, review, plan=_plan(actions={"enhance_audio": True}))

    result = _apply(repo, plan_id, tmp_path)

    assert result["success"] is True
    assert pipeline["enhance"] == 1


def test_requested_enhancement_failure_fails_loud(repo, review, pipeline, tmp_path) -> None:
    _drop_enhanced_artifact(review)
    plan_id = _seed(repo, review)

    import src.audio_processing as audio_processing

    class _FailingProcessor:
        enhancement_method = "deepfilternet"

        def __init__(self, *_args, **_kwargs):
            pass

        def process_sermon_audio(self, _source, _out):
            return False, {}

        def release_gpu(self):
            pass

    audio_processing.AudioProcessor = _FailingProcessor

    result = _apply(repo, plan_id, tmp_path, enhance_audio=True)

    assert result["success"] is False
    assert "enhancement" in (result.get("error") or "").lower()
