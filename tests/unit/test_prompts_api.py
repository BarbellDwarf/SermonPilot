"""Tests for the DB-backed prompt template endpoints.

The Settings > Prompt Templates console reads and writes the same
``config_cache.app_config.prompt_templates`` block the pipeline resolves. A
task the operator never edited resolves to the built-in default; a saved edit
wins for the next detection; a partial update keeps the fields it omits.
"""

from __future__ import annotations

from server.api.accounts import get_db_path


def _cut_detection(config: dict) -> dict:
    return config["templates"]["cut_detection"]


def test_prompts_require_auth(client):
    assert client.get("/api/prompts/config").status_code == 401


def test_unset_cut_detection_resolves_to_builtin_default(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    got = client.get("/api/prompts/config", headers=headers)
    assert got.status_code == 200, got.text
    data = got.json()
    assert data["templates"]["cut_detection"] == data["defaults"]["cut_detection"]
    assert data["templates"]["cut_detection"]["enabled"] is True


def test_saved_cut_detection_wins_and_partial_update_preserves(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    saved = client.put(
        "/api/prompts/config",
        json={
            "templates": {
                "cut_detection": {
                    "enabled": True,
                    "system": "custom system",
                    "user": "custom {transcript}",
                }
            }
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["templates"]["cut_detection"]["user"] == "custom {transcript}"

    from ui.config_utils import resolve_config

    resolved = resolve_config().get("prompt_templates", {})
    assert resolved["cut_detection"]["user"] == "custom {transcript}"

    client.put(
        "/api/prompts/config",
        json={"templates": {"cut_detection": {"user": "next prompt"}}},
        headers=headers,
    )
    after = client.get("/api/prompts/config", headers=headers).json()
    assert _cut_detection(after)["system"] == "custom system"
    assert _cut_detection(after)["user"] == "next prompt"


def test_disabled_cut_detection_falls_back_to_engine_default(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    client.put(
        "/api/prompts/config",
        json={"templates": {"cut_detection": {"enabled": False, "user": "ignored"}}},
        headers=headers,
    )
    from src.auto_edit import resolve_detection_template
    from ui.config_utils import resolve_config

    assert resolve_detection_template(resolve_config()) is None


def test_prompt_write_preserves_other_config(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    from ui.database import SermonDatabase

    db = SermonDatabase(db_path=get_db_path())
    db.save_config({"llm": {"primary": {"provider": "ollama"}}})

    client.put(
        "/api/prompts/config",
        json={"templates": {"cut_detection": {"user": "keep me"}}},
        headers=headers,
    )
    stored = db.load_config()
    assert stored["llm"] == {"primary": {"provider": "ollama"}}
    assert stored["prompt_templates"]["cut_detection"]["user"] == "keep me"
