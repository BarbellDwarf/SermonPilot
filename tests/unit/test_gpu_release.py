from __future__ import annotations

import sys
import types

from src.transcription import release_transcription_gpu


def test_release_transcription_gpu_clears_cache(monkeypatch):
    calls: list[str] = []
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: True,
            empty_cache=lambda: calls.append("empty_cache"),
            ipc_collect=lambda: calls.append("ipc_collect"),
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    release_transcription_gpu()
    assert "empty_cache" in calls
    assert "ipc_collect" in calls


def test_release_transcription_gpu_tolerates_missing_cuda(monkeypatch):
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False)
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    release_transcription_gpu()


def test_audio_processor_release_gpu_drops_models():
    pytest = __import__("pytest")
    audio_processing = pytest.importorskip("src.audio_processing")

    processor = audio_processing.AudioProcessor.__new__(audio_processing.AudioProcessor)
    processor.df_model = object()
    processor.df_state = object()
    processor.qa_normalizer = object()
    processor.release_gpu()
    assert processor.df_model is None
    assert processor.df_state is None
    assert processor.qa_normalizer is None
