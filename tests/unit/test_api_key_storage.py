"""API-key storage contract: env vars + DB, never literals in config.yaml.

Seams under test:
- src.core.config.ConfigManager (env substitution, project-root resolution)
- ui.config_utils plaintext warning + save path
- src.transcription key hygiene
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _write_yaml(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_env_substitution_resolves_var(tmp_path, monkeypatch):
    from src.core.config import ConfigManager

    monkeypatch.setenv("TEST_SERMONPILOT_KEY", "resolved-value-123")
    monkeypatch.delenv("SERMONAUDIO_API_KEY", raising=False)
    cfg_path = _write_yaml(tmp_path / "c.yaml", 'test_probe_value: "${TEST_SERMONPILOT_KEY}"\n')
    mgr = ConfigManager(cfg_path)
    assert mgr.get("test_probe_value") == "resolved-value-123"


def test_env_override_wins_over_file(tmp_path, monkeypatch):
    from src.core.config import ConfigManager

    monkeypatch.setenv("SERMONAUDIO_API_KEY", "fake-env-key-for-test")
    cfg_path = _write_yaml(tmp_path / "c.yaml", 'api_key: "file-key-should-lose"\n')
    mgr = ConfigManager(cfg_path)
    assert mgr.get("api_key") == "fake-env-key-for-test"


def test_env_substitution_missing_var_documented_fallback(tmp_path, monkeypatch):
    from src.core.config import ConfigManager

    monkeypatch.delenv("TEST_SERMONPILOT_MISSING_VAR", raising=False)
    cfg_path = _write_yaml(
        tmp_path / "c.yaml",
        'a: "${TEST_SERMONPILOT_MISSING_VAR}"\n'
        'b: "${TEST_SERMONPILOT_MISSING_VAR:-fallback123}"\n',
    )
    mgr = ConfigManager(cfg_path)
    assert mgr.get("a") == ""
    assert mgr.get("b") == "fallback123"


def test_config_path_resolution_is_absolute(tmp_path, monkeypatch):
    """Bare 'config.yaml' must resolve project-root-based, never stay relative."""
    from src.core import config as config_mod
    from src.core.config import ConfigManager

    monkeypatch.delenv("SA_UPDATER_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    mgr = ConfigManager.__new__(ConfigManager)
    resolved = mgr._resolve_config_path("config.yaml")
    assert Path(resolved).is_absolute(), f"expected absolute, got {resolved!r}"
    project_root = Path(config_mod.__file__).resolve().parent.parent.parent
    assert Path(resolved) == project_root / "config.yaml"


def test_find_config_file_never_returns_bare_relative(tmp_path, monkeypatch):
    from src.core.config import ConfigManager

    monkeypatch.delenv("SA_UPDATER_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    mgr = ConfigManager.__new__(ConfigManager)
    found = mgr._find_config_file()
    assert Path(found).is_absolute(), f"expected absolute, got {found!r}"


def test_plaintext_warning_silent_for_placeholders_db_only(tmp_path, monkeypatch, caplog):
    import ui.config_utils as cu

    monkeypatch.setattr(cu, "project_root", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "api_key": "${SERMONAUDIO_API_KEY}",
                "transcription": {"whisper_openai": {"api_key": "${OPENAI_API_KEY}"}},
                "llm": {"primary": {"openai": {"api_key": "${OPENAI_API_KEY}"}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "streamlit", None)
    with caplog.at_level(logging.WARNING, logger=""):
        cu._warn_plaintext_api_keys()
    assert not cu._find_plaintext_api_keys(
        yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    )


def test_plaintext_warning_flags_literals():
    import ui.config_utils as cu

    found = cu._find_plaintext_api_keys(
        {"api_key": "literal-key-value", "transcription": {"whisper_openai": {"api_key": "abc"}}}
    )
    assert "api_key" in found
    assert any("whisper_openai" in p for p in found)


def test_save_does_not_reintroduce_literals(tmp_path, monkeypatch):
    import ui.config_utils as cu

    monkeypatch.setattr(cu, "project_root", tmp_path)
    monkeypatch.setattr(cu, "reload_configuration", lambda: {})
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "save-test.db"))
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)

    config = {
        "api_key": "literal-sermonaudio-key",
        "broadcaster_id": "b123",
        "transcription": {"whisper_openai": {"api_key": "abc", "model": "whisper-1"}},
        "llm": {"primary": {"provider": "openai", "openai": {"api_key": "sk-live-key"}}},
    }
    assert cu.save_config_to_file(config) is True
    on_disk = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    flat_values = []

    def collect(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                collect(v)
        elif isinstance(obj, list):
            for v in obj:
                collect(v)
        elif isinstance(obj, str):
            flat_values.append(obj)

    collect(on_disk)
    assert "literal-sermonaudio-key" not in flat_values
    assert "sk-live-key" not in flat_values
    assert "abc" not in flat_values
    assert cu._find_plaintext_api_keys(on_disk) == []
    assert on_disk["api_key"] == "${SERMONAUDIO_API_KEY}"
    assert on_disk["transcription"]["whisper_openai"]["api_key"] == "${OPENAI_API_KEY}"

    from ui.database import SermonDatabase

    db_config = SermonDatabase().load_config()
    assert db_config is not None
    assert db_config["api_key"] == "literal-sermonaudio-key"
    assert db_config["transcription"]["whisper_openai"]["api_key"] == "abc"


def test_transcription_junk_key_treated_as_unset(monkeypatch):
    from src import transcription as t

    assert t._resolve_transcription_api_key("TEST_TKEY_MISSING", "abc") == ""
    assert t._resolve_transcription_api_key("TEST_TKEY_MISSING", "   ") == ""
    assert t._resolve_transcription_api_key("TEST_TKEY_MISSING", "${OPENAI_API_KEY}") == ""
    assert t._resolve_transcription_api_key("TEST_TKEY_MISSING", "") == ""
    monkeypatch.delenv("TEST_TKEY_MISSING", raising=False)

    monkeypatch.setenv("TEST_TKEY_PRESENT", "sk-valid-key-1234567890")
    assert t._resolve_transcription_api_key("TEST_TKEY_PRESENT", "abc") == "sk-valid-key-1234567890"
