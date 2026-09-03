"""Tests for SQLite-backed config resolution, env seeding, and export/import."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "ui")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from ui import config_utils  # noqa: E402
from ui.config_utils import (  # noqa: E402
    ENV_CONFIG_MAP,
    INFRA_ONLY_ENV_VARS,
    load_config_from_file,
    resolve_config,
    resolve_config_with_sources,
    save_config_to_file,
)
from ui.database import SermonDatabase  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "config_test.db"))
    return SermonDatabase()


@pytest.fixture
def clear_config_env(monkeypatch):
    for var in ENV_CONFIG_MAP:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("SA_UPDATER_CONFIG", raising=False)


def test_env_overrides_db_for_mapped_keys(fresh_db, clear_config_env, monkeypatch):
    fresh_db.save_config({"broadcaster_id": "db-broadcaster", "api_key": "db-key"})
    monkeypatch.setenv("SERMONAUDIO_BROADCASTER_ID", "env-broadcaster")

    config = resolve_config(fresh_db)

    assert config["broadcaster_id"] == "env-broadcaster"
    assert config["api_key"] == "db-key"


def test_db_layer_used_for_unmapped_keys(fresh_db, clear_config_env):
    fresh_db.save_config({"metadata_processing": {"description": {"min_words": 42}}})

    config = resolve_config(fresh_db)

    assert config["metadata_processing"]["description"]["min_words"] == 42


def test_defaults_fill_missing_layers(fresh_db, clear_config_env):
    config = resolve_config(fresh_db)

    assert config["llm"]["primary"]["ollama"]["host"] == "http://localhost:11434"
    assert config["llm"]["primary"]["provider"] == "ollama"


def test_first_run_seeding_persists_env_once(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.setenv("SERMONAUDIO_API_KEY", "env-seed-key")
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")

    config = resolve_config(fresh_db)

    assert config["api_key"] == "env-seed-key"
    assert config["llm"]["primary"]["openai"]["api_key"] == "env-openai-key"
    assert fresh_db.load_config() is not None
    meta = fresh_db.load_config_meta()
    assert meta is not None
    assert meta["version"] == config_utils.CONFIG_SEED_VERSION
    assert "SERMONAUDIO_API_KEY" in meta["env_vars"]

    monkeypatch.delenv("SERMONAUDIO_API_KEY", raising=False)
    second = resolve_config(fresh_db)

    assert second["api_key"] == "env-seed-key"
    assert fresh_db.load_config_meta() == meta


def test_no_seeding_without_env_vars(fresh_db, clear_config_env):
    config = resolve_config(fresh_db)

    assert fresh_db.load_config() is None
    assert fresh_db.load_config_meta() is None
    assert config["llm"]["primary"]["ollama"]["host"] == "http://localhost:11434"


def test_load_config_without_any_config_file(fresh_db, clear_config_env):
    config = load_config_from_file()

    assert isinstance(config, dict)
    assert "llm" in config


def test_compose_env_vars_are_covered():
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    env_entries = data["services"]["sermon-pilot"]["environment"]
    compose_keys = {entry.split("=", 1)[0] for entry in env_entries}

    uncovered = compose_keys - set(ENV_CONFIG_MAP) - set(INFRA_ONLY_ENV_VARS)

    assert not uncovered, f"Compose env vars without a mapping: {sorted(uncovered)}"


def test_ollama_host_reaches_primary_and_fallback(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama-internal:11434")

    config = resolve_config(fresh_db)

    assert config["llm"]["primary"]["ollama"]["host"] == "http://ollama-internal:11434"
    assert config["llm"]["fallback"]["ollama"]["host"] == "http://ollama-internal:11434"


def test_export_import_round_trip(fresh_db, clear_config_env, monkeypatch, tmp_path):
    monkeypatch.setattr(config_utils, "project_root", tmp_path)
    saved = {
        "broadcaster_id": "round-trip-broadcaster",
        "metadata_processing": {"description": {"min_words": 55}},
    }

    assert save_config_to_file(saved) is True
    assert not (tmp_path / "config.yaml").exists()

    loaded = load_config_from_file()

    assert loaded["broadcaster_id"] == "round-trip-broadcaster"
    assert loaded["metadata_processing"]["description"]["min_words"] == 55


def test_yaml_export_only_when_file_exists(fresh_db, clear_config_env, monkeypatch, tmp_path):
    monkeypatch.setattr(config_utils, "project_root", tmp_path)
    existing = tmp_path / "config.yaml"
    existing.write_text("broadcaster_id: old-value\n", encoding="utf-8")

    assert save_config_to_file({"broadcaster_id": "new-value"}) is True

    exported = yaml.safe_load(existing.read_text(encoding="utf-8"))
    assert exported["broadcaster_id"] == "new-value"


def test_save_fails_without_database(monkeypatch):
    import ui.database as database_module

    def unavailable(*args, **kwargs):
        raise RuntimeError("settings database unavailable")

    monkeypatch.setattr(database_module, "SermonDatabase", unavailable)

    assert save_config_to_file({"broadcaster_id": "unused"}) is False


def test_plaintext_db_secret_warns(fresh_db, clear_config_env, caplog):
    fresh_db.save_config({"api_key": "stored-plain-key"})

    with caplog.at_level(logging.WARNING, logger="ui.config_utils"):
        load_config_from_file()

    warnings = [record.message for record in caplog.records]
    assert any("plaintext" in message and "api_key" in message for message in warnings)


def test_env_secret_does_not_warn(fresh_db, clear_config_env, monkeypatch, caplog):
    fresh_db.save_config({"api_key": "stored-plain-key"})
    monkeypatch.setenv("SERMONAUDIO_API_KEY", "env-key")

    with caplog.at_level(logging.WARNING, logger="ui.config_utils"):
        load_config_from_file()

    assert not any("plaintext" in record.message for record in caplog.records)


def test_placeholder_expansion_in_db_values(fresh_db, clear_config_env, monkeypatch):
    fresh_db.save_config({"llm": {"primary": {"openai": {"api_key": "${OPENAI_API_KEY}"}}}})
    monkeypatch.setenv("OPENAI_API_KEY", "expanded-key")

    config = resolve_config(fresh_db)
    assert config["llm"]["primary"]["openai"]["api_key"] == "expanded-key"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    second = resolve_config(fresh_db)
    assert second["llm"]["primary"]["openai"]["api_key"] == "${OPENAI_API_KEY}"


def test_sources_report_env_db_and_default(fresh_db, clear_config_env, monkeypatch):
    fresh_db.save_config(
        {"broadcaster_id": "db-broadcaster", "llm": {"primary": {"model_tag": "from-db"}}}
    )
    monkeypatch.setenv("SERMONAUDIO_BROADCASTER_ID", "env-broadcaster")

    config, sources = resolve_config_with_sources(fresh_db)

    assert config["broadcaster_id"] == "env-broadcaster"
    assert sources["broadcaster_id"] == "env"
    assert sources["llm.primary.model_tag"] == "db"
    assert sources["llm.primary.ollama.host"] == "default"
