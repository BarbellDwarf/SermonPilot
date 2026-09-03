"""Tests for disk-backed temp path defaults, job file cleanup, and stale sweep."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from ui.config_utils import default_cache_root, sweep_stale_job_files  # noqa: E402
from ui.job_executors import _cleanup_job_files  # noqa: E402


class _LogJob:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def add_log(self, message: str) -> None:
        self.logs.append(message)


def test_default_cache_root_honors_xdg_override(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    assert default_cache_root() == tmp_path / "xdg-cache" / "sermonpilot"


def test_default_cache_root_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_cache_root() == tmp_path / ".cache" / "sermonpilot"


def test_default_cache_root_ignores_empty_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_cache_root() == tmp_path / ".cache" / "sermonpilot"


def test_cleanup_job_files_removes_upload_copy_and_processing_dir(tmp_path):
    upload_dir = tmp_path / "sermon_uploads"
    processing_root = tmp_path / "sermon_processing"
    upload_dir.mkdir()
    processing_root.mkdir()

    uploaded = upload_dir / "1700000000000_sermon.mp3"
    uploaded.write_bytes(b"x")
    muxed = upload_dir / "1700000000000_sermon_enhanced.mp3"
    muxed.write_bytes(b"x")
    untouched = tmp_path / "user_media.mp3"
    untouched.write_bytes(b"x")
    job_dir = processing_root / "abc123"
    job_dir.mkdir()
    (job_dir / "enhanced_audio.wav").write_bytes(b"x")

    _cleanup_job_files({'upload_dir': str(upload_dir)}, str(uploaded), str(job_dir), _LogJob())

    assert not uploaded.exists()
    assert not muxed.exists()
    assert untouched.exists()
    assert not job_dir.exists()
    assert processing_root.exists()


def test_cleanup_job_files_is_idempotent(tmp_path):
    upload_dir = tmp_path / "sermon_uploads"
    upload_dir.mkdir()
    uploaded = upload_dir / "1700000000000_sermon.mp3"
    uploaded.write_bytes(b"x")
    job = _LogJob()
    config = {'upload_dir': str(upload_dir)}

    _cleanup_job_files(config, str(uploaded), None, job)
    _cleanup_job_files(config, str(uploaded), None, job)

    assert not uploaded.exists()


def test_cleanup_job_files_falls_back_to_cache_root(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    uploads = tmp_path / "cache" / "sermonpilot" / "sermon_uploads"
    uploads.mkdir(parents=True)
    uploaded = uploads / "1700000000000_sermon.mp3"
    uploaded.write_bytes(b"x")

    _cleanup_job_files({}, str(uploaded), None, _LogJob())

    assert not uploaded.exists()


def test_sweep_removes_only_stale_entries(tmp_path):
    upload_dir = tmp_path / "sermon_uploads"
    processing_root = tmp_path / "sermon_processing"
    upload_dir.mkdir()
    processing_root.mkdir()

    stale_upload = upload_dir / "old_upload.mp3"
    stale_upload.write_bytes(b"x")
    fresh_upload = upload_dir / "fresh_upload.mp3"
    fresh_upload.write_bytes(b"x")
    stale_job_dir = processing_root / "stalejob"
    stale_job_dir.mkdir()
    (stale_job_dir / "enhanced_audio.wav").write_bytes(b"x")
    fresh_job_dir = processing_root / "freshjob"
    fresh_job_dir.mkdir()
    (fresh_job_dir / "enhanced_audio.wav").write_bytes(b"x")

    stale_time = time.time() - 48 * 3600
    os.utime(stale_upload, (stale_time, stale_time))
    os.utime(stale_job_dir, (stale_time, stale_time))

    sweep_stale_job_files({
        'upload_dir': str(upload_dir),
        'processing_temp_dir': str(processing_root),
    })

    assert not stale_upload.exists()
    assert fresh_upload.exists()
    assert not stale_job_dir.exists()
    assert fresh_job_dir.exists()


def test_sweep_never_touches_output_directory(tmp_path):
    output_root = tmp_path / "processed_sermons"
    nested_uploads = output_root / "nested_uploads"
    nested_uploads.mkdir(parents=True)
    stale_sermon = output_root / "some_sermon.mp3"
    stale_sermon.write_bytes(b"x")
    stale_nested = nested_uploads / "old.bin"
    stale_nested.write_bytes(b"x")

    stale_time = time.time() - 48 * 3600
    os.utime(stale_sermon, (stale_time, stale_time))
    os.utime(stale_nested, (stale_time, stale_time))

    sweep_stale_job_files({
        'upload_dir': str(nested_uploads),
        'processing_temp_dir': str(output_root),
        'output_directory': str(output_root),
    })

    assert stale_sermon.exists()
    assert stale_nested.exists()
