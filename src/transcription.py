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

import ipaddress
import logging
import os
import sys
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

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


def _api_key_defect(value: Any) -> str | None:
    """Describe why a candidate key is unusable, or None when it is usable.

    Never includes the value itself: only the shape of the problem (empty,
    placeholder, known dummy, or the failing length) so diagnostics cannot
    leak a credential.
    """
    if value is None:
        return "not set"
    if not isinstance(value, str):
        return "not a string"
    cleaned = value.strip()
    if not cleaned:
        return "empty"
    if "${" in cleaned or cleaned.startswith("$"):
        return "an unresolved ${VAR} placeholder"
    if cleaned.lower() in _KNOWN_KEY_PLACEHOLDERS:
        return "a known placeholder value"
    if len(cleaned) < _MIN_PLAUSIBLE_API_KEY_LEN:
        return f"length {len(cleaned)} < {_MIN_PLAUSIBLE_API_KEY_LEN}"
    return None


def _clean_api_key(value: Any) -> str:
    """Normalize a candidate API key, returning '' when it is unusable.

    Empty-after-trim, unresolved ``${VAR}`` placeholders, known dummy
    words, and obviously-invalid short strings (such as stray few-char
    junk left in config files) are treated as unset so they are never
    sent to a transcription endpoint.
    """
    if _api_key_defect(value) is not None:
        return ""
    return str(value).strip()


def _resolve_transcription_api_key(env_var: str, cfg_value: Any) -> str:
    """Prefer a valid env var, fall back to a valid config value, else ''."""
    from_env = _clean_api_key(os.getenv(env_var, ""))
    if from_env:
        return from_env
    return _clean_api_key(cfg_value)


def _is_local_endpoint(base_url: str | None) -> bool:
    """True when a transcription base URL points at a private LAN address.

    Loopback, RFC1918 addresses, and ``.local`` mDNS names are treated as
    local services: they run on the operator's own network and commonly
    ignore auth, so a missing key must not fail the request. Hostnames that
    resolve to a public name are not local, and an unparseable URL is not
    local.
    """
    if not base_url:
        return False
    host = urlparse(base_url).hostname
    if not host:
        return False
    host = host.strip().lower().rstrip(".")
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def _env_var_for_config_path(key_path: str) -> str | None:
    """Return the env var that supplied a dotted config path, if any.

    When several mapped variables target the same path, the last one the
    resolver applied wins, mirroring ``apply_env_overrides``.
    """
    try:
        from .core.config import ENV_CONFIG_MAP
    except ImportError:
        from core.config import ENV_CONFIG_MAP

    selected: str | None = None
    for env_var, paths in ENV_CONFIG_MAP.items():
        if os.getenv(env_var) and any(".".join(path) == key_path for path in paths):
            selected = env_var
    return selected


def _config_source_for_path(key_path: str) -> str:
    """Label where the effective value at a config path came from.

    Reuses the resolver's source map; an ``env`` source is narrowed to the
    specific environment variable so the message names the override that
    silently won.
    """
    try:
        from ui.config_utils import resolve_config_with_sources

        _config, sources = resolve_config_with_sources()
        source = sources.get(key_path, "default")
    except Exception:
        return "default"
    if source != "env":
        return source
    env_var = _env_var_for_config_path(key_path)
    return f"env {env_var}" if env_var else "env"


def _unusable_key_message(key_path: str, raw_value: Any) -> str:
    """Build an actionable message naming the path, its source, and the defect."""
    defect = _api_key_defect(raw_value) or "unusable"
    source = _config_source_for_path(key_path)
    return (
        f"Transcription API key {key_path} came from {source} and is unusable ({defect})"
    )


def _auth_headers(
    api_key: str, base_url: str, key_path: str, raw_api_key: Any
) -> dict[str, str]:
    """Return request headers, allowing keyless local endpoints.

    A usable key is always sent. Without one, a local endpoint is called
    unauthenticated with a single log line; anything else fails with a
    message that names the config path and the layer that supplied the value.
    """
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    if _is_local_endpoint(base_url):
        logger.info(
            "Transcription endpoint %s is local; skipping API key authentication",
            base_url,
        )
        return {}
    raise TranscriptionError(_unusable_key_message(key_path, raw_api_key))


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


def _ensure_info_logging() -> None:
    """Make this module's INFO records visible without a root logger config.

    The Streamlit worker never calls logging.basicConfig, so the root logger
    sits at WARNING with no handler and INFO stage logs (VRAM numbers) vanish.
    Pin this module's logger to INFO and attach a stderr handler only when the
    root logger has none, so CLI/verbose configurations keep their formatting.
    """
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    if any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        return
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)


