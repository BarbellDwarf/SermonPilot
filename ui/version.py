"""Resolve the running application version for display in the UI."""

from __future__ import annotations

from pathlib import Path


def app_version() -> str:
    """Return the version from pyproject.toml, falling back to package metadata."""
    try:
        import tomllib

        root = Path(__file__).resolve().parent.parent
        with open(root / "pyproject.toml", "rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except Exception:
        pass
    try:
        from importlib.metadata import version

        return version("sermonpilot")
    except Exception:
        return "unknown"
