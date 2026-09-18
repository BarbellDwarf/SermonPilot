from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.auto_edit import DEFAULT_FADE_OUT_TAIL_SECONDS, EditPlan, apply_edit, shift_snippet_audio

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe required")

SR = 48000
START = 2.0
END = 22.0
DUR = END - START
D = 0.9
FADE = 1.0
TAIL_DEFAULT = 2.0


def _make_wav(path: Path, src_dur: float) -> None:
    n = int(src_dur * SR)
    t = np.arange(n) / SR
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    audio[t >= END] *= 0.3
    blip = (t >= 10.0) & (t < 10.3)
    audio[blip] += 0.9 * np.sin(2 * np.pi * 1200 * t[blip])
    closing = (t >= END - 1.5) & (t < END)
    audio[closing] = 0.5 * np.sin(2 * np.pi * 880 * t[closing])
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _make_source(path: Path, src_dur: float) -> None:
    wav = path.with_suffix(".wav")
    _make_wav(wav, src_dur)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={src_dur}:size=320x240:rate=25",
            "-i",
            str(wav),
            "-vf",
            "drawbox=x=0:y=0:w=iw:h=ih:c=white:t=fill:enable='between(t,10,10.3)'",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(proc.stdout.strip())


def _zone_rms(path: Path, t0: float, t1: float, sr: int = 8000) -> float:
    proc = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-i",
            str(path),
            "-ss",
            f"{max(t0, 0.0):.3f}",
            "-to",
            f"{max(t1, 0.0):.3f}",
            "-map",
            "0:a",
            "-ar",
            str(sr),
            "-ac",
            "1",
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float64) / 32768.0
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2)))


def _plan(**overrides: Any) -> EditPlan:
    defaults: dict[str, Any] = {
        "start": START,
        "end": END,
        "fade_in": FADE,
        "logo_hold": 0.0,
        "fade_to_black": True,
    }
    defaults.update(overrides)
    return EditPlan(**defaults)


def _first_pts(path: Path, stream: str) -> float:
    proc = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            stream,
            "-show_entries",
            "packet=pts_time",
            "-of",
            "csv=p=0",
            "-read_intervals",
            "%+#1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    values = [float(v) for v in proc.stdout.split() if v.strip() not in ("", "N/A")]
    assert values, f"no packets for {stream}"
    return min(values)


def _audio_peak_time(path: Path, lo: float, hi: float) -> float:
    proc = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a",
            "-ar",
            "8000",
            "-ac",
            "1",
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float64) / 32768.0
    sr = 8000
    win = int(0.05 * sr)
    lo_i, hi_i = int(lo * sr), int(hi * sr)
    best_t, best_e = lo, -1.0
    for i in range(lo_i, min(hi_i, samples.size - win), win):
        e = float(np.mean(samples[i : i + win] ** 2))
        if e > best_e:
            best_e, best_t = e, i / sr
    return best_t + _first_pts(path, "a:0")


def _video_flash_time(path: Path) -> float:
    proc = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            "fps=25",
            "-pix_fmt",
            "gray8",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    out = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = (int(v) for v in out.stdout.strip().split(","))
    frames = np.frombuffer(proc.stdout, dtype=np.uint8).reshape(-1, h, w)
    return float(np.argmax(frames.mean(axis=(1, 2))) / 25.0)