def log_cuda_memory(stage: str) -> None:
    """Log free/total VRAM and live PyTorch allocations for a pipeline stage."""
    _ensure_info_logging()
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            allocated = torch.cuda.memory_allocated()
            logger.info(
                "VRAM %s: %.2f/%.2f GB free, %.2f GB allocated by PyTorch",
                stage,
                free / 1e9,
                total / 1e9,
                allocated / 1e9,
            )
    except Exception:
        pass


def _allocated_bytes() -> float | None:
    """Live PyTorch allocation in bytes, or None when CUDA is unmeasurable."""
    try:
        import torch

        if torch.cuda.is_available():
            return float(torch.cuda.memory_allocated())
    except Exception:
        pass
    return None


def _free_vram_gb() -> float | None:
    """Free device VRAM in GB, or None when CUDA is unmeasurable."""
    try:
        import torch

        if torch.cuda.is_available():
            free, _total = torch.cuda.mem_get_info()
            return float(free) / (1024**3)
    except Exception:
        pass
    return None


def _total_vram_gb() -> float | None:
    """Total device VRAM in GB, or None when CUDA is unmeasurable."""
    try:
        import torch

        if torch.cuda.is_available():
            return float(torch.cuda.get_device_properties(0).total_memory) / (1024**3)
    except Exception:
        pass
    return None


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


DEFAULT_MIN_GPU_VRAM_GB = 12.0
_MIN_FREE_VRAM_GB_BEFORE_WHISPER = 3.5

_DF_CACHE_ATTRS = (
    "_MODEL_CACHE",
    "_model_cache",
    "_CACHED_MODEL",
    "_cached_model",
    "MODEL_CACHE",
    "_DF_STATE",
    "_df_state",
    "_CACHED_STATE",
    "_cached_state",
    "DF_STATE_CACHE",
)
_DF_MODULE_NAMES = ("df.enhance", "df.modules", "df.utils", "df")

_last_enhancement_release_bytes: int | None = None


def enhancement_settings(config: dict[str, Any] | None) -> tuple[str, float]:
    """Read ``enhancement.device`` and ``enhancement.min_gpu_vram_gb``.

    Returns ``(device, min_gpu_vram_gb)``. Unknown device values fall back to
    ``"auto"`` and an unparseable threshold falls back to the 12 GB default, so
    a malformed config never prevents processing.
    """
    raw = (config or {}).get("enhancement")
    cfg = raw if isinstance(raw, dict) else {}
    device = str(cfg.get("device", "auto") or "auto").strip().lower()
    if device not in {"auto", "cpu", "cuda"}:
        device = "auto"
    try:
        min_gb = float(cfg.get("min_gpu_vram_gb", DEFAULT_MIN_GPU_VRAM_GB))
    except (TypeError, ValueError):
        min_gb = DEFAULT_MIN_GPU_VRAM_GB
    return device, min_gb


def resolve_enhancement_device(
    requested: str = "auto",
    min_gpu_vram_gb: float = DEFAULT_MIN_GPU_VRAM_GB,
    total_vram_gb: float | None = None,
) -> str:
    """Pick the compute device for audio enhancement.

    An explicit ``cpu``/``cuda`` always wins. With ``auto``, DeepFilterNet runs
    on CPU when the GPU is absent or its total VRAM is below
    ``min_gpu_vram_gb``: a small card must not lose enhancement to whisper,
    since CPU enhancement is slower but leaves the GPU free for transcription.
    """
    preference = (requested or "auto").strip().lower()
    if preference == "cpu":
        return "cpu"
    if preference in {"cuda", "rocm", "gpu"}:
        return "cuda"
    if total_vram_gb is None:
        total_vram_gb = _total_vram_gb()
    if total_vram_gb is None:
        return "cpu"
    return "cpu" if float(total_vram_gb) < float(min_gpu_vram_gb) else "cuda"


def _clear_deepfilternet_cache() -> bool:
    """Best-effort drop of DeepFilterNet's module-level cached model/state.

    The ``df`` package can retain its loaded model and DF state in module
    globals, which keeps their tensors live on the GPU even after the caller
    drops its own handle. Clear the known cache attributes so the following
    ``gc.collect()`` and ``torch.cuda.empty_cache()`` can reclaim them.
    """
    cleared = False
    for module_name in _DF_MODULE_NAMES:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr in _DF_CACHE_ATTRS:
            if hasattr(module, attr):
                try:
                    setattr(module, attr, None)
                    cleared = True
                except Exception:
                    pass
    return cleared


