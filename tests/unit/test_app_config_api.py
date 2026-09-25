"""Tests for the console config section endpoints.

The endpoints read and write ``config_cache.app_config``: the same store the
pipeline resolves. These tests pin the real round-trip (a saved setting is what
``resolve_config`` returns), the environment-source reporting (a saved value is
shadowed by a named variable), secret masking, and value-free validation
errors that name the path, source, and length.
"""

from __future__ import annotations

import pytest

from ui.config_utils import ENV_CONFIG_MAP


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for var in ENV_CONFIG_MAP:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("SERMONPILOT_VARIANT", raising=False)
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(tmp_path / "absent-config.yaml"))
    return None


def test_config_section_requires_authentication(client):
    assert client.get("/api/config/sections/general").status_code == 401
    assert client.get("/api/config/sources").status_code == 401


def test_unknown_section_is_rejected(client, scoped_setup, clean_env):
    headers = scoped_setup["a"]["headers"]
    response = client.get("/api/config/sections/wizard", headers=headers)
    assert response.status_code == 404


def test_saved_section_is_what_the_pipeline_resolves(client, scoped_setup, clean_env):
    headers = scoped_setup["admin_headers"]
    body = {
        "values": {
            "dry_run": True,
            "output_directory": "console_out",
            "save_transcript": False,
        }
    }
    saved = client.put("/api/config/sections/general", json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    fields = saved.json()["fields"]
    assert fields["dry_run"]["value"] is True
    assert fields["dry_run"]["source"] == "db"
    assert fields["output_directory"]["value"] == "console_out"

    from ui.config_utils import resolve_config

    config = resolve_config()
    assert config["dry_run"] is True
    assert config["output_directory"] == "console_out"
    assert config["save_transcript"] is False


def test_environment_source_names_the_variable_and_outranks_db(
    client, scoped_setup, clean_env, monkeypatch
):
    headers = scoped_setup["admin_headers"]
    client.put(
        "/api/config/sections/general",
        json={"values": {"output_directory": "db_out"}},
        headers=headers,
    )
    monkeypatch.setenv("OUTPUT_DIRECTORY", "env_out")

    view = client.get("/api/config/sections/general", headers=headers).json()
    field = view["fields"]["output_directory"]
    assert field["value"] == "env_out"
    assert field["source"] == "OUTPUT_DIRECTORY"


def test_filesystem_root_config_is_admin_only(client, scoped_setup, clean_env, tmp_path):
    user = scoped_setup["a"]["headers"]
    denied = client.put(
        "/api/config/sections/general",
        json={"values": {"output_directory": str(tmp_path / "user-root")}},
        headers=user,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "admin role required for filesystem root settings"

    allowed = client.put(
        "/api/config/sections/general",
        json={"values": {"output_directory": str(tmp_path / "operator-root")}},
        headers=scoped_setup["admin_headers"],
    )
    assert allowed.status_code == 200, allowed.text


def test_default_source_is_reported(client, scoped_setup, clean_env):
    headers = scoped_setup["a"]["headers"]
    view = client.get("/api/config/sections/audio", headers=headers).json()
    assert view["fields"]["audio_gain_db"]["source"] == "default"


def test_secret_is_write_only_and_masked(client, scoped_setup, clean_env):
    headers = scoped_setup["a"]["headers"]
    secret = "sk-transcription-secret-77bb"
    saved = client.put(
        "/api/config/sections/transcription",
        json={"values": {"transcription.whisper_openai.api_key": secret}},
        headers=headers,
    )
    assert saved.status_code == 200
    assert secret not in saved.text
    field = saved.json()["fields"]["transcription.whisper_openai.api_key"]
    assert field["secret"] is True
    assert field["has_value"] is True
    assert field["masked"].endswith("77bb")

    got = client.get("/api/config/sections/transcription", headers=headers)
    assert secret not in got.text
    assert got.json()["fields"]["transcription.whisper_openai.api_key"]["has_value"] is True


def test_empty_secret_does_not_clear_a_stored_key(client, scoped_setup, clean_env):
    headers = scoped_setup["a"]["headers"]
    client.put(
        "/api/config/sections/transcription",
        json={"values": {"transcription.whisper_openai.api_key": "sk-keep-me-1234"}},
        headers=headers,
    )
    saved = client.put(
        "/api/config/sections/transcription",
        json={"values": {"transcription.whisper_openai.api_key": ""}},
        headers=headers,
    )
    field = saved.json()["fields"]["transcription.whisper_openai.api_key"]
    assert field["has_value"] is True
    assert field["masked"].endswith("1234")


def test_validation_error_names_path_source_and_length_without_the_value(
    client, scoped_setup, clean_env
):
    headers = scoped_setup["a"]["headers"]
    response = client.put(
        "/api/config/sections/audio",
        json={"values": {"audio_gain_db": "not-a-number"}},
        headers=headers,
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "audio_gain_db" in detail
    assert "source: saved setting" in detail
    assert "12 characters" in detail
    assert "not-a-number" not in detail


def test_unknown_paths_are_ignored(client, scoped_setup, clean_env):
    headers = scoped_setup["a"]["headers"]
    saved = client.put(
        "/api/config/sections/general",
        json={"values": {"api_key": "should-not-be-written", "dry_run": True}},
        headers=headers,
    )
    assert saved.status_code == 200
    assert "api_key" not in saved.json()["fields"]
    assert "should-not-be-written" not in saved.text

    from ui.config_utils import resolve_config

    assert "should-not-be-written" != resolve_config().get("api_key")


def test_sources_endpoint_reports_no_values(client, scoped_setup, clean_env):
    headers = scoped_setup["a"]["headers"]
    response = client.get("/api/config/sources", headers=headers)
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert isinstance(sources, dict)
    assert sources.get("llm.primary.ollama.host") == "default"


def test_embeddings_surface_is_gone_from_the_console_config(
    client, scoped_setup, clean_env
):
    from server.api.routers.app_config import SECTIONS

    assert "embeddings" not in SECTIONS
    assert not any(
        path == "embeddings" or path.startswith("embeddings.")
        for paths in SECTIONS.values()
        for path in paths
    )

    headers = scoped_setup["a"]["headers"]
    response = client.get("/api/config/sections/embeddings", headers=headers)
    assert response.status_code == 404


def test_embeddings_env_overrides_are_gone():
    from src.core.config import ENV_CONFIG_MAP

    assert "EMBEDDING_PROVIDER" not in ENV_CONFIG_MAP
    assert "EMBEDDING_MODEL" not in ENV_CONFIG_MAP
    assert not any(
        path[:1] == ["embeddings"]
        for paths in ENV_CONFIG_MAP.values()
        for path in paths
    )


def test_sermonaudio_section_reports_env_source_without_the_secret(
    client, scoped_setup, clean_env, monkeypatch
):
    env_key = "placeholder-sermonaudio-secret"
    monkeypatch.setenv("SERMONAUDIO_API_KEY", env_key)
    monkeypatch.setenv("SERMONAUDIO_BROADCASTER_ID", "env-broadcaster")
    headers = scoped_setup["a"]["headers"]

    response = client.get("/api/config/sections/sermonaudio", headers=headers)

    assert response.status_code == 200
    assert env_key not in response.text
    fields = response.json()["fields"]
    assert fields["api_key"]["secret"] is True
    assert fields["api_key"]["has_value"] is True
    assert fields["api_key"]["source"] == "SERMONAUDIO_API_KEY"
    assert fields["broadcaster_id"]["value"] == "env-broadcaster"
    assert fields["broadcaster_id"]["source"] == "SERMONAUDIO_BROADCASTER_ID"


def test_sermonaudio_section_saves_to_db_and_reports_db_source(
    client, scoped_setup, clean_env
):
    headers = scoped_setup["a"]["headers"]
    stored_key = "placeholder-db-secret"

    saved = client.put(
        "/api/config/sections/sermonaudio",
        json={"values": {"api_key": stored_key, "broadcaster_id": "db-broadcaster"}},
        headers=headers,
    )

    assert saved.status_code == 200
    assert stored_key not in saved.text
    fields = saved.json()["fields"]
    assert fields["api_key"]["source"] == "db"
    assert fields["api_key"]["has_value"] is True
    assert fields["api_key"]["masked"].endswith("cret")
    assert fields["broadcaster_id"]["value"] == "db-broadcaster"
    assert fields["broadcaster_id"]["source"] == "db"

    got = client.get("/api/config/sections/sermonaudio", headers=headers)
    assert stored_key not in got.text
    assert got.json()["fields"]["api_key"]["source"] == "db"

