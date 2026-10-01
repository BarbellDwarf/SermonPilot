from __future__ import annotations

from typing import Any

from ui.system_status import SystemStatusManager


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


def test_fallback_with_no_provider_is_ok_because_it_is_optional() -> None:
    config = {"llm": {"fallback": {"enabled": True}}}
    result = SystemStatusManager(config).check_llm_provider("fallback")
    assert result["status"] == "ok"
    assert "optional" in result["details"].lower()


def test_primary_path_unchanged() -> None:
    missing = SystemStatusManager({"llm": {"primary": {}}}).check_llm_provider("primary")
    assert missing["status"] == "error"
    assert "no ai provider chosen" in missing["message"].lower()

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


def test_status_endpoint_reports_real_config_not_an_empty_one(
    client, scoped_setup, monkeypatch
) -> None:
    """Regression: the manager used to be built from an empty dict.

    Every credential check then failed on a healthy install and the endpoint
    dressed the failure up as a soft warning.
    """
    import server.api.routers.status as status_router

    def fake_resolve() -> dict[str, Any]:
        return {"api_key": "seeded-key", "broadcaster_id": "42"}

    monkeypatch.setattr(status_router, "_resolved_config", fake_resolve)
    monkeypatch.setattr(status_router, "_accounts_exist", lambda: False)

    body = client.get("/api/status", headers=scoped_setup["admin_headers"]).json()
    entry = body["status"]["sermonaudio_api"]
    assert entry["status"] != "warning", "seeded credentials must not read as a warning"
    assert "unconfigured in API context" not in entry["message"]
    assert "unconfigured in API context" not in entry["details"]


def test_status_endpoint_never_builds_the_manager_from_an_empty_config(
    client, scoped_setup, monkeypatch
) -> None:
    """The exact defect: SystemStatusManager({}) must not reach the endpoint."""
    from ui import system_status

    configs: list[dict[str, Any]] = []
    original = system_status.SystemStatusManager.__init__

    def spy(self, config, **kwargs):
        configs.append(config)
        return original(self, config, **kwargs)

    monkeypatch.setattr(system_status.SystemStatusManager, "__init__", spy)
    client.get("/api/status", headers=scoped_setup["admin_headers"])
    assert configs, "the manager was never constructed"
    for config in configs:
        assert config != {}, "the manager was constructed with an empty config"


def test_status_endpoint_falls_back_to_unknown_when_config_cannot_resolve(
    client, scoped_setup, monkeypatch
) -> None:
    """Config resolution failing must not read as eight broken services."""
    import server.api.routers.status as status_router
    from ui import config_utils

    def boom() -> dict[str, Any]:
        raise RuntimeError("no settings database")

    monkeypatch.setattr(config_utils, "resolve_config", boom)
    body = client.get("/api/status", headers=scoped_setup["admin_headers"]).json()
    for key in status_router.SERVICE_KEYS:
        assert body["status"][key]["status"] == "unknown", key
    assert body["checked_at"]


def test_status_endpoint_names_the_settings_tab_for_a_real_problem(
    client, scoped_setup, monkeypatch
) -> None:
    """A genuine failure has to tell the operator where to go, not just that it broke."""
    from ui import system_status

    def fake_status(self):
        return {
            "sermonaudio_api": {
                "status": "error",
                "message": "SermonAudio is not connected",
                "details": "No account has been connected yet.",
            }
        }

    monkeypatch.setattr(
        system_status.SystemStatusManager, "get_comprehensive_status", fake_status
    )
    body = client.get("/api/status", headers=scoped_setup["admin_headers"]).json()
    details = body["status"]["sermonaudio_api"]["details"]
    assert "Settings" in details
    assert "SermonAudio" in details


def test_status_endpoint_downgrades_an_unrecognised_state_to_unknown(
    client, scoped_setup, monkeypatch
) -> None:
    from ui import system_status

    def fake_status(self):
        return {"database": {"status": "wat", "message": "?"}}

    monkeypatch.setattr(
        system_status.SystemStatusManager, "get_comprehensive_status", fake_status
    )
    body = client.get("/api/status", headers=scoped_setup["admin_headers"]).json()
    assert body["status"]["database"]["status"] == "unknown"


def test_no_sermonaudio_credentials_reports_a_plain_error() -> None:
    entry = SystemStatusManager({}).check_sermonaudio_api()
    assert entry["status"] == "error"
    assert entry["message"] == "SermonAudio is not connected"
    assert "api context" not in entry["message"].lower()


def test_sermonaudio_accounts_stored_per_user_count_as_connected() -> None:
    entry = SystemStatusManager({}, sermonaudio_accounts_exist=True).check_sermonaudio_api()
    assert entry["status"] == "ok"
    assert entry["message"] == "Connected per user"


def test_remediation_is_only_added_to_checks_that_need_it() -> None:
    from ui.system_status import with_remediation

    ok = with_remediation("sermonaudio_api", {"status": "ok", "details": "All good."})
    assert ok["details"] == "All good."

    broken = with_remediation(
        "sermonaudio_api", {"status": "error", "details": "Authentication failed."}
    )
    assert broken["details"].startswith("Authentication failed.")
    assert "Settings" in broken["details"]

    unknown = with_remediation("database", {"status": "unknown", "details": "No reading."})
    assert "Settings" not in unknown["details"]

    once = with_remediation("sermonaudio_api", broken)
    assert once["details"].count("Settings") == 1


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


def test_missing_resource_monitoring_is_unknown_not_a_warning(
    client, scoped_setup, monkeypatch
) -> None:
    """An unreadable gauge is not a warning. It is an unknown."""
    import builtins

    from ui import system_status

    real_import = builtins.__import__

    def no_psutil(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_psutil)
    entry = system_status.SystemStatusManager({}).check_system_resources()
    assert entry["status"] == "unknown"
