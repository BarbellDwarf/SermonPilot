"""Library edit-apply core shared by the page and the background worker.

The Streamlit page must never run ``process_new_sermon`` inline: when the
browser session ends mid-render, Streamlit stops the script run, the ffmpeg
child is orphaned/killed, and the apply dies with the job row stuck at
``running``. This module holds the reusable apply callable so the page only
enqueues a ``JobType.AUTO_EDIT_APPLY`` job and the worker executes the same
logic outside the page lifecycle.

No Streamlit imports here. Progress flows to the caller-supplied callback
(the worker wires it to ``job.update_progress``), and completion handling
(plan status updates) happens here so the worker's own ``background_jobs``
row is the single row per apply.

Source-resolution contract (metadata.json fields):

- ``original_file`` is the full-length retained source. Apply write-backs
  (``process_new_sermon`` dry-run/upload saves with an applied edit plan)
  must preserve an existing on-disk ``original_file`` value instead of
  repointing it at the trimmed render, or the next apply resolves its own
  trimmed output and trips plan validation.
- ``processed_file`` is the latest render output and may be a trimmed cut.
  ``_resolve_apply_source`` treats a recorded render as the render base only
  when its duration matches the retained full-length original or keeper
  (within a small tolerance), so a previous cut can never become the next
  apply's source while a full-length file still exists. A render whose
  duration cannot be measured is never trusted as full length. With no
  retained full-length file at all there is nothing to compare against, so
  resolution keeps its historical best-effort order and the pipeline's
  plan-end check stays the guard.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ACTIVE_APPLY_STATUSES = ("queued", "running")

_FULL_SOURCE = "full"
_RENDER_SOURCE = "render"

_FULL_LENGTH_TOLERANCE_SECONDS = 3.0

_MEDIA_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mov",
        ".avi",
        ".webm",
        ".mkv",
        ".m4v",
        ".mp3",
        ".wav",
        ".m4a",
        ".ogg",
        ".flac",
    }
)


def _source_duration(path: str | Path) -> float | None:
    try:
        from sermon_updater import _ffprobe_duration
    except Exception:
        return None
    try:
        return _ffprobe_duration(path)
    except Exception:
        return None


def _candidate_covers_plan(path: str | Path, min_duration: float | None) -> bool:
    if min_duration is None:
        return True
    try:
        duration = _source_duration(path)
    except Exception:
        return True
    if duration is None:
        return True
    return float(min_duration) <= float(duration) + 1.0


def _candidate_is_full_length(path: str | Path, reference_duration: float | None) -> bool:
    """True when a candidate spans the whole service, not a previous cut.

    The retained full-length original or keeper supplies the reference. A
    candidate whose duration cannot be measured is never trusted, and neither
    is one materially shorter than the reference.
    """
    duration = _source_duration(path)
    if duration is None or reference_duration is None:
        return False
    return (
        abs(float(duration) - float(reference_duration))
        <= _FULL_LENGTH_TOLERANCE_SECONDS
    )


def config_enhancement_enabled(config: dict[str, Any] | None) -> bool:
    """Whether app settings ask for audio enhancement.

    ``audio_enhancement_method == "none"`` means skip, and it wins over the
    legacy ``metadata_processing.process_audio`` boolean, matching the fresh-run
    path where the method also decides. When the two disagree the log names the
    winner once per resolution. Absent settings mean enhancement is on, the
    pipeline default, so an apply never reads silence as "skip".
    """
    cfg = config or {}
    method = cfg.get("audio_enhancement_method")
    none_method = isinstance(method, str) and method.strip().lower() == "none"
    metadata = cfg.get("metadata_processing")
    if isinstance(metadata, dict) and "process_audio" in metadata:
        legacy = bool(metadata.get("process_audio"))
        if none_method:
            if legacy:
                logger.info(
                    "Apply settings: audio_enhancement_method=none wins over legacy "
                    "metadata_processing.process_audio=true; audio enhancement is skipped"
                )
            return False
        return legacy
    if none_method:
        return False
    return True


def plan_enhancement(plan: dict[str, Any] | None) -> bool | None:
    """The enhancement flag a plan recorded, or None when it recorded none."""
    if not isinstance(plan, dict):
        return None
    actions = plan.get("actions")
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except (json.JSONDecodeError, TypeError):
            actions = None
    if isinstance(actions, dict) and "enhance_audio" in actions:
        return bool(actions.get("enhance_audio"))
    return None


def resolve_enhancement(
    config: dict[str, Any] | None,
    request_value: bool | None = None,
    plan: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Resolve the enhancement action from request, then plan, then settings.

    Silence is never consent to skip: when no layer states a preference the app
    config decides, and its default is on.
    """
    if request_value is not None:
        return bool(request_value), "request"
    plan_value = plan_enhancement(plan)
    if plan_value is not None:
        return plan_value, "plan"
    return config_enhancement_enabled(config), "settings"


