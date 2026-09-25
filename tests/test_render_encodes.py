"""A gate-active video run must not re-encode the full video more than twice.

The render consumes the enhanced mux, which is built from the keeper with a
video stream copy. That leaves one keeper encode plus one render encode, and the
mux is scratch (cleaned with the job), never an orphan beside the source.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import Mock

import sermon_updater as su


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


def test_gate_active_video_run_encodes_twice_without_an_orphan(
    tmp_path: Path, monkeypatch
) -> None:
    import src.auto_edit as auto_edit_mod
    from src.auto_edit import EditPlan

    video = tmp_path / "service.mp4"
    video.write_bytes(b"fake video bytes")

    keeper_calls: list[Path] = []

    def _fake_keeper(_source, out, *_args, **_kwargs):
        out = Path(out)
        keeper_calls.append(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"keeper")
        return out

    monkeypatch.setattr(
        auto_edit_mod, "transcode_to_keeper", Mock(side_effect=_fake_keeper)
    )

    config = {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {
            "enabled": False,
            "min_sermon_seconds": 1,
            "keeper": {"enabled": True, "min_source_gb": 0},
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

    mux_inputs: list[str] = []

    def _fake_mux(video_input, _audio_input, out, *_args, **_kwargs):
        mux_inputs.append(str(video_input))
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mux")
        return []

    monkeypatch.setattr(su, "_mux_video_with_audio", Mock(side_effect=_fake_mux))

    render_sources: list[str] = []

    def _fake_apply(source, _plan, out, **_kwargs):
        render_sources.append(str(source))
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"edited")
        return out

    monkeypatch.setattr(su, "apply_edit", Mock(side_effect=_fake_apply))

    result = su.process_new_sermon(
        str(video),
        speaker_name=f"Encode Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        dry_run=True,
        auto_edit_mode="auto",
    )

    assert result["success"] is True
    # Two full video encodes: the keeper and the render. The mux copies video.
    assert len(keeper_calls) == 1
    assert len(render_sources) == 1
    assert len(keeper_calls) + len(render_sources) <= 2
    # The render consumed the mux, and the mux was built from the keeper.
    assert Path(render_sources[0]).name.endswith("_enhanced.mp4")
    assert Path(mux_inputs[0]) == keeper_calls[0]
    # Nothing is left orphaned beside the source.
    assert not list(video.parent.glob("*_enhanced*"))
