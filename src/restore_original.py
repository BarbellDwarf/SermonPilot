"""Restore a sermon's original recording after an auto-edit was applied."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
_PLAYABLE_EXTENSIONS = frozenset({".mp4", ".m4v", ".webm", ".mp3", ".wav", ".m4a", ".ogg"})


class RestoreOriginalError(Exception):
    """The original recording could not be resolved or written."""


def _is_file(value: str | Path | None) -> bool:
    if not value:
        return False
    try:
        return Path(value).is_file()
    except OSError:
        return False


def _read_metadata(path: Path | None) -> dict[str, Any]:
    if path is None or not _is_file(path):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _file_rows(sermon_id: str, repo: Any) -> dict[str, str]:
    rows = repo.get_sermon_files(sermon_id)
    return {
        str(row.get("file_type")): str(row.get("file_path"))
        for row in rows
        if row.get("file_type") and row.get("file_path")
    }


def _siblings_named(anchor: str | Path | None, needle: str) -> list[Path]:
    if not anchor:
        return []
    try:
        directory = Path(anchor).parent
        if not directory.is_dir():
            return []
    except OSError:
        return []
    found: list[Path] = []
    try:
        for candidate in sorted(directory.iterdir()):
            if (
                candidate.is_file()
                and needle in candidate.name.lower()
                and candidate.suffix.lower() in _MEDIA_EXTENSIONS
            ):
                found.append(candidate)
    except OSError:
        return []
    return found


def _resolve_original(
    metadata: dict[str, Any],
    files: dict[str, str],
    plan: dict[str, Any],
    metadata_path: Path | None,
) -> Path:
    direct = [
        metadata.get("original_file"),
        files.get("original_video"),
        files.get("original_audio"),
        plan.get("source_path"),
    ]
    for value in direct:
        if _is_file(value):
            return Path(str(value))

    anchors = [
        metadata_path,
        files.get("audio"),
        files.get("processed_audio"),
        files.get("preview"),
        metadata.get("original_file"),
        metadata.get("processed_file"),
    ]
    for anchor in anchors:
        for candidate in _siblings_named(anchor, "original"):
            return candidate
    raise RestoreOriginalError("No original recording was found for this teaching.")


def _same_length(original: Path, preview: Path) -> bool:
    try:
        from sermon_updater import _ffprobe_duration

        first = _ffprobe_duration(original)
        second = _ffprobe_duration(preview)
    except Exception:
        return True
    if not first or not second:
        return True
    return abs(float(first) - float(second)) <= 3.0


def _resolve_preview(
    original: Path,
    metadata: dict[str, Any],
    files: dict[str, str],
) -> Path | None:
    direct = [files.get("preview"), metadata.get("preview_file")]
    for value in direct:
        if _is_file(value):
            candidate = Path(str(value))
            if _same_length(original, candidate):
                return candidate
    for anchor in (original, files.get("audio"), files.get("processed_audio")):
        for candidate in _siblings_named(anchor, "preview"):
            if candidate.suffix.lower() == ".mp4" and _same_length(original, candidate):
                return candidate
    return None


def _write_metadata(path: Path, original: Path, preview: Path | None) -> None:
    data = _read_metadata(path)
    data["original_file"] = str(original)
    data.pop("processed_file", None)
    if preview is not None:
        data["preview_file"] = str(preview)
    else:
        data.pop("preview_file", None)
    tmp = path.with_suffix(path.suffix + ".restore")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RestoreOriginalError(f"Could not rewrite {path.name}: {exc}") from exc


def _repoint_files(
    sermon_id: str, repo: Any, playback: Path, preview: Path | None
) -> None:
    try:
        size = playback.stat().st_size
    except OSError:
        size = None
    with repo.db.get_connection() as conn:
        conn.execute(
            "DELETE FROM sermon_files WHERE sermon_id = ? "
            "AND file_type IN ('processed', 'processed_audio', 'preview')",
            (sermon_id,),
        )
        for kind, path in (("audio", playback), ("preview", preview)):
            if path is None:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO sermon_files (sermon_id, file_type, file_path, file_size) "
                "VALUES (?, ?, ?, ?)",
                (sermon_id, kind, str(path), size),
            )
        conn.commit()


def restore_original(sermon_id: str, repo: Any) -> dict[str, Any]:
    """Point a sermon back at its unedited recording and reset the plan.

    The original media file and any browser preview are left in place; only
    the database pointers, the review metadata, and the current plan change.
    """
    sermon = repo.get_sermon(sermon_id)
    if not sermon:
        raise RestoreOriginalError("This teaching is not in the library.")
    plan = repo.get_current_edit_plan(sermon_id) or {}
    files = _file_rows(sermon_id, repo)
    metadata_path = Path(files["metadata"]) if files.get("metadata") else None
    metadata = _read_metadata(metadata_path)

    original = _resolve_original(metadata, files, plan, metadata_path)
    preview = _resolve_preview(original, metadata, files)
    playback = preview or original

    if metadata_path is not None:
        _write_metadata(metadata_path, original, preview)
    _repoint_files(sermon_id, repo, playback, preview)

    duration = float(sermon.get("duration") or 0.0)
    if duration <= 0:
        try:
            from sermon_updater import _ffprobe_duration

            duration = float(_ffprobe_duration(original) or 0.0)
        except Exception:
            duration = 0.0

    actions = plan.get("actions")
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except (json.JSONDecodeError, TypeError):
            actions = None

    repo.save_edit_plan_revision(
        sermon_id,
        {
            "proposed_start": 0.0,
            "proposed_end": duration,
            "final_start": 0.0,
            "final_end": duration,
            "audio_offset": 0.0,
            "remove_segments": [],
            "confidence": 1.0,
            "needs_review": False,
            "evidence": "Original recording restored",
            "qa_judgment": "restored",
            "reasoning": "The operator restored the unedited recording.",
            "detection_status": "ok",
            "status": "draft",
            "source_path": str(original),
            "notes": "Restored original recording",
            "actions": actions,
        },
    )
    repo.update_sermon_edit_status(sermon_id, "draft")

    info = sermon.get("upload_info") or {}
    remote_id = str(info.get("sermonaudio_id") or "")
    published = bool(remote_id) or sermon.get("status") == "processed"
    if not remote_id and published:
        remote_id = sermon_id

    return {
        "original_path": str(original),
        "playback_path": str(playback),
        "preview_path": str(preview) if preview is not None else None,
        "duration": duration,
        "published": published,
        "remote_id": remote_id,
    }