def enhancement_run_message(reason: str) -> str:
    return f"Running audio enhancement (requested by {reason})"


def enhancement_skip_message(reason: str) -> str:
    detail = {
        "request": "request turned it off",
        "plan": "plan turned it off",
        "settings": "settings have it off",
    }.get(reason, "not requested")
    return f"Skipping audio enhancement (not requested; {detail})"


def _matches_apply_source(
    enhanced_path: str | Path,
    media_path: str | Path,
    metadata: dict[str, Any] | None,
) -> bool:
    """True when a retained enhancement came from the media the apply renders."""
    try:
        media = Path(str(media_path)).resolve()
    except OSError:
        return False
    recorded: list[Path] = []
    if isinstance(metadata, dict):
        for key in ("original_file", "keeper_file"):
            value = metadata.get(key)
            if value:
                try:
                    recorded.append(Path(str(value)).resolve())
                except OSError:
                    continue
    if recorded:
        return media in recorded
    try:
        return Path(str(enhanced_path)).resolve().parent == media.parent
    except OSError:
        return False


def _enhanced_artifact_usable(
    enhanced_path: str | None,
    media_path: str | Path,
    metadata: dict[str, Any] | None,
    min_duration: float | None,
) -> bool:
    """A retained enhancement is reusable only if present, current and matched."""
    if not enhanced_path:
        return False
    candidate = Path(str(enhanced_path))
    try:
        if not candidate.exists():
            return False
    except OSError:
        return False
    if not _candidate_covers_plan(candidate, min_duration):
        return False
    return _matches_apply_source(candidate, media_path, metadata)


def _select_enhanced_artifact(
    media_path: str,
    source_is_enhanced: bool,
    enhanced_path: str | None,
    metadata: dict[str, Any] | None,
    min_duration: float | None,
) -> str | None:
    """The enhanced material the apply can reuse, or None to run enhancement.

    A processed source already carries the enhanced audio, so it counts as
    reusable. A retained ``enhanced_file`` counts only when it exists, covers
    the approved plan, and came from the same source.
    """
    if source_is_enhanced:
        return media_path
    if _enhanced_artifact_usable(enhanced_path, media_path, metadata, min_duration):
        return str(enhanced_path)
    return None


def build_apply_job_params(
    sermon_id: str,
    plan_id: int | None,
    plan_revision: int | None,
    start: float,
    end: float,
    audio_offset: float = 0.0,
    render_only: bool = False,
    re_detect: bool = False,
    config: dict[str, Any] | None = None,
    enhance_audio: bool | None = None,
) -> dict[str, Any]:
    mode = "render_only" if render_only else "upload"
    return {
        "sermon_id": str(sermon_id),
        "plan_id": plan_id,
        "plan_revision": plan_revision,
        "start": float(start),
        "end": float(end),
        "audio_offset": float(audio_offset or 0.0),
        "render_only": bool(render_only),
        "mode": mode,
        "re_detect": bool(re_detect),
        "config": config or {},
        "enhance_audio": enhance_audio,
    }


