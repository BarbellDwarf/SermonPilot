"""Model garbage must never be stored as a description.

A refusal, a stub, a placeholder, or a reply below the minimum length is
unusable. In that case the existing description stays, the record is flagged
for review, and the job log names the reason. Both description generators (the
pipeline one and the console regenerate path) route through the single shared
validator in ``src.metadata_cleanup`` so they cannot drift apart again.
"""

from __future__ import annotations

from datetime import datetime

import pytest

import sermon_updater as su
from llm_manager import LLMManager
from ui.database import SermonDatabase, SermonRepository

GOOD = (
    "Pastor Example Speaker teaches on the biblical doctrine of work, concluding "
    "with Matthew 5:16 and Colossians 3:23-24, where believers are called to "
    "labor 'as unto the Lord' and not merely for men, so their diligent work "
    "shines before others. A discussion followed on vocation versus career and "
    "the temptation to chase status, closing with a call to work faithfully, "
    "rest rightly, and prepare for worship."
)

REFUSAL = (
    "I'm sorry, but I cannot write a description for this sermon. As an AI "
    "language model I do not have enough context from the provided transcript "
    "to produce an accurate summary. Please provide a longer transcript or "
    "write the description yourself. I am unable to complete this request."
)

PLACEHOLDER_STUB = "lorem ipsum dolor sit amet consectetur adipiscing elit " * 8

TOO_SHORT = "A short but real description."


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


def _manager_with(provider) -> LLMManager:
    manager = LLMManager({"llm": {"primary": {"provider": "ollama"}}})
    manager.primary_provider = provider
    manager.fallback_providers = []
    manager.call_timeout_seconds = 0.5
    manager.total_budget_seconds = 5.0
    return manager


@pytest.mark.parametrize(
    "reply, expected_reason",
    [
        (REFUSAL, "refusal"),
        (PLACEHOLDER_STUB, "placeholder"),
        (TOO_SHORT, "too short"),
    ],
)
def test_pipeline_generator_rejects_unusable_reply(
    monkeypatch: pytest.MonkeyPatch, reply: str, expected_reason: str
) -> None:
    provider = _ScriptedProvider([reply, reply])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))
    notes: dict = {}

    with pytest.raises(su.DescriptionGenerationError) as excinfo:
        su.generate_summary("grace and mercy " * 40, notes=notes)

    assert provider.calls == 2
    assert expected_reason in str(excinfo.value)
    assert notes["description_needs_review"] is True
    assert expected_reason in notes["description_error"]


def test_generator_returns_a_genuine_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _ScriptedProvider([GOOD])
    monkeypatch.setattr(su, "llm_manager", _manager_with(provider))

    summary = su.generate_summary("grace and mercy " * 40)

    assert summary == GOOD
    assert provider.calls == 1


def test_every_description_path_routes_through_the_shared_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One generator, one validator.

    The console's "Regenerate description" action queues a metadata-update job
    that calls ``process_single_sermon(force_description=True)``, so the only
    path that writes a description is ``generate_summary``. If it ever grows a
    second entry point, this test is where that gets noticed.
    """
    seen: list[str] = []

    def _fake_validate(raw, regenerate, **_kwargs):
        seen.append(raw)
        return GOOD, None

    monkeypatch.setattr(su, "validate_description", _fake_validate)
    monkeypatch.setattr(su, "llm_manager", _manager_with(_ScriptedProvider([GOOD])))

    su.generate_summary("grace and mercy " * 40)

    assert len(seen) == 1


def test_metadata_job_treats_a_flagged_description_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused description must not be reported as a successful regenerate."""
    from ui.job_executors import _classify_metadata_update_result

    actions = {"generate_description": True, "push_metadata": False}

    flagged = _classify_metadata_update_result(
        {"action": "processed", "description_needs_review": True, "description_error": "refusal"},
        actions,
    )
    assert flagged["ok"] is False
    assert flagged["reason"] == "refusal"

    skipped = _classify_metadata_update_result({"action": "skipped"}, actions)
    assert skipped["ok"] is False

    done = _classify_metadata_update_result(
        {"action": "processed", "completed": ["description"]}, actions
    )
    assert done["ok"] is True
    assert done["reason"] is None


def test_metadata_job_logs_rejection_reason_and_keeps_description(
    tmp_path, monkeypatch
) -> None:
    from types import SimpleNamespace

    from ui import job_executors
    from ui.job_queue import Job, JobStatus, JobType

    db_path = tmp_path / "job.db"
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.setattr("ui.database._db", None)
    monkeypatch.setattr("database._db", None)
    repo = SermonRepository(SermonDatabase(db_path=str(db_path)))
    repo.save_sermon({
        "id": "s-job",
        "title": "Stored Title",
        "speaker": "Test Speaker",
        "recorded_date": "2024-01-01",
        "status": "processed",
        "description": "Stored description",
        "content": {"description": "Stored description"},
    })

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

    provider = _ScriptedProvider([REFUSAL, REFUSAL])
    real_manager = LLMManager

    def _factory(cfg):
        manager = real_manager(cfg)
        manager.primary_provider = provider
        manager.fallback_providers = []
        return manager

    monkeypatch.setattr(su, "LLMManager", _factory)

    config = {
        "output_directory": str(tmp_path / "out"),
        "metadata_processing": {"enabled": True},
    }
    job = Job(
        id="j-integrity",
        type=JobType.METADATA_UPDATE,
        title="Metadata update",
        description="Metadata update",
        status=JobStatus.RUNNING,
        progress=0,
        created_at=datetime.now(),
        parameters={
            "sermon_ids": ["s-job"],
            "actions": {"generate_description": True},
            "config": config,
        },
    )

    result = job_executors.execute_metadata_update_job(job)

    assert result.success is False
    assert "refusal" in (result.error or "")
    stored = repo.get_sermon("s-job")
    assert stored["description"] == "Stored description"
    assert bool(stored["description_needs_review"]) is True
    joined = "\n".join(job.logs or [])
    assert "refusal" in joined
    assert "no usable text" in joined
    assert "0 completed, 1 failed" in joined
