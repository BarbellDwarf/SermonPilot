"""A previous trimmed render must never become the next apply's render base.

The retained full-length original or keeper is the only reference that can
certify a recorded render as full length. A render that is materially shorter
than the reference, or whose duration cannot be measured at all, is skipped so
the new plan's absolute timestamps land on the original timeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

import auto_edit_apply as core  # noqa: E402


class _Repo:
    def __init__(self, full: dict):
        self._full = full

    def get_sermon(self, _sermon_id):
        return dict(self._full)


def _sermon(tmp_path: Path, render: Path, original: Path | None) -> dict:
    metadata = tmp_path / "metadata.json"
    payload = {"processed_file": str(render)}
    if original is not None:
        payload["original_file"] = str(original)
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "id": "sermon-1",
        "speaker": "Spk",
        "recorded_date": "2024-01-01",
        "event_type": "Sunday Service",
        "title": "T",
        "file_paths": {"audio": str(render), "metadata": str(metadata)},
    }


def _durations(monkeypatch, render: Path, original: Path, render_seconds: float | None) -> None:
    def _duration(path):
        if Path(str(path)).name == render.name:
            return render_seconds
        if Path(str(path)).name == original.name:
            return 3600.0
        return None

    monkeypatch.setattr(core, "_source_duration", _duration)


def test_previous_render_shorter_than_new_plan_end_is_skipped(tmp_path, monkeypatch):
    render = tmp_path / "Sermon_Processed.mkv"
    render.write_bytes(b"x")
    original = tmp_path / "Sermon_Original.mkv"
    original.write_bytes(b"x")
    sermon = _sermon(tmp_path, render, original)
    _durations(monkeypatch, render, original, render_seconds=2972.0)

    source, enhanced = core._resolve_apply_source(sermon, _Repo(sermon), min_duration=2900.0)

    assert source == str(original)
    assert enhanced is False


def test_plan_end_beyond_render_duration_never_falls_back_to_render(tmp_path, monkeypatch):
    render = tmp_path / "Sermon_Processed.mkv"
    render.write_bytes(b"x")
    original = tmp_path / "Sermon_Original.mkv"
    original.write_bytes(b"x")
    sermon = _sermon(tmp_path, render, original)
    _durations(monkeypatch, render, original, render_seconds=2972.0)

    source, _enhanced = core._resolve_apply_source(
        sermon, _Repo(sermon), min_duration=3700.0
    )

    assert source == str(original)


def test_full_length_recorded_render_is_still_reused_as_enhanced_source(tmp_path, monkeypatch):
    render = tmp_path / "Sermon_Processed.mkv"
    render.write_bytes(b"x")
    original = tmp_path / "Sermon_Original.mkv"
    original.write_bytes(b"x")
    sermon = _sermon(tmp_path, render, original)
    _durations(monkeypatch, render, original, render_seconds=3600.0)

    source, enhanced = core._resolve_apply_source(sermon, _Repo(sermon), min_duration=2900.0)

    assert source == str(render)
    assert enhanced is True


def test_unmeasurable_render_duration_is_not_full_length(tmp_path, monkeypatch):
    render = tmp_path / "Sermon_Processed.mkv"
    render.write_bytes(b"x")
    original = tmp_path / "Sermon_Original.mkv"
    original.write_bytes(b"x")
    sermon = _sermon(tmp_path, render, original)
    _durations(monkeypatch, render, original, render_seconds=None)

    source, _enhanced = core._resolve_apply_source(
        sermon, _Repo(sermon), min_duration=2900.0
    )

    assert source == str(original)


def test_previous_render_without_a_full_length_reference_keeps_historical_fallback(
    tmp_path, monkeypatch
):
    render = tmp_path / "Sermon_Processed.mkv"
    render.write_bytes(b"x")
    sermon = _sermon(tmp_path, render, None)
    monkeypatch.setattr(core, "_source_duration", lambda _path: 2918.0)

    source, enhanced = core._resolve_apply_source(sermon, _Repo(sermon), min_duration=2900.0)

    assert source == str(render)
    assert enhanced is True
