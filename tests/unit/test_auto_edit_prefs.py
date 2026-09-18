from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

import auto_edit_apply as core  # noqa: E402

import sermon_updater  # noqa: E402


def _sermon_with_metadata(tmp_path: Path, trimmed: Path, full: Path, auto_edit: dict) -> dict:
    metadata = tmp_path / "metadata.json"
    payload = {
        "original_file": str(full),
        "processed_file": str(trimmed),
        "auto_edit": auto_edit,
    }
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "id": "sermon-1",
        "speaker": "Spk",
        "recorded_date": "2024-01-01",
        "event_type": "Sunday Service",
        "title": "T",
        "file_paths": {"audio": str(trimmed), "metadata": str(metadata)},
    }


def _plan(plan_id: int = 7) -> dict:
    return {
        "id": plan_id,
        "revision": 1,
        "proposed_start": 40.0,
        "proposed_end": 2958.0,
        "confidence": 1.0,
        "needs_review": False,
        "evidence": "approved in Library",
        "qa_judgment": "approved",
        "reasoning": "",
        "status": "approved",
        "notes": "",
    }


class _StubRepo:
    def __init__(self, sermon: dict, plan: dict):
        self._sermon = sermon
        self._plan = plan

    def get_sermon(self, _sermon_id):
        return dict(self._sermon)

    def get_edit_plan_history(self, _sermon_id):
        return [dict(self._plan)]

    def get_current_edit_plan(self, _sermon_id):
        return dict(self._plan)


def test_merge_auto_edit_prefs_overrides_only_pref_keys() -> None:
    config = {"auto_edit": {"enabled": True, "logo_path": "", "fade_in": 1.5}}
    metadata = {"auto_edit": {"logo_path": "/tmp/logo.png", "fade_to_black": False}}
    merged = core._merge_auto_edit_prefs(config, metadata)
    assert merged is not config and merged["auto_edit"] is not config["auto_edit"]
    assert merged["auto_edit"] == {
        "enabled": True,
        "logo_path": "/tmp/logo.png",
        "fade_in": 1.5,
        "fade_to_black": False,
    }


def test_merge_auto_edit_prefs_inputs_not_mutated() -> None:
    config = {"auto_edit": {"enabled": True}}
    metadata = {"auto_edit": {"logo_path": "/tmp/logo.png"}}
    core._merge_auto_edit_prefs(config, metadata)
    assert config == {"auto_edit": {"enabled": True}}


def test_merge_auto_edit_prefs_no_prefs_returns_config_unchanged() -> None:
    config = {"auto_edit": {"enabled": True}}
    assert core._merge_auto_edit_prefs(config, {}) is config
    assert core._merge_auto_edit_prefs(config, {"auto_edit": "junk"}) is config
    assert core._merge_auto_edit_prefs(config, None) is config


def test_merge_auto_edit_prefs_config_none_builds_auto_edit() -> None:
    merged = core._merge_auto_edit_prefs(None, {"auto_edit": {"logo_hold": 4.0}})
    assert merged == {"auto_edit": {"logo_hold": 4.0}}


def test_run_library_apply_injects_stored_prefs(tmp_path, monkeypatch):
    trimmed = tmp_path / "Sermon_Processed.mkv"
    trimmed.write_bytes(b"x")
    full = tmp_path / "Sermon_Original.mkv"
    full.write_bytes(b"x")
    logo = tmp_path / "ending.png"
    logo.write_bytes(b"png")
    sermon = _sermon_with_metadata(
        tmp_path,
        trimmed,
        full,
        {"logo_path": str(logo), "fade_to_black": False},
    )
    repo = _StubRepo(sermon, _plan())

    monkeypatch.setattr(core, "_source_duration", lambda _p: 3600.0)
    process = Mock(return_value={"success": True, "edit_plan_status": "auto_applied"})
    monkeypatch.setitem(sys.modules, "sermon_updater", Mock(process_new_sermon=process))

    core.run_library_apply(
        repo,
        "sermon-1",
        40.0,
        2958.0,
        render_only=True,
        plan_id=7,
        config={"auto_edit": {"logo_path": ""}},
    )

    merged = process.call_args.kwargs["config"]["auto_edit"]
    assert merged["logo_path"] == str(logo)
    assert merged["fade_to_black"] is False


def test_auto_edit_metadata_block_resolves_existing_logo(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"png")
    block = sermon_updater._auto_edit_metadata_block(
        {"logo_path": str(logo), "logo_hold": 2.5, "fade_to_black": False}
    )
    assert block["logo_path"] == str(logo)
    assert block["logo_hold"] == 2.5
    assert block["fade_to_black"] is False
    assert block["fade_out_tail_seconds"] == 2.0


def test_auto_edit_metadata_block_missing_logo_and_defaults() -> None:
    block = sermon_updater._auto_edit_metadata_block({"logo_path": "/no/such/file.png"})
    assert block == {
        "logo_path": "",
        "logo_hold": 3.0,
        "fade_to_black": True,
        "fade_out_tail_seconds": 2.0,
    }


def test_auto_edit_metadata_block_tolerates_non_dict() -> None:
    for bad in (None, "junk", ["x"]):
        block = sermon_updater._auto_edit_metadata_block(bad)
        assert block["logo_path"] == ""
        assert block["logo_hold"] == 3.0
        assert block["fade_to_black"] is True
        assert block["fade_out_tail_seconds"] == 2.0