def release_enhancement_gpu(processor: Any = None) -> int | None:
    """Release VRAM held by the audio enhancement stage before transcription.

    Drops the processor's DeepFilterNet handle, clears the ``df`` package's
    module-level cached model/state, then delegates to
    ``release_transcription_gpu`` so the caching allocator returns its blocks
    to the driver. Returns the bytes reclaimed, or None when CUDA memory is not
    measurable. A zero result is logged as an incomplete release.
    """
    global _last_enhancement_release_bytes

    before = _allocated_bytes()
    if processor is not None:
        try:
            processor.release_gpu()
        except Exception as exc:
            logger.debug("Enhancement processor release failed: %s", exc)
    if _clear_deepfilternet_cache():
        logger.info("Cleared DeepFilterNet module-level model/state cache")
    release_transcription_gpu()
    after = _allocated_bytes()
    log_cuda_memory("after enhancement release")

    if before is None or after is None:
        _last_enhancement_release_bytes = None
        return None

    reclaimed = max(int(before - after), 0)
    _last_enhancement_release_bytes = reclaimed
    logger.info(
        "Enhancement GPU release reclaimed %.2f GB (allocated %.2f -> %.2f GB)",
        reclaimed / 1e9,
        before / 1e9,
        after / 1e9,
    )
    if before > 0 and reclaimed == 0:
        logger.warning(
            "Enhancement GPU release reclaimed nothing; %.2f GB is still allocated "
            "by PyTorch. Whisper will be guarded before its model load.",
            after / 1e9,
        )
    return reclaimed


def guard_transcription_device(
    device: str,
    free_vram_gb: float | None = None,
    reclaimed_bytes: int | None = None,
) -> str:
    """Return the device to use for whisper, downgrading to CPU if needed.

    Stays on the requested device unless free VRAM is measurably below the
    threshold AND the enhancement release reclaimed nothing (an incomplete
    release means the memory is still held). A completed CPU transcription is
    better than a failed GPU job, so the fallback is conservative and logged.
    """
    if device != "cuda":
        return device
    if free_vram_gb is None:
        free_vram_gb = _free_vram_gb()
    if free_vram_gb is None or float(free_vram_gb) >= _MIN_FREE_VRAM_GB_BEFORE_WHISPER:
        return device
    if reclaimed_bytes is None:
        reclaimed_bytes = _last_enhancement_release_bytes
    if reclaimed_bytes is not None and reclaimed_bytes > 0:
        logger.warning(
            "Only %.2f GB VRAM free before whisper load, but the enhancement "
            "release reclaimed %.2f GB; keeping device=%s",
            float(free_vram_gb),
            reclaimed_bytes / 1e9,
            device,
        )
        return device
    logger.warning(
        "Only %.2f GB VRAM free before whisper load. The audio enhancement stage "
        "held the GPU and the release reclaimed nothing, so transcription falls "
        "back to CPU instead of failing the job outright.",
        float(free_vram_gb),
    )
    return "cpu"


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
    """Load an openai-whisper model, raising TranscriptionError on failure.

    openai-whisper loads float32 weights by default. Loading straight onto CUDA
    allocates that float32 copy on the device first, which spikes a large model
    past an 8 GB card before any conversion happens. So the model is loaded on
    CPU, converted to half precision, and only then moved to CUDA: the GPU only
    ever sees the fp16 weights. If even the fp16 move runs out of memory the
    CPU model is kept, with the reason logged.
    """
    import warnings

    _ensure_info_logging()

    try:
        import whisper
    except ImportError as e:
        raise TranscriptionError(
            "whisper library not installed - install with: pip install openai-whisper"
        ) from e

    log_cuda_memory(f"before whisper load ({device}, cpu weights)")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = whisper.load_model(model_size, device="cpu")
    except Exception as e:
        raise TranscriptionError(
            f"Failed to load Whisper model {model_size} on cpu: {e}"
        ) from e

    if device != "cuda":
        logger.info(
            "Whisper model loaded: model=%s device=cpu dtype=float32", model_size
        )
        return model

    dtype = "float32"
    try:
        model = model.half()
        dtype = "float16"
    except Exception as exc:
        logger.warning("Could not convert whisper model to fp16, staying float32: %s", exc)

    log_cuda_memory(f"before whisper move to {device} ({dtype})")
    try:
        model = model.to(device)
    except Exception as e:
        if _is_cuda_out_of_memory(e):
            free_gb = _free_vram_gb()
            free_text = f"{free_gb:.2f} GB free" if free_gb is not None else "free VRAM unknown"
            logger.warning(
                "whisper %s could not fit on the GPU in %s (%s); keeping the CPU model",
                model_size,
                dtype,
                free_text,
            )
            release_transcription_gpu()
            try:
                model = model.to("cpu")
            except Exception as exc:
                logger.warning("Could not move whisper model back to CPU: %s", exc)
            if dtype == "float16":
                try:
                    model = model.float()
                except Exception as exc:
                    logger.warning("Could not restore fp32 weights on CPU: %s", exc)
            logger.info(
                "Whisper model loaded: model=%s device=cpu dtype=float32 "
                "(fp16 GPU move ran out of memory)",
                model_size,
            )
            return model
        raise TranscriptionError(
            f"Failed to load Whisper model {model_size} on {device}: {e}"
        ) from e

    logger.info(
        "Whisper model loaded: model=%s device=%s dtype=%s", model_size, device, dtype
    )
    log_cuda_memory("after whisper load")
    return model


