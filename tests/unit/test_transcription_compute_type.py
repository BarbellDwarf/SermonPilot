from __future__ import annotations

import sys
import types

import pytest

import src.transcription as transcription
from src.transcription import (
    _build_whisper_model,
    _configured_compute_type,
    _detect_device,
    _resolve_compute_type,
)


def _fake_torch(cuda_available: bool) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: cuda_available),
        version=types.SimpleNamespace(cuda="12.6", hip=None),
    )


@pytest.fixture(autouse=True)
def _no_gpu_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcription, "release_transcription_gpu", lambda: None)
    monkeypatch.setattr(transcription, "log_cuda_memory", lambda stage: None)


class _Factory:
    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.calls: list[str] = []
        self.failures = list(failures or [])

    def __call__(self, model_size: str, device: str, compute_type: str):
        self.calls.append(compute_type)
        if self.failures:
            raise self.failures.pop(0)
        return object()


class OutOfMemoryError(RuntimeError):
    pass


def _oom() -> OutOfMemoryError:
    return OutOfMemoryError("CUDA out of memory. Tried to allocate 26.00 MiB")


def test_cuda_device_defaults_to_float16(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(True))
    device = _detect_device("cuda")
    assert device == "cuda"
    assert _resolve_compute_type(None, device) == "float16"
    assert _resolve_compute_type("auto", device) == "float16"


def test_cpu_device_defaults_to_int8(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(False))
    device = _detect_device("auto")
    assert device == "cpu"
    assert _resolve_compute_type(None, device) == "int8"
    assert _resolve_compute_type("auto", device) == "int8"


def test_explicit_compute_type_is_honoured_on_both_devices() -> None:
    assert _resolve_compute_type("float32", "cuda") == "float32"
    assert _resolve_compute_type("int8_float16", "cuda") == "int8_float16"
    assert _resolve_compute_type("float16", "cpu") == "float16"
    assert _resolve_compute_type("AUTO", "cuda") == "float16"


def test_unknown_compute_type_falls_back_to_device_default() -> None:
    assert _resolve_compute_type("bogus", "cuda") == "float16"
    assert _resolve_compute_type("", "cpu") == "int8"


def test_config_top_level_wins_over_legacy_backend_key() -> None:
    cfg = {"compute_type": "float16", "faster_whisper_local": {"compute_type": "int8"}}
    assert _configured_compute_type(cfg, cfg["faster_whisper_local"]) == "float16"


def test_config_legacy_backend_key_still_read() -> None:
    faster = {"compute_type": "int8_float16"}
    assert _configured_compute_type({"faster_whisper_local": faster}, faster) == "int8_float16"


def test_config_auto_and_blank_resolve_to_device_default() -> None:
    assert _configured_compute_type({"compute_type": "auto"}, {}) == "auto"
    auto = _configured_compute_type({"compute_type": "auto"}, {})
    assert _resolve_compute_type(auto, "cuda") == "float16"
    assert _configured_compute_type({}, {"compute_type": "  "}) is None
    assert _configured_compute_type({}, {}) is None


def test_cuda_oom_falls_back_down_the_ladder_and_stops_on_success() -> None:
    factory = _Factory([_oom(), _oom()])
    model = _build_whisper_model(factory, "large", "cuda", "float16")
    assert model is not None
    assert factory.calls == ["float16", "int8_float16", "int8"]


def test_explicit_float32_oom_ladder_covers_float16_then_int8_types() -> None:
    factory = _Factory([_oom(), _oom(), _oom()])
    _build_whisper_model(factory, "large", "cuda", "float32")
    assert factory.calls == ["float32", "float16", "int8_float16", "int8"]


def test_cuda_success_on_first_try_does_not_fall_back() -> None:
    factory = _Factory()
    _build_whisper_model(factory, "large", "cuda", "float16")
    assert factory.calls == ["float16"]


def test_non_oom_error_is_raised_immediately() -> None:
    factory = _Factory([ValueError("unsupported compute type")])
    with pytest.raises(ValueError):
        _build_whisper_model(factory, "large", "cuda", "float16")
    assert factory.calls == ["float16"]


def test_oom_on_last_rung_surfaces_the_real_error() -> None:
    factory = _Factory([_oom(), _oom(), _oom()])
    with pytest.raises(RuntimeError, match="out of memory"):
        _build_whisper_model(factory, "large", "cuda", "int8")
    assert factory.calls == ["int8", "float16", "int8_float16"]


def test_cpu_never_uses_the_cuda_ladder() -> None:
    factory = _Factory([_oom()])
    with pytest.raises(RuntimeError):
        _build_whisper_model(factory, "base", "cpu", "int8")
    assert factory.calls == ["int8"]


def test_backend_dispatcher_passes_configured_compute_type(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeModel:
        def transcribe(self, audio_path, **kwargs):
            return [], types.SimpleNamespace()

    def fake_whisper_model(model_size, device, compute_type):
        captured["model_size"] = model_size
        captured["device"] = device
        captured["compute_type"] = compute_type
        return _FakeModel()

    faster_whisper = types.ModuleType("faster_whisper")
    faster_whisper.WhisperModel = fake_whisper_model
    monkeypatch.setitem(sys.modules, "faster_whisper", faster_whisper)
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(True))

    config = {
        "transcription": {
            "backend": "faster_whisper_local",
            "compute_type": "int8_float16",
            "faster_whisper_local": {"model": "large", "device": "cuda"},
        }
    }
    transcription.transcribe("audio.mp3", model_size="large", config=config)
    assert captured == {"model_size": "large", "device": "cuda", "compute_type": "int8_float16"}
