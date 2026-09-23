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

    assert provider.calls >= 2
    assert any("retrying once" in r.message for r in caplog.records)
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

    assert provider.calls >= 2
    assert notes["description_needs_review"] is True


def test_successful_generation_logs_success_exactly_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = _ScriptedProvider([GOOD])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))

    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        summary = su.generate_summary("grace and mercy " * 40)

    assert summary == GOOD
    assert provider.calls >= 1
    success_lines = [r for r in caplog.records if "Description generated (" in r.message]
    assert len(success_lines) == 1


def test_save_sermon_does_not_blank_description_when_omitted(tmp_path, monkeypatch) -> None:
    from ui.database import SermonDatabase, SermonRepository

    db_path = tmp_path / "review.db"
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.setattr("ui.database._db", None)
    repo = SermonRepository(SermonDatabase(db_path=str(db_path)))
    repo.save_sermon(
        {
            "id": "s-review",
            "title": "T",
            "description": "Stored description",
            "content": {"description": "Stored description", "hashtags": "#stored"},
        }
    )

    # A metadata-only save that omits description must leave it intact.
    repo.save_sermon(
        {
            "id": "s-review",
            "title": "T",
            "content": {"hashtags": "#new"},
        }
    )

    stored = repo.get_sermon("s-review")
    assert stored["description"] == "Stored description"
    assert stored["content"]["description"] == "Stored description"
    assert stored["content"]["hashtags"] == "#new"


def test_single_sermon_failure_keeps_stored_description_and_flags_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from ui.database import SermonDatabase, SermonRepository

    db_path = tmp_path / "single.db"
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.setattr("ui.database._db", None)
    monkeypatch.setattr("database._db", None)
    repo = SermonRepository(SermonDatabase(db_path=str(db_path)))
    repo.save_sermon(
        {
            "id": "s-fail",
            "title": "Stored Title",
            "speaker": "Test Speaker",
            "recorded_date": "2024-01-01",
            "status": "processed",
            "description": "Stored description",
            "content": {"description": "Stored description"},
        }
    )

    details = SimpleNamespace(
        speaker=SimpleNamespace(full_name="Test Speaker"),
        display_title="Stored Title",
        event_type="Sunday Service",
        preachDate="2024-01-01",
        bibleText="John 3:16",
        durationSeconds=1800,
        moreInfoText="Stored description",
        keywords="#stored",
        media=None,
    )
    monkeypatch.setattr(su, "Node", SimpleNamespace(get_sermon=lambda sid: details))
    monkeypatch.setattr(su, "needs_metadata_processing", lambda *a, **k: (True, False))
    monkeypatch.setattr(su, "needs_audio_processing", lambda *a, **k: False)
    monkeypatch.setattr(su, "get_sermon_transcript", lambda sid: "grace and mercy " * 20)

    def _fail(*_args, **_kwargs):
        raise su.DescriptionGenerationError("all providers failed")

    monkeypatch.setattr(su, "generate_summary", _fail)
    config = {
        "output_directory": str(tmp_path / "out"),
        "metadata_processing": {"enabled": True},
    }

    result = su.process_single_sermon("s-fail", config=config)

    stored = repo.get_sermon("s-fail")
    assert stored["description"] == "Stored description"
    assert stored["content"]["description"] == "Stored description"
    assert "generation failed" not in str(stored["description"]).lower()
    assert bool(stored["description_needs_review"]) is True
    assert result["description_needs_review"] is True


def test_single_sermon_success_updates_description_and_clears_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from ui.database import SermonDatabase, SermonRepository

    db_path = tmp_path / "single_ok.db"
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.setattr("ui.database._db", None)
    monkeypatch.setattr("database._db", None)
    repo = SermonRepository(SermonDatabase(db_path=str(db_path)))
    repo.save_sermon(
        {
            "id": "s-ok",
            "title": "Stored Title",
            "speaker": "Test Speaker",
            "recorded_date": "2024-01-01",
            "status": "processed",
            "description": "Old description",
            "description_needs_review": True,
            "content": {"description": "Old description"},
        }
    )

    details = SimpleNamespace(
        speaker=SimpleNamespace(full_name="Test Speaker"),
        display_title="Stored Title",
        event_type="Sunday Service",
        preachDate="2024-01-01",
        bibleText="John 3:16",
        durationSeconds=1800,
        moreInfoText="Old description",
        keywords="#stored",
        media=None,
    )
    monkeypatch.setattr(su, "Node", SimpleNamespace(get_sermon=lambda sid: details))
    monkeypatch.setattr(su, "needs_metadata_processing", lambda *a, **k: (True, False))
    monkeypatch.setattr(su, "needs_audio_processing", lambda *a, **k: False)
    monkeypatch.setattr(su, "get_sermon_transcript", lambda sid: "grace and mercy " * 20)
    monkeypatch.setattr(su, "generate_summary", lambda *a, **k: GOOD)
    config = {
        "output_directory": str(tmp_path / "out"),
        "metadata_processing": {"enabled": True},
    }

    result = su.process_single_sermon("s-ok", config=config)

    stored = repo.get_sermon("s-ok")
    assert stored["description"] == GOOD
    assert stored["content"]["description"] == GOOD
    assert bool(stored["description_needs_review"]) is False
    assert result["description_needs_review"] is False


def test_pipeline_failure_leaves_description_empty_and_flags_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "out")})
    monkeypatch.setattr(su, "llm_manager", _manager_with(_FailingProvider()))
    monkeypatch.setattr(su, "_reuse_existing_transcript", lambda *a, **k: "")
    monkeypatch.setattr(su, "_reuse_existing_transcript_segments", lambda *a, **k: [])
    monkeypatch.setattr(
        su,
        "transcribe_segments",
        lambda *a, **k: [{"start": 0.0, "end": 5.0, "text": "grace and mercy"}],
    )

    with caplog.at_level(logging.WARNING, logger="sermon_updater"):
        result = su.process_new_sermon(
            str(audio_file),
            speaker_name="Test Speaker",
            recorded_date="2024-01-01",
            dry_run=True,
            skip_audio=True,
        )

    assert result["success"] is True
    assert result["description_needs_review"] is True
    assert result["description"] in (None, "")
    assert FAILURE_TEXT not in str(result.get("description") or "")
    assert any(
        "description generation failed" in str(r.message).lower()
        or "leaving the field empty" in r.message
        for r in caplog.records
    )
