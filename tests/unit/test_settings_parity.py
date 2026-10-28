"""Settings parity: every resolved config leaf has a known home.

The console Settings page reads an explicit allowlist. A key the resolver
honours but no section exposes is a silent loss: the operator can see the
effect but cannot change it. This test flattens every shipped template, the
canonical example, and the environment map, then requires each leaf to be in a
console section, a documented retirement, or the documented template-only list.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from server.api.routers.app_config import (
    RETIRED_CONFIG_KEYS,
    SECTIONS,
    TEMPLATE_ONLY_CONFIG_KEYS,
)
from src.core.config import ENV_CONFIG_MAP

ROOT = Path(__file__).resolve().parents[2]


def _flatten(node: dict, prefix: str = "") -> set[str]:
    leaves: set[str] = set()
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            leaves |= _flatten(value, path)
        else:
            leaves.add(path)
    return leaves


def _resolved_leaves() -> set[str]:
    paths = sorted((ROOT / "config" / "templates").glob("*.yaml"))
    paths.append(ROOT / "config" / "config.example.yaml")
    leaves: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            leaves |= _flatten(loaded)
    for config_paths in ENV_CONFIG_MAP.values():
        leaves |= {".".join(parts) for parts in config_paths}
    return leaves


def _section_paths() -> set[str]:
    return {path for section in SECTIONS.values() for path in section}


def test_every_resolved_leaf_is_editable_or_documented() -> None:
    covered = (
        _section_paths()
        | set(RETIRED_CONFIG_KEYS)
        | set(TEMPLATE_ONLY_CONFIG_KEYS)
    )
    missing = sorted(
        path
        for path in _resolved_leaves()
        if path not in covered and not path.startswith("llm.")
    )
    assert not missing, (
        "config leaves with no Settings home: "
        + ", ".join(missing)
        + ". Add a SECTIONS entry plus UI, or document a retirement/template-only reason."
    )


def test_parity_lists_only_name_real_leaves() -> None:
    leaves = _resolved_leaves()
    stale = sorted(key for key in RETIRED_CONFIG_KEYS if key not in leaves)
    assert not stale, f"retired keys no longer exist in any template: {stale}"


def test_new_operational_sections_are_exposed() -> None:
    assert SECTIONS["storage"]["input_directory"] == "str"
    assert SECTIONS["storage"]["trash_retention_days"] == "float"
    assert SECTIONS["storage"]["upload_dir"] == "str"
    assert SECTIONS["resources"]["job_queue.min_free_ram_gb"] == "float"
    assert SECTIONS["resources"]["enhancement.min_gpu_vram_gb"] == "float"
    assert SECTIONS["audio"]["preprocess_noise_gate"] == "bool"
    assert SECTIONS["validation"]["metadata_processing.enabled"] == "bool"
    assert SECTIONS["transcription"]["transcription.faster_whisper_local.compute_type"] == "str"
