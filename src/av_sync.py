from __future__ import annotations

import logging
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

FPS = 10
FRAME_W, FRAME_H = 640, 360
PROTO_URL = (
    "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/dnn/"
    "face_detector/deploy.prototxt"
)
MODEL_URL = (
    "https://github.com/opencv/opencv_3rdparty/raw/"
    "dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"
)


@dataclass
class OffsetMeasurement:
    """Measured audio lead in seconds; positive means audio leads video."""

    offset_seconds: float | None
    confidence: float
    available: bool
    method: str
    detail: str = ""


def _load_cv2():
    try:
        import cv2

        return cv2
    except Exception:
        return None


def _ensure_face_model(cache_dir: Path) -> tuple[str, str] | None:
    proto_name = "deploy.prototxt"
    model_name = "res10.caffemodel"
    for target in (cache_dir, Path("/tmp/av_sync_models")):
        proto = target / proto_name
        model = target / model_name
        try:
            target.mkdir(parents=True, exist_ok=True)
            if not proto.exists():
                urllib.request.urlretrieve(PROTO_URL, proto)
            if not model.exists():
                urllib.request.urlretrieve(MODEL_URL, model)
            return str(proto), str(model)
        except Exception as e:
            logger.warning("av_sync: face model unavailable in %s: %s", target, e)
    return None


def _extract_frames(video: Path, start: float, duration: float) -> np.ndarray | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    out = Path("/tmp/av_sync_frames.raw")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-ss", str(start), "-t", str(duration), "-i",
             str(video), "-vf", f"fps={FPS},scale={FRAME_W}:{FRAME_H}", "-pix_fmt", "bgr24",
             "-f", "rawvideo", str(out)],
            check=True, capture_output=True, timeout=600,
        )
    except Exception as e:
        logger.warning("av_sync: frame extraction failed: %s", e)
        return None
    raw = np.fromfile(out, dtype=np.uint8)
    n = len(raw) // (FRAME_W * FRAME_H * 3)
    return raw[: n * FRAME_W * FRAME_H * 3].reshape(n, FRAME_H, FRAME_W, 3)


def _audio_envelope(video: Path, start: float, duration: float) -> np.ndarray | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    out = Path("/tmp/av_sync_env.raw")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-ss", str(start), "-t", str(duration), "-i",
             str(video), "-vn", "-ac", "1", "-ar", str(FPS * 10), "-f", "s16le", str(out)],
            check=True, capture_output=True, timeout=600,
        )
    except Exception as e:
        logger.warning("av_sync: audio extraction failed: %s", e)
        return None
    a = np.fromfile(out, dtype=np.int16).astype(np.float64)
    n = (len(a) // 10) * 10
    if n == 0:
        return None
    return np.sqrt((a[:n].reshape(-1, 10) ** 2).mean(axis=1))


def energy_onsets(envelope: np.ndarray, min_gap_seconds: float = 1.0) -> list[int]:
    """Onset sample indices (at 10 Hz) where energy rises above a local floor."""
    if len(envelope) < 20:
        return []
    floor = float(np.percentile(envelope, 25))
    onsets: list[int] = []
    last = -10_000
    for i in range(5, len(envelope) - 5):
        window = envelope[max(i - 10, 0) : i]
        if window.size and window.min() < floor * 1.5 and envelope[i] > floor * 3.0:
            if i - last >= int(min_gap_seconds * FPS):
                onsets.append(i)
                last = i
    return onsets


def _face_boxes(cv2: Any, net: Any, frames: np.ndarray) -> tuple[list, float]:
    boxes: list = []
    prev = None
    hits = 0
    for frame in frames:
        blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104.0, 177.0, 123.0))
        net.setInput(blob)
        det = net.forward()
        best, score = None, 0.35
        for i in range(det.shape[2]):
            conf = float(det[0, 0, i, 2])
            if conf > score:
                x1, y1, x2, y2 = det[0, 0, i, 3:7] * np.array(
                    [FRAME_W, FRAME_H, FRAME_W, FRAME_H]
                )
                best = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
                score = conf
        if best is not None:
            prev = best
            hits += 1
        boxes.append(prev)
    return boxes, hits / max(len(frames), 1)


def mouth_motion(frames: np.ndarray, boxes: list) -> np.ndarray:
    gray = frames.mean(axis=3)
    signal = np.zeros(len(frames))
    for i in range(1, len(frames)):
        box = boxes[i] if boxes[i] is not None else boxes[i - 1]
        if box is None:
            continue
        x, y, w, h = box
        mx, my = max(x + int(0.15 * w), 0), max(y + int(0.55 * h), 0)
        mw, mh = int(0.7 * w), int(0.4 * h)
        a = gray[i - 1][my : my + mh, mx : mx + mw].astype(np.float32)
        b = gray[i][my : my + mh, mx : mx + mw].astype(np.float32)
        if a.size:
            signal[i] = float(np.abs(b - a).mean())
    return signal


def median_eta(motion: np.ndarray, onset_idx: list[int],
               pre_seconds: float = 2.0, post_seconds: float = 2.0) -> np.ndarray:
    """Median event-triggered average of the motion signal locked to onsets."""
    pre_n, post_n = int(pre_seconds * FPS), int(post_seconds * FPS)
    stack = []
    for i in onset_idx:
        if pre_n <= i < len(motion) - post_n:
            seg = motion[i - pre_n : i + post_n]
            std = seg.std()
            stack.append((seg - seg.mean()) / (std + 1e-9))
    if len(stack) < 5:
        return np.zeros(pre_n + post_n)
    curve = np.median(np.array(stack), axis=0)
    return np.convolve(curve, np.ones(3) / 3, mode="same")


