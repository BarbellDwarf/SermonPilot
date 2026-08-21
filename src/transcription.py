# transcription.py
"""
Transcription abstraction layer for SermonPilot.
Supports multiple backends:
- whisper_local: Uses OpenAI Whisper via the `whisper` Python package.
- whisper_openrouter: Calls OpenRouter's Whisper endpoint (compatible with OpenAI API).
- whisper_openai: Calls OpenAI's Whisper endpoint.
- faster_whisper_local: Uses faster-whisper (CTranslate2) for faster transcription.
The backend is selected via the `transcription.backend` entry in the config file.
All backends return a plain transcript string (or empty string on failure).
"""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when a transcription backend fails hard (uninstalled, disabled,
    model load failure, or cloud API error). Callers should mark the job
    failed with this reason instead of treating it as an empty transcript."""


def _detect_device(preference: str = "auto", allow_rocm: bool = True) -> str:
    """Detect the compute device for local Whisper.

    Args:
        preference: "auto", "cpu", "cuda", or "rocm".
        allow_rocm: When True, ROCm (AMD GPU) maps to "cuda" (works for
            standard Whisper, which runs on torch). When False, ROCm maps
            to "cpu" because CTranslate2 (faster-whisper) has no ROCm
            support and fails with "CUDA driver version is insufficient".
    Returns:
        "cpu" or "cuda".
    """
    if preference == "cpu":
        return "cpu"
    # Preference "cuda" or "rocm" or "auto"
    try:
        import torch
        if torch.cuda.is_available():
            # Pure ROCm builds set torch.version.hip
            if getattr(torch.version, "hip", None) is not None:
                logger.debug("Detected AMD GPU (ROCm) via torch.version.hip")
                return "cuda" if allow_rocm else "cpu"
            # Older ROCm builds set torch.version.cuda to "rocmX.Y"
            if "rocm" in (getattr(torch.version, "cuda", "") or "").lower():
                logger.debug("Detected AMD GPU (ROCm) via torch.version.cuda")
                return "cuda" if allow_rocm else "cpu"
            logger.debug("Detected NVIDIA GPU via torch.cuda")
            return "cuda"
    except Exception:
        pass
    # Fallback to CPU
    return "cpu"


def _transcribe_whisper_local(
    audio_path: str,
    model_size: str,
    device_preference: str = "auto",
    language: str | None = None,
) -> str:
    """Transcribe using the `whisper` library.

    Args:
        audio_path: Path to audio file.
        model_size: Whisper model size (tiny, base, small, medium, large).
        device_preference: Device selection string.
        language: ISO 639 language code; None lets Whisper detect it.
    Returns:
        Transcript text or empty string on error.
    """
    try:
        import warnings

        import whisper
    except ImportError as e:
        raise TranscriptionError(
            "whisper library not installed - install with: pip install openai-whisper"
        ) from e

    device = _detect_device(device_preference)
    logger.info("Local Whisper transcription: model=%s, device=%s", model_size, device)

    # Load model on detected device (cpu, cuda, or rocm)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = whisper.load_model(model_size, device=device)
    except Exception as e:
        raise TranscriptionError(
            f"Failed to load Whisper model {model_size} on {device}: {e}"
        ) from e

    # Transcribe
    try:
        transcribe_kwargs = {"language": language} if language else {}
        result = model.transcribe(audio_path, **transcribe_kwargs)
        transcript = result.get("text", "").strip()
        logger.info("Local transcription succeeded (%d characters)", len(transcript))
        return transcript
    except Exception as e:
        raise TranscriptionError(f"Local transcription error: {e}") from e


def _transcribe_faster_whisper_local(
    audio_path: str,
    model_size: str,
    device_preference: str = "auto",
    compute_type: str | None = None,
    language: str | None = None,
) -> str:
    """Transcribe using faster-whisper (CTranslate2 backend).

    Args:
        audio_path: Path to audio file.
        model_size: Whisper model size (tiny, base, small, medium, large).
        device_preference: Device selection string.
        compute_type: CTranslate2 compute type; defaults to int8 on CPU
            and float32 on GPU when not configured.
        language: ISO 639 language code; None lets faster-whisper detect it.
    Returns:
        Transcript text or empty string on error.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("faster-whisper library not installed, falling back to standard whisper")
        return _transcribe_whisper_local(audio_path, model_size, device_preference)

    device = _detect_device(device_preference, allow_rocm=False)
    effective_compute_type = compute_type or ("int8" if device == "cpu" else "float32")
    logger.info(
        "Faster Whisper transcription: model=%s, device=%s, compute_type=%s, language=%s",
        model_size, device, effective_compute_type, language,
    )

    try:
        model = WhisperModel(model_size, device=device, compute_type=effective_compute_type)

        # Transcribe with VAD filtering for better performance
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}
        )

        transcript = " ".join([segment.text for segment in segments]).strip()
        logger.info("Faster Whisper transcription succeeded (%d characters)", len(transcript))
        return transcript
    except Exception as e:
        logger.error("Faster Whisper transcription error: %s", e)
        # Fallback to standard whisper
        return _transcribe_whisper_local(audio_path, model_size, device_preference)


