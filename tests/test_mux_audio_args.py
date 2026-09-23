"""Tests for mux audio codec selection and command construction."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import sermon_updater as su  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(
    not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe required"
)


def test_aac_family_is_stream_copied():
    for name in ("enhanced.mp4", "enhanced.m4a", "enhanced.aac", "ENHANCED.MP4"):
        assert su._mux_audio_codec_args(name) == ["-c:a", "copy"]


def test_other_formats_encode_at_192k():
    for name in ("enhanced.wav", "enhanced.flac", "enhanced.mp3"):
        assert su._mux_audio_codec_args(name) == ["-c:a", "aac", "-b:a", "192k"]


def test_build_mux_command_codec_args_track_the_audio_input():
    """The codec args must describe the same path handed to ``-i``.

    The old bug computed them from a transcoded sibling while the mux read the
    WAV, so ``-c:a copy`` stream-copied PCM into MP4. A divergence here is a
    regression.
    """
    for audio, expected in (
        ("enhanced.wav", ["-c:a", "aac", "-b:a", "192k"]),
        ("enhanced.mp4", ["-c:a", "copy"]),
    ):
        cmd = su._build_mux_command("source.mp4", audio, "out.mp4")
        first_i = cmd.index("-i")
        audio_i = cmd[cmd.index("-i", first_i + 1) + 1]
        assert audio_i == audio
        assert su._mux_audio_codec_args(audio_i) == expected
        codec_v = cmd.index("-c:v")
        assert cmd[codec_v + 2 : codec_v + 2 + len(expected)] == expected


@needs_ffmpeg
def test_wav_input_to_video_container_is_encoded_aac(tmp_path: Path) -> None:
    """A PCM WAV muxed into MP4 must be encoded AAC, never stream-copied."""
    video = tmp_path / "source.mp4"
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
            "-t", "1", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
        ],
        check=True,
        capture_output=True,
    )
    wav = tmp_path / "enhanced.wav"
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:a", "pcm_s16le", str(wav),
        ],
        check=True,
        capture_output=True,
    )
    out = tmp_path / "muxed.mp4"
    subprocess.run(
        su._build_mux_command(video, wav, out), check=True, capture_output=True
    )
    probe = subprocess.run(
        [
            FFPROBE, "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip() == "aac"
