"""The executor must never run config-less.

Jobs enqueued through the API used to carry ``"config": {}`` and the executors
read it verbatim, so every stage that needs the LLM configuration raised
"No model configured". The fix resolves the application config and merges the
job's values over it. These tests pin the resolution, the override order, and
the diagnostic that names the config source when a model goes missing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

try:  # noqa: E402 - package path so ui.* is one module identity
    from ui.job_queue import Job, JobStatus, JobType
except ImportError:  # Streamlit entrypoint
    from job_queue import Job, JobStatus, JobType

from src.llm_manager import create_llm_manager
from ui.job_executors import execute_sermon_processing_job, resolve_job_config

MODEL = "test-model:latest"
JOB_MODEL = "job-model:latest"

AUDIO_FILE = str(Path(__file__).resolve())

FORM_DATA = {
    "speaker_name": "Test Speaker",
    "recorded_date": "2024-01-01",
    "event_type": "Sunday Service",
}

SUCCESS_RESULT = {"success": True, "sermon_id": "s-1", "transcript": "body"}


def _resolved_config(model: str = MODEL) -> dict[str, Any]:
    return {
        "api_key": "test-api-key",
        "broadcaster_id": "test-broadcaster",
        "output_directory": "resolved_out",
        "llm": {
            "primary": {
                "provider": "ollama",
                "ollama": {"host": "http://localhost:11434", "model": model},
            },
            "fallback": {"enabled": False},
        },
    }


def _job(params: dict[str, Any]) -> Job:
    return Job(
        id="job-config",
        type=JobType.SERMON_PROCESSING,
        title="Config resolution",
        description="Config resolution",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=params,
    )


def _patch_resolved(monkeypatch, model: str = MODEL) -> None:
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: _resolved_config(model))


def test_executor_with_empty_config_builds_llm_with_resolved_model(monkeypatch) -> None:
    _patch_resolved(monkeypatch)
    process = Mock(return_value=SUCCESS_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)

    job = _job({"form_data": FORM_DATA, "config": {}, "uploaded_file_path": AUDIO_FILE})
    result = execute_sermon_processing_job(job)

    assert result.success is True
    passed = process.call_args.kwargs["config"]
    assert passed["llm"]["primary"]["ollama"]["model"] == MODEL

    import sermon_updater

    info = sermon_updater.llm_manager.get_provider_info()
    assert info["primary"] is not None
    assert info["primary"]["model"] == MODEL


def test_job_config_values_override_resolved_app_config(monkeypatch) -> None:
    _patch_resolved(monkeypatch)
    process = Mock(return_value=SUCCESS_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)

    job = _job({
        "form_data": FORM_DATA,
        "config": {
            "output_directory": "job_out",
            "llm": {"primary": {"ollama": {"model": JOB_MODEL}}},
        },
        "uploaded_file_path": AUDIO_FILE,
    })
    execute_sermon_processing_job(job)

    passed = process.call_args.kwargs["config"]
    assert passed["output_directory"] == "job_out"
    assert passed["llm"]["primary"]["ollama"]["model"] == JOB_MODEL
    assert passed["llm"]["primary"]["ollama"]["host"] == "http://localhost:11434"
    assert passed["api_key"] == "test-api-key"


def test_empty_config_path_never_reports_no_model_when_configured(monkeypatch) -> None:
    _patch_resolved(monkeypatch)

    effective = resolve_job_config(_job({"config": {}}))
    info = create_llm_manager(effective).get_provider_info()

    assert info["primary"] is not None
    assert info["primary"]["model"] == MODEL

    assert create_llm_manager({}).get_provider_info()["primary"] is None


def test_missing_model_logs_job_and_resolved_sources(monkeypatch, caplog) -> None:
    _patch_resolved(monkeypatch)
    job = _job({"config": {"llm": {"primary": {"ollama": {"model": ""}}}}})

    with caplog.at_level(logging.WARNING, logger="ui.job_executors"):
        effective = resolve_job_config(job)

    assert effective["llm"]["primary"]["ollama"]["model"] == ""
    assert "resolved app config" in caplog.text
    assert "llm.primary.ollama.model" in caplog.text
