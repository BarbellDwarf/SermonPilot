from __future__ import annotations

import sys
import types

import pytest

import src.transcription as transcription
from src.transcription import TranscriptionError, _load_whisper_model, _resolve_backend


class _FakeWhisperModel:
    def __init__(self, device: str) -> None:
        self.device = device
        self.half_calls = 0

    def half(self) -> _FakeWhisperModel:
        self.half_calls += 1
        return self


def _fake_whisper(loader) -> types.ModuleType:
    module = types.ModuleType("whisper")
    module.load_model = loader
    return module


class OutOfMemoryError(RuntimeError):
    pass


def _oom() -> OutOfMemoryError:
    return OutOfMemoryError("CUDA out of memory. Tried to allocate 26.00 MiB")


def test_cuda_model_is_converted_to_fp16(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeWhisperModel] = []

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        model = _FakeWhisperModel(device)
        created.append(model)
        return model

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    model = _load_whisper_model("large", "cuda")
    assert model is created[0]
    assert model.half_calls == 1


def test_cpu_model_stays_float32(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeWhisperModel] = []

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        model = _FakeWhisperModel(device)
        created.append(model)
        return model

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    model = _load_whisper_model("large", "cpu")
    assert model.device == "cpu"
    assert model.half_calls == 0


def test_cuda_oom_retries_on_cpu_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    devices: list[str] = []

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        devices.append(device)
        if device == "cuda":
            raise _oom()
        return _FakeWhisperModel(device)

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    model = _load_whisper_model("large", "cuda")
    assert devices == ["cuda", "cpu"]
    assert model.device == "cpu"
    assert model.half_calls == 0


def test_non_oom_load_error_propagates_without_cpu_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    devices: list[str] = []

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        devices.append(device)
        raise ValueError("unsupported checkpoint")

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    with pytest.raises(TranscriptionError, match="unsupported checkpoint"):
        _load_whisper_model("large", "cuda")
    assert devices == ["cuda"]


def test_oom_on_cpu_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    devices: list[str] = []

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        devices.append(device)
        raise _oom()

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    with pytest.raises(TranscriptionError, match="out of memory"):
        _load_whisper_model("large", "cpu")
    assert devices == ["cpu"]


def test_backend_auto_prefers_faster_whisper_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    assert _resolve_backend("auto", None) == "faster_whisper_local"
    assert _resolve_backend(None, None) == "faster_whisper_local"
    assert _resolve_backend(None, "auto") == "faster_whisper_local"


def test_explicit_backend_wins_over_preference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    assert _resolve_backend("whisper_local", None) == "whisper_local"
    assert _resolve_backend("whisper_openai", None) == "whisper_openai"
    assert _resolve_backend("auto", "whisper_local") == "whisper_local"


def test_backend_auto_falls_back_to_whisper_when_faster_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert _resolve_backend("auto", None) == "whisper_local"
    assert _resolve_backend(None, None) == "whisper_local"


def _recording_backend(calls: list[str], name: str):
    def _run(*args, **kwargs) -> str:
        calls.append(name)
        return "text"

    return _run


def test_transcribe_dispatches_to_faster_path_on_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    calls: list[str] = []
    monkeypatch.setattr(
        transcription, "_transcribe_faster_whisper_local", _recording_backend(calls, "faster")
    )
    monkeypatch.setattr(
        transcription, "_transcribe_whisper_local", _recording_backend(calls, "whisper")
    )
    config = {"transcription": {"backend": "auto"}}
    assert transcription.transcribe("audio.mp3", model_size="large", config=config) == "text"
    assert calls == ["faster"]


def test_transcribe_explicit_config_routes_to_whisper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    calls: list[str] = []
    monkeypatch.setattr(
        transcription, "_transcribe_faster_whisper_local", _recording_backend(calls, "faster")
    )
    monkeypatch.setattr(
        transcription, "_transcribe_whisper_local", _recording_backend(calls, "whisper")
    )
    config = {"transcription": {"backend": "whisper_local"}}
    assert transcription.transcribe("audio.mp3", model_size="large", config=config) == "text"
    assert calls == ["whisper"]
