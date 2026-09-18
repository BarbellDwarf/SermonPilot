from __future__ import annotations

import numpy as np
import pytest

from src.av_sync import energy_onsets, median_eta, pick_offset


def _motion_with_responses(length: int, onsets: list[int], shift: int,
                           noise: float = 0.05) -> np.ndarray:
    rng = np.random.default_rng(42)
    signal = rng.normal(0.0, noise, length)
    for onset in onsets:
        start = onset + shift
        if 0 <= start < length - 8:
            signal[start : start + 8] += 1.0
    return signal


def test_offset_recovered_when_audio_leads():
    onsets = [40, 90, 140, 190, 240, 290]
    motion = _motion_with_responses(360, onsets, shift=10)  # 1.0 s
    curve = median_eta(motion, onsets)
    offset, confidence = pick_offset(curve)
    assert offset == pytest.approx(1.0, abs=0.15)
    assert confidence > 0.3


def test_offset_recovered_when_video_leads():
    onsets = [40, 90, 140, 190, 240, 290]
    motion = _motion_with_responses(360, onsets, shift=-10)  # -1.0 s
    curve = median_eta(motion, onsets)
    offset, confidence = pick_offset(curve)
    assert offset == pytest.approx(-1.0, abs=0.15)
    assert confidence > 0.3


def test_zero_offset_for_synced_signal():
    onsets = [40, 90, 140, 190, 240, 290]
    motion = _motion_with_responses(360, onsets, shift=0)
    curve = median_eta(motion, onsets)
    offset, _ = pick_offset(curve)
    assert offset == pytest.approx(0.0, abs=0.15)


def test_confidence_is_low_for_noise():
    rng = np.random.default_rng(7)
    motion = rng.normal(0.0, 1.0, 360)
    curve = median_eta(motion, [40, 90, 140, 190, 240, 290])
    _, confidence = pick_offset(curve)
    assert confidence < 0.1


def test_energy_onsets_find_rises():
    envelope = np.full(200, 0.1)
    envelope[50:70] = 5.0
    envelope[120:150] = 4.0
    onsets = energy_onsets(envelope, min_gap_seconds=1.0)
    assert any(abs(o - 50) <= 2 for o in onsets)
    assert any(abs(o - 120) <= 2 for o in onsets)
