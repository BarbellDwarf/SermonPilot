"""A removed transcription backend migrates and the pipeline still transcribes.

The OpenRouter-named Whisper backend was removed because it duplicated the
OpenAI-compatible hosted backend. A stored value that names it must become
``whisper_openai`` so an existing install keeps working.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import transcription as tr  # noqa: E402
from ui.config_utils import resolve_config  # noqa: E402
from ui.database import SermonDatabase  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "backend-migration.db"))
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(tmp_path / "absent.yaml"))
    return SermonDatabase()


def _clear_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "TRANSCRIPTION_BACKEND",
        "WHISPER_OPENAI_BASE_URL",
        "WHISPER_OPENAI_MODEL",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def test_stored_openrouter_backend_migrates_and_transcribes(
    fresh_db, monkeypatch, caplog, tmp_path
):
    _clear_backend_env(monkeypatch)
    fresh_db.save_config(
        {
            "transcription": {
                "backend": "whisper_openrouter",
                "whisper_openai": {
                    "base_url": "http://203.0.113.5:8780/v1",
                    "model": "whisper-1",
                },
            }
        }
    )

    with caplog.at_level(logging.INFO, logger="ui.config_utils"):
        config = resolve_config(fresh_db)

    assert config["transcription"]["backend"] == "whisper_openai"
    assert any(
        "whisper_openrouter" in record.message and "whisper_openai" in record.message
        for record in caplog.records
    )
    assert fresh_db.load_config()["transcription"]["backend"] == "whisper_openai"

    calls: list[str] = []

    class _FakeResponse:
        headers: dict = {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"text": "  migrated transcript  "}

    def fake_post(url, headers=None, data=None, files=None, stream=None, timeout=None):
        calls.append(url)
        return _FakeResponse()

    monkeypatch.setattr(tr.requests, "post", fake_post)
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"RIFF0000WAVE")

    result = tr.transcribe(str(audio), config=config)

    assert result == "migrated transcript"
    assert calls == ["http://203.0.113.5:8780/v1/audio/transcriptions"]
