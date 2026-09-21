"""Fast (no-GPU) tests for the enhancement -> transcription VRAM release.

Covers the enhancement-stage release call path, the small-GPU enhancement
device guard, the pre-whisper VRAM warning/fallback, and parsing of the two
new ``enhancement`` config keys.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import Mock

import src.transcription as transcription
from src.transcription import (
    _clear_deepfilternet_cache,
    enhancement_settings,
    guard_transcription_device,
    release_enhancement_gpu,
    resolve_enhancement_device,
)


class _FakeProcessor:
    def __init__(self) -> None:
        self.released = False

    def release_gpu(self) -> None:
        self.released = True


def _fake_torch(cuda_available: bool = True, mem_get_info=None, memory_allocated=None):
    cuda = types.SimpleNamespace(is_available=lambda: cuda_available)
    if mem_get_info is not None:
        cuda.mem_get_info = mem_get_info
    if memory_allocated is not None:
        cuda.memory_allocated = memory_allocated
    return types.SimpleNamespace(cuda=cuda)


# --- config parsing -------------------------------------------------------


def test_enhancement_settings_defaults_to_auto_and_12gb():
    assert enhancement_settings({}) == ("auto", 12.0)
    assert enhancement_settings(None) == ("auto", 12.0)


def test_enhancement_settings_reads_both_keys():
    cfg = {"enhancement": {"device": "Cuda", "min_gpu_vram_gb": 8}}
    assert enhancement_settings(cfg) == ("cuda", 8.0)


def test_enhancement_settings_sanitizes_bad_values():
    cfg = {"enhancement": {"device": "bogus", "min_gpu_vram_gb": "nope"}}
    assert enhancement_settings(cfg) == ("auto", 12.0)


# --- enhancement device guard --------------------------------------------


def test_device_auto_picks_cpu_below_threshold():
    assert resolve_enhancement_device("auto", 12, total_vram_gb=7.7) == "cpu"


def test_device_auto_picks_cuda_at_or_above_threshold():
    assert resolve_enhancement_device("auto", 12, total_vram_gb=12) == "cuda"
    assert resolve_enhancement_device("auto", 12, total_vram_gb=24) == "cuda"


def test_device_explicit_override_wins():
    assert resolve_enhancement_device("cuda", 12, total_vram_gb=4) == "cuda"
    assert resolve_enhancement_device("cpu", 12, total_vram_gb=48) == "cpu"


def test_device_auto_without_a_gpu_is_cpu(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda_available=False))
    assert resolve_enhancement_device("auto", 12) == "cpu"


# --- release call path ----------------------------------------------------


def test_release_enhancement_gpu_drops_processor_and_clears_cache(monkeypatch):
    events: list[str] = []

    class _Processor:
        def release_gpu(self) -> None:
            events.append("processor")

    processor = _Processor()
    monkeypatch.setattr(transcription, "_allocated_bytes", lambda: 5_000_000_000.0)
    monkeypatch.setattr(
        transcription, "_clear_deepfilternet_cache", lambda: events.append("df") or True
    )
    monkeypatch.setattr(
        transcription, "release_transcription_gpu", lambda: events.append("torch")
    )
    monkeypatch.setattr(transcription, "log_cuda_memory", lambda stage: events.append("log"))

    released = release_enhancement_gpu(processor)

    assert released == 0
    assert events == ["processor", "df", "torch", "log"]


def test_release_enhancement_gpu_reports_bytes_reclaimed(monkeypatch):
    before_after = iter([5_000_000_000.0, 1_000_000_000.0])
    monkeypatch.setattr(transcription, "_allocated_bytes", lambda: next(before_after))
    monkeypatch.setattr(transcription, "_clear_deepfilternet_cache", lambda: False)
    monkeypatch.setattr(transcription, "release_transcription_gpu", lambda: None)
    monkeypatch.setattr(transcription, "log_cuda_memory", lambda stage: None)

    assert release_enhancement_gpu() == 4_000_000_000


def test_clear_deepfilternet_cache_clears_module_state(monkeypatch):
    fake_df = types.ModuleType("df.enhance")
    fake_df._model_cache = object()
    fake_df._df_state = object()
    monkeypatch.setitem(sys.modules, "df.enhance", fake_df)

    assert _clear_deepfilternet_cache() is True
    assert fake_df._model_cache is None
    assert fake_df._df_state is None


def test_release_enhancement_gpu_uses_lazy_torch_for_measurement(monkeypatch):
    processor = _FakeProcessor()
    calls: list[str] = []

    def _empty_cache() -> None:
        calls.append("empty_cache")

    fake_torch = _fake_torch(
        mem_get_info=lambda: (1_000_000_000, 8_000_000_000),
        memory_allocated=lambda: 4_000_000_000,
    )
    fake_torch.cuda.empty_cache = _empty_cache
    fake_torch.cuda.ipc_collect = lambda: calls.append("ipc_collect")
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(transcription, "_clear_deepfilternet_cache", lambda: False)

    released = release_enhancement_gpu(processor)

    assert processor.released is True
    assert released == 0
    assert "empty_cache" in calls


# --- pre-whisper VRAM guard ----------------------------------------------


def test_guard_keeps_cuda_when_free_memory_is_healthy():
    assert guard_transcription_device("cuda", free_vram_gb=6.0, reclaimed_bytes=0) == "cuda"


def test_guard_falls_back_to_cpu_when_low_and_nothing_reclaimed():
    assert guard_transcription_device("cuda", free_vram_gb=0.013, reclaimed_bytes=0) == "cpu"


def test_guard_keeps_cuda_when_low_but_release_reclaimed():
    assert (
        guard_transcription_device("cuda", free_vram_gb=0.5, reclaimed_bytes=4_000_000_000)
        == "cuda"
    )


def test_guard_never_downgrades_cpu():
    assert guard_transcription_device("cpu", free_vram_gb=0.0, reclaimed_bytes=0) == "cpu"


def test_guard_does_not_trigger_when_free_memory_unknown(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda_available=True))
    assert guard_transcription_device("cuda", free_vram_gb=None, reclaimed_bytes=0) == "cuda"


def test_guard_reads_free_memory_from_torch_when_not_passed(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "torch",
        _fake_torch(
            cuda_available=True,
            mem_get_info=lambda: (100_000_000, 8_000_000_000),
        ),
    )
    assert guard_transcription_device("cuda", reclaimed_bytes=0) == "cpu"


# --- transition wiring ----------------------------------------------------


def test_transcription_transition_releases_enhancement_gpu(tmp_path: Path, monkeypatch):
    import sermon_updater as su

    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    monkeypatch.setattr(su, "_reuse_existing_transcript", lambda *a, **k: "")
    monkeypatch.setattr(
        su,
        "transcribe_segments",
        Mock(return_value=[{"start": 0.0, "end": 1.0, "text": "hello"}]),
    )
    release = Mock(return_value=123)
    monkeypatch.setattr(su, "release_enhancement_gpu", release)

    result = su.process_new_sermon(
        str(audio_file),
        speaker_name="Test Speaker",
        recorded_date="2024-01-01",
        dry_run=True,
        skip_audio=True,
        skip_ai_generation=True,
    )

    assert result["success"] is True
    release.assert_called_once()
