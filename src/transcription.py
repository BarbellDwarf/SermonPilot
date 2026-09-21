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


_MIN_PLAUSIBLE_API_KEY_LEN = 8

_KNOWN_KEY_PLACEHOLDERS = frozenset(
    {
        "",
        "test",
        "demo",
        "example",
        "placeholder",
        "none",
        "null",
        "xxx",
        "your-key-here",
        "your-openai-key-here",
    }
)


def _clean_api_key(value: Any) -> str:
    """Normalize a candidate API key, returning '' when it is unusable.

    Empty-after-trim, unresolved ``${VAR}`` placeholders, known dummy
    words, and obviously-invalid short strings (such as stray few-char
    junk left in config files) are treated as unset so they are never
    sent to a transcription endpoint.
    """
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    if "${" in cleaned or cleaned.startswith("$"):
        return ""
    if cleaned.lower() in _KNOWN_KEY_PLACEHOLDERS:
        return ""
    if len(cleaned) < _MIN_PLAUSIBLE_API_KEY_LEN:
        return ""
    return cleaned


def _resolve_transcription_api_key(env_var: str, cfg_value: Any) -> str:
    """Prefer a valid env var, fall back to a valid config value, else ''."""
    from_env = _clean_api_key(os.getenv(env_var, ""))
    if from_env:
        return from_env
    return _clean_api_key(cfg_value)


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


def log_cuda_memory(stage: str) -> None:
    """Log free/total VRAM for a pipeline stage when CUDA is present."""
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            logger.info("VRAM %s: %.2f/%.2f GB free", stage, free / 1e9, total / 1e9)
    except Exception:
        pass


def release_transcription_gpu() -> None:
    """Return reserved CUDA memory to the driver after a transcription stage."""
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
    except Exception:
        pass


_VALID_COMPUTE_TYPES = frozenset({"float16", "float32", "int8_float16", "int8", "auto"})
_DEFAULT_COMPUTE_TYPE = {"cpu": "int8", "cuda": "float16"}
_CUDA_FALLBACK_LADDER = ("float16", "int8_float16", "int8")


def _resolve_compute_type(requested: Any, device: str) -> str:
    """Resolve the compute type for a device.

    ``None``, empty, "auto", and unknown values fall through to the device
    default: int8 on CPU, float16 on CUDA. float16 halves the large-model
    weight footprint versus float32 and keeps an 8 GB card inside its budget.
    """
    if isinstance(requested, str) and requested.strip().lower() in _VALID_COMPUTE_TYPES:
        requested = requested.strip().lower()
        if requested != "auto":
            return requested
    return _DEFAULT_COMPUTE_TYPE.get(device, "int8")


def _is_cuda_out_of_memory(exc: BaseException) -> bool:
    """True when the failure is CUDA VRAM exhaustion, not a config error."""
    if type(exc).__name__ in {"OutOfMemoryError", "CudaOutOfMemoryError"}:
        return True
    return "out of memory" in str(exc).lower()


def _compute_type_ladder(desired: str) -> list[str]:
    """Desired type first, then the CUDA precision ladder down to int8."""
    attempts = [desired]
    for candidate in _CUDA_FALLBACK_LADDER:
        if candidate not in attempts:
            attempts.append(candidate)
    return attempts


def _build_whisper_model(model_factory, model_size: str, device: str, compute_type: str) -> Any:
    """Load a faster-whisper model, walking down the precision ladder on OOM.

    On CPU the ladder collapses to a single attempt. On CUDA, an out-of-memory
    failure retries with the next lower-precision type in
    ``_CUDA_FALLBACK_LADDER`` so a full card degrades instead of failing the
    job. Any non-OOM error (bad compute type, missing weights) surfaces at once.
    """
    if device != "cuda":
        return model_factory(model_size, device=device, compute_type=compute_type)

    attempts = _compute_type_ladder(compute_type)
    for index, candidate in enumerate(attempts):
        release_transcription_gpu()
        log_cuda_memory(f"before whisper load ({candidate})")
        try:
            model = model_factory(model_size, device=device, compute_type=candidate)
            if index > 0:
                logger.warning(
                    "Whisper fell back to compute_type=%s after CUDA out-of-memory "
                    "with %s",
                    candidate,
                    attempts[index - 1],
                )
            logger.info(
                "Whisper model loaded: model=%s device=%s compute_type=%s",
                model_size,
                device,
                candidate,
            )
            return model
        except Exception as exc:
            if not _is_cuda_out_of_memory(exc) or index == len(attempts) - 1:
                raise
            logger.warning(
                "Whisper load on cuda with compute_type=%s ran out of memory (%s); "
                "retrying with %s",
                candidate,
                exc,
                attempts[index + 1],
            )


