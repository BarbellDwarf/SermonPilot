"""The live regression: a cancelled apply render must stop its ffmpeg child.

An apply job cancelled from the console used to leave the render's ffmpeg
running for many minutes while the single worker stayed blocked. These tests
stand a fake ``ffmpeg`` on PATH that writes a partial output and then sleeps,
so the render only finishes if the cancel path fails to stop it.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

import pytest

from src.auto_edit import EditPlan, apply_edit
from src.supervised_process import ProcessCancelled


def _install_fake_ffmpeg(bin_dir: Path) -> None:
    script = bin_dir / "ffmpeg"
    script.write_text(
        "#!/bin/sh\n"
        'for last; do :; done\n'
        'echo partial-placeholder > "$last"\n'
        "sleep 600\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _plan() -> EditPlan:
    return EditPlan(start=1.0, end=60.0, fade_in=1.0, logo_hold=0.0, fade_to_black=False)


def test_cancelled_render_stops_child_trashes_partial_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_ffmpeg(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))

    started = threading.Event()

    def cancel_check() -> None:
        if started.is_set():
            raise RuntimeError("stop-placeholder")

    threading.Thread(target=lambda: (time.sleep(0.2), started.set())).start()

    lines: list[str] = []
    out = tmp_path / "out_edited.mp4"

    begin = time.monotonic()
    with pytest.raises(ProcessCancelled):
        apply_edit(
            tmp_path / "in.mp4",
            _plan(),
            out,
            cancel_check=cancel_check,
            cancel_log=lines.append,
        )
    elapsed = time.monotonic() - begin

    assert elapsed < 8.0, f"the render child was not stopped promptly ({elapsed:.2f}s)"
    assert not out.exists(), "the partial render was left in place"
    assert list((tmp_path / "trash").rglob("out_edited.mp4")), (
        "the partial render was not moved into the trash area"
    )
    assert lines and lines[0] == "Cancel requested - stopping edit render", lines
    assert any(
        "Cancelled during edit render (stopped after" in line for line in lines
    ), lines
