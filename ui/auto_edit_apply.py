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
  ``_resolve_apply_source`` must skip any candidate whose duration is
  shorter than the approved plan end (``min_duration``) so a poisoned
  ``processed_file`` pointer can never become the next apply's source while
  the retained full-length file still exists.
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
    }


def get_active_apply_job(
    repo: Any, sermon_id: str, plan_revision: int | None = None
) -> dict[str, Any] | None:
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
        if plan_revision is not None and params.get("plan_revision") is not None:
            try:
                if int(params.get("plan_revision")) != int(plan_revision):
                    continue
            except (TypeError, ValueError):
                pass
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
    ordered: list[tuple[str, bool]] = []
    for source in (sermon, full):
        if not isinstance(source, dict):
            continue
        metadata = _read_edit_plan_metadata(source)
        processed = metadata.get("processed_file")
        if processed:
            path = Path(str(processed))
            if path.exists():
                ordered.append((str(path), True))
    for source in (full, sermon):
        if not isinstance(source, dict):
            continue
        audio = (source.get("file_paths") or {}).get("audio") or ""
        if audio and _looks_like_processed_artifact(audio) and Path(str(audio)).exists():
            ordered.append((str(audio), True))
    for source in (sermon, full):
        if not isinstance(source, dict):
            continue
        metadata = _read_edit_plan_metadata(source)
        original = metadata.get("original_file")
        if original:
            path = Path(str(original))
            if path.exists():
                ordered.append((str(path), False))
        file_paths = source.get("file_paths") or {}
        for key in ("original_audio", "original_video", "audio"):
            value = file_paths.get(key)
            if value and Path(str(value)).exists():
                ordered.append((str(value), False))
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
            ordered.append((str(original), False))
    seen: set[str] = set()
    deduped: list[tuple[str, bool]] = []
    for path, enhanced in ordered:
        if path not in seen:
            seen.add(path)
            deduped.append((path, enhanced))
    for path, enhanced in deduped:
        if _candidate_covers_plan(path, min_duration):
            return path, enhanced
    if deduped:
        return deduped[0]
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
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "audio_file": media_path,
        "speaker_name": full_sermon.get("speaker") or "Unknown",
        "recorded_date": full_sermon.get("recorded_date") or datetime.now().strftime("%Y-%m-%d"),
        "event_type": full_sermon.get("event_type") or "Sunday Service",
        "title": full_sermon.get("title") or None,
        "series_title": full_sermon.get("series_title") or None,
        "auto_edit_mode": "auto",
        "edit_plan_file": plan_file,
        "audio_offset": audio_offset,
        "dry_run": render_only,
        "skip_audio": skip_audio,
    }
    if config:
        kwargs["config"] = config
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
    config: dict[str, Any] | None = None,
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
    media_path, already_enhanced = _resolve_apply_source(full_sermon, repo, min_duration=float(end))
    if not media_path:
        if plan_file:
            Path(plan_file).unlink(missing_ok=True)
        return {
            "success": False,
            "error": "Original media file not found locally. Cannot apply the edit.",
        }

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

    import sermon_updater

    apply_kwargs = _build_apply_kwargs(
        full_sermon,
        media_path,
        plan_file,
        bool(render_only),
        float(audio_offset or 0.0),
        skip_audio=already_enhanced,
        config=config,
    )
    if progress_callback is not None:
        apply_kwargs["progress_callback"] = progress_callback
    if cancel_check is not None:
        apply_kwargs["cancel_check"] = cancel_check

    try:
        result = sermon_updater.process_new_sermon(**apply_kwargs)
    except Exception as e:
        logger.exception("Library apply failed for %s", sermon_id)
        return {"success": False, "error": str(e)}
    finally:
        if plan_file:
            Path(plan_file).unlink(missing_ok=True)

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
            return result
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
    return result