def _with_gpu_release(fn):
    """Release cached CUDA memory after a local transcription backend returns.

    PyTorch keeps reserved blocks in its caching allocator; without an explicit
    empty_cache the Streamlit process holds several GB after the job finishes
    and the next model load OOMs.
    """

    def wrapper(*args, **kwargs):
        log_cuda_memory("before transcription")
        try:
            return fn(*args, **kwargs)
        finally:
            release_transcription_gpu()
            log_cuda_memory("after transcription release")

    wrapper.__name__ = getattr(fn, "__name__", "wrapped")
    return wrapper


def _load_whisper_model(model_size: str, device: str):
    """Load an openai-whisper model, raising TranscriptionError on failure."""
    import warnings

    try:
        import whisper
    except ImportError as e:
        raise TranscriptionError(
            "whisper library not installed - install with: pip install openai-whisper"
        ) from e

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return whisper.load_model(model_size, device=device)
    except Exception as e:
        raise TranscriptionError(
            f"Failed to load Whisper model {model_size} on {device}: {e}"
        ) from e


@_with_gpu_release
def _transcribe_whisper_local_segments(
    audio_path: str,
    model_size: str,
    device_preference: str = "auto",
    language: str | None = None,
) -> list[dict[str, float | str]]:
    """Transcribe using the `whisper` library, returning timed segments."""
    device = _detect_device(device_preference)
    logger.info("Local Whisper transcription: model=%s, device=%s", model_size, device)

    model = _load_whisper_model(model_size, device)

    try:
        transcribe_kwargs = {"language": language} if language else {}
        result = model.transcribe(audio_path, **transcribe_kwargs)
        raw = result.get("segments") or []
        segments = [
            {
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": str(seg.get("text", "")).strip(),
            }
            for seg in raw
            if isinstance(seg, dict)
        ]
        logger.info("Local transcription succeeded (%d segments)", len(segments))
        return segments
    except Exception as e:
        raise TranscriptionError(f"Local transcription error: {e}") from e


@_with_gpu_release
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
    device = _detect_device(device_preference)
    logger.info("Local Whisper transcription: model=%s, device=%s", model_size, device)

    model = _load_whisper_model(model_size, device)

    # Transcribe
    try:
        transcribe_kwargs = {"language": language} if language else {}
        result = model.transcribe(audio_path, **transcribe_kwargs)
        transcript = result.get("text", "").strip()
        logger.info("Local transcription succeeded (%d characters)", len(transcript))
        return transcript
    except Exception as e:
        raise TranscriptionError(f"Local transcription error: {e}") from e


@_with_gpu_release
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
    effective_compute_type = _resolve_compute_type(compute_type, device)
    logger.info(
        "Faster Whisper transcription: model=%s, device=%s, compute_type=%s, language=%s",
        model_size,
        device,
        effective_compute_type,
        language,
    )

    try:
        model = _build_whisper_model(WhisperModel, model_size, device, effective_compute_type)

        # Transcribe with VAD filtering for better performance
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        transcript = " ".join([segment.text for segment in segments]).strip()
        logger.info("Faster Whisper transcription succeeded (%d characters)", len(transcript))
        return transcript
    except Exception as e:
        raise TranscriptionError(f"Faster Whisper transcription failed: {e}") from e