def get_active_apply_job(
    repo: Any, sermon_id: str, plan_revision: int | None = None
) -> dict[str, Any] | None:
    """Newest queued/running apply for a sermon, whatever its plan revision.

    ``plan_revision`` is accepted for call-site compatibility but never
    filters: an apply started from a superseded revision still occupies the
    sermon (same source media and output paths), so it must block a re-apply
    of the current revision and vice versa.
    """
    try:
        rows = repo.get_apply_jobs_by_status("auto_edit_apply", list(ACTIVE_APPLY_STATUSES))
    except Exception:
        return None
    for row in rows:
        try:
            params = json.loads(row.get("parameters") or "{}")
        except (json.JSONDecodeError, TypeError):
            params = {}
        if str(params.get("sermon_id") or "") != str(sermon_id):
            continue
        return row
    return None


def _read_edit_plan_metadata(sermon: dict[str, Any]) -> dict[str, Any]:
    file_paths = sermon.get("file_paths") or {}
    metadata_path = file_paths.get("metadata") or ""
    if metadata_path and Path(metadata_path).exists():
        try:
            return json.loads(Path(metadata_path).read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            pass
    return {}


_AUTO_EDIT_PREF_KEYS = ("logo_path", "logo_hold", "fade_to_black", "fade_out_tail_seconds")


def _merge_auto_edit_prefs(
    config: dict[str, Any] | None, metadata: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Overlay per-sermon ending-card prefs (metadata['auto_edit']) onto the render config."""
    prefs = metadata.get("auto_edit") if isinstance(metadata, dict) else None
    if not isinstance(prefs, dict) or not prefs:
        return config
    merged = dict(config) if config else {}
    auto_cfg = dict(merged.get("auto_edit") or {})
    for key in _AUTO_EDIT_PREF_KEYS:
        if key in prefs:
            auto_cfg[key] = prefs[key]
    merged["auto_edit"] = auto_cfg
    return merged


def _full_sermon_or_none(sermon: dict[str, Any], repo: Any) -> dict[str, Any] | None:
    try:
        return repo.get_sermon(sermon.get("id") or sermon.get("sermon_id"))
    except Exception:
        return None


def _resolve_edit_media_path(sermon: dict[str, Any], repo: Any) -> str | None:
    candidates: list[Path] = []
    metadata = _read_edit_plan_metadata(sermon)
    for key in ("original_file", "processed_file"):
        value = metadata.get(key)
        if value:
            candidates.append(Path(str(value)))
    for source in (sermon, _full_sermon_or_none(sermon, repo)):
        if not isinstance(source, dict):
            continue
        file_paths = source.get("file_paths") or {}
        for key in ("original_audio", "original_video", "audio"):
            value = file_paths.get(key)
            if value:
                candidates.append(Path(value))
    for candidate in candidates:
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            continue
    return None


def _looks_like_processed_artifact(value: str) -> bool:
    stem = Path(str(value)).stem.lower()
    return "processed" in stem and "_keeper" not in stem


def _resolve_apply_source(
    sermon: dict[str, Any], repo: Any, min_duration: float | None = None
) -> tuple[str | None, bool]:
    full = _full_sermon_or_none(sermon, repo)
    ordered: list[tuple[str, bool, str]] = []
    for source in (sermon, full):
        if not isinstance(source, dict):
            continue
        metadata = _read_edit_plan_metadata(source)
        processed = metadata.get("processed_file")
        if processed:
            path = Path(str(processed))
            if path.exists():
                ordered.append((str(path), True, _RENDER_SOURCE))
    for source in (full, sermon):
        if not isinstance(source, dict):
            continue
        audio = (source.get("file_paths") or {}).get("audio") or ""
        if audio and _looks_like_processed_artifact(audio) and Path(str(audio)).exists():
            ordered.append((str(audio), True, _RENDER_SOURCE))
    for source in (sermon, full):
        if not isinstance(source, dict):
            continue
        metadata = _read_edit_plan_metadata(source)
        for key in ("original_file", "keeper_file"):
            value = metadata.get(key)
            if value:
                path = Path(str(value))
                if path.exists():
                    ordered.append((str(path), False, _FULL_SOURCE))
        file_paths = source.get("file_paths") or {}
        for key in ("original_audio", "original_video", "keeper_audio", "keeper", "audio"):
            value = file_paths.get(key)
            if value and Path(str(value)).exists():
                ordered.append((str(value), False, _FULL_SOURCE))
    for source in (sermon, full):
        if not isinstance(source, dict):
            continue
        metadata_path = (source.get("file_paths") or {}).get("metadata") or ""
        parent = Path(str(metadata_path)).parent if metadata_path else None
        if parent is None or not parent.exists():
            continue
        try:
            originals = sorted(
                p
                for p in parent.glob("*Original*")
                if p.is_file() and p.suffix.lower() in _MEDIA_EXTENSIONS
            )
        except OSError:
            continue
        for original in originals:
            ordered.append((str(original), False, _FULL_SOURCE))
    seen: set[str] = set()
    deduped: list[tuple[str, bool, str]] = []
    for path, enhanced, role in ordered:
        if path not in seen:
            seen.add(path)
            deduped.append((path, enhanced, role))
    full_paths = [path for path, _enhanced, role in deduped if role == _FULL_SOURCE]
    reference_duration: float | None = None
    for path in full_paths:
        duration = _source_duration(path)
        if duration is not None and (
            reference_duration is None or duration > reference_duration
        ):
            reference_duration = float(duration)
    for path, enhanced, role in deduped:
        if not _candidate_covers_plan(path, min_duration):
            continue
        if role == _FULL_SOURCE:
            return path, enhanced
        if not full_paths or _candidate_is_full_length(path, reference_duration):
            return path, enhanced
    for path, enhanced, role in deduped:
        if role == _FULL_SOURCE:
            return path, enhanced
    if deduped:
        return deduped[0][0], deduped[0][1]
    media_path = _resolve_edit_media_path(sermon, repo)
    return media_path, False


def _build_apply_kwargs(
    full_sermon: dict[str, Any],
    media_path: str,
    plan_file: str | None,
    render_only: bool,
    audio_offset: float,
    skip_audio: bool = False,
    config: dict[str, Any] | None = None,
    existing_sermon_id: str | None = None,
    stored_metadata: dict[str, Any] | None = None,
    reuse_transcript: str | None = None,
    reuse_transcript_segments: list | None = None,
    enhanced_audio_file: str | None = None,
    require_enhancement: bool = False,
    keeper_prepared: bool = False,
) -> dict[str, Any]:
    stored = stored_metadata or {}

    def _pick(*values: Any) -> Any:
        for value in values:
            if value:
                return value
        return None

    kwargs: dict[str, Any] = {
        "audio_file": media_path,
        "speaker_name": full_sermon.get("speaker") or "Unknown",
        "recorded_date": full_sermon.get("recorded_date") or datetime.now().strftime("%Y-%m-%d"),
        "event_type": full_sermon.get("event_type") or "Sunday Service",
        "title": _pick(stored.get("title"), full_sermon.get("title")),
        "subtitle": _pick(stored.get("subtitle"), full_sermon.get("subtitle")),
        "series_title": _pick(stored.get("series_title"), full_sermon.get("series_title")),
        "bible_text": _pick(
            stored.get("bible_text"),
            full_sermon.get("bible_text"),
            full_sermon.get("scripture_reference"),
        ),
        "description": _pick(stored.get("description")),
        "hashtags": _pick(stored.get("hashtags")),
        "auto_edit_mode": "auto",
        "edit_plan_file": plan_file,
        "audio_offset": audio_offset,
        "dry_run": render_only,
        "skip_audio": skip_audio,
    }
    if existing_sermon_id:
        kwargs["existing_sermon_id"] = str(existing_sermon_id)
    # A render that reuses the stored description must not clear the record's
    # review flag; only a fresh generation may change it.
    kwargs["existing_description_needs_review"] = bool(
        full_sermon.get("description_needs_review")
    )
    if config:
        kwargs["config"] = config
    if enhanced_audio_file:
        kwargs["enhanced_audio_file"] = str(enhanced_audio_file)
    if require_enhancement:
        kwargs["require_enhancement"] = True
    if keeper_prepared:
        kwargs["keeper_prepared"] = True
    if reuse_transcript is not None:
        kwargs["reuse_transcript"] = reuse_transcript
        kwargs["reuse_transcript_segments"] = list(reuse_transcript_segments or [])
    return kwargs


def _write_edit_plan_file(
    plan_id: Any, start: float, end: float, audio_offset: float = 0.0
) -> str | None:
    payload = {
        "start": float(start),
        "end": float(end),
        "audio_offset": float(audio_offset),
        "confidence": 1.0,
        "needs_review": False,
        "evidence": "approved in Library edit-review panel",
        "qa_judgment": "approved",
    }
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix=f"edit_plan_{plan_id}_", delete=False
        )
        with handle as f:
            json.dump(payload, f)
        return handle.name
    except OSError as e:
        logger.error("Could not write edit plan file: %s", e)
        return None


def _find_plan(repo: Any, sermon_id: str, plan_id: Any) -> dict[str, Any] | None:
    try:
        history = repo.get_edit_plan_history(sermon_id)
    except Exception:
        history = []
    for row in history:
        if plan_id is not None and row.get("id") == plan_id:
            return row
    try:
        return repo.get_current_edit_plan(sermon_id)
    except Exception:
        return None


def _find_retained_artifact(
    sermon: dict[str, Any],
    repo: Any,
    metadata_keys: tuple[str, ...],
    file_keys: tuple[str, ...],
) -> str | None:
    """First existing review artifact named by metadata or file rows."""
    for source in (sermon, _full_sermon_or_none(sermon, repo)):
        if not isinstance(source, dict):
            continue
        metadata = _read_edit_plan_metadata(source)
        for key in metadata_keys:
            value = metadata.get(key)
            if value and Path(str(value)).exists():
                return str(value)
        file_paths = source.get("file_paths") or {}
        for key in file_keys:
            value = file_paths.get(key)
            if value and Path(str(value)).exists():
                return str(value)
    return None


def _retained_keeper(sermon: dict[str, Any], repo: Any) -> str | None:
    """Compact full-length video retained by the review pass, if any."""
    return _find_retained_artifact(
        sermon, repo, ("keeper_file",), ("keeper_audio", "keeper")
    )


def _retained_enhanced(sermon: dict[str, Any], repo: Any) -> str | None:
    """Enhanced audio retained by the review pass, if any."""
    return _find_retained_artifact(
        sermon, repo, ("enhanced_file",), ("enhanced_audio",)
    )


def _stored_apply_metadata(
    full_sermon: dict[str, Any], review_metadata: dict[str, Any]
) -> dict[str, Any]:
    """Metadata the apply render reuses verbatim.

    Operator authority rule: when the console saved a title or description
    (``sermons.metadata_edited_at`` is set), the live row wins over the
    metadata.json snapshot the review pass wrote. Otherwise the snapshot stays
    first so an untouched review keeps the exact metadata it was approved with.
    """
    content = full_sermon.get("content") or {}
    operator_edited = bool(full_sermon.get("metadata_edited_at"))

    def _pick(*values: Any) -> Any:
        for value in values:
            if value:
                return value
        return None

    if operator_edited:
        title_sources = (full_sermon.get("title"), review_metadata.get("title"))
        description_sources = (
            full_sermon.get("description"),
            content.get("description"),
            review_metadata.get("description"),
        )
    else:
        title_sources = (review_metadata.get("title"), full_sermon.get("title"))
        description_sources = (
            review_metadata.get("description"),
            full_sermon.get("description"),
            content.get("description"),
        )

    return {
        "title": _pick(*title_sources),
        "description": _pick(*description_sources),
        "hashtags": _pick(review_metadata.get("hashtags"), content.get("hashtags")),
        "subtitle": _pick(review_metadata.get("subtitle"), full_sermon.get("subtitle")),
        "bible_text": _pick(
            review_metadata.get("bible_text"),
            full_sermon.get("bible_text"),
            full_sermon.get("scripture_reference"),
        ),
        "series_title": _pick(full_sermon.get("series_title")),
    }


def _retained_transcript(
    full_sermon: dict[str, Any], review_metadata: dict[str, Any]
) -> tuple[str | None, list]:
    """Transcript text and segments retained by the review pass."""
    content = full_sermon.get("content") or {}
    text = content.get("transcript_text")
    transcript_file = review_metadata.get("transcript_file")
    if not text and transcript_file and Path(str(transcript_file)).exists():
        try:
            text = Path(str(transcript_file)).read_text(encoding="utf-8")
        except OSError:
            text = None
    segments: list = []
    timestamps_file = review_metadata.get("transcript_timestamps_file")
    if timestamps_file and Path(str(timestamps_file)).exists():
        try:
            loaded = json.loads(Path(str(timestamps_file)).read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                segments = loaded
        except (json.JSONDecodeError, OSError):
            segments = []
    return text, segments


def _log_reuse_lines(
    media_path: str,
    source_is_enhanced: bool,
    keeper_path: str | None,
    enhanced_path: str | None,
    reuse_transcript: str | None,
    stored_metadata: dict[str, Any],
) -> None:
    """Name every retained artifact the apply reuses, and every empty field."""
    if source_is_enhanced:
        logger.info(
            "Apply reuses retained processed media %s; it already carries "
            "enhanced audio",
            media_path,
        )
    if keeper_path:
        logger.info("Apply found retained keeper %s", keeper_path)
    if enhanced_path:
        logger.info("Apply found retained enhanced audio %s", enhanced_path)
    if reuse_transcript is not None:
        logger.info(
            "Apply reuses retained transcript (%d characters); no model call",
            len(reuse_transcript),
        )
    for field in ("title", "description", "hashtags"):
        if not stored_metadata.get(field):
            logger.info(
                "Apply metadata field %r is empty; it will be generated", field
            )


_REUSE_POINTER_KEYS = (
    "keeper_file",
    "enhanced_file",
    "transcript_file",
    "transcript_timestamps_file",
)


def _persist_reuse_pointers(output_dir: Any, metadata: dict[str, Any]) -> None:
    """Carry retained-artifact pointers into a render's metadata for the next apply.

    A render writes a fresh metadata.json that drops the review pointers, so a
    later re-edit would resolve its own trimmed output and re-run every stage.
    Copying the still-existing pointers forward keeps the retained original,
    keeper, enhanced audio and transcript reachable.
    """
    if not output_dir or not isinstance(metadata, dict):
        return
    pointers = {
        key: str(metadata[key])
        for key in _REUSE_POINTER_KEYS
        if metadata.get(key) and Path(str(metadata[key])).exists()
    }
    if not pointers:
        return
    meta_path = Path(str(output_dir)) / "metadata.json"
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        if all(data.get(key) for key in pointers):
            return
        data.update(pointers)
        meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not persist retained pointers to %s: %s", meta_path, exc)


def _review_dir_for_sermon(sermon_id: str, repo: Any) -> Path | None:
    """Review directory recorded for a sermon, or None when it has none."""
    try:
        from src.review_media import review_dir_for_sermon

        return review_dir_for_sermon(sermon_id, repo)
    except Exception as exc:
        logger.warning("Could not locate review media for %s: %s", sermon_id, exc)
        return None


def _set_edit_status(repo: Any, sermon_id: str, status: str) -> None:
    """Advance the sermon's edit lifecycle, never failing the apply over it."""
    try:
        repo.update_sermon_edit_status(sermon_id, status)
    except Exception as exc:
        logger.warning("Could not set edit_status=%s for %s: %s", status, sermon_id, exc)


def _finalize_review_dir(review_dir: Path | None, outcome: str) -> None:
    """Release retained review media; safe to call more than once."""
    if review_dir is None:
        return
    try:
        from src.review_media import finalize_review_media

        finalize_review_media(review_dir, outcome)
    except Exception as exc:
        logger.warning("Could not finalize review media %s: %s", review_dir, exc)


def _emit_enhancement_decision(
    progress_callback: Callable[[float, str], None] | None, message: str
) -> None:
    """Put the enhancement decision and its reason in the operator's log."""
    logger.info("Apply enhancement decision: %s", message)
    if progress_callback is not None:
        try:
            progress_callback(20, message)
        except Exception:
            pass


def run_library_apply(
    repo: Any,
    sermon_id: str,
    start: float,
    end: float,
    audio_offset: float = 0.0,
    render_only: bool = False,
    re_detect: bool = False,
    plan_id: Any = None,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    cancel_log: Callable[[str], None] | None = None,
    config: dict[str, Any] | None = None,
    enhance_audio: bool | None = None,
) -> dict[str, Any]:
    sermon_id = str(sermon_id or "")
    plan = _find_plan(repo, sermon_id, plan_id)
    if plan is None:
        return {"success": False, "error": f"No edit plan found for {sermon_id}"}
    plan_id = plan.get("id", plan_id)

    plan_file = None
    if not re_detect:
        plan_file = _write_edit_plan_file(plan_id, start, end, audio_offset)
        if not plan_file:
            return {"success": False, "error": "Could not write edit plan file"}

    try:
        sermon = repo.get_sermon(sermon_id) or {"id": sermon_id}
    except Exception:
        sermon = {"id": sermon_id}
    full_sermon = _full_sermon_or_none(sermon, repo) or sermon
    metadata = _read_edit_plan_metadata(full_sermon)
    review_dir = _review_dir_for_sermon(sermon_id, repo)
    stored_metadata = _stored_apply_metadata(full_sermon, metadata)
    reuse_transcript, reuse_transcript_segments = _retained_transcript(
        full_sermon, metadata
    )
    keeper_path = _retained_keeper(full_sermon, repo)
    enhanced_path = _retained_enhanced(full_sermon, repo)
    config = _merge_auto_edit_prefs(config, metadata)
    media_path, source_is_enhanced = _resolve_apply_source(
        full_sermon, repo, min_duration=float(end)
    )
    if not media_path:
        if plan_file:
            Path(plan_file).unlink(missing_ok=True)
        return {
            "success": False,
            "error": "Original media file not found locally. Cannot apply the edit.",
        }
    keeper_used = False
    if keeper_path and not source_is_enhanced:
        # The review pass already transcoded and retained the compact
        # full-length base; apply from it instead of re-transcoding the raw
        # source. The keeper is not enhanced, so it does not decide the
        # enhancement step.
        media_path = keeper_path
        keeper_used = True

    if plan_file is not None:
        source_duration = _source_duration(media_path)
        if source_duration is not None and float(end) > float(source_duration) + 1.0:
            Path(plan_file).unlink(missing_ok=True)
            return {
                "success": False,
                "sermon_id": None,
                "edit_plan_status": None,
                "auto_edit_applied": False,
                "error": (
                    f"Approved edit plan end {float(end):.1f}s exceeds source duration "
                    f"{float(source_duration):.1f}s for {media_path}; nothing was rendered."
                ),
            }

    enhance, reason = resolve_enhancement(config, request_value=enhance_audio, plan=plan)
    enhanced_input = (
        _select_enhanced_artifact(
            media_path,
            source_is_enhanced,
            enhanced_path,
            metadata,
            float(end),
        )
        if enhance
        else None
    )
    run_enhancement = enhance and enhanced_input is None
    skip_audio = not run_enhancement
    if run_enhancement:
        _emit_enhancement_decision(
            progress_callback, enhancement_run_message(reason)
        )
    elif enhance:
        _emit_enhancement_decision(
            progress_callback,
            f"Reusing retained enhancement ({Path(str(enhanced_input)).name}, full length)",
        )
    else:
        _emit_enhancement_decision(
            progress_callback, enhancement_skip_message(reason)
        )

    _log_reuse_lines(
        media_path,
        source_is_enhanced,
        keeper_path,
        enhanced_path,
        reuse_transcript,
        stored_metadata,
    )

    import sermon_updater

    apply_kwargs = _build_apply_kwargs(
        full_sermon,
        media_path,
        plan_file,
        bool(render_only),
        float(audio_offset or 0.0),
        skip_audio=skip_audio,
        config=config,
        existing_sermon_id=sermon_id,
        stored_metadata=stored_metadata,
        reuse_transcript=reuse_transcript,
        reuse_transcript_segments=reuse_transcript_segments,
        enhanced_audio_file=enhanced_input,
        require_enhancement=run_enhancement,
        keeper_prepared=keeper_used,
    )
    if progress_callback is not None:
        apply_kwargs["progress_callback"] = progress_callback
    if cancel_check is not None:
        apply_kwargs["cancel_check"] = cancel_check
    if cancel_log is not None:
        apply_kwargs["cancel_log"] = cancel_log

    _set_edit_status(repo, sermon_id, "applied")
    try:
        result = sermon_updater.process_new_sermon(**apply_kwargs)
    except Exception as e:
        logger.exception("Library apply failed for %s", sermon_id)
        _set_edit_status(repo, sermon_id, "failed")
        _finalize_review_dir(review_dir, "failed")
        return {"success": False, "error": str(e)}
    finally:
        if plan_file:
            Path(plan_file).unlink(missing_ok=True)

    if result.get("success"):
        _persist_reuse_pointers(result.get("output_dir"), metadata)

    if bool(render_only) and result.get("success"):
        if result.get("auto_edit_applied") is True and result.get("edit_plan_status") in (
            "auto_applied",
            "applied_local",
        ):
            rendered_id = str(result.get("sermon_id") or "")
            try:
                repo.update_edit_plan_status(
                    plan.get("id"),
                    "applied_local",
                    notes=((plan.get("notes") or "") + "; rendered locally, not uploaded").strip(
                        "; "
                    ),
                    applied_media_id=rendered_id,
                )
            except Exception as e:
                logger.warning("Could not mark plan applied_local: %s", e)
            _set_edit_status(repo, sermon_id, "rendered")
            _finalize_review_dir(review_dir, "approved")
            return result
        _set_edit_status(repo, sermon_id, "failed")
        _finalize_review_dir(review_dir, "failed")
        return {
            "success": False,
            "sermon_id": result.get("sermon_id"),
            "edit_plan_status": result.get("edit_plan_status"),
            "auto_edit_applied": False,
            "output_dir": result.get("output_dir"),
            "error": (
                "Pipeline returned "
                f"{result.get('edit_plan_status') or 'no status'} for the approved plan "
                f"(end {float(end):.1f}s); nothing was rendered."
            ),
        }
    if (
        plan_file is not None
        and not result.get("cancelled")
        and result.get("success")
        and result.get("edit_plan_status") == "pending_review"
    ):
        _set_edit_status(repo, sermon_id, "failed")
        _finalize_review_dir(review_dir, "failed")
        return {
            "success": False,
            "sermon_id": result.get("sermon_id"),
            "edit_plan_status": result.get("edit_plan_status"),
            "auto_edit_applied": False,
            "output_dir": result.get("output_dir"),
            "error": (
                "Pipeline returned pending_review for the approved plan "
                f"(end {float(end):.1f}s); nothing was rendered."
            ),
        }
    if result.get("success") and result.get("auto_edit_applied"):
        _set_edit_status(repo, result.get("sermon_id") or sermon_id, "uploaded")
        _finalize_review_dir(review_dir, "approved")
    elif not result.get("success") and not result.get("cancelled"):
        _set_edit_status(repo, sermon_id, "failed")
        _finalize_review_dir(review_dir, "failed")
    return result