@_with_gpu_release
def _transcribe_whisper_local_segments(
    audio_path: str,
    model_size: str,
    device_preference: str = "auto",
    language: str | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> list[dict[str, float | str]]:
    """Transcribe using the `whisper` library, returning timed segments.

    ``cancel_check`` is polled once per decoded segment. A single segment
    decode and the model load are the only uninterruptible steps, so the
    worst-case delay between a cancel request and the raise is one segment
    decode; the queue's cancel bound is asserted in the job queue tests.
    """
    device = guard_transcription_device(_detect_device(device_preference))
    logger.info("Local Whisper transcription: model=%s, device=%s", model_size, device)

    model = _load_whisper_model(model_size, device)

    try:
        transcribe_kwargs = {"language": language} if language else {}
        result = model.transcribe(audio_path, **transcribe_kwargs)
    except Exception as e:
        raise TranscriptionError(f"Local transcription error: {e}") from e

    segments = []
    for seg in result.get("segments") or []:
        if cancel_check is not None:
            cancel_check()
        if isinstance(seg, dict):
            segments.append({
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": str(seg.get("text", "")).strip(),
            })
    logger.info("Local transcription succeeded (%d segments)", len(segments))
    return segments


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
    device = guard_transcription_device(_detect_device(device_preference))
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

    device = guard_transcription_device(_detect_device(device_preference, allow_rocm=False))
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
    cancel_check: Callable[[], None] | None = None,
) -> list[dict[str, float | str]]:
    """Transcribe using faster-whisper, returning timed segments.

    ``cancel_check`` is polled once per decoded segment, and the check sits
    outside the model-call try/except so a cancellation is never wrapped as a
    TranscriptionError. One CTranslate2 segment decode and the model load are
    not interruptible; that is the documented worst-case cancel delay.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("faster-whisper library not installed, falling back to standard whisper")
        return _transcribe_whisper_local_segments(
            audio_path, model_size, device_preference, cancel_check=cancel_check
        )

    device = guard_transcription_device(_detect_device(device_preference, allow_rocm=False))
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
    except Exception as e:
        raise TranscriptionError(f"Faster Whisper transcription failed: {e}") from e

    timed = []
    for segment in segments:
        if cancel_check is not None:
            cancel_check()
        timed.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": str(segment.text).strip(),
            }
        )
    logger.info("Faster Whisper transcription succeeded (%d segments)", len(timed))
    return timed


def _transcribe_openrouter(
    audio_path: str,
    api_key: str,
    base_url: str,
    model: str,
    progress_callback=None,
    key_path: str = "transcription.whisper_openrouter.api_key",
    raw_api_key: Any = None,
) -> str:
    """Transcribe using OpenRouter's Whisper endpoint.

    OpenRouter follows the OpenAI API shape: POST /audio/transcriptions.
    A local base URL is called without auth when no usable key is resolved.
    """
    effective_base = base_url.rstrip("/") if base_url else "https://openrouter.ai/api/v1"
    headers = _auth_headers(api_key, effective_base, key_path, raw_api_key)
    files = {"file": open(audio_path, "rb")}
    data = {"model": model}
    try:
        url = f"{effective_base}/audio/transcriptions"
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
    key_path: str = "transcription.whisper_openai.api_key",
    raw_api_key: Any = None,
) -> str | list[dict[str, float | str]]:
    """Transcribe using OpenAI's Whisper endpoint.

    If base_url is not provided, defaults to OpenAI's official endpoint.
    Supports SSE streaming for progress reporting when the endpoint supports it.
    With want_segments=True, requests verbose_json and returns timed segments,
    or an empty list when the response carries no usable timestamps. A local
    base URL is called without auth when no usable key is resolved.
    """
    effective_base = base_url.rstrip("/") if base_url else "https://api.openai.com/v1"
    headers = _auth_headers(api_key, effective_base, key_path, raw_api_key)
    url = f"{effective_base}/audio/transcriptions"
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


def _faster_whisper_available() -> bool:
    """True when the optional faster-whisper (CTranslate2) package is importable."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_backend(backend_value: Any, backend_override: str | None) -> str:
    """Resolve the local/cloud backend, preferring faster-whisper when asked to auto-pick.

    An explicit backend (config value or caller override) always wins. An unset
    or "auto" backend chooses faster_whisper_local when CTranslate2 is
    importable: it runs int8/float16 in roughly a third of the memory of the
    float32 PyTorch path. Without faster-whisper, openai-whisper is kept.
    """
    requested = backend_override or backend_value
    if isinstance(requested, str) and requested.strip() and requested.strip().lower() != "auto":
        return requested
    if _faster_whisper_available():
        logger.info(
            "transcription backend unset/auto; using faster_whisper_local (CTranslate2) "
            "because faster-whisper is available"
        )
        return "faster_whisper_local"
    logger.info(
        "transcription backend unset/auto; using whisper_local because faster-whisper "
        "is not installed"
    )
    return "whisper_local"


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
    backend = _resolve_backend(transcription_cfg.get("backend"), backend_override)

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
        cfg_key = or_cfg.get("api_key", "")
        api_key = _resolve_transcription_api_key("OPENROUTER_API_KEY", cfg_key)
        base_url = or_cfg.get("base_url", "https://openrouter.ai/api/v1")
        model = (
            model_size
            if _is_cloud_model_override(model_size)
            else or_cfg.get("model", "openai/whisper-large-v3")
        )
        return _transcribe_openrouter(
            audio_path,
            api_key,
            base_url,
            model,
            progress_callback=progress_callback,
            raw_api_key=cfg_key,
        )
    elif backend == "whisper_openai":
        oi_cfg = transcription_cfg.get("whisper_openai", {})
        cfg_key = oi_cfg.get("api_key", "")
        api_key = _resolve_transcription_api_key("OPENAI_API_KEY", cfg_key)
        base_url = oi_cfg.get("base_url", "https://api.openai.com/v1")
        model = (
            model_size if _is_cloud_model_override(model_size) else oi_cfg.get("model", "whisper-1")
        )
        return _transcribe_openai(
            audio_path,
            api_key,
            base_url,
            model,
            progress_callback=progress_callback,
            raw_api_key=cfg_key,
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
    cancel_check: Callable[[], None] | None = None,
) -> list[dict[str, float | str]]:
    """High-level transcription dispatcher returning timed segments.

    Mirrors transcribe() for backend selection. Backends without timestamp
    support return an empty list. ``cancel_check`` is polled between decoded
    segments by the local backends; the configured backend is never overridden.
    """
    cfg = config or {}
    transcription_cfg = cfg.get("transcription", {})
    backend = _resolve_backend(transcription_cfg.get("backend"), backend_override)

    if backend == "whisper_local":
        local_cfg = transcription_cfg.get("whisper_local", {})
        device_pref = local_cfg.get("device", "auto")
        language = local_cfg.get("language")
        model = model_size or local_cfg.get("model", "base")
        return _normalize_segments(
            _transcribe_whisper_local_segments(
                audio_path, model, device_pref, language=language, cancel_check=cancel_check
            )
        )
    elif backend == "faster_whisper_local":
        faster_cfg = transcription_cfg.get("faster_whisper_local", {})
        device_pref = faster_cfg.get("device", "auto")
        model = model_size or faster_cfg.get("model", "base")
        compute_type = _configured_compute_type(transcription_cfg, faster_cfg)
        language = faster_cfg.get("language")
        return _normalize_segments(
            _transcribe_faster_whisper_local_segments(
                audio_path,
                model,
                device_pref,
                compute_type=compute_type,
                language=language,
                cancel_check=cancel_check,
            )
        )
    elif backend == "whisper_openrouter":
        return []
    elif backend == "whisper_openai":
        oi_cfg = transcription_cfg.get("whisper_openai", {})
        cfg_key = oi_cfg.get("api_key", "")
        api_key = _resolve_transcription_api_key("OPENAI_API_KEY", cfg_key)
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
            raw_api_key=cfg_key,
        )
        return _normalize_segments(result)
    else:
        logger.warning("Unknown transcription backend '%s', skipping transcription", backend)
        return []
