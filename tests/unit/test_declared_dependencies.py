"""The declared dependency set has to cover what the API actually imports.

A deploy shipped a console that never came up. The entrypoint's supervision loop
kept re-running config resolution because ``import server.api.app`` raised: the
upload router registers ``File()``/``Form()`` parameters, FastAPI refuses to
register those without ``python-multipart``, and that package was declared
nowhere in the repo. It had reached the previous image only as a transitive
dependency of something else, so the day that path changed the API module
stopped importing and the whole web surface died with it.

Importing the app in a test does not catch this on a machine that happens to
have the package installed. What catches it before an image is built is the
declaration set, so this asserts the declaration first and the import second.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_SOURCES = sorted((ROOT / "server" / "api").rglob("*.py"))
REQUIREMENTS = ROOT / "requirements" / "requirements.txt"

# FastAPI and Pydantic ship features that only work when an extra package is
# present. Some raise at import time rather than at call time, which takes the
# whole API module down instead of failing one request. Each entry maps a
# feature to the distribution that provides it.
OPTIONAL_EXTRAS: dict[str, tuple[str, ...]] = {
    "python-multipart": (r"\bFile\s*\(", r"\bForm\s*\(", r"\bUploadFile\b"),
    "email-validator": (r"\bEmailStr\b", r"\bNameEmail\b", r"\bEmailUrl\b"),
    "jinja2": (r"\bJinja2Templates\b",),
    "pydantic-settings": (r"\bBaseSettings\b",),
}


def _distribution_name(requirement: str) -> str:
    return re.split(r"[\s\[<>=!;@]", requirement.strip(), maxsplit=1)[0].lower()


def _runtime_dependencies() -> set[str]:
    """pyproject runtime dependencies only. The dev extras belong to
    requirements-dev.txt and are deliberately not runtime."""
    parsed = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {_distribution_name(spec) for spec in parsed["project"]["dependencies"]}


def _installed_requirements() -> set[str]:
    """Distribution names in requirements/requirements.txt, the file the
    Dockerfile installs for every GPU variant."""
    names: set[str] = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        names.add(_distribution_name(stripped))
    return names


def _api_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("distribution", sorted(OPTIONAL_EXTRAS))
def test_optional_extra_in_use_is_declared(distribution: str) -> None:
    patterns = OPTIONAL_EXTRAS[distribution]
    used_by = [
        path.relative_to(ROOT).as_posix()
        for path in API_SOURCES
        if any(re.search(pattern, _api_source(path)) for pattern in patterns)
    ]
    if not used_by:
        pytest.skip(f"no {distribution}-backed feature is used by the API")
    assert distribution in _runtime_dependencies(), (
        f"the API uses a {distribution}-backed feature at {used_by}, but "
        f"pyproject declares no {distribution}; importing server.api.app raises "
        f"at boot and the console never comes up"
    )
    assert distribution in _installed_requirements(), (
        f"{distribution} is declared in pyproject but absent from "
        f"{REQUIREMENTS.relative_to(ROOT)}, which is what the image installs"
    )


def test_requirements_mirror_pyproject_runtime_dependencies() -> None:
    """A dependency added to one file and not the other builds an image that
    does not have what the code needs."""
    missing = _runtime_dependencies() - _installed_requirements()
    assert missing == set(), (
        f"declared in pyproject but absent from {REQUIREMENTS.relative_to(ROOT)}: "
        f"{sorted(missing)}"
    )


def test_api_app_imports() -> None:
    """The exact import the entrypoint performs."""
    from server.api.app import app  # noqa: F401

    assert app is not None


def test_upload_route_is_registered() -> None:
    """The route the missing package broke. FastAPI raises while registering a
    File()/Form() parameter without it, so the route never reaches the table."""
    from server.api.app import create_app

    paths = create_app().openapi()["paths"]
    assert "/api/sermons/upload" in paths
    assert "post" in paths["/api/sermons/upload"]