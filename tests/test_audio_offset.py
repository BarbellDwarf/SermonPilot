from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.auto_edit import EditPlan, _render_snippet, apply_edit, shift_snippet_audio, validate_plan
from src.av_sync import resolve_audio_correction

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe required")


def test_validate_rejects_offset_beyond_limit():
    bounds = dict(start=0, end=100, audio_offset=0.0)
    assert validate_plan(
        EditPlan(**{**bounds, "audio_offset": 6.0}), min_sermon_seconds=0.0
    )
    assert validate_plan(
        EditPlan(**{**bounds, "audio_offset": -5.5}), min_sermon_seconds=0.0
    )
    assert not validate_plan(
        EditPlan(**{**bounds, "audio_offset": 5.0}), min_sermon_seconds=0.0
    )
    assert not validate_plan(
        EditPlan(**{**bounds, "audio_offset": -0.4}), min_sermon_seconds=0.0
    )


def test_manual_offset_skips_auto_correction():
    correction, reason = resolve_audio_correction(
        0.5, 1.2, 0.9, auto_correct=True, min_confidence=0.12, max_offset=2.0
    )
    assert correction == 0.0
    assert "manual" in reason


def test_auto_correction_applies_when_no_manual_offset():
    correction, reason = resolve_audio_correction(
        0.0, 0.8, 0.9, auto_correct=True, min_confidence=0.12, max_offset=2.0
    )
    assert correction == pytest.approx(0.8)
    assert "auto" in reason


def test_auto_correction_respects_gates():
    assert resolve_audio_correction(0, 0.8, 0.9, auto_correct=False,
                                    min_confidence=0.12, max_offset=2.0)[0] == 0.0
    assert resolve_audio_correction(0, 0.05, 0.9, auto_correct=True,
                                    min_confidence=0.12, max_offset=2.0)[0] == 0.0
    assert resolve_audio_correction(0, 0.8, 0.05, auto_correct=True,
                                    min_confidence=0.12, max_offset=2.0)[0] == 0.0
    assert resolve_audio_correction(0, 3.0, 0.9, auto_correct=True,
                                    min_confidence=0.12, max_offset=2.0)[0] == 0.0


def _make_source(path: Path) -> None:
    subprocess.run(
        [FFMPEG, "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
         "-t", "4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(path)],
        check=True, capture_output=True,
    )


def _first_pts(path: Path, stream: str) -> float:
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", stream,
         "-show_entries", "packet=pts_time", "-of", "csv=p=0",
         "-read_intervals", "%+1", str(path)],
        check=True, capture_output=True, text=True,
    )
    values = [float(v.strip(",")) for v in proc.stdout.replace("\n", " ").split()
              if v.strip(",") not in ("", "N/A")]
    assert values, f"no packets for {stream}"
    return min(values)


@needs_ffmpeg
@pytest.mark.parametrize("offset", [0.5, -0.5])
def test_apply_edit_shifts_audio_stream(tmp_path, offset):
    source = tmp_path / "source.mp4"
    _make_source(source)
    plan = EditPlan(start=0.5, end=3.0, fade_in=0.0, logo_hold=0.0,
                    fade_to_black=False, audio_offset=offset)
    out = tmp_path / "edited.mp4"
    apply_edit(source, plan, out)
    video_start = _first_pts(out, "v:0")
    audio_start = _first_pts(out, "a:0")
    delta = audio_start - video_start
    assert delta == pytest.approx(offset, abs=0.12)


@needs_ffmpeg
def test_apply_edit_without_offset_stays_aligned(tmp_path):
    source = tmp_path / "source.mp4"
    _make_source(source)
    plan = EditPlan(start=0.5, end=3.0, fade_in=0.0, logo_hold=0.0,
                    fade_to_black=False)
    out = tmp_path / "edited.mp4"
    apply_edit(source, plan, out)
    delta = _first_pts(out, "a:0") - _first_pts(out, "v:0")
    assert abs(delta) <= 0.05


@needs_ffmpeg
@pytest.mark.parametrize("offset", [0.5, -0.5])
def test_shift_snippet_audio_remuxes_offset(tmp_path, offset):
    source = tmp_path / "source.mp4"
    _make_source(source)
    base = tmp_path / "base.mp4"
    _render_snippet(source, 0.5, 3.0, base)
    out = tmp_path / f"shifted_{offset:+.1f}.mp4"
    shift_snippet_audio(base, offset, out)
    delta = _first_pts(out, "a:0") - _first_pts(out, "v:0")
    assert delta == pytest.approx(offset, abs=0.12)
