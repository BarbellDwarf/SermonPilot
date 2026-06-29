# transcription.py
"""
Transcription abstraction layer for SermonAudio Processor.
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


def _detect_device(preference: str = "auto") -> str:
    """Detect the compute device for local Whisper.

    Args:
        preference: "auto", "cpu", "cuda", or "rocm".
    Returns:
        "cpu" or "cuda" (for both Nvidia and ROCm CUDA).
    """
    if preference == "cpu":
        return "cpu"
    # Preference "cuda" or "rocm" or "auto"
    try:
        import torch
        if torch.cuda.is_available():
            # Detect ROCm (AMD GPU) — pure ROCm builds set torch.version.hip
            if getattr(torch.version, "hip", None) is not None:
                logger.debug("Detected AMD GPU (ROCm) via torch.version.hip")
                return "cuda"
            # Older ROCm builds set torch.version.cuda to "rocmX.Y"
            if "rocm" in (getattr(torch.version, "cuda", "") or "").lower():
                logger.debug("Detected AMD GPU (ROCm) via torch.version.cuda")
                return "cuda"
            logger.debug("Detected NVIDIA GPU via torch.cuda")
            return "cuda"
    except Exception:
        pass
    # Fallback to CPU
    return "cpu"


def _transcribe_whisper_local(
    audio_path: str, model_size: str, device_preference: str = "auto"
) -> str:
    """Transcribe using the `whisper` library.

    Args:
        audio_path: Path to audio file.
        model_size: Whisper model size (tiny, base, small, medium, large).
        device_preference: Device selection string.
    Returns:
        Transcript text or empty string on error.
    """
    try:
        import warnings

        import whisper
    except ImportError:
        logger.warning("whisper library not installed, cannot perform local transcription")
        return ""

    device = _detect_device(device_preference)
    logger.info("Local Whisper transcription: model=%s, device=%s", model_size, device)

    # Load model on detected device (cpu, cuda, or rocm)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = whisper.load_model(model_size, device=device)
    except Exception as e:
        # Network errors while downloading model are common; try tiny as fallback.
        logger.warning("Failed to load Whisper model %s on %s: %s", model_size, device, e)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            logger.info("Attempting to load tiny model as fallback")
            try:
                model = whisper.load_model("tiny", device=device)
            except Exception as e2:
                logger.error("Fallback tiny model also failed: %s", e2)
                return ""
        else:
            return ""

    # Transcribe
    try:
        result = model.transcribe(audio_path)
        transcript = result.get("text", "").strip()
        logger.info("Local transcription succeeded (%d characters)", len(transcript))
        return transcript
    except Exception as e:
        logger.error("Local transcription error: %s", e)
        return ""


def _transcribe_faster_whisper_local(
    audio_path: str, model_size: str, device_preference: str = "auto"
) -> str:
    """Transcribe using faster-whisper (CTranslate2 backend).

    Args:
        audio_path: Path to audio file.
        model_size: Whisper model size (tiny, base, small, medium, large).
        device_preference: Device selection string.
    Returns:
        Transcript text or empty string on error.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("faster-whisper library not installed, falling back to standard whisper")
        return _transcribe_whisper_local(audio_path, model_size, device_preference)

    device = _detect_device(device_preference)
    logger.info("Faster Whisper transcription: model=%s, device=%s", model_size, device)

    try:
        # Initialize model with appropriate compute type
        # float16 works well for both AMD and NVIDIA GPUs
        compute_type = "float16"
        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        # Transcribe with VAD filtering for better performance
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language="en",
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


def _transcribe_openrouter(audio_path: str, api_key: str, base_url: str, model: str) -> str:
    """Transcribe using OpenRouter's Whisper endpoint.

    OpenRouter follows the OpenAI API shape: POST /audio/transcriptions.
    """
    if not api_key:
        logger.error("OpenRouter API key missing for transcription")
        return ""
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": open(audio_path, "rb")}
    data = {"model": model}
    try:
        url = f"{base_url.rstrip('/')}/audio/transcriptions"
        logger.info("Calling OpenRouter Whisper at %s", url)
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=120)
        resp.raise_for_status()
        transcript = resp.json().get("text", "").strip()
        logger.info("OpenRouter transcription succeeded (%d characters)", len(transcript))
        return transcript
    except Exception as e:
        logger.error("OpenRouter transcription failed: %s", e)
        return ""
    finally:
        files["file"].close()


def _transcribe_openai(audio_path: str, api_key: str, base_url: str, model: str) -> str:
    """Transcribe using OpenAI's Whisper endpoint.

    If base_url is not provided, defaults to OpenAI's official endpoint.
    """
    if not api_key:
        logger.error("OpenAI API key missing for transcription")
        return ""
    effective_base = base_url.rstrip('/') if base_url else "https://api.openai.com/v1"
    url = f"{effective_base}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": open(audio_path, "rb")}
    data = {"model": model}
    try:
        logger.info("Calling OpenAI Whisper at %s", url)
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=120)
        resp.raise_for_status()
        transcript = resp.json().get("text", "").strip()
        logger.info("OpenAI transcription succeeded (%d characters)", len(transcript))
        return transcript
    except Exception as e:
        logger.error("OpenAI transcription failed: %s", e)
        return ""
    finally:
        files["file"].close()


def transcribe(audio_path: str, model_size: str = "base", config: dict[str, Any] = None,
                backend_override: str | None = None) -> str:
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
        # model_size from CLI overrides config size if provided
        model = model_size or local_cfg.get("model", "base")
        return _transcribe_whisper_local(audio_path, model, device_pref)
    elif backend == "faster_whisper_local":
        faster_cfg = transcription_cfg.get("faster_whisper_local", {})
        device_pref = faster_cfg.get("device", "auto")
        # model_size from CLI overrides config size if provided
        model = model_size or faster_cfg.get("model", "base")
        return _transcribe_faster_whisper_local(audio_path, model, device_pref)
    elif backend == "whisper_openrouter":
        or_cfg = transcription_cfg.get("whisper_openrouter", {})
        api_key = os.getenv("OPENROUTER_API_KEY", or_cfg.get("api_key", ""))
        base_url = or_cfg.get("base_url", "https://openrouter.ai/api/v1")
        model = or_cfg.get("model", "openai/whisper-large-v3")
        return _transcribe_openrouter(audio_path, api_key, base_url, model)
    elif backend == "whisper_openai":
        oi_cfg = transcription_cfg.get("whisper_openai", {})
        api_key = os.getenv("OPENAI_API_KEY", oi_cfg.get("api_key", ""))
        base_url = oi_cfg.get("base_url", "https://api.openai.com/v1")
        model = oi_cfg.get("model", "whisper-1")
        return _transcribe_openai(audio_path, api_key, base_url, model)
    else:
        logger.warning("Unknown transcription backend '%s', skipping transcription", backend)
        return ""
