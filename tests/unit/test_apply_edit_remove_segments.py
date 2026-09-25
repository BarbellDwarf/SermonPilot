from __future__ import annotations

import array
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.auto_edit import EditPlan, apply_edit


def _capture_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: EditPlan, logo: Path | None = None
) -> list[str]:
    captured: list[str] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 1, "", "")
        captured.extend(cmd)
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    if logo is not None:
        monkeypatch.setattr("src.auto_edit._ffprobe_frame_rate", lambda *_args: "25/1")
    apply_edit(
        Path("in.mp4"),
        plan,
        tmp_path / "out.mp4",
        logo_path=logo,
        fade_out_tail_seconds=0.0,
    )
    return captured


def test_two_removals_build_one_concat_filter() -> None:
    plan = EditPlan(
        start=10.0,
        end=100.0,
        remove_segments=[
            {"start_sec": 30.0, "end_sec": 40.0},
            {"start_sec": 60.0, "end_sec": 70.0},
        ],
        fade_in=0.0,
        logo_hold=0.0,
        fade_to_black=False,
    )
    captured: list[str] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 1, "", "")
        captured.extend(cmd)
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    import subprocess as subprocess_module

    original_run = subprocess_module.run
    try:
        subprocess_module.run = fake_run
        apply_edit(Path("in.mp4"), plan, Path("out.mp4"), fade_out_tail_seconds=0.0)
    finally:
        subprocess_module.run = original_run

    filter_complex = captured[captured.index("-filter_complex") + 1]
    assert "concat=n=3:v=1:a=1" in filter_complex
    assert "trim=start=0.000:end=20.000" in filter_complex
    assert "trim=start=30.000:end=50.000" in filter_complex
    assert "trim=start=60.000:end=90.000" in filter_complex
    assert "asetpts=PTS-STARTPTS" in filter_complex
    assert captured[captured.index("-t") + 1] == "70.000"
    assert captured[captured.index("-ss") + 1] == "10.000"


def test_empty_removals_keep_single_trim_command(tmp_path: Path, monkeypatch) -> None:
    plan = EditPlan(start=1.0, end=60.0, fade_in=1.0, logo_hold=0.0)
    captured = _capture_command(tmp_path, monkeypatch, plan)
    filter_complex = captured[captured.index("-filter_complex") + 1]

    assert "concat=" not in filter_complex
    assert captured[captured.index("-ss") + 1] == "1.000"
    assert captured[captured.index("-to") + 1] == "60.000"
    assert "-filter_complex" in captured


def test_removal_render_keeps_ending_card_duration_math(
    tmp_path: Path, monkeypatch
) -> None:
    plan = EditPlan(
        start=10.0,
        end=100.0,
        remove_segments=[{"start_sec": 30.0, "end_sec": 40.0}],
        fade_in=1.0,
        logo_hold=3.0,
        fade_to_black=True,
    )
    captured = _capture_command(tmp_path, monkeypatch, plan, Path("logo.png"))
    filter_complex = captured[captured.index("-filter_complex") + 1]

    assert "xfade=transition=fade:duration=0.800:offset=79.200" in filter_complex
    assert captured[captured.index("-t", captured.index("logo.png")) + 1] == "82.200"


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


def _sample_rgb(path: Path, second: float) -> tuple[int, int, int]:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{second:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    center = (len(raw) // 2) // 3
    return tuple(raw[center * 3 : center * 3 + 3])


def _sample_frequency(path: Path, second: float) -> float:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{second:.3f}",
            "-t",
            "0.6",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw)
    crossings = sum(
        (left < 0) != (right < 0)
        for left, right in zip(samples, samples[1:], strict=False)
    )
    return crossings * 8000 / max(len(samples) * 2, 1)


@pytest.mark.heavy
def test_two_removals_render_long_input_with_join_markers(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg tools are required")

    source = tmp_path / "long-source.mp4"
    colors = ["red", "green", "blue", "yellow", "magenta"]
    durations = [1000, 1000, 2000, 1000, 2200]
    command = ["ffmpeg", "-y"]
    for color, duration in zip(colors, durations, strict=True):
        command += [
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=160x90:r=1:d={duration}",
        ]
    frequencies = [440, 880, 220, 1320, 660]
    for frequency, duration in zip(frequencies, durations, strict=True):
        command += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
        ]
    video_inputs = "".join(f"[{i}:v]" for i in range(5))
    audio_inputs = "".join(f"[{i + 5}:a]" for i in range(5))
    filter_complex = (
        f"{video_inputs}concat=n=5:v=1:a=0[v];"
        f"{audio_inputs}concat=n=5:v=0:a=1[a]"
    )
    command += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        "7200",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(source),
    ]
    subprocess.run(command, capture_output=True, text=True, check=True, timeout=600)

    out = tmp_path / "edited.mp4"
    plan = EditPlan(
        start=60.0,
        end=7000.0,
        remove_segments=[
            {"start_sec": 1000.0, "end_sec": 2000.0},
            {"start_sec": 4000.0, "end_sec": 5000.0},
        ],
        fade_in=0.0,
        logo_hold=0.0,
        fade_to_black=False,
    )
    apply_edit(source, plan, out, fade_out_tail_seconds=0.0)

    expected = (7000.0 - 60.0) - 1000.0 - 1000.0
    assert _probe_duration(out) == pytest.approx(expected, abs=1.0)
    red = _sample_rgb(out, 900.0)
    blue = _sample_rgb(out, 1000.0)
    magenta = _sample_rgb(out, 3000.0)
    assert red[0] > 180 and red[1] < 80 and red[2] < 80
    assert blue[2] > 180 and blue[0] < 80 and blue[1] < 80
    assert magenta[0] > 180 and magenta[2] > 180 and magenta[1] < 80
    assert 350 < _sample_frequency(out, 900.0) < 550
    assert 150 < _sample_frequency(out, 1000.0) < 300
    assert 550 < _sample_frequency(out, 3000.0) < 750
