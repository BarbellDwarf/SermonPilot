"""Deletion policy: recoverable moves, cloud-safe deletes, bounded trash sweep."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from src.safe_delete import (
    TRASH_RECORD_FILENAME,
    keep_remote_media,
    redact_remote_reference,
    sweep_trash,
    trash_base_dir,
    trash_local,
    trash_remote,
    trash_sermon_media,
    trash_summary,
    trash_target,
)


def _fixed_now() -> float:
    return 1_700_000_000.0  # 2023-11-14


def _stub_runner(store: dict):
    def run(cmd, **kwargs):
        store["cmd"] = cmd
        store["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0)

    return run


def test_trash_local_moves_file_and_writes_record(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    source = tmp_path / "Sermon - Original.mp4"
    source.write_bytes(b"original bytes")

    record = trash_local(
        source,
        reason="auto_edit_keeper_replaced_original",
        sermon_id="sermon-1",
        job_id="job-1",
        stage="post_publish",
        now=_fixed_now(),
    )

    assert record is not None
    assert record.mode == "local"
    assert record.moved is True
    assert not source.exists()
    destination = Path(record.destination)
    assert destination.is_file()
    assert destination.read_bytes() == b"original bytes"
    assert destination.parent.parent.name == "2023-11-14"
    sidecar = json.loads((destination.parent / TRASH_RECORD_FILENAME).read_text(encoding="utf-8"))
    assert sidecar["source"] == str(source)
    assert sidecar["destination"] == str(destination)
    assert sidecar["reason"] == "auto_edit_keeper_replaced_original"
    assert sidecar["sermon_id"] == "sermon-1"
    assert sidecar["job_id"] == "job-1"
    assert sidecar["stage"] == "post_publish"


def test_trash_local_moves_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    directory = tmp_path / "output" / "Sermon - Series - Speaker"
    directory.mkdir(parents=True)
    (directory / "audio.mp3").write_bytes(b"audio")

    record = trash_local(directory, reason="sermon_deleted", now=_fixed_now())

    assert record is not None
    assert not directory.exists()
    moved = Path(record.destination)
    assert moved.is_dir()
    assert (moved / "audio.mp3").read_bytes() == b"audio"


def test_trash_local_missing_source_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    assert trash_local(tmp_path / "gone.mp3", reason="sermon_deleted") is None


def test_trash_local_refuses_to_nest_inside_trash(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    root = tmp_path / "trash" / "2023-11-14" / "item"
    root.mkdir(parents=True)
    candidate = root / "file.mp3"
    candidate.write_bytes(b"x")

    assert trash_local(candidate, reason="sermon_deleted") is None
    assert candidate.exists()


def test_trash_remote_issues_moveto_without_purge(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    store: dict = {}

    record = trash_remote(
        "remote:gdrive:talks/example/service.mp4",
        user_id="user-1",
        reason="sermon_deleted",
        sermon_id="sermon-1",
        now=_fixed_now(),
        runner=_stub_runner(store),
        exe="/usr/bin/rclone",
    )

    cmd = store["cmd"]
    assert cmd[0] == "/usr/bin/rclone"
    assert cmd[1] == "moveto"
    assert cmd[2] == "gdrive:talks/example/service.mp4"
    assert cmd[3] == "gdrive:_trash/2023-11-14/service.mp4"
    assert record.destination == "remote:gdrive:_trash/2023-11-14/service.mp4"
    assert record.mode == "remote"
    assert record.moved is True
    assert "purge" not in cmd
    assert not any(str(part).startswith("--drive-use-trash") for part in cmd)
    assert "--config" in cmd


def test_trash_remote_failure_leaves_object_and_marks_unmoved(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))

    def failing_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stderr="quota exceeded")

    record = trash_remote(
        "remote:gdrive:talks/service.mp4",
        user_id="user-1",
        reason="sermon_deleted",
        now=_fixed_now(),
        runner=failing_run,
        exe="/usr/bin/rclone",
    )

    assert record.moved is False
    assert record.recoverable is True
    assert record.destination == "remote:gdrive:_trash/2023-11-14/service.mp4"


def test_keep_remote_media_reports_original_reference():
    record = keep_remote_media(
        "remote:gdrive:talks/service.mp4",
        reason="sermon_deleted",
        sermon_id="sermon-1",
    )
    assert record.mode == "remote-kept"
    assert record.moved is False
    assert record.destination == "remote:gdrive:talks/service.mp4"
    assert record.recoverable is True


def test_trash_target_dispatches_local_and_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    local = tmp_path / "audio.mp3"
    local.write_bytes(b"audio")
    store: dict = {}

    local_record = trash_target(local, reason="sermon_deleted")
    assert local_record is not None and local_record.mode == "local"

    remote_record = trash_target(
        "remote:gdrive:talks/service.mp4",
        reason="sermon_deleted",
        user_id="user-1",
        runner=_stub_runner(store),
        exe="/usr/bin/rclone",
    )
    assert remote_record is not None and remote_record.mode == "remote"


def test_trash_target_refuses_remote_without_user_id():
    assert trash_target("remote:gdrive:talks/service.mp4", reason="sermon_deleted") is None


def test_trash_sermon_media_moves_local_and_keeps_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    local = tmp_path / "out" / "audio.mp3"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"audio")

    records = trash_sermon_media(
        [str(local), "remote:gdrive:talks/service.mp4", str(local)],
        sermon_id="sermon-1",
    )

    assert len(records) == 2
    modes = {record.mode for record in records}
    assert modes == {"local", "remote-kept"}
    assert not local.exists()
    kept = next(record for record in records if record.mode == "remote-kept")
    assert kept.destination == "remote:gdrive:talks/service.mp4"


def test_sweep_trash_honours_retention_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    monkeypatch.setenv("SERMONPILOT_TRASH_RETENTION_DAYS", "7")

    old = tmp_path / "trash" / "2023-01-01" / "old-item"
    old.mkdir(parents=True)
    (old / "a.mp3").write_bytes(b"old")
    fresh = tmp_path / "trash" / "2023-11-01" / "fresh-item"
    fresh.mkdir(parents=True)
    (fresh / "b.mp3").write_bytes(b"fresh")
    os.utime(old, (1, 1))
    os.utime(fresh, (2_000_000_000, 2_000_000_000))

    first = sweep_trash(now=_fixed_now())
    assert str(old) in first["removed"]
    assert not old.exists()
    assert fresh.is_dir()

    second = sweep_trash(now=_fixed_now())
    assert second["removed"] == []
    assert fresh.is_dir()


def test_sweep_trash_disabled_at_zero_retention(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    monkeypatch.setenv("SERMONPILOT_TRASH_RETENTION_DAYS", "0")
    old = tmp_path / "trash" / "2023-01-01" / "old-item"
    old.mkdir(parents=True)
    (old / "a.mp3").write_bytes(b"old")
    os.utime(old, (1, 1))

    result = sweep_trash(now=_fixed_now())

    assert result["removed"] == []
    assert old.is_dir()


def test_trash_summary_reports_root_and_retention(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
    monkeypatch.setenv("SERMONPILOT_TRASH_RETENTION_DAYS", "14")
    assert trash_base_dir() == tmp_path / "trash"
    summary = trash_summary()
    assert summary["root"] == str(tmp_path / "trash")
    assert summary["retention_days"] == 14.0


def test_redact_remote_reference_hides_folder_trail():
    assert redact_remote_reference("remote:gdrive:church/series/service.mp4") == (
        "remote:gdrive:…/service.mp4"
    )
    assert redact_remote_reference("not-a-ref") == "not-a-ref"
