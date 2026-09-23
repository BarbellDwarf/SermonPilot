"""The measured A/V correction must reach the finalized render.

The correction used to be applied with ``-itsoffset`` only to the intermediate
enhanced mux, which the edit render then ignored. These tests prove the plan
handed to ``apply_edit`` carries the correction, that a manual offset wins when
explicitly set, and that the correction is not applied twice.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

import sermon_updater as su
from src.av_sync import OffsetMeasurement


def _fake_audio_processor(monkeypatch) -> None:
    fake = types.ModuleType("src.audio_processing")

    class _Processor:
        enhancement_method = "deepfilternet"

        def __init__(self, *_args, **_kwargs):
            pass

        def process_sermon_audio(self, _source, out, **_kwargs):
            Path(out).write_bytes(b"RIFF0000WAVE")
            return True, {}

        def release_gpu(self):
            pass

    fake.AudioProcessor = _Processor
    monkeypatch.setitem(sys.modules, "src.audio_processing", fake)


def _stub_measurements(monkeypatch, *, content: float, waveform: float = 0.0) -> None:
    import src.av_sync as av_sync

    monkeypatch.setattr(
        av_sync,
        "measure_content_offset",
        Mock(
            return_value=OffsetMeasurement(
                offset_seconds=content,
                confidence=0.9,
                available=True,
                method="content",
            )
        ),
    )
    monkeypatch.setattr(
        av_sync,
        "measure_waveform_offset",
        Mock(
            return_value=OffsetMeasurement(
                offset_seconds=waveform,
                confidence=0.9,
                available=True,
                method="waveform",
            )
        ),
    )


def _run_pipeline(tmp_path: Path, monkeypatch, **overrides) -> tuple[dict, Mock, Mock]:
    from src.auto_edit import EditPlan

    video = tmp_path / "service.mp4"
    video.write_bytes(b"fake video bytes")

    config = {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {"enabled": False, "min_sermon_seconds": 1},
        "av_sync": {
            "enabled": True,
            "auto_correct": True,
            "max_offset_seconds": 2.0,
            "min_confidence": 0.12,
        },
    }
    monkeypatch.setattr(su, "config", config)
    monkeypatch.setattr(su, "transcribe_segments", Mock(return_value=[]))
    monkeypatch.setattr(
        su,
        "detect_cut_points",
        Mock(
            return_value=EditPlan(
                start=30.0,
                end=600.0,
                confidence=0.9,
                needs_review=False,
                evidence="quotes",
            )
        ),
    )

    _fake_audio_processor(monkeypatch)
    _stub_measurements(monkeypatch, content=0.7)

    mux = Mock(side_effect=lambda _v, _a, out, *_args, **_kw: (Path(out).write_bytes(b"mux"), [])[1])
    monkeypatch.setattr(su, "_mux_video_with_audio", mux)

    captured: dict = {}

    def _fake_apply(source, plan, out, **_kwargs):
        captured["source"] = Path(source)
        captured["plan"] = plan
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"edited")
        return out

    apply_edit = Mock(side_effect=_fake_apply)
    monkeypatch.setattr(su, "apply_edit", apply_edit)

    kwargs = {
        "speaker_name": f"AV Speaker {tmp_path.name}",
        "recorded_date": "2024-01-01",
        "dry_run": True,
        "auto_edit_mode": "auto",
    }
    kwargs.update(overrides)
    result = su.process_new_sermon(str(video), **kwargs)
    return result, mux, captured


def test_auto_correction_reaches_the_render_plan(tmp_path: Path, monkeypatch) -> None:
    result, mux, captured = _run_pipeline(tmp_path, monkeypatch)

    assert result["success"] is True
    assert result["auto_edit_applied"] is True
    assert captured["plan"].audio_offset == pytest.approx(0.7)
    # The render consumes the mux; the offset must not also be baked in there.
    assert mux.call_args.args[3] == pytest.approx(0.0)


def test_manual_offset_wins_over_measured_correction(tmp_path: Path, monkeypatch) -> None:
    result, mux, captured = _run_pipeline(tmp_path, monkeypatch, audio_offset=0.3)

    assert result["success"] is True
    assert captured["plan"].audio_offset == pytest.approx(0.3)
    assert mux.call_args.args[3] == pytest.approx(0.0)
