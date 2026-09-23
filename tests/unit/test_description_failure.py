"""Description generation must signal failure, never return an error string.

A generator that cannot produce usable prose raises ``DescriptionGenerationError``
so the caller can leave the stored field untouched. A failure string must never
be a return value, because the callers persist whatever comes back.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest  # noqa: E402

import sermon_updater as su  # noqa: E402
from llm_manager import LLMManager  # noqa: E402

GOOD = (
    "Pastor Example Speaker teaches on the biblical doctrine of work, concluding "
    "with Matthew 5:16 and Colossians 3:23-24, where believers are called to "
    "labor 'as unto the Lord' and not merely for men, so their diligent work "
    "shines before others. A discussion followed on vocation versus career and "
    "the temptation to chase status, closing with a call to work faithfully, "
    "rest rightly, and prepare for worship."
)

GARBAGE = (
    "Let me count characters roughly. That's about 1,180 characters. Let me count "
    "more carefully. Sentence 1: the description would go here but I have not "
    "written it yet. Roughly 270 chars."
)

FAILURE_TEXT = (
    "All LLM providers failed. Please check your configuration and network connectivity."
)


class _ScriptedProvider:
    def __init__(self, responses: list[str]) -> None:
        self.config: dict = {}
        self.model = "script-model"
        self.host = "http://script.invalid"
        self.responses = list(responses)
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        return self.responses.pop(0) if self.responses else ""


class _FailingProvider:
    def __init__(self) -> None:
        self.config: dict = {}
        self.model = "fail-model"
        self.host = "http://fail.invalid"
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        raise RuntimeError(FAILURE_TEXT)


def _manager_with(provider) -> LLMManager:
    manager = LLMManager({"llm": {"primary": {"provider": "ollama"}}})
    manager.primary_provider = provider
    manager.fallback_providers = []
    manager.call_timeout_seconds = 0.5
    manager.total_budget_seconds = 5.0
    return manager


def test_failed_generation_raises_typed_error_and_retries_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = _FailingProvider()
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))

    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        with pytest.raises(su.DescriptionGenerationError) as excinfo:
            su.generate_summary("grace and mercy " * 40)

    assert provider.calls == 2
    assert FAILURE_TEXT in str(excinfo.value)
    assert not any("Description generated (" in r.message for r in caplog.records)


def test_garbage_only_generation_raises_and_never_returns_failure_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _ScriptedProvider([GARBAGE, GARBAGE])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))
    notes: dict = {}

    with pytest.raises(su.DescriptionGenerationError):
        su.generate_summary("grace and mercy " * 40, notes=notes)

    assert provider.calls == 2
    assert notes["description_needs_review"] is True


def test_successful_generation_logs_success_exactly_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = _ScriptedProvider([GOOD])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))

    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        summary = su.generate_summary("grace and mercy " * 40)

    assert summary == GOOD
    assert provider.calls == 1
    success_lines = [r for r in caplog.records if "Description generated (" in r.message]
    assert len(success_lines) == 1
