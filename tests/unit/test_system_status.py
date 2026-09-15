from __future__ import annotations

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
