from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.auto_edit import EditPlan, apply_edit, render_review_snippets


def _plan(**overrides: Any) -> EditPlan:
    defaults: dict[str, Any] = {
        "start": 1.0,
        "end": 60.0,
        "fade_in": 1.0,
        "logo_hold": 3.0,
        "fade_to_black": True,
    }
    defaults.update(overrides)
    return EditPlan(**defaults)


def test_invalid_plan_raises_without_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        raise AssertionError("ffmpeg must not be called for invalid plans")

    monkeypatch.setattr(subprocess, "run", fake_run)
    for start, end in ((-1.0, 5.0), (5.0, 5.0), (10.0, 5.0)):
        with pytest.raises(ValueError):
            apply_edit(Path("in.mp4"), _plan(start=start, end=end), tmp_path / "out.mp4")
    assert calls == []


def test_no_logo_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = tmp_path / "out_no_logo.mp4"
    result = apply_edit(Path("in.mp4"), _plan(), out, fade_to_black=False)

    assert result == out
    cmd = captured["cmd"]
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    ss = cmd[cmd.index("-ss") + 1]
    to = cmd[cmd.index("-to") + 1]
    assert (ss, to) == ("1.000", "60.000")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "fade=t=in:st=0.000:d=1.000" in fc
    assert "afade=t=in" in fc
    assert "[1:v]" not in fc and "xfade" not in fc
    assert "fade=t=out" not in fc
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-b:a" in cmd


def test_fade_to_black_no_logo_includes_fade_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "ffprobe" in cmd[0]:
            return subprocess.CompletedProcess(cmd, 1, "", "")
        captured["fc"] = cmd[cmd.index("-filter_complex") + 1]
        captured["t"] = cmd[cmd.index("-t") + 1]
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    apply_edit(Path("in.mp4"), _plan(), tmp_path / "out.mp4")
    assert "fade=t=out:st=58.000:d=1.000" in captured["fc"]
    assert "afade=t=out:st=58.000:d=1.000" in captured["fc"]
    assert captured["t"] == "59.000"


def test_logo_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = apply_edit(Path("in.mp4"), _plan(), tmp_path / "out.mp4", logo_path=Path("logo.png"))

    assert result == tmp_path / "out.mp4"
    cmd = captured["cmd"]
    logo_idx = cmd.index("-loop") + 1
    assert cmd[logo_idx] == "1"
    assert cmd[cmd.index("-t") + 1] == "3.000"
    assert "logo.png" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.800:offset=58.200" in fc
    assert "scale2ref" in fc
    assert "fade=t=out:st=58.000:d=1.000" in fc
    assert "[cv]" in fc and "apad" in fc
    assert "fps=30,settb=1/30[cv]" in fc
    assert "[lg0]fps=30,settb=1/30[lg]" in fc
    assert cmd[cmd.index("-t", cmd.index("logo.png")) + 1] == "61.200"
    assert cmd[cmd.index("-b:a") + 1] == "160k"


def test_logo_command_uses_probed_frame_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("src.auto_edit._ffprobe_frame_rate", lambda *_a: "30000/1001")
    apply_edit(Path("in.mp4"), _plan(), tmp_path / "out.mp4", logo_path=Path("logo.png"))

    fc = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert "fps=30000/1001,settb=1/30000[cv]" in fc
    assert "[lg0]fps=30000/1001,settb=1/30000[lg]" in fc


def test_ffmpeg_failure_raises_runtime_error_with_stderr_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "ffprobe" in cmd[0]:
            return subprocess.CompletedProcess(cmd, 1, "", "")
        raise subprocess.CalledProcessError(1, cmd, output="", stderr="E" * 500 + "boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc_info:
        apply_edit(Path("in.mp4"), _plan(), tmp_path / "out.mp4")
    message = str(exc_info.value)
    assert message.endswith("boom")
    assert len(message.split("ffmpeg failed: ", 1)[1]) <= 400


def test_render_review_snippets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "ffprobe" in cmd[0]:
            return subprocess.CompletedProcess(cmd, 1, "", "")
        runs.append(cmd)
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"fake")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    snippets = render_review_snippets(
        Path("in.mp4"), _plan(start=10.0, end=50.0), tmp_path, logo_path=Path("logo.png")
    )

    assert len(snippets) == 3
    assert all(snippet.exists() for snippet in snippets)
    windows = {
        Path(cmd[-1]).name: (cmd[cmd.index("-ss") + 1], cmd[cmd.index("-to") + 1])
        for cmd in runs
        if cmd[0] == "ffmpeg"
    }
    assert windows == {
        "snippet_start.mp4": ("0.000", "20.000"),
        "snippet_end.mp4": ("40.000", "60.000"),
        "snippet_ending.mp4": ("20.000", "50.000"),
    }


def test_render_review_snippets_short_span_skips_ending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    snippets = render_review_snippets(Path("in.mp4"), _plan(start=0.0, end=0.2), tmp_path)
    assert [snippet.name for snippet in snippets] == ["snippet_start.mp4", "snippet_end.mp4"]


def _probe_json(path: Path, show: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", f"-show_{show}", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (OSError, FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("ffprobe not usable in this environment")
    return json.loads(proc.stdout)


@pytest.mark.heavy
class TestApplyEditRealFfmpeg:
    @pytest.fixture
    def sample(self, tmp_path: Path) -> Path:
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        source = tmp_path / "sample.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=6:size=320x240:rate=25",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=6",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
        return source

    @pytest.fixture
    def logo(self, tmp_path: Path) -> Path:
        logo_path = tmp_path / "logo.png"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=320x240:rate=1",
                "-frames:v",
                "1",
                str(logo_path),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
        return logo_path

    def test_apply_edit_with_logo_card(self, tmp_path: Path, sample: Path, logo: Path) -> None:
        out = tmp_path / "edited.mp4"
        result = apply_edit(
            sample,
            _plan(start=1.0, end=5.0, logo_hold=1.0),
            out,
            logo_path=logo,
            fade_to_black=True,
        )

        assert result == out and out.exists() and out.stat().st_size > 0
        streams = _probe_json(out, "streams")["streams"]
        types = {stream["codec_type"] for stream in streams}
        assert types == {"video", "audio"}
        duration = float(_probe_json(out, "format")["format"]["duration"])
        assert 5.2 == pytest.approx(duration, abs=0.6)

    def test_apply_edit_hard_end_no_logo(self, tmp_path: Path, sample: Path) -> None:
        out = tmp_path / "edited_hard.mp4"
        apply_edit(sample, _plan(start=1.0, end=4.0), out, fade_to_black=False)
        streams = _probe_json(out, "streams")["streams"]
        types = {stream["codec_type"] for stream in streams}
        assert types == {"video", "audio"}
        duration = float(_probe_json(out, "format")["format"]["duration"])
        assert 5.0 == pytest.approx(duration, abs=0.6)

    def test_apply_edit_logo_card_30fps_source(self, tmp_path: Path, logo: Path) -> None:
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        source = tmp_path / "sample30.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=6:size=320x240:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=6",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
        out = tmp_path / "edited30.mp4"
        result = apply_edit(
            source,
            _plan(start=1.0, end=5.0, logo_hold=1.0),
            out,
            logo_path=logo,
            fade_to_black=False,
        )

        assert result == out and out.exists() and out.stat().st_size > 0
        duration = float(_probe_json(out, "format")["format"]["duration"])
        assert 5.2 == pytest.approx(duration, abs=0.6)