@_with_gpu_release
def _transcribe_faster_whisper_local_segments(
    audio_path: str,
    model_size: str,
    device_preference: str = "auto",
    compute_type: str | None = None,
    language: str | None = None,
) -> list[dict[str, float | str]]:
    """Transcribe using faster-whisper, returning timed segments."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("faster-whisper library not installed, falling back to standard whisper")
        return _transcribe_whisper_local_segments(audio_path, model_size, device_preference)

    device = _detect_device(device_preference, allow_rocm=False)
    effective_compute_type = _resolve_compute_type(compute_type, device)
    logger.info(
        "Faster Whisper transcription: model=%s, device=%s, compute_type=%s, language=%s",
        model_size,
        device,
        effective_compute_type,
        language,
    )

    try:
        model = _build_whisper_model(WhisperModel, model_size, device, effective_compute_type)

        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        timed = [
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": str(segment.text).strip(),
            }
            for segment in segments
        ]
        logger.info("Faster Whisper transcription succeeded (%d segments)", len(timed))
        return timed
    except Exception as e:
        raise TranscriptionError(f"Faster Whisper transcription failed: {e}") from e


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


def _parse_verbose_json_segments(resp: requests.Response) -> list[dict[str, float | str]]:
    """Extract timed segments from a verbose_json transcription response."""
    try:
        payload = resp.json()
    except ValueError as e:
        logger.warning("OpenAI verbose_json response was not valid JSON: %s", e)
        return []
    raw = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        logger.warning("OpenAI verbose_json response contained no segments")
        return []
    segments: list[dict[str, float | str]] = []
    for seg in raw:
        if not isinstance(seg, dict):
            continue
        try:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        segments.append({"start": start, "end": end, "text": str(seg.get("text", "")).strip()})
    return segments


def _transcribe_openai(
    audio_path: str,
    api_key: str,
    base_url: str,
    model: str,
    progress_callback=None,
    want_segments: bool = False,
) -> str | list[dict[str, float | str]]:
    """Transcribe using OpenAI's Whisper endpoint.

    If base_url is not provided, defaults to OpenAI's official endpoint.
    Supports SSE streaming for progress reporting when the endpoint supports it.
    With want_segments=True, requests verbose_json and returns timed segments,
    or an empty list when the response carries no usable timestamps.
    """
    if not api_key:
        raise TranscriptionError("OpenAI API key missing for transcription")
    effective_base = base_url.rstrip("/") if base_url else "https://api.openai.com/v1"
    url = f"{effective_base}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": open(audio_path, "rb")}
    data = {"model": model}
    if want_segments:
        data["response_format"] = "verbose_json"
    try:
        logger.info("Calling OpenAI Whisper at %s", url)
        resp = requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
            stream=not want_segments,
            timeout=600,
        )
        resp.raise_for_status()
        if want_segments:
            segments = _parse_verbose_json_segments(resp)
            logger.info("OpenAI transcription returned %d segments", len(segments))
            return segments
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


def _configured_compute_type(transcription_cfg: dict, faster_cfg: dict[str, Any]) -> Any:
    """Read transcription.compute_type, falling back to the per-backend key.

    The top-level key is the supported surface (default "auto"). Older configs
    only carried ``faster_whisper_local.compute_type``, so that stays honoured.
    """
    for value in (transcription_cfg.get("compute_type"), faster_cfg.get("compute_type")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_cloud_model_override(model_size: str | None) -> bool:
    """True when the caller passed a specific cloud model rather than the
    generic local default ("base"). Cloud backends serve named models, so
    sizes like tiny/base/small do not map to anything meaningful there."""
    if not model_size:
        return False
    return model_size.lower() not in {"tiny", "base", "small", "medium", "large"}


def transcribe(
    audio_path: str,
    model_size: str = "base",
    config: dict[str, Any] = None,
    backend_override: str | None = None,
    progress_callback=None,
) -> str:
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
        return _transcribe_whisper_local(audio_path, model, device_pref, language=language)
    elif backend == "faster_whisper_local":
        faster_cfg = transcription_cfg.get("faster_whisper_local", {})
        device_pref = faster_cfg.get("device", "auto")
        # model_size from CLI overrides config size if provided
        model = model_size or faster_cfg.get("model", "base")
        compute_type = _configured_compute_type(transcription_cfg, faster_cfg)
        language = faster_cfg.get("language")
        return _transcribe_faster_whisper_local(
            audio_path, model, device_pref, compute_type=compute_type, language=language
        )
    elif backend == "whisper_openrouter":
        or_cfg = transcription_cfg.get("whisper_openrouter", {})
        api_key = _resolve_transcription_api_key("OPENROUTER_API_KEY", or_cfg.get("api_key", ""))
        base_url = or_cfg.get("base_url", "https://openrouter.ai/api/v1")
        model = (
            model_size
            if _is_cloud_model_override(model_size)
            else or_cfg.get("model", "openai/whisper-large-v3")
        )
        return _transcribe_openrouter(
            audio_path, api_key, base_url, model, progress_callback=progress_callback
        )
    elif backend == "whisper_openai":
        oi_cfg = transcription_cfg.get("whisper_openai", {})
        api_key = _resolve_transcription_api_key("OPENAI_API_KEY", oi_cfg.get("api_key", ""))
        base_url = oi_cfg.get("base_url", "https://api.openai.com/v1")
        model = (
            model_size if _is_cloud_model_override(model_size) else oi_cfg.get("model", "whisper-1")
        )
        return _transcribe_openai(
            audio_path, api_key, base_url, model, progress_callback=progress_callback
        )
    else:
        logger.warning("Unknown transcription backend '%s', skipping transcription", backend)
        return ""


def _normalize_segments(raw: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    """Coerce raw segment dicts into monotonic, non-overlapping seconds."""
    segments: list[dict[str, float | str]] = []
    cursor = 0.0
    for seg in raw:
        if not isinstance(seg, dict):
            continue
        try:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end < start:
            end = start
        if start < cursor:
            start = cursor
        if end < cursor:
            end = cursor
        cursor = end
        segments.append({"start": start, "end": end, "text": str(seg.get("text", "")).strip()})
    return segments


def transcribe_segments(
    audio_path: str,
    model_size: str = "base",
    config: dict[str, Any] = None,
    backend_override: str | None = None,
    progress_callback=None,
) -> list[dict[str, float | str]]:
    """High-level transcription dispatcher returning timed segments.

    Mirrors transcribe() for backend selection. Backends without timestamp
    support return an empty list.
    """
    cfg = config or {}
    transcription_cfg = cfg.get("transcription", {})
    backend = backend_override or transcription_cfg.get("backend", "whisper_local")

    if backend == "whisper_local":
        local_cfg = transcription_cfg.get("whisper_local", {})
        device_pref = local_cfg.get("device", "auto")
        language = local_cfg.get("language")
        model = model_size or local_cfg.get("model", "base")
        return _normalize_segments(
            _transcribe_whisper_local_segments(audio_path, model, device_pref, language=language)
        )
    elif backend == "faster_whisper_local":
        faster_cfg = transcription_cfg.get("faster_whisper_local", {})
        device_pref = faster_cfg.get("device", "auto")
        model = model_size or faster_cfg.get("model", "base")
        compute_type = _configured_compute_type(transcription_cfg, faster_cfg)
        language = faster_cfg.get("language")
        return _normalize_segments(
            _transcribe_faster_whisper_local_segments(
                audio_path, model, device_pref, compute_type=compute_type, language=language
            )
        )
    elif backend == "whisper_openrouter":
        return []
    elif backend == "whisper_openai":
        oi_cfg = transcription_cfg.get("whisper_openai", {})
        api_key = _resolve_transcription_api_key("OPENAI_API_KEY", oi_cfg.get("api_key", ""))
        base_url = oi_cfg.get("base_url", "https://api.openai.com/v1")
        model = (
            model_size if _is_cloud_model_override(model_size) else oi_cfg.get("model", "whisper-1")
        )
        result = _transcribe_openai(
            audio_path,
            api_key,
            base_url,
            model,
            progress_callback=progress_callback,
            want_segments=True,
        )
        return _normalize_segments(result)
    else:
        logger.warning("Unknown transcription backend '%s', skipping transcription", backend)
        return []