def _transcribe_openrouter(
    audio_path: str, api_key: str, base_url: str, model: str, progress_callback=None
) -> str:
    """Transcribe using OpenRouter's Whisper endpoint.

    OpenRouter follows the OpenAI API shape: POST /audio/transcriptions.
    """
    if not api_key:
        raise TranscriptionError("OpenRouter API key missing for transcription")
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": open(audio_path, "rb")}
    data = {"model": model}
    try:
        url = f"{base_url.rstrip('/')}/audio/transcriptions"
        logger.info("Calling OpenRouter Whisper at %s", url)
        if progress_callback:
            progress_callback(5, f"Uploading audio to {url}")
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=600)
        resp.raise_for_status()
        transcript = resp.json().get("text", "").strip()
        if progress_callback:
            progress_callback(90, "Transcription received")
        logger.info("OpenRouter transcription succeeded (%d characters)", len(transcript))
        return transcript
    except requests.RequestException as e:
        raise TranscriptionError(f"OpenRouter transcription failed: {e}") from e
    finally:
        files["file"].close()


def _transcribe_openai(audio_path: str, api_key: str, base_url: str, model: str,
                       progress_callback=None) -> str:
    """Transcribe using OpenAI's Whisper endpoint.

    If base_url is not provided, defaults to OpenAI's official endpoint.
    Supports SSE streaming for progress reporting when the endpoint supports it.
    """
    if not api_key:
        raise TranscriptionError("OpenAI API key missing for transcription")
    effective_base = base_url.rstrip('/') if base_url else "https://api.openai.com/v1"
    url = f"{effective_base}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": open(audio_path, "rb")}
    data = {"model": model}
    try:
        logger.info("Calling OpenAI Whisper at %s", url)
        resp = requests.post(url, headers=headers, data=data, files=files, stream=True, timeout=600)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            transcript_parts = []
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    import json
                    chunk = json.loads(payload)
                    text = chunk.get("text", "")
                    if text:
                        transcript_parts.append(text)
                    if progress_callback:
                        total_len = sum(len(p) for p in transcript_parts)
                        progress_callback(
                            min(total_len / 50000, 0.95),
                            f"Transcribing... ({total_len} chars)",
                        )
                except json.JSONDecodeError:
                    continue
            transcript = "".join(transcript_parts).strip()
        else:
            transcript = resp.json().get("text", "").strip()
        logger.info("OpenAI transcription succeeded (%d characters)", len(transcript))
        return transcript
    except requests.RequestException as e:
        raise TranscriptionError(f"OpenAI transcription failed: {e}") from e
    finally:
        files["file"].close()


def _is_cloud_model_override(model_size: str | None) -> bool:
    """True when the caller passed a specific cloud model rather than the
    generic local default ("base"). Cloud backends serve named models, so
    sizes like tiny/base/small do not map to anything meaningful there."""
    if not model_size:
        return False
    return model_size.lower() not in {"tiny", "base", "small", "medium", "large"}


def transcribe(audio_path: str, model_size: str = "base", config: dict[str, Any] = None,
                backend_override: str | None = None, progress_callback=None) -> str:
    """High‑level transcription dispatcher.

    Args:
        audio_path: Path to the audio file.
        model_size: Whisper model size for the local backend (ignored for cloud backends).
        config: Full application config. If None, defaults to {}.
        backend_override: If provided, overrides the backend from config.
    Returns:
        Transcript string (empty if transcription failed or disabled).
    """
    cfg = config or {}
    transcription_cfg = cfg.get("transcription", {})
    backend = backend_override or transcription_cfg.get("backend", "whisper_local")

    if backend == "whisper_local":
        local_cfg = transcription_cfg.get("whisper_local", {})
        device_pref = local_cfg.get("device", "auto")
        language = local_cfg.get("language")
        model = model_size or local_cfg.get("model", "base")
        return _transcribe_whisper_local(
            audio_path, model, device_pref, language=language
        )
    elif backend == "faster_whisper_local":
        faster_cfg = transcription_cfg.get("faster_whisper_local", {})
        device_pref = faster_cfg.get("device", "auto")
        # model_size from CLI overrides config size if provided
        model = model_size or faster_cfg.get("model", "base")
        compute_type = faster_cfg.get("compute_type")
        language = faster_cfg.get("language")
        return _transcribe_faster_whisper_local(
            audio_path, model, device_pref, compute_type=compute_type, language=language
        )
    elif backend == "whisper_openrouter":
        or_cfg = transcription_cfg.get("whisper_openrouter", {})
        api_key = os.getenv("OPENROUTER_API_KEY", or_cfg.get("api_key", ""))
        base_url = or_cfg.get("base_url", "https://openrouter.ai/api/v1")
        model = (
            model_size if _is_cloud_model_override(model_size)
            else or_cfg.get("model", "openai/whisper-large-v3")
        )
        return _transcribe_openrouter(
            audio_path, api_key, base_url, model, progress_callback=progress_callback
        )
    elif backend == "whisper_openai":
        oi_cfg = transcription_cfg.get("whisper_openai", {})
        api_key = os.getenv("OPENAI_API_KEY", oi_cfg.get("api_key", ""))
        base_url = oi_cfg.get("base_url", "https://api.openai.com/v1")
        model = (
            model_size if _is_cloud_model_override(model_size)
            else oi_cfg.get("model", "whisper-1")
        )
        return _transcribe_openai(
            audio_path, api_key, base_url, model, progress_callback=progress_callback
        )
    else:
        logger.warning("Unknown transcription backend '%s', skipping transcription", backend)
        return ""
