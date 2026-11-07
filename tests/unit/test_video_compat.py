from __future__ import annotations

from pathlib import Path

import pytest

from src import auto_edit


def test_probe_video_codec_reads_first_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0
        stdout = "hevc\n"

    monkeypatch.setattr(auto_edit.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(auto_edit.subprocess, "run", lambda *a, **kw: Result())
    assert auto_edit.probe_video_codec(Path("sermon.mp4")) == "hevc"


def test_ensure_browser_video_leaves_h264_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sermon.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(auto_edit, "probe_video_codec", lambda path: "h264")
    monkeypatch.setattr(
        auto_edit,
        "_run_ffmpeg",
        lambda *a, **kw: pytest.fail("h264 must not be transcoded"),
    )
    assert auto_edit.ensure_browser_video(source) == source


def test_ensure_browser_video_transcodes_hevc_with_nvenc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sermon.mp4"
    source.write_bytes(b"x")
    captured: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"h264")

    monkeypatch.setattr(auto_edit, "probe_video_codec", lambda path: "hevc")
    monkeypatch.setattr(auto_edit, "detect_hardware_encoder", lambda: ("h264_nvenc", []))
    monkeypatch.setattr(auto_edit.shutil, "which", lambda name: None)
    monkeypatch.setattr(auto_edit, "_run_ffmpeg", fake_run)

    result = auto_edit.ensure_browser_video(source)

    assert result.name == "sermon-h264.mp4"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[cmd.index("-c:v") + 1] == "h264_nvenc"
    assert cmd[cmd.index("-cq") + 1] == "21"
    assert result.exists()


def test_ensure_browser_video_falls_back_to_libx264(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sermon.mp4"
    source.write_bytes(b"x")
    captured: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"h264")

    monkeypatch.setattr(auto_edit, "probe_video_codec", lambda path: "hevc")
    monkeypatch.setattr(auto_edit, "detect_hardware_encoder", lambda: ("libx264", []))
    monkeypatch.setattr(auto_edit.shutil, "which", lambda name: None)
    monkeypatch.setattr(auto_edit, "_run_ffmpeg", fake_run)

    auto_edit.ensure_browser_video(source)

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-crf") + 1] == "20"


def test_ensure_browser_video_registers_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sermon.mp4"
    source.write_bytes(b"x")
    captured: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        captured.update(kwargs)
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(auto_edit, "probe_video_codec", lambda path: "hevc")
    monkeypatch.setattr(auto_edit, "detect_hardware_encoder", lambda: ("libx264", []))
    monkeypatch.setattr(auto_edit.shutil, "which", lambda name: None)
    monkeypatch.setattr(auto_edit, "_run_ffmpeg", fake_run)

    with pytest.raises(RuntimeError):
        auto_edit.ensure_browser_video(source)
    partials = captured["partial_paths"]
    assert isinstance(partials, list)
    assert partials[0] == tmp_path / "sermon-h264.mp4"
