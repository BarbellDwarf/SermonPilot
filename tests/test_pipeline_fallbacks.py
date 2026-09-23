"""A requested stage that fails must fail the job, never ship a wrong artifact.

Enhancement used to fall back to the raw audio and the mux used to fall back to
an audio-only upload, both with only a log line. A video service must not
silently lose its enhanced audio or its picture.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import Mock

import sermon_updater as su


def _video(tmp_path: Path) -> Path:
    video = tmp_path / "service.mp4"
    video.write_bytes(b"fake video bytes")
    return video


def _fake_audio_processor(monkeypatch, *, ok: bool) -> None:
    fake = types.ModuleType("src.audio_processing")

    class _Processor:
        enhancement_method = "deepfilternet"

        def __init__(self, *_args, **_kwargs):
            pass

        def process_sermon_audio(self, _source, out, **_kwargs):
            if not ok:
                return False, {}
            Path(out).write_bytes(b"RIFF0000WAVE")
            return True, {}

        def release_gpu(self):
            pass

    fake.AudioProcessor = _Processor
    monkeypatch.setitem(sys.modules, "src.audio_processing", fake)


def _stub_api(monkeypatch) -> tuple[Mock, Mock]:
    create = Mock(return_value="111")
    upload = Mock(return_value=True)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    return create, upload


def _base_config(tmp_path: Path) -> dict:
    return {"output_directory": str(tmp_path / "output")}


def test_enhancement_failure_fails_instead_of_shipping_raw_audio(
    tmp_path: Path, monkeypatch
) -> None:
    video = _video(tmp_path)
    monkeypatch.setattr(su, "config", _base_config(tmp_path))
    _fake_audio_processor(monkeypatch, ok=False)
    create, upload = _stub_api(monkeypatch)

    result = su.process_new_sermon(
        str(video),
        speaker_name=f"Fallback Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        title="Test Title",
        description="Test description",
        hashtags="#test",
        dry_run=False,
    )

    assert result["success"] is False
    assert "enhancement" in (result.get("error") or "").lower()
    assert result.get("needs_review") is True
    create.assert_not_called()
    upload.assert_not_called()


def test_mux_failure_fails_instead_of_audio_only_downgrade(
    tmp_path: Path, monkeypatch
) -> None:
    video = _video(tmp_path)
    monkeypatch.setattr(su, "config", _base_config(tmp_path))
    _fake_audio_processor(monkeypatch, ok=True)
    monkeypatch.setattr(
        su, "_mux_video_with_audio", Mock(side_effect=RuntimeError("boom"))
    )
    create, upload = _stub_api(monkeypatch)

    result = su.process_new_sermon(
        str(video),
        speaker_name=f"Mux Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        title="Test Title",
        description="Test description",
        hashtags="#test",
        dry_run=False,
    )

    assert result["success"] is False
    assert "mux" in (result.get("error") or "").lower()
    assert result.get("needs_review") is True
    create.assert_not_called()
    upload.assert_not_called()
