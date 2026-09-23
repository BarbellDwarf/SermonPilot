"""Metadata generation must never wedge a job.

A provider that blocks must be abandoned once its timeout elapses; the
pipeline logs a warning and continues with the template fallback metadata.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

import sermon_updater as su
from llm_manager import LLMManager, LLMModelNotFoundError, LLMTimeoutError


class _HangingProvider:
    def __init__(self, release: threading.Event) -> None:
        self.config: dict = {}
        self.model = "hang-model"
        self.host = "http://hang.invalid"
        self.calls = 0
        self._release = release

    def chat(self, messages):
        self.calls += 1
        self._release.wait(30)
        return "too late"


class _WorkingProvider:
    def __init__(self, response: str) -> None:
        self.config: dict = {}
        self.model = "good-model"
        self.host = "http://good.invalid"
        self.response = response

    def chat(self, messages):
        return self.response


class _MissingModelProvider:
    def __init__(self) -> None:
        self.config: dict = {}
        self.model = "llama3"
        self.host = "http://missing.invalid"

    def chat(self, messages):
        raise LLMModelNotFoundError("llama3", ["glm-5.3-flash:cloud"])


def _manager_with(provider) -> LLMManager:
    manager = LLMManager({"llm": {"primary": {"provider": "ollama"}}})
    manager.primary_provider = provider
    manager.fallback_providers = []
    manager.call_timeout_seconds = 0.2
    manager.total_budget_seconds = 1.0
    return manager


def test_manager_bounds_a_hanging_call() -> None:
    release = threading.Event()
    provider = _HangingProvider(release)
    manager = _manager_with(provider)
    try:
        with pytest.raises(LLMTimeoutError):
            manager.chat([{"role": "user", "content": "hi"}])
    finally:
        release.set()
    assert provider.calls == 1


def test_pipeline_continues_when_metadata_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "out")})

    release = threading.Event()
    manager = _manager_with(_HangingProvider(release))
    monkeypatch.setattr(su, "llm_manager", manager)
    monkeypatch.setattr(su, "_reuse_existing_transcript", lambda *a, **k: "")
    monkeypatch.setattr(su, "_reuse_existing_transcript_segments", lambda *a, **k: [])
    monkeypatch.setattr(
        su,
        "transcribe_segments",
        lambda *a, **k: [{"start": 0.0, "end": 5.0, "text": "grace and mercy"}],
    )

    progress: list[str] = []
    try:
        with caplog.at_level(logging.WARNING, logger="sermon_updater"):
            result = su.process_new_sermon(
                str(audio_file),
                speaker_name="Test Speaker",
                recorded_date="2024-01-01",
                dry_run=True,
                skip_audio=True,
                progress_callback=lambda pct, msg: progress.append(msg),
            )
    finally:
        release.set()

    assert result["success"] is True
    assert any("timed out" in record.message for record in caplog.records)
    assert any("Generating description with" in message for message in progress)
    assert result["description"] != "Summary generation failed"


GOOD_DESCRIPTION = (
    "A faithful exposition of grace and mercy for the listener, tracing the "
    "Apostle Paul's argument that salvation is a gift received by faith apart "
    "from works. The speaker applies this to daily life, urging the hearer to "
    "rest in Christ's finished work and to let gratitude, not guilt, drive "
    "obedience. The message closes with a call to extend that same mercy to "
    "neighbors and to keep the gospel central in every season."
)


def test_generate_summary_returns_metadata_on_a_normal_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager_with(_WorkingProvider(GOOD_DESCRIPTION))
    monkeypatch.setattr(su, "llm_manager", manager)

    summary = su.generate_summary("grace mercy peace " * 20)

    assert summary == GOOD_DESCRIPTION


def test_generate_hashtags_returns_metadata_on_a_normal_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager_with(_WorkingProvider("#Grace #Mercy #Faith"))
    monkeypatch.setattr(su, "llm_manager", manager)

    hashtags = su.generate_hashtags("a sermon about grace and mercy")

    assert "#Grace" in hashtags
    assert "#Mercy" in hashtags


def test_pipeline_continues_when_model_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "out")})

    manager = _manager_with(_MissingModelProvider())
    monkeypatch.setattr(su, "llm_manager", manager)
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
    assert any("llama3" in record.message for record in caplog.records)
    assert any("not available" in record.message for record in caplog.records)
    assert result["description"] != "Summary generation failed"
    assert result["title"] == "Sermon by Test Speaker"


def test_metadata_stage_deadline_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "out")})

    release = threading.Event()
    # The metadata stage runs on a daemon thread that the deadline abandons.
    # Once released it keeps going, so signal its last stage and wait for it
    # before returning: a still-running thread would otherwise read the next
    # test's llm_manager and consume its scripted replies.
    stage_finished = threading.Event()

    def _fake_hashtags(*_args, **_kwargs):
        stage_finished.set()
        return "#test"

    manager = _manager_with(_HangingProvider(release))
    manager.call_timeout_seconds = 30.0
    manager.total_budget_seconds = 30.0
    monkeypatch.setattr(su, "llm_manager", manager)
    monkeypatch.setattr(su, "_metadata_stage_budget_seconds", lambda: 0.2)
    monkeypatch.setattr(su, "_reuse_existing_transcript", lambda *a, **k: "")
    monkeypatch.setattr(su, "_reuse_existing_transcript_segments", lambda *a, **k: [])
    monkeypatch.setattr(su, "generate_hashtags", _fake_hashtags)
    monkeypatch.setattr(
        su,
        "transcribe_segments",
        lambda *a, **k: [{"start": 0.0, "end": 5.0, "text": "grace and mercy"}],
    )

    try:
        with caplog.at_level(logging.WARNING, logger="sermon_updater"):
            result = su.process_new_sermon(
                str(audio_file),
                speaker_name="Test Speaker",
                recorded_date="2024-01-01",
                dry_run=True,
                skip_audio=True,
            )
    finally:
        release.set()
        assert stage_finished.wait(5)

    assert result["success"] is True
    assert any(
        "metadata stage exceeded its budget" in record.message for record in caplog.records
    )
    assert result["title"] == "Sermon by Test Speaker"