@pytest.fixture(scope="module")
def src25(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("tail") / "src25.mp4"
    _make_source(path, 25.0)
    return path


@needs_ffmpeg
def test_default_tail_seconds_is_two() -> None:
    assert DEFAULT_FADE_OUT_TAIL_SECONDS == 2.0


@needs_ffmpeg
def test_example_config_documents_tail_key() -> None:
    from pathlib import Path as _P

    text = (
        _P(__file__).resolve().parent.parent.parent / "config" / "config.example.yaml"
    ).read_text(encoding="utf-8")
    assert "fade_out_tail_seconds: 2.0" in text


@needs_ffmpeg
def test_duration_matches_L_with_positive_offset(tmp_path: Path, src25: Path) -> None:
    out = tmp_path / "out.mp4"
    apply_edit(src25, _plan(audio_offset=D), out)
    assert _probe_duration(out) == pytest.approx(DUR + TAIL_DEFAULT + D, abs=0.35)


@needs_ffmpeg
def test_duration_matches_L_with_zero_offset(tmp_path: Path, src25: Path) -> None:
    out = tmp_path / "out.mp4"
    apply_edit(src25, _plan(audio_offset=0.0), out)
    assert _probe_duration(out) == pytest.approx(DUR + TAIL_DEFAULT, abs=0.35)


@needs_ffmpeg
def test_tail_clamps_to_room(tmp_path: Path) -> None:
    src = tmp_path / "src_small.mp4"
    _make_source(src, 23.5)
    out = tmp_path / "out.mp4"
    apply_edit(src, _plan(audio_offset=D), out)
    assert _probe_duration(out) == pytest.approx(DUR + 0.6 + D, abs=0.35)


@needs_ffmpeg
def test_no_room_tail_zero(tmp_path: Path) -> None:
    src = tmp_path / "src_tight.mp4"
    _make_source(src, END)
    out = tmp_path / "out.mp4"
    apply_edit(src, _plan(audio_offset=D), out)
    assert _probe_duration(out) == pytest.approx(DUR + D, abs=0.35)


@needs_ffmpeg
def test_closing_words_at_full_level(tmp_path: Path, src25: Path) -> None:
    out = tmp_path / "out.mp4"
    apply_edit(src25, _plan(audio_offset=D), out)
    mid = _zone_rms(out, 5.0, 15.0)
    closing = _zone_rms(out, DUR + D - 0.6, DUR + D - 0.1)
    assert closing >= 0.9 * mid


@needs_ffmpeg
def test_end_fade_attenuated_and_speech_untouched(tmp_path: Path, src25: Path) -> None:
    out = tmp_path / "out.mp4"
    apply_edit(src25, _plan(audio_offset=D), out)
    total = DUR + TAIL_DEFAULT + D
    mid = _zone_rms(out, 5.0, 15.0)
    assert _zone_rms(out, total - FADE, total) <= 0.25 * mid
    assert _zone_rms(out, DUR - 1.0, DUR) >= 0.9 * mid


@needs_ffmpeg
def test_sync_marker_preserved(tmp_path: Path, src25: Path) -> None:
    out = tmp_path / "out.mp4"
    apply_edit(src25, _plan(audio_offset=D), out)
    assert _audio_peak_time(out, 6.0, 12.0) == pytest.approx(10.0 - START + D, abs=0.25)
    assert _video_flash_time(out) == pytest.approx(10.0 - START, abs=0.3)


@needs_ffmpeg
def test_negative_offset_keeps_tail_after_content(tmp_path: Path, src25: Path) -> None:
    out = tmp_path / "out.mp4"
    apply_edit(src25, _plan(audio_offset=-0.5), out)
    total = DUR + TAIL_DEFAULT
    assert _probe_duration(out) == pytest.approx(total, abs=0.35)
    mid = _zone_rms(out, 5.0, 15.0)
    assert _zone_rms(out, total - FADE, total) <= 0.25 * mid


def _mocked_command(monkeypatch: pytest.MonkeyPatch, src_dur: str = "25.0") -> dict[str, list[str]]:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "ffprobe" in cmd[0]:
            return subprocess.CompletedProcess(cmd, 0, src_dur, "")
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_no_logo_window_and_fade_placement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _mocked_command(monkeypatch)
    apply_edit(Path("in.mp4"), _plan(audio_offset=D), tmp_path / "out.mp4")
    cmd = captured["cmd"]
    assert cmd[cmd.index("-to") + 1] == "24.900"
    assert cmd[cmd.index("-t") + 1] == "22.900"
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "fade=t=out:st=21.900:d=1.000" in fc
    assert "afade=t=out:st=21.900:d=1.000" in fc


def test_logo_crossfade_starts_after_content_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _mocked_command(monkeypatch)
    plan = _plan(audio_offset=D, logo_hold=3.0)
    apply_edit(Path("in.mp4"), plan, tmp_path / "out.mp4", logo_path=Path("logo.png"))
    cmd = captured["cmd"]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.800:offset=22.100" in fc
    assert "fade=t=out:st=21.900:d=1.000" in fc
    assert "afade=t=out:st=21.900:d=1.000" in fc
    assert float(22.100) > DUR
    assert cmd[cmd.index("-t", cmd.index("logo.png")) + 1] == "25.100"


def test_negative_offset_window_ignores_d_pos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _mocked_command(monkeypatch)
    apply_edit(Path("in.mp4"), _plan(audio_offset=-0.5), tmp_path / "out.mp4")
    cmd = captured["cmd"]
    assert cmd[cmd.index("-to") + 1] == "24.000"
    assert cmd[cmd.index("-t") + 1] == "22.000"
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "afade=t=out:st=21.000:d=1.000" in fc


def test_unknown_duration_falls_back_to_no_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _mocked_command(monkeypatch, src_dur="not-a-number")
    apply_edit(Path("in.mp4"), _plan(audio_offset=D), tmp_path / "out.mp4")
    cmd = captured["cmd"]
    assert cmd[cmd.index("-to") + 1] == "22.900"
    assert cmd[cmd.index("-t") + 1] == "20.900"


@needs_ffmpeg
def test_logo_branch_real_render(tmp_path: Path, src25: Path) -> None:
    logo = tmp_path / "logo.png"
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x240:rate=1",
            "-frames:v",
            "1",
            str(logo),
        ],
        check=True,
        capture_output=True,
    )
    out = tmp_path / "out_logo.mp4"
    apply_edit(src25, _plan(audio_offset=D, logo_hold=1.0), out, logo_path=logo)
    assert _probe_duration(out) == pytest.approx(DUR + TAIL_DEFAULT + D + 1.0 - 0.8, abs=0.4)


@needs_ffmpeg
def test_shift_snippet_audio_preserves_tail(tmp_path: Path, src25: Path) -> None:
    from src.auto_edit import _render_snippet

    base = tmp_path / "base.mp4"
    _render_snippet(src25, START, END, base)
    base_dur = _probe_duration(base)
    out = tmp_path / "shifted.mp4"
    shift_snippet_audio(base, 0.5, out)
    assert _probe_duration(out) == pytest.approx(base_dur + 0.5, abs=0.35)
    mid = _zone_rms(out, 2.0, 8.0)
    assert _zone_rms(out, base_dur - 0.2, base_dur + 0.4) >= 0.5 * mid
