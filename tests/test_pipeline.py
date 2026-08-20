"""Fast tests for the core processing pipeline entry point.

``process_new_sermon`` with ``dry_run=True`` must complete without network,
transcription, or LLM calls and save the draft locally.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

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
    monkeypatch.setattr(su, "transcribe", transcribe)

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
