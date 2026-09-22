"""Tests for the LLM provider manager endpoints.

Covers the real config round-trip (the same ``config_cache.app_config.llm`` the
pipeline resolves), secret masking, and the live connection test against a
stubbed provider: success with measured latency and model echo, provider error
text surfaced, and a fast timeout failure.
"""

from __future__ import annotations

import time

import httpx
import pytest

from ui.config_utils import ENV_CONFIG_MAP


@pytest.fixture
def clean_llm_env(monkeypatch, tmp_path):
    for var in ENV_CONFIG_MAP:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("SERMONPILOT_VARIANT", raising=False)
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(tmp_path / "absent-config.yaml"))
    return None


def _put_primary(client, headers, **fields):
    body = {"primary": {"provider": "ollama", "model": "test-model", **fields}}
    response = client.put("/api/llm/config", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response


def test_config_round_trip_and_secret_masking(client, scoped_setup, clean_llm_env):
    headers = scoped_setup["a"]["headers"]
    secret = "sk-live-secret-9f2a"
    body = {
        "primary": {
            "provider": "ollama",
            "model": "glm-5.3-flash:cloud",
            "endpoint": "http://host.docker.internal:11434",
            "numCtx": "32768",
            "maxTokens": "16000",
            "apiKey": secret,
        },
        "fallback": {"enabled": False},
        "validator": {"enabled": False},
        "routing": {
            "metadata": "primary",
            "validation": "validator",
            "transcription_assist": "primary",
            "fallback": "fallback",
        },
    }

    saved = client.put("/api/llm/config", json=body, headers=headers)
    assert saved.status_code == 200
    assert secret not in saved.text
    data = saved.json()
    assert data["primary"]["provider"] == "ollama"
    assert data["primary"]["model"] == "glm-5.3-flash:cloud"
    assert data["primary"]["endpoint"] == "http://host.docker.internal:11434"
    assert data["primary"]["numCtx"] == "32768"
    assert data["primary"]["maxTokens"] == "16000"
    assert data["primary"]["hasKey"] is True
    assert data["primary"]["maskedKey"].endswith("9f2a")
    assert data["routing"]["validation"] == "validator"

    got = client.get("/api/llm/config", headers=headers)
    assert got.status_code == 200
    assert secret not in got.text
    assert got.json()["primary"]["model"] == "glm-5.3-flash:cloud"
    assert got.json()["primary"]["maskedKey"].endswith("9f2a")


def test_saved_change_is_what_the_pipeline_resolves(client, scoped_setup, clean_llm_env):
    headers = scoped_setup["a"]["headers"]
    _put_primary(
        client,
        headers,
        model="glm-5.3-flash:cloud",
        endpoint="http://host.docker.internal:11434",
        numCtx="32768",
        maxTokens="16000",
    )

    from ui.config_utils import resolve_config

    llm = resolve_config().get("llm", {})
    assert llm["primary"]["ollama"]["model"] == "glm-5.3-flash:cloud"
    assert llm["primary"]["ollama"]["host"] == "http://host.docker.internal:11434"


def test_secrets_never_appear_in_any_response(client, scoped_setup, clean_llm_env):
    headers = scoped_setup["a"]["headers"]
    secret = "xai-live-token-abcd1234"
    client.put(
        "/api/llm/config",
        json={
            "fallback": {
                "provider": "groq",
                "model": "llama-3.1",
                "endpoint": "https://api.groq.com/openai/v1",
                "apiKey": secret,
            }
        },
        headers=headers,
    )
    for response in (
        client.get("/api/llm/config", headers=headers),
        client.post("/api/llm/test-connection", json={"role": "fallback"}, headers=headers),
    ):
        assert secret not in response.text


def test_update_with_empty_key_keeps_stored_secret(client, scoped_setup, clean_llm_env):
    headers = scoped_setup["a"]["headers"]
    _put_primary(client, headers, apiKey="sk-keep-me-77bb")
    updated = client.put(
        "/api/llm/config",
        json={"primary": {"provider": "ollama", "model": "test-model-2", "apiKey": ""}},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["primary"]["hasKey"] is True
    assert updated.json()["primary"]["maskedKey"].endswith("77bb")


def test_connection_success_reports_measured_latency_and_model(
    client, scoped_setup, clean_llm_env, monkeypatch
):
    headers = scoped_setup["a"]["headers"]
    client.put(
        "/api/llm/config",
        json={
            "primary": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "endpoint": "https://api.openai.com/v1",
                "apiKey": "sk-test-123456",
            }
        },
        headers=headers,
    )

    from server.api.routers import llm_config as mod

    clock = {"now": 100.0}
    monkeypatch.setattr(mod.time, "perf_counter", lambda: clock["now"])
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        clock["now"] += 0.25
        return httpx.Response(
            200, json={"model": "gpt-4o-mini-2024", "choices": [{"message": {"content": "p"}}]}
        )

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    response = client.post(
        "/api/llm/test-connection", json={"role": "primary"}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["latency_ms"] == 250
    assert body["model_echo"] == "gpt-4o-mini-2024"
    assert body["error"] is None
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert captured["json"]["max_tokens"] == 1


def test_ollama_test_uses_chat_endpoint_with_trivial_prompt(
    client, scoped_setup, clean_llm_env, monkeypatch
):
    headers = scoped_setup["a"]["headers"]
    _put_primary(client, headers, endpoint="http://host.docker.internal:11434")
    from server.api.routers import llm_config as mod

    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, json={"model": "glm-5.3-flash:cloud"})

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    body = client.post(
        "/api/llm/test-connection", json={"role": "primary"}, headers=headers
    ).json()
    assert body["ok"] is True
    assert body["model_echo"] == "glm-5.3-flash:cloud"
    assert captured["url"] == "http://host.docker.internal:11434/api/chat"
    assert captured["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert captured["json"]["options"] == {"num_predict": 1}


def test_connection_surfaces_provider_error_text(client, scoped_setup, clean_llm_env, monkeypatch):
    headers = scoped_setup["a"]["headers"]
    _put_primary(client, headers, endpoint="http://host.docker.internal:11434")
    from server.api.routers import llm_config as mod

    def fake_post(url, **kwargs):
        return httpx.Response(404, json={"error": "model 'nope' not found"})

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    body = client.post(
        "/api/llm/test-connection", json={"role": "primary"}, headers=headers
    ).json()
    assert body["ok"] is False
    assert body["error"] == "model 'nope' not found"
    assert body["model_echo"] is None


def test_connection_timeout_fails_fast_without_fake_success(
    client, scoped_setup, clean_llm_env, monkeypatch
):
    headers = scoped_setup["a"]["headers"]
    _put_primary(client, headers, endpoint="http://host.docker.internal:11434")
    from server.api.routers import llm_config as mod

    def fake_post(url, **kwargs):
        raise httpx.ReadTimeout("provider did not answer")

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    started = time.perf_counter()
    body = client.post(
        "/api/llm/test-connection",
        json={"role": "primary", "timeout_seconds": 2},
        headers=headers,
    ).json()
    elapsed = time.perf_counter() - started
    assert body["ok"] is False
    assert "Timed out after 2s" in body["error"]
    assert elapsed < 1.0


def test_connection_requires_endpoint_and_model(client, scoped_setup, clean_llm_env):
    headers = scoped_setup["a"]["headers"]
    body = client.post(
        "/api/llm/test-connection", json={"role": "primary"}, headers=headers
    ).json()
    assert body["ok"] is False
    assert body["error"] == "No model configured."

    from server.api.routers.llm_config import _test_connection

    blank = _test_connection({"primary": {"provider": "ollama", "ollama": {}}}, "primary")
    assert blank["ok"] is False
    assert blank["error"] == "No endpoint configured."


def test_unknown_role_rejected(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    response = client.post(
        "/api/llm/test-connection", json={"role": "wizard"}, headers=headers
    )
    assert response.status_code == 422


def test_endpoints_require_authentication(client):
    assert client.get("/api/llm/config").status_code == 401
    assert client.post("/api/llm/test-connection", json={"role": "primary"}).status_code == 401
