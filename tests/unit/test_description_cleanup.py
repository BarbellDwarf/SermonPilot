"""Description generation must store cleaned prose, never model narration."""

from __future__ import annotations

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

NARRATION = (
    "Let me count characters roughly. That's about 1,180 characters. Let me count "
    "more carefully. Sentence 1: \"Pastor Example Speaker teaches on the biblical "
    "doctrine of work, concluding with Matthew 5:16 and Colossians 3:23-24, where "
    "believers are called to labor 'as unto the Lord' and not merely for men, so "
    "their diligent work shines before others.\" - roughly 270 chars."
)

LEAKED = GOOD + "\n\n" + NARRATION


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


def _manager_with(provider: _ScriptedProvider) -> LLMManager:
    manager = LLMManager({"llm": {"primary": {"provider": "ollama"}}})
    manager.primary_provider = provider
    manager.fallback_providers = []
    return manager


def test_leaked_narration_is_not_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _ScriptedProvider([LEAKED])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))

    summary = su.generate_summary("grace mercy peace " * 20)

    assert summary == GOOD
    assert "Let me count" not in summary
    assert "chars" not in summary
    assert provider.calls == 1


def test_commentary_only_triggers_exactly_one_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _ScriptedProvider([NARRATION, GOOD])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))
    notes: dict = {}

    summary = su.generate_summary("grace mercy peace " * 20, notes=notes)

    assert summary == GOOD
    assert provider.calls == 2
    assert notes["description_needs_review"] is False


def test_failed_retry_rejects_junk_and_marks_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _ScriptedProvider([NARRATION, "A short but real description."])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))
    notes: dict = {}

    with pytest.raises(su.DescriptionGenerationError):
        su.generate_summary("grace mercy peace " * 20, notes=notes)

    assert provider.calls == 2
    assert notes["description_needs_review"] is True
