"""Tests for cooperative cancellation of long child processes."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from src.supervised_process import run_supervised

LONG_SLEEP = [sys.executable, "-c", "import time; time.sleep(600)"]


def _cancel_check_raising():
    def _check() -> None:
        raise RuntimeError("stop-placeholder")

    return _check


def test_cancel_stops_long_child_within_seconds_and_logs() -> None:
    lines: list[str] = []
    started = threading.Event()

    def _check() -> None:
        if started.is_set():
            raise RuntimeError("stop-placeholder")

    thread = threading.Thread(target=lambda: (time.sleep(0.2), started.set()))
    thread.start()

    begin = time.monotonic()
    with pytest.raises(RuntimeError):
        run_supervised(
            LONG_SLEEP,
            cancel_check=_check,
            step="edit render",
            poll_interval=0.05,
            terminate_grace=2.0,
            log=lines.append,
        )
    elapsed = time.monotonic() - begin
    thread.join(timeout=2.0)

    assert elapsed < 5.0, f"taking {elapsed:.2f}s to stop the child is too slow"
    assert lines[0] == "Cancel requested - stopping edit render"
    assert any(
        "Cancelled during edit render (stopped after" in line for line in lines
    ), lines


def test_cancel_moves_partial_output_to_trash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trash_root = tmp_path / "trash_root"
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(trash_root))
    partial = tmp_path / "render_edited.mp4"
    partial.write_bytes(b"half-written-placeholder")

    with pytest.raises(RuntimeError):
        run_supervised(
            LONG_SLEEP,
            cancel_check=_cancel_check_raising(),
            step="edit render",
            poll_interval=0.05,
            terminate_grace=2.0,
            partial_paths=[partial],
        )

    assert not partial.exists(), "partial render was left in place"
    moved = list(trash_root.rglob("render_edited.mp4"))
    assert moved, "partial render was not moved into the trash root"
    records = list(trash_root.rglob("trash_record.json"))
    assert records, "trash move left no recoverable trash record"


def test_hard_kill_fallback_is_reported(tmp_path: Path) -> None:
    lines: list[str] = []
    ready = tmp_path / "ready.txt"
    ignores_term = [
        sys.executable,
        "-c",
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).write_text('ready'); "
        "time.sleep(600)",
        str(ready),
    ]

    def _check() -> None:
        if ready.exists():
            raise RuntimeError("stop-placeholder")

    begin = time.monotonic()
    with pytest.raises(RuntimeError):
        run_supervised(
            ignores_term,
            cancel_check=_check,
            step="stubborn encode",
            poll_interval=0.05,
            terminate_grace=0.3,
            log=lines.append,
        )
    elapsed = time.monotonic() - begin

    assert elapsed < 5.0, "hard-kill fallback did not free the worker"
    assert any(
        "Cancelled during stubborn encode" in line and "hard kill" in line
        for line in lines
    ), lines


def test_without_cancel_hook_defers_to_subprocess_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_supervised(["ffmpeg", "-version"], capture_output=True, text=True)

    assert calls and calls[0][0] == ["ffmpeg", "-version"]
    assert result.returncode == 0


def test_timeout_stops_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        run_supervised(
            LONG_SLEEP,
            timeout=0.3,
            poll_interval=0.05,
            terminate_grace=1.0,
        )
