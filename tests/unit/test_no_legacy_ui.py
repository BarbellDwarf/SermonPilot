"""The legacy Streamlit interface must stay gone.

River asked for the old interface to be removed. Nothing in the repo may bring
it back by accident, so the absence is asserted rather than trusted: no source
file imports streamlit, no dependency lists it, no container publishes the port
it ran on, and the modules that only existed to serve it are not on disk.

A reinstall that reintroduces any of these would otherwise look healthy in CI
and surprise the operator on the next deploy.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Directories and files that are part of the removed interface.
REMOVED_PATHS = (
    "streamlit_app.py",
    ".streamlit",
    "ui/ui_pages",
    "ui/components",
    "ui/pages.py",
    "ui/shared_navigation.py",
    "ui/auth.py",
    "ui/ui_state.py",
    "ui/ui_processor.py",
    "ui/media_server.py",
    "ui/sermon_manager.py",
    "ui/analytics_manager.py",
    "ui/sermonaudio_analytics.py",
    "ui/sermonaudio_api.py",
    "ui/performance_monitor.py",
    "ui/sermon_importer.py",
    "ui/sermon_metadata.py",
    "ui/README.md",
    "ui/requirements-ui.txt",
)

SOURCE_SUFFIXES = (".py", ".ts", ".tsx")
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", "validation", ".venv"}


def _sources() -> list[Path]:
    found: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SOURCE_SUFFIXES:
            found.append(path)
    return sorted(found)


@pytest.mark.parametrize("relative", REMOVED_PATHS)
def test_removed_module_is_not_on_disk(relative: str) -> None:
    assert not (ROOT / relative).exists(), f"{relative} came back"


def test_no_source_file_imports_streamlit() -> None:
    offenders: list[str] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("import streamlit", "from streamlit")):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert offenders == [], f"streamlit imported at {offenders}"


def test_no_dependency_list_mentions_streamlit() -> None:
    requirements = ROOT / "requirements" / "requirements.txt"
    assert "streamlit" not in requirements.read_text(encoding="utf-8").lower()

    pyproject = ROOT / "pyproject.toml"
    parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = list(parsed["project"].get("dependencies", []))
    for extra in parsed["project"].get("optional-dependencies", {}).values():
        deps.extend(extra)
    assert not [d for d in deps if d.lower().startswith("streamlit")]


def test_the_retired_port_is_not_published() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8504" in dockerfile
    assert "8501" not in dockerfile

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "8504:8504" in compose
    assert "8501" not in compose

    nginx = (ROOT / "docker" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "sermon-processor:8504" in nginx
    assert "8501" not in nginx


def test_the_entrypoint_starts_only_the_console() -> None:
    script = (ROOT / "docker" / "start_production.sh").read_text(encoding="utf-8")
    assert "streamlit" not in script.lower()
    assert "uvicorn server.api.app:app" in script
    assert "STREAMLIT_PID" not in script


def test_the_pipeline_no_longer_needs_the_legacy_metadata_module() -> None:
    """``sermon_updater`` imports the enum from the streamlit-free module."""
    updater = (ROOT / "sermon_updater.py").read_text(encoding="utf-8")
    assert "ui.sermon_metadata_core import get_event_types" in updater
    assert "ui.sermon_metadata import" not in updater
