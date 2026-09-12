"""Tests for mux audio codec selection."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import sermon_updater as su  # noqa: E402


def test_aac_family_is_stream_copied():
    for name in ("enhanced.mp4", "enhanced.m4a", "enhanced.aac", "ENHANCED.MP4"):
        assert su._mux_audio_codec_args(name) == ["-c:a", "copy"]


def test_other_formats_encode_at_192k():
    for name in ("enhanced.wav", "enhanced.flac", "enhanced.mp3"):
        assert su._mux_audio_codec_args(name) == ["-c:a", "aac", "-b:a", "192k"]
