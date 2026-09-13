"""Fast tests for the core processing pipeline entry point.

``process_new_sermon`` with ``dry_run=True`` must complete without network,
transcription, or LLM calls and save the draft locally.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

import sermon_updater as su


def test_process_new_sermon_dry_run_saves_locally(tmp_path: Path, monkeypatch) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")

    output_root = tmp_path / "output"
    monkeypatch.setattr(su, "config", {"output_directory": str(output_root)})

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name="Test Speaker",
        recorded_date="2024-01-01",
        title="Test Title",
        description="Test description",
        hashtags="#test",
        dry_run=True,
        skip_audio=True,
        skip_transcription=True,
    )

    assert result["success"] is True
    assert result["error"] is None
    assert result["sermon_id"].startswith("draft_")
    assert result["output_dir"] is not None
    output_dir = Path(result["output_dir"])
    assert output_dir.exists()
    assert (output_dir / "metadata.json").exists()
    assert any(f.suffix == ".mp3" for f in output_dir.iterdir())


def test_process_new_sermon_dry_run_skips_api_calls(tmp_path: Path, monkeypatch) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")

    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    create = Mock()
    upload = Mock()
    transcribe = Mock()
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    monkeypatch.setattr(su, "transcribe_segments", transcribe)

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name="Test Speaker",
        recorded_date="2024-01-01",
        dry_run=True,
        skip_audio=True,
        skip_transcription=True,
    )

    assert result["success"] is True
    create.assert_not_called()
    upload.assert_not_called()
    transcribe.assert_not_called()


def test_process_new_sermon_missing_audio_returns_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})

    result = su.process_new_sermon(
        str(tmp_path / "missing.mp3"),
        speaker_name="Test Speaker",
        recorded_date="2024-01-01",
        dry_run=True,
    )

    assert result["success"] is False
    assert "not found" in result["error"]


def _make_video(tmp_path: Path) -> Path:
    audio_file = tmp_path / "sermon.mp4"
    audio_file.write_bytes(b"fake video bytes")
    return audio_file


def _auto_edit_config(
    tmp_path: Path,
    monkeypatch,
    *,
    auto_edit: dict | None = None,
    plan: su.EditPlan | None = None,
    segments: list | None = None,
) -> su.EditPlan:
    from src.auto_edit import EditPlan

    output_root = tmp_path / "output"
    cfg = {
        "output_directory": str(output_root),
        "auto_edit": {
            "enabled": False,
            "min_sermon_seconds": 1,
            "qa_margin_seconds": 3.0,
        },
    }
    if auto_edit:
        cfg["auto_edit"].update(auto_edit)
    plan = plan or EditPlan(
        start=30.0,
        end=600.0,
        confidence=0.9,
        needs_review=False,
        evidence="quotes",
    )
    segments = segments if segments is not None else [
        {"start": 0.0, "end": 120.0, "text": "teaching"}
    ]
    monkeypatch.setattr(su, "config", cfg)
    monkeypatch.setattr(su, "transcribe_segments", Mock(return_value=segments))
    monkeypatch.setattr(su, "detect_cut_points", Mock(return_value=plan))
    return plan


def _stub_apply_edit(destination_dir: Path):
    def fake_apply_edit(source, plan, out, logo_path=None, fade_to_black=None):
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"edited video bytes")
        return out

    return Mock(side_effect=fake_apply_edit)


def test_auto_edit_interactive_stops_before_api(tmp_path: Path, monkeypatch) -> None:
    audio_file = _make_video(tmp_path)
    _auto_edit_config(tmp_path, monkeypatch)

    create = Mock(return_value="111")
    upload = Mock(return_value=True)
    apply_edit = _stub_apply_edit(tmp_path)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    monkeypatch.setattr(su, "apply_edit", apply_edit)

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name=f"Review Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        dry_run=False,
        skip_audio=True,
        auto_edit_mode="interactive",
    )

    assert result["success"] is True
    assert result["edit_plan_status"] == "pending_review"
    assert result["auto_edit_applied"] is False
    assert result["sermon_id"].startswith("draft_")
    create.assert_not_called()
    upload.assert_not_called()
    apply_edit.assert_not_called()

    from ui.database import SermonRepository
    repo = SermonRepository()
    row = repo.get_current_edit_plan(result["sermon_id"])
    assert row is not None
    assert row["status"] == "pending_review"
    assert row["proposed_start"] == 30.0
    assert row["proposed_end"] == 600.0


def test_auto_edit_auto_applies_and_uploads_edited_file(
    tmp_path: Path, monkeypatch
) -> None:
    audio_file = _make_video(tmp_path)
    _auto_edit_config(
        tmp_path,
        monkeypatch,
        auto_edit={"auto_confidence_threshold": 0.8},
    )

    create = Mock(return_value="111")
    upload = Mock(return_value=True)
    apply_edit = _stub_apply_edit(tmp_path)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    monkeypatch.setattr(su, "apply_edit", apply_edit)

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name=f"Auto Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        title="Test Title",
        description="Test description",
        hashtags="#test",
        dry_run=False,
        skip_audio=True,
        auto_edit_mode="auto",
    )

    assert result["success"] is True
    assert result["edit_plan_status"] == "auto_applied"
    assert result["auto_edit_applied"] is True
    assert result["final_upload_path"].endswith("_edited.mp4")
    create.assert_called_once()
    apply_edit.assert_called_once()
    upload.assert_called_once()
    upload_args = upload.call_args
    assert upload_args.args[0] == "111"
    assert upload_args.args[1] == result["final_upload_path"]
    assert upload_args.args[2] == "original-video"

    from ui.database import SermonRepository
    repo = SermonRepository()
    row = repo.get_current_edit_plan("111")
    assert row is not None
    assert row["status"] == "auto_applied"
    assert row["needs_review"] == 0


@pytest.mark.parametrize(
    "plan_kwargs",
    [{"needs_review": True, "confidence": 0.9}, {"needs_review": False, "confidence": 0.5}],
)
def test_auto_edit_auto_falls_back_to_review(
    tmp_path: Path, monkeypatch, plan_kwargs: dict
) -> None:
    audio_file = _make_video(tmp_path)
    _auto_edit_config(tmp_path, monkeypatch, plan=su.EditPlan(
        start=30.0, end=600.0, evidence="quotes", **plan_kwargs
    ))

    apply_edit = _stub_apply_edit(tmp_path)
    create = Mock(return_value="111")
    upload = Mock(return_value=True)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    monkeypatch.setattr(su, "apply_edit", apply_edit)

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name=f"Fallback Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        dry_run=False,
        skip_audio=True,
        auto_edit_mode="auto",
    )

    assert result["edit_plan_status"] == "pending_review"
    assert result["auto_edit_applied"] is False
    apply_edit.assert_not_called()
    create.assert_not_called()
    upload.assert_not_called()


def test_auto_edit_confidence_threshold_IS_CLAMPED() -> None:
    assert su._auto_edit_confidence_threshold({"auto_confidence_threshold": 1.5}) == 0.99
    assert su._auto_edit_confidence_threshold({}) == 0.8


def test_edit_plan_file_overrides_detection(tmp_path: Path, monkeypatch) -> None:
    audio_file = _make_video(tmp_path)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        '{"start": 45.0, "end": 700.0, "confidence": 0.95, "needs_review": false,'
        ' "evidence": "from file"}',
        encoding="utf-8",
    )
    _auto_edit_config(tmp_path, monkeypatch)

    detect = Mock()
    apply_edit = _stub_apply_edit(tmp_path)
    create = Mock(return_value="222")
    upload = Mock(return_value=True)
    monkeypatch.setattr(su, "detect_cut_points", detect)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    monkeypatch.setattr(su, "apply_edit", apply_edit)

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name=f"FilePlan Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        dry_run=False,
        title="Test Title",
        description="Test description",
        hashtags="#test",
        skip_audio=True,
        auto_edit_mode="auto",
        edit_plan_file=str(plan_file),
    )

    assert result["success"] is True
    assert result["edit_plan_status"] == "auto_applied"
    detect.assert_not_called()
    plan_arg = apply_edit.call_args.args[1]
    assert plan_arg.start == 45.0
    assert plan_arg.end == 700.0
    assert upload.call_args.args[1] == result["final_upload_path"]

    from ui.database import SermonRepository
    repo = SermonRepository()
    row = repo.get_current_edit_plan("222")
    assert row["status"] == "auto_applied"


def test_dry_run_with_auto_edit_persists_plan_without_api(
    tmp_path: Path, monkeypatch
) -> None:
    audio_file = _make_video(tmp_path)
    _auto_edit_config(tmp_path, monkeypatch)

    create = Mock(return_value="333")
    upload = Mock(return_value=True)
    apply_edit = _stub_apply_edit(tmp_path)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    monkeypatch.setattr(su, "apply_edit", apply_edit)

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name=f"DryRun Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        dry_run=True,
        title="Test Title",
        description="Test description",
        hashtags="#test",
        skip_audio=True,
        auto_edit_mode="auto",
    )

    assert result["success"] is True
    assert result["edit_plan_status"] == "auto_applied"
    assert result["sermon_id"].startswith("draft_")
    create.assert_not_called()
    upload.assert_not_called()
    apply_edit.assert_called_once()

    from ui.database import SermonRepository
    repo = SermonRepository()
    row = repo.get_current_edit_plan(result["sermon_id"])
    assert row["status"] == "auto_applied"
