"""Shared test fixtures and environment setup.

The fast suite runs without network, audio, or GPU resources.  This module
points the app at a throwaway config and database, stubs optional
third-party modules, and skips tests marked ``heavy`` unless ``--run-heavy``
is passed.
"""

from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_TMP_DIR = Path(tempfile.mkdtemp(prefix="sermonpilot-tests-"))
_CONFIG_PATH = _TMP_DIR / "config.yaml"
_CONFIG_PATH.write_text(
    "api_key: test-api-key\nbroadcaster_id: test-broadcaster\noutput_directory: test_output\n",
    encoding="utf-8",
)
os.environ["SA_UPDATER_CONFIG"] = str(_CONFIG_PATH)
os.environ["DATABASE_URL"] = str(_TMP_DIR / "test.db")


def _stub_sermonaudio() -> None:
    stub = types.ModuleType("sermonaudio")
    stub.set_api_key = lambda key: None
    node = types.ModuleType("sermonaudio.node")
    requests_mod = types.ModuleType("sermonaudio.node.requests")
    requests_mod.Node = None
    node.requests = requests_mod
    stub.node = node
    sys.modules["sermonaudio"] = stub
    sys.modules["sermonaudio.node"] = node
    sys.modules["sermonaudio.node.requests"] = requests_mod


try:
    import sermonaudio  # noqa: F401
except ImportError:
    _stub_sermonaudio()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-heavy",
        action="store_true",
        default=False,
        help="Run heavy tests that need network, audio, or GPU resources",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-heavy"):
        return
    skip_heavy = pytest.mark.skip(reason="requires network, audio, or GPU; use --run-heavy")
    for item in items:
        if "heavy" in item.keywords:
            item.add_marker(skip_heavy)
