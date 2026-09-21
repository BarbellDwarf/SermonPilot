from __future__ import annotations

import sys
import types

import pytest

import src.transcription as transcription
from src.transcription import TranscriptionError, _load_whisper_model, _resolve_backend


class _FakeWhisperModel:
    def __init__(self, device: str, oom_on_move: bool = False) -> None:
        self.device = device
        self.oom_on_move = oom_on_move
        self.half_calls = 0
        self.float_calls = 0
        self.to_calls: list[str] = []

    def half(self) -> _FakeWhisperModel:
        self.half_calls += 1
        return self

    def float(self) -> _FakeWhisperModel:
        self.float_calls += 1
        return self

    def to(self, device: str) -> _FakeWhisperModel:
        self.to_calls.append(device)
        if self.oom_on_move and device != "cpu":
            raise _oom()
        self.device = device
        return self


def _fake_whisper(loader) -> types.ModuleType:
    module = types.ModuleType("whisper")
    module.load_model = loader
    return module


class OutOfMemoryError(RuntimeError):
    pass


def _oom() -> OutOfMemoryError:
    return OutOfMemoryError("CUDA out of memory. Tried to allocate 26.00 MiB")


def test_cuda_model_loads_on_cpu_half_then_moves_to_gpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_FakeWhisperModel] = []

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        model = _FakeWhisperModel(device)
        created.append(model)
        return model

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    model = _load_whisper_model("large", "cuda")
    assert model is created[0]
    assert model.half_calls == 1
    assert model.to_calls == ["cuda"]
    assert model.device == "cuda"


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
    assert model.to_calls == []


def test_cuda_fp16_move_oom_keeps_cpu_model(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeWhisperModel] = []

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        model = _FakeWhisperModel(device, oom_on_move=True)
        created.append(model)
        return model

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    model = _load_whisper_model("large", "cuda")
    assert model is created[0]
    assert model.half_calls == 1
    assert model.float_calls == 1
    assert model.to_calls == ["cuda", "cpu"]
    assert model.device == "cpu"


def test_non_oom_move_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeWhisperModel] = []

    class _BadMoveModel(_FakeWhisperModel):
        def to(self, device: str) -> _FakeWhisperModel:
            raise ValueError("unsupported checkpoint")

    def loader(model_size: str, device: str) -> _FakeWhisperModel:
        model = _BadMoveModel(device)
        created.append(model)
        return model

    monkeypatch.setitem(sys.modules, "whisper", _fake_whisper(loader))
    with pytest.raises(TranscriptionError, match="unsupported checkpoint"):
        _load_whisper_model("large", "cuda")
    assert len(created) == 1
    assert created[0].device == "cpu"


def test_oom_on_cpu_load_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
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
