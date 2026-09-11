"""Tests for the app version helper."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from ui.version import app_version  # noqa: E402


def test_app_version_matches_pyproject():
    import tomllib

    with open(PROJECT_ROOT / "pyproject.toml", "rb") as handle:
        expected = tomllib.load(handle)["project"]["version"]

    assert app_version() == expected
    assert app_version() != "unknown"
