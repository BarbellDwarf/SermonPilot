from __future__ import annotations

import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from job_queue import _coerce_job_result  # noqa: E402


def test_apply_result_shape_with_render_only_parses() -> None:
    result = _coerce_job_result({"success": True, "render_only": True, "elapsed_seconds": 123.4})
    assert result.success is True
    assert result.data["render_only"] is True
    assert result.data["elapsed_seconds"] == 123.4


def test_error_result_without_success_defaults_false() -> None:
    result = _coerce_job_result({"error": "boom", "elapsed_seconds": 1.2, "render_only": True})
    assert result.success is False
    assert result.error == "boom"
    assert result.data["render_only"] is True


def test_standard_result_passes_through() -> None:
    result = _coerce_job_result({"success": True, "message": "ok", "data": {"a": 1}, "error": None})
    assert result.success is True
    assert result.message == "ok"
    assert result.data == {"a": 1}
