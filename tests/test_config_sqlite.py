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
def clear_config_env(monkeypatch, tmp_path):
    for var in ENV_CONFIG_MAP:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(tmp_path / "absent-config.yaml"))


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


def test_config_like_env_seeds_db_once_and_is_idempotent(
    fresh_db, clear_config_env, monkeypatch
):
    monkeypatch.setenv("OLLAMA_HOST", "http://seeded-ollama:11434")
    calls: list[dict] = []
    original = fresh_db.save_config

    def counting_save(config):
        calls.append(config)
        return original(config)

    monkeypatch.setattr(fresh_db, "save_config", counting_save)

    config = resolve_config(fresh_db)

    assert config["llm"]["primary"]["ollama"]["host"] == "http://seeded-ollama:11434"
    stored = fresh_db.load_config()
    assert stored["llm"]["primary"]["ollama"]["host"] == "http://seeded-ollama:11434"
    meta = fresh_db.load_config_meta()
    assert "OLLAMA_HOST" in meta["env_vars"]
    writes_after_first = len(calls)
    assert writes_after_first >= 1

    second = resolve_config(fresh_db)
    assert second["llm"]["primary"]["ollama"]["host"] == "http://seeded-ollama:11434"
    assert len(calls) == writes_after_first


def test_config_like_env_value_survives_env_removal(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIRECTORY", "seeded-output")
    resolve_config(fresh_db)

    monkeypatch.delenv("OUTPUT_DIRECTORY", raising=False)
    second = resolve_config(fresh_db)

    assert second["output_directory"] == "seeded-output"


def test_provider_secrets_stay_in_environment_and_never_reach_db(
    fresh_db, clear_config_env, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "env-provider-key")

    config = resolve_config(fresh_db)

    assert config["llm"]["primary"]["openai"]["api_key"] == "env-provider-key"
    assert fresh_db.load_config() is None


def test_sermonaudio_credentials_seed_db_from_env(fresh_db, clear_config_env, monkeypatch):
    env_key = "placeholder-sermonaudio-key"
    monkeypatch.setenv("SERMONAUDIO_API_KEY", env_key)
    monkeypatch.setenv("SERMONAUDIO_BROADCASTER_ID", "env-broadcaster")

    config, sources = resolve_config_with_sources(fresh_db)

    assert sources["api_key"] == "SERMONAUDIO_API_KEY"
    assert sources["broadcaster_id"] == "SERMONAUDIO_BROADCASTER_ID"
    assert len(config["api_key"]) == len(env_key)
    stored = fresh_db.load_config()
    assert stored is not None
    assert len(stored["api_key"]) == len(env_key)
    assert stored["broadcaster_id"] == "env-broadcaster"


def test_sermonaudio_key_seeds_missing_path_in_existing_db(
    fresh_db, clear_config_env, monkeypatch
):
    fresh_db.save_config({"dry_run": True})
    env_key = "placeholder-existing-db-key"
    monkeypatch.setenv("SERMONAUDIO_API_KEY", env_key)

    config, sources = resolve_config_with_sources(fresh_db)

    assert sources["api_key"] == "SERMONAUDIO_API_KEY"
    assert len(config["api_key"]) == len(env_key)
    stored = fresh_db.load_config()
    assert stored["dry_run"] is True
    assert len(stored["api_key"]) == len(env_key)


def test_sermonaudio_env_still_wins_and_db_value_is_intact(
    fresh_db, clear_config_env, monkeypatch
):
    fresh_db.save_config({"api_key": "db-placeholder-key", "broadcaster_id": "db-broadcaster"})
    env_key = "env-placeholder-key"
    monkeypatch.setenv("SERMONAUDIO_API_KEY", env_key)

    config, sources = resolve_config_with_sources(fresh_db)

    assert sources["api_key"] == "SERMONAUDIO_API_KEY"
    assert len(config["api_key"]) == len(env_key)
    stored = fresh_db.load_config()
    assert stored["api_key"] == "db-placeholder-key"
    assert stored["broadcaster_id"] == "db-broadcaster"


def test_sermonaudio_db_source_when_env_unset(fresh_db, clear_config_env):
    fresh_db.save_config({"api_key": "db-placeholder-key", "broadcaster_id": "db-broadcaster"})

    config, sources = resolve_config_with_sources(fresh_db)

    assert sources["api_key"] == "db"
    assert sources["broadcaster_id"] == "db"
    assert len(config["api_key"]) == len("db-placeholder-key")


def test_sermonaudio_unconfigured_reports_default_not_invented(
    fresh_db, clear_config_env, monkeypatch
):
    monkeypatch.delenv("SERMONPILOT_VARIANT", raising=False)

    config, sources = resolve_config_with_sources(fresh_db)

    assert sources["api_key"] == "default"
    assert sources["broadcaster_id"] == "default"
    assert not config.get("api_key")
    assert not config.get("broadcaster_id")


def test_no_seeding_without_env_vars(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.delenv("SERMONPILOT_VARIANT", raising=False)
    config = resolve_config(fresh_db)

    assert fresh_db.load_config() is None
    assert fresh_db.load_config_meta() is None
    assert config["llm"]["primary"]["ollama"]["host"] == "http://localhost:11434"


def test_fresh_seeding_uses_variant_template(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_VARIANT", "cuda")
    config = resolve_config(fresh_db)

    stored = fresh_db.load_config()
    assert stored is not None
    meta = fresh_db.load_config_meta()
    assert meta["variant"] == "cuda"
    assert config["audio_enhancement_method"] == "deepfilternet"
    assert config["preprocess_noise_gate"] is False
    assert config["api_key"] == "${SERMONAUDIO_API_KEY}"
    assert config["broadcaster_id"] == "${SERMONAUDIO_BROADCASTER_ID}"


def test_variant_template_absent_no_seeding(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.delenv("SERMONPILOT_VARIANT", raising=False)
    config = resolve_config(fresh_db)

    assert fresh_db.load_config() is None
    assert "audio_enhancement_method" not in config


def test_variant_template_env_keys_win_over_placeholders(
    fresh_db, clear_config_env, monkeypatch
):
    monkeypatch.setenv("SERMONPILOT_VARIANT", "cuda")
    monkeypatch.setenv("SERMONAUDIO_API_KEY", "env-seed-key")
    config = resolve_config(fresh_db)

    assert config["api_key"] == "env-seed-key"
    assert config["audio_enhancement_method"] == "deepfilternet"


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
    exported = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert exported["broadcaster_id"] == "round-trip-broadcaster"

    loaded = load_config_from_file()

    assert loaded["broadcaster_id"] == "round-trip-broadcaster"
    assert loaded["metadata_processing"]["description"]["min_words"] == 55


def test_save_overwrites_config_file_without_literals(
    fresh_db, clear_config_env, monkeypatch, tmp_path
):
    monkeypatch.setattr(config_utils, "project_root", tmp_path)
    existing = tmp_path / "config.yaml"
    existing.write_text("broadcaster_id: old-value\n", encoding="utf-8")

    assert save_config_to_file({"broadcaster_id": "new-value", "api_key": "literal-key"}) is True

    exported = yaml.safe_load(existing.read_text(encoding="utf-8"))
    assert exported["broadcaster_id"] == "new-value"
    assert exported["api_key"] == "${SERMONAUDIO_API_KEY}"


def test_save_succeeds_when_database_unavailable(
    fresh_db, clear_config_env, monkeypatch, tmp_path
):
    import ui.database as database_module

    monkeypatch.setattr(config_utils, "project_root", tmp_path)
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "unavailable.db"))

    def unavailable(*args, **kwargs):
        raise RuntimeError("settings database unavailable")

    monkeypatch.setattr(database_module, "SermonDatabase", unavailable)

    assert save_config_to_file({"broadcaster_id": "best-effort"}) is True
    assert (tmp_path / "config.yaml").exists()


def test_plaintext_db_secret_warns(fresh_db, clear_config_env, caplog):
    fresh_db.save_config({"api_key": "stored-plain-key"})

    with caplog.at_level(logging.WARNING, logger="ui.config_utils"):
        load_config_from_file()

    warnings = [record.message for record in caplog.records]
    assert any("plaintext" in message and "api_key" in message for message in warnings)


def test_plaintext_warning_names_the_env_var(fresh_db, clear_config_env, caplog):
    fresh_db.save_config(
        {"transcription": {"whisper_openai": {"api_key": "stored-plain-key"}}}
    )

    with caplog.at_level(logging.WARNING, logger="ui.config_utils"):
        load_config_from_file()

    assert any(
        "OPENAI_API_KEY" in record.message for record in caplog.records
    )


def test_existing_db_gets_variant_template_defaults(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_VARIANT", "cuda")
    fresh_db.save_config({"api_key": "db-kept-key"})

    config = resolve_config(fresh_db)

    assert config["api_key"] == "db-kept-key"
    assert config["audio_enhancement_method"] == "deepfilternet"


def test_builtin_prompt_templates_always_resolve(fresh_db, clear_config_env):
    config = resolve_config(fresh_db)

    templates = config["prompt_templates"]
    expected = {"title", "short_title", "description", "hashtags", "hashtag_verification"}
    assert expected <= set(templates)
    assert templates["description"]["user"]
    assert templates["cut_detection"]["user"]
    assert '{"start": <seconds>' in templates["cut_detection"]["user"]


def test_cut_detection_template_db_override_wins(fresh_db, clear_config_env):
    fresh_db.save_config(
        {"prompt_templates": {"cut_detection": {"enabled": True, "user": "DB OVERRIDE"}}}
    )

    config = resolve_config(fresh_db)

    assert config["prompt_templates"]["cut_detection"]["user"] == "DB OVERRIDE"
    assert config["prompt_templates"]["cut_detection"]["system"]


def test_load_config_safely_uses_resolution(fresh_db, clear_config_env, monkeypatch):
    monkeypatch.setenv("SERMONAUDIO_API_KEY", "env-key")
    monkeypatch.setenv("SERMONPILOT_VARIANT", "cuda")
    from ui.shared_navigation import load_config_safely

    config = load_config_safely()

    assert config["api_key"] == "env-key"
    assert config["audio_enhancement_method"] == "deepfilternet"


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


def test_sources_report_env_var_name_db_and_default(fresh_db, clear_config_env, monkeypatch):
    fresh_db.save_config(
        {"broadcaster_id": "db-broadcaster", "llm": {"primary": {"model_tag": "from-db"}}}
    )
    monkeypatch.setenv("SERMONAUDIO_BROADCASTER_ID", "env-broadcaster")

    config, sources = resolve_config_with_sources(fresh_db)

    assert config["broadcaster_id"] == "env-broadcaster"
    assert sources["broadcaster_id"] == "SERMONAUDIO_BROADCASTER_ID"
    assert sources["llm.primary.model_tag"] == "db"
    assert sources["llm.primary.ollama.host"] == "default"


def test_normalisation_error_names_path_source_and_length_only(fresh_db, clear_config_env):
    from src.core.config import ConfigValueError, coerce_value

    with pytest.raises(ConfigValueError) as excinfo:
        coerce_value(("audio_gain_db",), "very-loud", "AUDIO_GAIN_DB")

    message = str(excinfo.value)
    assert "audio_gain_db" in message
    assert "AUDIO_GAIN_DB" in message
    assert "9 characters" in message
    assert "very-loud" not in message


def test_bad_env_numeric_value_logs_source_and_length(
    fresh_db, clear_config_env, monkeypatch, caplog
):
    monkeypatch.setenv("AUDIO_GAIN_DB", "much-too-loud")

    with caplog.at_level(logging.WARNING, logger="ui.config_utils"):
        config = resolve_config(fresh_db)

    assert config.get("audio_gain_db") != "much-too-loud"
    assert any(
        "audio_gain_db" in record.message and "AUDIO_GAIN_DB" in record.message
        for record in caplog.records
    )


def test_resolves_with_no_config_file_present(fresh_db, clear_config_env, monkeypatch, tmp_path):
    monkeypatch.delenv("SA_UPDATER_CONFIG", raising=False)
    monkeypatch.delenv("SERMONPILOT_VARIANT", raising=False)
    monkeypatch.setattr(config_utils, "project_root", tmp_path)
    assert not (tmp_path / "config.yaml").exists()

    config = load_config_from_file()

    assert isinstance(config, dict)
    assert config["llm"]["primary"]["provider"] == "ollama"
    assert fresh_db.load_config() is None


class _LogSpy:
    def __init__(self):
        self.lines: list[str] = []

    def add_log(self, message: str) -> None:
        self.lines.append(message)


def _make_job_files(upload_dir: Path, stem: str = "1788307151352_sermon") -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{stem}.mp4").write_bytes(b"x")
    (upload_dir / f"{stem}_enhanced.mp4").write_bytes(b"x")
    (upload_dir / f"{stem}_cleaned.wav").write_bytes(b"x")


def test_failure_keeps_upload_but_drops_derived(tmp_path):
    from ui.job_executors import _cleanup_job_files

    upload_dir = tmp_path / "uploads"
    _make_job_files(upload_dir)
    config = {"upload_dir": str(upload_dir)}
    uploaded = str(upload_dir / "1788307151352_sermon.mp4")

    _cleanup_job_files(config, uploaded, None, _LogSpy(), keep_upload=True)

    assert (upload_dir / "1788307151352_sermon.mp4").exists()
    assert not (upload_dir / "1788307151352_sermon_enhanced.mp4").exists()
    assert not (upload_dir / "1788307151352_sermon_cleaned.wav").exists()


def test_success_deletes_upload_and_derived(tmp_path):
    from ui.job_executors import _cleanup_job_files

    upload_dir = tmp_path / "uploads"
    _make_job_files(upload_dir)
    config = {"upload_dir": str(upload_dir)}
    uploaded = str(upload_dir / "1788307151352_sermon.mp4")

    _cleanup_job_files(config, uploaded, None, _LogSpy(), keep_upload=False)

    assert not (upload_dir / "1788307151352_sermon.mp4").exists()


def test_legacy_file_never_overrides_db(fresh_db, clear_config_env, monkeypatch, tmp_path):
    cfg_file = tmp_path / "override.yaml"
    cfg_file.write_text(yaml.safe_dump({"audio_gain_db": 9.9}))
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(cfg_file))
    fresh_db.save_config({"audio_gain_db": 0.5})

    config = resolve_config(fresh_db)

    assert config["audio_gain_db"] == 0.5


def test_legacy_yaml_migrates_once(fresh_db, clear_config_env, monkeypatch, tmp_path):
    monkeypatch.setattr(config_utils, "project_root", tmp_path)
    monkeypatch.delenv("SA_UPDATER_CONFIG", raising=False)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"hashtag_verification": False}))

    config = resolve_config(fresh_db)

    assert config["hashtag_verification"] is False
    assert fresh_db.load_config().get("hashtag_verification") is False
    assert (tmp_path / "config.yaml").exists()

    second = resolve_config(fresh_db)
    assert second["hashtag_verification"] is False


def test_sweep_uploads_root_is_pattern_filtered(tmp_path, monkeypatch):
    import os
    import time as _time

    from ui.config_utils import sweep_stale_job_files

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    old = _time.time() - 48 * 3600
    job_upload = uploads / "1788307151352_sermon.mp4"
    bystander = uploads / "keepme.txt"
    job_upload.write_bytes(b"x")
    bystander.write_bytes(b"x")
    os.utime(job_upload, (old, old))
    os.utime(bystander, (old, old))

    monkeypatch.setattr(config_utils, "project_root", tmp_path)
    sweep_stale_job_files({
        "upload_dir": str(uploads),
        "processing_temp_dir": str(tmp_path / "processing"),
        "output_directory": str(tmp_path / "out"),
    })

    assert not job_upload.exists()
    assert bystander.exists()


def test_defaults_have_no_embeddings_section(clear_config_env, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/cfg.db")
    config = resolve_config()
    assert "embeddings" not in config