def pick_offset(curve: np.ndarray, min_gap_seconds: float = 0.6) -> tuple[float, float]:
    """Return (offset_seconds, confidence) from an ETA curve; positive = audio leads."""
    if curve.size == 0:
        return 0.0, 0.0
    pre_n = curve.size // 2
    peak = int(np.argmax(np.abs(curve)))
    amp = float(abs(curve[peak]))
    gap = int(min_gap_seconds * FPS)
    rival = 0.0
    for i in range(curve.size):
        if abs(i - peak) > gap:
            rival = max(rival, float(abs(curve[i])))
    lag_ms = (peak - pre_n) / FPS * 1000.0
    return lag_ms / 1000.0, max(amp - rival, 0.0)


def measure_content_offset(
    video: Path,
    *,
    start_seconds: float = 0.0,
    window_seconds: float = 90.0,
    transcript_starts: list[float] | None = None,
    model_dir: Path | None = None,
) -> OffsetMeasurement:
    """Measure the audio-lead offset of a video from mouth motion vs speech onsets."""
    cv2 = _load_cv2()
    if cv2 is None:
        return OffsetMeasurement(None, 0.0, False, "content", "opencv unavailable")

    frames = _extract_frames(video, start_seconds, window_seconds)
    envelope = _audio_envelope(video, start_seconds, window_seconds)
    if frames is None or envelope is None or len(frames) < 50:
        return OffsetMeasurement(None, 0.0, False, "content", "extraction failed")

    model_paths = _ensure_face_model(model_dir or Path("/tmp/av_sync_models"))
    if model_paths is None:
        return OffsetMeasurement(None, 0.0, False, "content", "face model unavailable")
    net = cv2.dnn.readNetFromCaffe(*model_paths)

    boxes, face_rate = _face_boxes(cv2, net, frames)
    if face_rate < 0.25:
        return OffsetMeasurement(
            None, 0.0, False, "content", f"face detection rate too low ({face_rate:.2f})"
        )
    motion = mouth_motion(frames, boxes)

    if transcript_starts:
        onsets = [
            int(round((t - start_seconds) * FPS))
            for t in transcript_starts
            if start_seconds <= t <= start_seconds + window_seconds
        ]
    else:
        onsets = energy_onsets(envelope)
    curve = median_eta(motion, onsets)
    offset, confidence = pick_offset(curve)
    detail = f"face_rate={face_rate:.2f} onsets={len(onsets)}"
    return OffsetMeasurement(offset, confidence, True, "content", detail)


def resolve_audio_correction(
    manual_offset: float,
    auto_offset: float,
    auto_confidence: float,
    *,
    auto_correct: bool,
    min_confidence: float,
    max_offset: float,
) -> tuple[float, str]:
    """Decide the mux-time correction; a manual offset is authoritative.

    A non-zero manual offset is applied later by the edit render (apply_edit)
    and is never also applied at the mux, so the returned correction is 0.
    """
    if abs(float(manual_offset or 0.0)) > 1e-6:
        return 0.0, "manual offset set; auto-correction skipped"
    if not auto_correct:
        return 0.0, "auto-correction disabled"
    if abs(auto_offset) <= 0.1:
        return 0.0, "auto offset within tolerance"
    if abs(auto_offset) > max_offset:
        return 0.0, "auto offset exceeds max_offset_seconds; flagged for review"
    if auto_confidence < min_confidence:
        return 0.0, "auto offset below confidence threshold"
    return float(auto_offset), "auto-corrected"


def measure_waveform_offset(reference: Path, candidate: Path,
                            sample_rate: int = 8000) -> OffsetMeasurement:
    """Reliable waveform cross-correlation between two audio timelines."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return OffsetMeasurement(None, 0.0, False, "waveform", "ffmpeg missing")
    arrays = []
    for path in (reference, candidate):
        out = Path("/tmp/av_sync_wav.raw")
        try:
            subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-ss", "30", "-t", "120", "-i", str(path),
                 "-vn", "-ac", "1", "-ar", str(sample_rate),
                 "-af", "highpass=f=200,lowpass=f=3500", "-f", "s16le", str(out)],
                check=True, capture_output=True, timeout=600,
            )
        except Exception as e:
            return OffsetMeasurement(None, 0.0, False, "waveform", f"extraction failed: {e}")
        arrays.append(np.fromfile(out, dtype=np.int16).astype(np.float64))
    ref, cand = arrays
    n = min(len(ref), len(cand))
    if n < sample_rate * 10:
        return OffsetMeasurement(None, 0.0, False, "waveform", "too short")
    max_lag = sample_rate * 3
    ref = ref[:n] - ref[:n].mean()
    cand = cand[:n] - cand[:n].mean()
    size = 1
    while size < 2 * n:
        size <<= 1
    c = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(cand, size)), size)
    pos = c[: max_lag + 1]
    neg = c[size - max_lag :]
    lags = np.concatenate([np.arange(-max_lag, 0), np.arange(0, max_lag + 1)])
    vals = np.concatenate([neg, pos]) / (np.linalg.norm(ref) * np.linalg.norm(cand) + 1e-9)
    idx = int(np.argmax(np.abs(vals)))
    best = float(abs(vals[idx]))
    others = np.abs(vals).copy()
    others[max(0, idx - sample_rate // 2) : idx + sample_rate // 2] = 0.0
    confidence = best - float(others.max() if others.size else 0.0)
    return OffsetMeasurement(
        float(lags[idx]) / sample_rate, max(confidence, 0.0), True, "waveform",
        f"score={best:.3f}",
    )
