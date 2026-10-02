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
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_SOURCES = sorted((ROOT / "server" / "api").rglob("*.py"))
REQUIREMENTS = ROOT / "requirements" / "requirements.txt"

# Top-level packages the repo owns. They resolve from the checkout, not from a
# distribution, so nothing in the closure audit applies to them.
LOCAL_PACKAGES = frozenset({"server", "src", "ui", "sermon_updater"})

# Imports the entrypoint's module needs that no declared distribution provides.
# Each entry puts an import blocker ahead of the path finder, so a module that is
# only reachable through an undeclared distribution cannot be found at all.
BLOCKED_IMPORT_SCRIPT = """
import sys
sys.path.insert(0, {root!r})

import importlib.abc


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(
                "no declared dependency provides " + fullname, name=fullname
            )
        return None


BLOCKED = frozenset({blocked!r})
sys.meta_path.insert(0, Blocker())
import server.api.app
print("imported")
"""

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


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_closure() -> set[str]:
    """Every distribution reachable from the pyproject runtime dependencies.

    A transitive requirement counts as covered: FastAPI needs starlette and
    pydantic without declaring them itself, and the image resolves them. What
    does not count is anything behind an extras marker, which is the path that
    disappeared when the legacy UI was removed.
    """
    covered: set[str] = set()
    pending = list(_runtime_dependencies())
    while pending:
        name = _normalise(pending.pop())
        if name in covered:
            continue
        covered.add(name)
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        for requirement in distribution.requires or ():
            _, _, marker = requirement.partition(";")
            if "extra" in marker:
                continue
            pending.append(_distribution_name(requirement))
    return covered


def _undeclared_modules(covered: set[str]) -> list[str]:
    """Top-level import names that no declared distribution provides."""
    undeclared = []
    for module, providers in metadata.packages_distributions().items():
        if module in sys.stdlib_module_names or module in LOCAL_PACKAGES:
            continue
        if module.startswith("_"):
            continue
        if any(provider and _normalise(provider) in covered for provider in providers):
            continue
        undeclared.append(module)
    return sorted(undeclared)


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


def test_api_app_imports_on_the_declared_dependency_set_alone() -> None:
    """Import the app with every undeclared distribution made unreachable.

    Importing it in-process proves nothing, because a developer machine and a
    CI runner may both happen to carry a package the repo never asked for. Here
    each import name no declared distribution provides is blocked before the
    path finder sees it, so the import succeeds only if the declared closure
    covers everything ``server.api.app`` pulls in at startup. That is the shape
    the image has, and it is what the deploy was missing.
    """
    blocked = _undeclared_modules(_declared_closure())
    assert blocked, "no undeclared distributions found; the audit cannot see anything"
    script = BLOCKED_IMPORT_SCRIPT.format(root=str(ROOT), blocked=blocked)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "imported" in result.stdout


def test_upload_route_is_registered() -> None:
    """The route the missing package broke. FastAPI raises while registering a
    File()/Form() parameter without it, so the route never reaches the table."""
    from server.api.app import create_app

    paths = create_app().openapi()["paths"]
    assert "/api/sermons/upload" in paths
    assert "post" in paths["/api/sermons/upload"]
