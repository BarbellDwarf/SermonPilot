"""Cancellation polling between decoded transcription segments.

The job queue's cancel bound only holds if the long stages poll the cancel
hook. The local transcription backends decode one segment at a time; these
tests pin that the hook is called once per segment and that a cancellation
raised there is not wrapped as a TranscriptionError.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import src.transcription as tr  # noqa: E402


class _Cancelled(Exception):
    """Stand-in for the caller's cancellation signal."""


class _FakeWhisperModel:
    def __init__(self, segments: list[dict]) -> None:
        self._segments = segments

    def transcribe(self, path: str, **kwargs: object) -> dict:
        return {"segments": self._segments}


@pytest.fixture(autouse=True)
def _no_real_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "_detect_device", lambda preference="auto", **kwargs: "cpu")
    monkeypatch.setattr(tr, "guard_transcription_device", lambda device: device)


def test_segment_cancel_check_polls_once_per_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    segments = [
        {"start": 0.0, "end": 1.0, "text": "one"},
        {"start": 1.0, "end": 2.0, "text": "two"},
        {"start": 2.0, "end": 3.0, "text": "three"},
    ]
    monkeypatch.setattr(
        tr, "_load_whisper_model", lambda model_size, device: _FakeWhisperModel(segments)
    )

    polls: list[int] = []

    def cancel_check() -> None:
        polls.append(len(polls))

    result = tr._transcribe_whisper_local_segments(
        "audio.wav", "base", cancel_check=cancel_check
    )

    assert [segment["text"] for segment in result] == ["one", "two", "three"]
    assert polls == [0, 1, 2]


def test_segment_cancel_raises_before_consuming_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    segments = [
        {"start": 0.0, "end": 1.0, "text": "one"},
        {"start": 1.0, "end": 2.0, "text": "two"},
        {"start": 2.0, "end": 3.0, "text": "three"},
    ]
    monkeypatch.setattr(
        tr, "_load_whisper_model", lambda model_size, device: _FakeWhisperModel(segments)
    )

    polls: list[int] = []

    def cancel_check() -> None:
        polls.append(len(polls))
        if len(polls) >= 2:
            raise _Cancelled("stop")

    with pytest.raises(_Cancelled):
        tr._transcribe_whisper_local_segments("audio.wav", "base", cancel_check=cancel_check)

    assert len(polls) == 2
