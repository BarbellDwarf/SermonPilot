from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.auto_edit import EditPlan, apply_edit


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_apply_edit_reports_monotonic_progress_for_a_real_encode(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=160x120:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
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
        check=True,
        timeout=30,
    )

    reports: list[tuple[float, str]] = []
    output = tmp_path / "edited.mp4"
    apply_edit(
        source,
        EditPlan(start=0.0, end=1.5, fade_in=0.0, logo_hold=0.0, fade_to_black=False),
        output,
        progress_callback=lambda pct, message: reports.append((pct, message)),
        cancel_check=lambda: None,
    )

    values = [pct for pct, _message in reports]
    assert output.exists()
    assert len(values) >= 2
    assert all(0.0 <= pct <= 100.0 for pct in values)
    assert all(
        earlier < later for earlier, later in zip(values[:-1], values[1:], strict=True)
    )
    assert values[-1] == 100.0
