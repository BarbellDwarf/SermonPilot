from __future__ import annotations

from ui.system_status import SystemStatusManager


def test_database_status_counts_the_configured_console_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "console.db"
    monkeypatch.setenv("SERMONPILOT_DB", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("ui.database._db", None)

    from ui.database import SermonDatabase, SermonRepository

    repo = SermonRepository(SermonDatabase(db_path=str(db_path)))
    for index in range(3):
        repo.save_sermon(
            {
                "id": f"s-{index}",
                "title": f"Sample Teaching {index}",
                "speaker": "Speaker A",
                "recorded_date": "2026-09-05",
                "status": "processed",
            }
        )

    result = SystemStatusManager({}).check_database()

    assert result["status"] == "ok"
    assert result["message"] == "Database healthy (3 sermons)"


def test_local_storage_count_is_labelled_as_folders_not_sermons(tmp_path) -> None:
    result = SystemStatusManager({"output_directory": str(tmp_path)}).check_local_storage()

    assert result["message"] == "0 sermon folders on disk"


def test_disabled_fallback_is_not_an_error() -> None:
    config = {
        "llm": {
            "fallback": {
                "enabled": False,
                "provider": "openai",
                "openai": {},
            }
        }
    }
    result = SystemStatusManager(config).check_llm_provider("fallback")
    assert result["status"] != "error"
    assert result["status"] == "ok"
    assert "disabled" in result["message"].lower()


def test_enabled_fallback_with_no_api_key_is_an_error() -> None:
    config = {
        "llm": {
            "fallback": {
                "enabled": True,
                "provider": "openai",
                "openai": {},
            }
        }
    }
    result = SystemStatusManager(config).check_llm_provider("fallback")
    assert result["status"] == "error"
    assert "api key missing" in result["message"].lower()


def test_fallback_with_no_enabled_key_and_no_api_key_is_an_error() -> None:
    config = {
        "llm": {
            "fallback": {
                "provider": "openai",
                "openai": {},
            }
        }
    }
    result = SystemStatusManager(config).check_llm_provider("fallback")
    assert result["status"] == "error"


def test_primary_path_unchanged() -> None:
    missing = SystemStatusManager({"llm": {"primary": {}}}).check_llm_provider("primary")
    assert missing["status"] == "error"
    assert "not configured" in missing["message"].lower()

    configured = SystemStatusManager(
        {
            "llm": {
                "primary": {
                    "provider": "openai",
                    "openai": {"api_key": "test-key", "model": "gpt-4"},
                }
            }
        }
    ).check_llm_provider("primary")
    assert configured["status"] == "ok"


def test_status_endpoint_empty_llm_block_is_warning_not_error(
    client, scoped_setup
) -> None:
    body = client.get("/api/status", headers=scoped_setup["admin_headers"]).json()
    for key in ("llm_primary", "llm_fallback", "sermonaudio_api"):
        entry = body["status"][key]
        assert entry["status"] == "warning", f"{key} reported {entry['status']}"
        assert "unconfigured in API context" in entry["message"]


def test_status_endpoint_keeps_genuine_errors(client, scoped_setup, monkeypatch) -> None:
    from ui import system_status

    def fake_status(self):
        return {
            "llm_primary": {
                "status": "error",
                "message": "Primary Ollama server not running",
                "details": "Cannot connect to Ollama",
            },
            "sermonaudio_api": {
                "status": "error",
                "message": "Authentication failed",
                "details": "Invalid API key",
            },
        }

    monkeypatch.setattr(
        system_status.SystemStatusManager, "get_comprehensive_status", fake_status
    )
    body = client.get("/api/status", headers=scoped_setup["admin_headers"]).json()
    assert body["status"]["llm_primary"]["status"] == "error"
    assert body["status"]["sermonaudio_api"]["status"] == "error"
