"""Tests for the job queue resource gate."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from ui import config_utils  # noqa: E402
from ui.job_queue import JobQueue  # noqa: E402


def _queue() -> JobQueue:
    instance = JobQueue.__new__(JobQueue)
    instance._resource_wait_logged_at = 0.0
    return instance


def _ram(monkeypatch, available_bytes: int) -> None:
    fake = types.ModuleType("psutil")
    fake.virtual_memory = lambda: SimpleNamespace(available=available_bytes)
    monkeypatch.setitem(sys.modules, "psutil", fake)


def test_waits_when_ram_below_threshold(monkeypatch):
    monkeypatch.setattr(
        config_utils, "resolve_config",
        lambda: {"job_queue": {"min_free_ram_gb": 4.0, "min_free_vram_gb": 0}},
    )
    _ram(monkeypatch, 2 * 10**9)

    assert _queue()._resources_available() is False


def test_starts_when_ram_available(monkeypatch):
    monkeypatch.setattr(
        config_utils, "resolve_config",
        lambda: {"job_queue": {"min_free_ram_gb": 4.0, "min_free_vram_gb": 0}},
    )
    _ram(monkeypatch, 16 * 10**9)

    assert _queue()._resources_available() is True


def test_defaults_wait_under_three_gb(monkeypatch):
    monkeypatch.setattr(config_utils, "resolve_config", lambda: {})
    _ram(monkeypatch, 1 * 10**9)

    assert _queue()._resources_available() is False
