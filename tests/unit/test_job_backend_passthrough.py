"""Regression guards for the transcription backend chosen for a job.

A queued sermon must use the configured transcription backend. The executor used
to pass ``form_data.get('transcription_backend', 'whisper_local')``, which forced
the in-process PyTorch backend even when the user had configured a different one
(for example a local HTTP Whisper service), which is how a working setup started
failing with CUDA out-of-memory errors.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.transcription import _resolve_backend

EXECUTOR = Path(__file__).resolve().parents[2] / "ui" / "job_executors.py"


def test_executor_never_forces_a_literal_backend_default() -> None:
    """The executor must not invent a backend; an absent value stays absent."""
    source = EXECUTOR.read_text(encoding="utf-8")
    offenders = re.findall(
        r"transcription_backend\s*[:=]\s*form_data\.get\(\s*['\"]transcription_backend['\"]\s*,\s*['\"][a-z_]+['\"]",
        source,
    )
    assert offenders == [], (
        "job_executors.py must not default transcription_backend to a literal "
        f"backend name (found {offenders}); pass the form value through and let "
        "the configured transcription.backend win"
    )


def test_configured_backend_wins_when_no_override_is_given() -> None:
    assert _resolve_backend("whisper_openai", None) == "whisper_openai"
    assert _resolve_backend("faster_whisper_local", None) == "faster_whisper_local"
