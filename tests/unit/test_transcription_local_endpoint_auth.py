"""Auth handling for private vs public transcription endpoints.

A LAN Whisper service that ignores auth must not require a plausible API key,
while a public endpoint keeps strict key hygiene. When a key really is
required, the error names the config path and the layer that supplied it.
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
from src.transcription import TranscriptionError  # noqa: E402

_KEY_ENV_VARS = ("OPENAI_API_KEY", "WHISPER_OPENAI_API_KEY", "OPENROUTER_API_KEY")


class _FakeResponse:
    def __init__(self, payload: dict, headers: dict | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload

    def iter_lines(self, decode_unicode: bool = False):
        return iter(())


@pytest.fixture(autouse=True)
def _clear_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _KEY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _capture_post(monkeypatch: pytest.MonkeyPatch, payload: dict) -> list[dict]:
    calls: list[dict] = []

    def fake_post(url, headers=None, data=None, files=None, stream=None, timeout=None):
        calls.append({"url": url, "headers": dict(headers or {})})
        return _FakeResponse(payload)

    monkeypatch.setattr(tr.requests, "post", fake_post)
    return calls


def _openai_config(base_url: str, api_key: str = "abc") -> dict:
    return {
        "transcription": {
            "backend": "whisper_openai",
            "whisper_openai": {
                "api_key": api_key,
                "base_url": base_url,
                "model": "whisper-1",
            },
        }
    }


def _audio_file(tmp_path: Path) -> str:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF0000WAVE")
    return str(audio)


def test_private_base_url_transcribes_without_a_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    calls = _capture_post(monkeypatch, {"text": "  hello world  "})

    with caplog.at_level(logging.INFO, logger="src.transcription"):
        result = tr.transcribe(
            _audio_file(tmp_path), config=_openai_config("http://10.0.0.5:8780/v1/")
        )

    assert result == "hello world"
    assert len(calls) == 1
    assert calls[0]["url"] == "http://10.0.0.5:8780/v1/audio/transcriptions"
    assert "Authorization" not in calls[0]["headers"]
    assert any("local" in record.message.lower() for record in caplog.records)


def test_private_base_url_uses_a_valid_key_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _capture_post(monkeypatch, {"text": "ok"})

    result = tr.transcribe(
        _audio_file(tmp_path),
        config=_openai_config("http://10.0.0.5:8780/v1/", api_key="sk-valid-key-1234567890"),
    )

    assert result == "ok"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-valid-key-1234567890"


def test_private_base_url_segments_without_a_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _capture_post(
        monkeypatch,
        {
            "segments": [
                {"start": 0.0, "end": 1.5, "text": " hello"},
                {"start": 1.5, "end": 3.0, "text": " world"},
            ]
        },
    )

    result = tr.transcribe_segments(
        _audio_file(tmp_path), config=_openai_config("http://10.0.0.5:8780/v1/")
    )

    assert [segment["text"] for segment in result] == ["hello", "world"]
    assert "Authorization" not in calls[0]["headers"]


def test_public_base_url_unusable_key_names_env_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_OPENAI_API_KEY", "abc")
    called: list[object] = []
    monkeypatch.setattr(
        tr.requests,
        "post",
        lambda *args, **kwargs: called.append(args) or _FakeResponse({"text": ""}),
    )

    with pytest.raises(TranscriptionError) as excinfo:
        tr.transcribe("audio.wav", config=_openai_config("https://api.openai.com/v1", "abc"))

    message = str(excinfo.value)
    assert "transcription.whisper_openai.api_key" in message
    assert "WHISPER_OPENAI_API_KEY" in message
    assert "length 3" in message
    assert called == []


def test_public_base_url_unusable_key_names_db_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "auth-source.db"))
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(tmp_path / "absent.yaml"))

    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    dbmod.SermonDatabase().save_config(
        {"transcription": {"whisper_openai": {"api_key": "abc"}}}
    )

    with pytest.raises(TranscriptionError) as excinfo:
        tr.transcribe("audio.wav", config=_openai_config("https://api.openai.com/v1", "abc"))

    message = str(excinfo.value)
    assert "transcription.whisper_openai.api_key" in message
    assert "db" in message


def test_public_base_url_unusable_key_names_db_source_after_legacy_file_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "resolution.yaml"
    config_path.write_text(
        "transcription:\n  whisper_openai:\n    api_key: abc\n", encoding="utf-8"
    )
    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "legacy-file-source.db"))
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(config_path))

    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)

    with pytest.raises(TranscriptionError) as excinfo:
        tr.transcribe("audio.wav", config=_openai_config("https://api.openai.com/v1", "abc"))

    message = str(excinfo.value)
    assert "transcription.whisper_openai.api_key" in message
    assert "db" in message


def test_placeholder_and_dummy_keys_still_resolve_to_unset() -> None:
    assert tr._clean_api_key("${SOME_VAR}") == ""
    assert tr._clean_api_key("$SOME_VAR") == ""
    assert tr._clean_api_key("test") == ""
    assert tr._clean_api_key("placeholder") == ""
    assert tr._clean_api_key("abc") == ""
    assert tr._clean_api_key("sk-valid-key-1234567890") == "sk-valid-key-1234567890"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://10.0.0.5:8780/v1/",
        "http://192.168.1.20:8780/v1/",
        "http://172.16.0.9:8780/v1/",
        "http://127.0.0.1:8780/v1/",
        "http://localhost:8780/v1/",
        "http://[::1]:8780/v1/",
        "http://example.local:8780/v1/",
    ],
)
def test_private_endpoints_are_detected(base_url: str) -> None:
    assert tr._is_local_endpoint(base_url) is True


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "https://8.8.8.8/v1",
        "http://example.com:8780/v1/",
    ],
)
def test_public_endpoints_are_not_local(base_url: str) -> None:
    assert tr._is_local_endpoint(base_url) is False
