"""Tests for Ollama provider thinking control and truncation warnings."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from src.llm_manager import OllamaProvider  # noqa: E402


class _FakeClient:
    def __init__(self, fail_on_think: bool = False, done_reason: str = "stop"):
        self.kwargs: dict | None = None
        self.fail_on_think = fail_on_think
        self.done_reason = done_reason

    def chat(self, **kwargs):
        if self.fail_on_think and "think" in kwargs:
            raise TypeError("unexpected keyword argument 'think'")
        self.kwargs = kwargs
        return {"message": {"content": "hello"}, "done_reason": self.done_reason}


def _provider(client: _FakeClient, **config):
    provider = OllamaProvider({"host": "http://localhost:11434", "model": "m", **config})
    provider.ollama = client
    return provider


def test_think_defaults_to_false():
    client = _FakeClient()

    assert _provider(client).chat([{"role": "user", "content": "hi"}]) == "hello"
    assert client.kwargs["think"] is False


def test_think_config_enables_reasoning():
    client = _FakeClient()

    _provider(client, think=True).chat([{"role": "user", "content": "hi"}])

    assert client.kwargs["think"] is True


def test_think_kwarg_fallback_for_old_clients():
    client = _FakeClient(fail_on_think=True)

    assert _provider(client).chat([{"role": "user", "content": "hi"}]) == "hello"
    assert "think" not in client.kwargs


def test_truncation_logs_warning(caplog):
    client = _FakeClient(done_reason="length")

    with caplog.at_level(logging.WARNING, logger="src.llm_manager"):
        _provider(client).chat([{"role": "user", "content": "hi"}])

    assert any("truncated" in record.message for record in caplog.records)
