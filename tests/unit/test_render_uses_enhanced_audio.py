"""The auto-edit render must carry the enhanced audio.

For a video input ``process_new_sermon`` muxes the enhanced audio back into a
``*_enhanced`` video. The render's ``apply_edit`` source has to be that enhanced
mux so the rendered/uploaded sermon carries the enhancement. Before the fix the
render used the un-enhanced keeper or original, so a published video still had
the raw room audio even though enhancement had run.

These tests drive the real ``apply_edit`` with a recorded ``run_supervised`` so
they can assert on the ffmpeg input path, not only on an intermediate variable.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import sermon_updater as su
from src.auto_edit import EditPlan


def _make_video(tmp_path: Path) -> Path:
    video = tmp_path / "sermon.mp4"
    video.write_bytes(b"fake video bytes")
    return video


def _enhanced_mux_path(video: Path) -> Path:
    return video.with_name(f"{video.stem}_enhanced{video.suffix}")


class _RunRecorder:
    """Stand-in for ``run_supervised`` that records commands and makes outputs."""

    def __init__(self, fail_steps: set[str] | None = None) -> None:
        self.fail_steps = fail_steps or set()
        self.commands: list[tuple[str | None, list[str]]] = []

    def __call__(self, cmd, *, step=None, partial_paths=None, check=False, **_kwargs):
        self.commands.append((step, list(cmd)))
        if step in self.fail_steps:
            raise RuntimeError(f"forced failure at {step}")
        target = partial_paths[0] if partial_paths else cmd[-1]
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(b"x")
        return subprocess.CompletedProcess(list(cmd), 0, stdout="", stderr="")

    def edit_render_input(self) -> str:
        for step, cmd in self.commands:
            if step == "edit render":
                return cmd[cmd.index("-i") + 1]
        raise AssertionError("no edit render command was built")


def _install_fake_processor(monkeypatch, counter: dict) -> None:
    fake = types.ModuleType("src.audio_processing")

    class _FakeProcessor:
        enhancement_method = "deepfilternet"

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def process_sermon_audio(self, _source, out):
            counter["enhance"] += 1
            Path(out).write_bytes(b"wav")
            return True, {}

        def release_gpu(self) -> None:
            pass

    fake.AudioProcessor = _FakeProcessor
    monkeypatch.setitem(sys.modules, "src.audio_processing", fake)


def _config(tmp_path: Path) -> dict:
    return {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {
            "enabled": False,
            "min_sermon_seconds": 1,
            "auto_confidence_threshold": 0.8,
        },
        "av_sync": {"enabled": False},
    }


def _wire_pipeline(monkeypatch, tmp_path: Path, counter: dict, recorder: _RunRecorder) -> None:
    import src.auto_edit as auto_edit_mod

    monkeypatch.setattr(su, "config", _config(tmp_path))
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
    monkeypatch.setattr(
        auto_edit_mod,
        "transcode_to_keeper",
        Mock(side_effect=lambda source, *_a, **_k: source),
    )
    _install_fake_processor(monkeypatch, counter)
    monkeypatch.setattr(su, "run_supervised", recorder)
    # ``apply_edit`` is imported into sermon_updater from whichever auto_edit
    # module is on sys.path (bare ``auto_edit``), which is a distinct module
    # object from ``src.auto_edit``. Patch the runner on the function's own
    # module so the real apply_edit builds its command against the recorder.
    apply_edit_module = sys.modules[su.apply_edit.__module__]
    monkeypatch.setattr(apply_edit_module, "run_supervised", recorder)


def _run(video: Path, **kwargs) -> dict:
    return su.process_new_sermon(
        str(video),
        speaker_name="Enhanced Speaker",
        recorded_date="2024-01-01",
        title="Test Title",
        description="Test description",
        hashtags="#test",
        dry_run=True,
        skip_transcription=True,
        auto_edit_mode="auto",
        **kwargs,
    )


def test_render_source_is_enhanced_mux_when_enhancement_runs(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    video = _make_video(tmp_path)
    counter = {"enhance": 0}
    recorder = _RunRecorder()
    _wire_pipeline(monkeypatch, tmp_path, counter, recorder)

    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        result = _run(video)

    assert result["success"] is True
    assert counter["enhance"] == 1
    expected = _enhanced_mux_path(video)
    assert expected.exists()
    assert recorder.edit_render_input() == str(expected)
    assert "Rendering from the enhanced audio" in caplog.text

    from ui.database import SermonRepository

    row = SermonRepository().get_current_edit_plan(result["sermon_id"])
    assert row is not None
    assert row["source_path"] == str(expected)


def test_render_source_is_enhanced_mux_when_retained_enhancement_reused(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    video = _make_video(tmp_path)
    retained = tmp_path / "Enhanced.mp4"
    retained.write_bytes(b"retained enhanced audio")
    counter = {"enhance": 0}
    recorder = _RunRecorder()
    _wire_pipeline(monkeypatch, tmp_path, counter, recorder)

    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        result = _run(video, skip_audio=True, enhanced_audio_file=str(retained))

    assert result["success"] is True
    assert counter["enhance"] == 0
    expected = _enhanced_mux_path(video)
    assert recorder.edit_render_input() == str(expected)
    assert "Rendering from the enhanced audio" in caplog.text


def test_render_source_unchanged_when_enhancement_skipped(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    video = _make_video(tmp_path)
    counter = {"enhance": 0}
    recorder = _RunRecorder()
    _wire_pipeline(monkeypatch, tmp_path, counter, recorder)

    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        result = _run(video, skip_audio=True)

    assert result["success"] is True
    assert counter["enhance"] == 0
    assert recorder.edit_render_input() == str(video)
    assert "Rendering from the enhanced audio" not in caplog.text
    assert "enhancement was NOT applied to the render" not in caplog.text
    assert f"Rendering from {video}" in caplog.text


def test_mux_failure_renders_unenhanced_and_warns(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    video = _make_video(tmp_path)
    counter = {"enhance": 0}
    recorder = _RunRecorder(fail_steps={"video mux"})
    _wire_pipeline(monkeypatch, tmp_path, counter, recorder)

    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        result = _run(video)

    assert result["success"] is True
    assert counter["enhance"] == 1
    assert recorder.edit_render_input() == str(video)
    assert "enhancement was NOT applied to the render" in caplog.text
    assert "Rendering from the enhanced audio" not in caplog.text
