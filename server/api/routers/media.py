"""Media streaming for sermon artifacts with HTTP Range support.

Artifacts are resolved exclusively from paths recorded on the sermon/job
record (``sermon_files`` rows and ``metadata.json``), never from a
client-supplied path. Every resolved path must live under an allowed root
(the caller's output directory, the raw ingest directory, or the configured
output/input directories) so a tampered database row cannot read arbitrary
files. Playback in the browser cannot attach an Authorization header, so the
auth gate also accepts ``?token=`` for ``/api/media`` only.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from server.api.db import get_repository
from server.api.scoping import request_user, visible

router = APIRouter(prefix="/api/media", tags=["media"])

_CHUNK_SIZE = 1024 * 1024

_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}

_MEDIA_KINDS = (
    "source",
    "processed",
    "enhanced",
    "keeper",
    "transcript",
    "transcript_timestamps",
    "snippet_start",
    "snippet_end",
    "snippet_ending",
)

_ALIASES = {
    "original": "source",
    "render": "processed",
    "output": "processed",
    "audio": "processed",
    "transcript_txt": "transcript",
    "transcript_json": "transcript_timestamps",
}

_LABELS = {
    "source": "Source media",
    "processed": "Rendered audio",
    "enhanced": "Enhanced audio",
    "keeper": "Keeper video",
    "transcript": "Transcript",
    "transcript_timestamps": "Transcript timestamps",
    "snippet_start": "Start cut preview",
    "snippet_end": "End cut preview",
    "snippet_ending": "Proposed ending",
}


class RangeNotSatisfiable(Exception):
    """Raised when a syntactically valid Range cannot be served."""


def normalize_kind(kind: str) -> str:
    return _ALIASES.get(kind.strip().lower(), kind.strip().lower())


def content_type_for(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse a single-range header into an inclusive-exclusive (start, end).

    Returns ``None`` for "serve the whole entity". Raises
    ``RangeNotSatisfiable`` for ``bytes=`` ranges outside the file.
    """
    if not header:
        return None
    value = header.strip()
    if not value.lower().startswith("bytes="):
        return None
    spec = value[len("bytes=") :].split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    raw_start, _, raw_end = spec.partition("-")
    raw_start = raw_start.strip()
    raw_end = raw_end.strip()
    try:
        if not raw_start:
            suffix = int(raw_end)
            if suffix <= 0:
                raise RangeNotSatisfiable
            start = max(0, size - suffix)
            end = size
        else:
            start = int(raw_start)
            if start < 0 or start >= size:
                raise RangeNotSatisfiable
            end = int(raw_end) + 1 if raw_end else size
            if raw_end and end <= start:
                raise RangeNotSatisfiable
            end = min(end, size)
    except ValueError:
        return None
    if start >= end:
        raise RangeNotSatisfiable
    return start, end


def _resolve_output_path(value: str) -> Path:
    from server.api.routers.userdata import _resolve_output_path as resolve

    return resolve(value)


def allowed_roots(user: dict[str, Any]) -> list[Path]:
    """Roots an artifact path may live under for this user."""
    from server.api.routers.userdata import resolve_user_output_dir

    roots: list[Path] = [resolve_user_output_dir(user)]
    raw_ingest = os.environ.get("SERMONPILOT_RAW_INGEST", "/data/raw_ingest")
    if raw_ingest:
        roots.append(_resolve_output_path(raw_ingest))
    try:
        from ui.config_utils import resolve_config

        config = resolve_config()
        for key in ("output_directory", "input_directory"):
            configured = str(config.get(key) or "").strip()
            if configured and not configured.startswith("remote:"):
                roots.append(_resolve_output_path(configured))
    except Exception:
        pass
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except (OSError, RuntimeError):
            continue
        if str(resolved) not in seen:
            seen.add(str(resolved))
            unique.append(resolved)
    return unique


def within_roots(candidate: Path, roots: list[Path]) -> bool:
    return any(candidate == root or root in candidate.parents for root in roots)


def _safe_resolve(value: str | Path | None) -> Path | None:
    if not value:
        return None
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _read_metadata(files: dict[str, str]) -> dict[str, Any]:
    raw = files.get("metadata")
    if not raw:
        return {}
    path = _safe_resolve(raw)
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _media_dirs(files: dict[str, str], metadata: dict[str, Any]) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if not value:
            return
        resolved = _safe_resolve(str(value))
        if resolved is None:
            return
        parent = resolved.parent
        if str(parent) not in seen:
            seen.add(str(parent))
            dirs.append(parent)

    add(metadata.get("original_file"))
    add(metadata.get("processed_file"))
    for key in (
        "audio",
        "enhanced_audio",
        "original_audio",
        "original_video",
        "metadata",
        "transcript",
        "transcript_timestamps",
    ):
        add(files.get(key))
    return dirs


def artifact_candidates(
    kind: str, files: dict[str, str], metadata: dict[str, Any], roots: list[Path]
) -> list[Path]:
    dirs = _media_dirs(files, metadata)
    raw: list[Any] = []
    if kind == "source":
        raw = [metadata.get("original_file")]
    elif kind == "processed":
        raw = [
            metadata.get("processed_file"),
            files.get("processed_audio"),
            files.get("audio"),
            files.get("enhanced_audio"),
        ]
    elif kind == "enhanced":
        raw = [files.get("enhanced_audio"), metadata.get("enhanced_file")]
    elif kind == "keeper":
        stems = [
            Path(str(value)).stem
            for value in (
                metadata.get("original_file"),
                metadata.get("processed_file"),
                files.get("audio"),
            )
            if value
        ]
        raw = [metadata.get("keeper_file"), files.get("keeper_audio"), files.get("keeper")]
        for root in roots:
            for stem in stems:
                raw.append(str(root / "keepers" / f"{stem}_keeper.mp4"))
    elif kind == "transcript":
        raw = [files.get("transcript"), metadata.get("transcript_file")]
        raw.extend(str(directory / "transcript.txt") for directory in dirs)
    elif kind == "transcript_timestamps":
        raw = [files.get("transcript_timestamps"), metadata.get("transcript_timestamps_file")]
        raw.extend(str(directory / "transcript_timestamps.json") for directory in dirs)
    elif kind.startswith("snippet_"):
        raw = [files.get(kind), metadata.get(kind)]
        raw.extend(str(directory / "snippets" / f"{kind}.mp4") for directory in dirs)
    candidates: list[Path] = []
    for value in raw:
        resolved = _safe_resolve(value)
        if resolved is not None:
            candidates.append(resolved)
    return candidates


def _load_owned_sermon(repo: Any, sermon_id: str, user: dict[str, Any] | None) -> dict[str, Any]:
    sermon = repo.get_sermon(sermon_id)
    if sermon is None or not visible(sermon.get("user_id"), user):
        raise HTTPException(status_code=404, detail="sermon not found")
    return sermon


def resolve_artifact(
    sermon: dict[str, Any],
    kind: str,
    roots: list[Path],
    *,
    strict: bool = True,
) -> Path:
    normalized = normalize_kind(kind)
    if normalized not in _MEDIA_KINDS:
        raise HTTPException(status_code=404, detail=f"unknown artifact kind: {kind}")
    files = {k: str(v) for k, v in (sermon.get("file_paths") or {}).items() if v}
    metadata = _read_metadata(files)
    for candidate in artifact_candidates(normalized, files, metadata, roots):
        if not within_roots(candidate, roots):
            if strict:
                raise HTTPException(
                    status_code=403,
                    detail="artifact path is outside the allowed roots",
                )
            continue
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    raise HTTPException(status_code=404, detail=f"artifact not available: {normalized}")


def _snippet_windows(sermon_id: str) -> dict[str, tuple[float, float] | None]:
    repo = get_repository()
    plan = repo.get_current_edit_plan(sermon_id) or {}
    start = plan.get("proposed_start")
    if start is None:
        start = plan.get("final_start")
    end = plan.get("proposed_end")
    if end is None:
        end = plan.get("final_end")
    start = float(start) if start is not None else None
    end = float(end) if end is not None else None
    return {
        "snippet_start": (max(start - 10.0, 0.0), start + 10.0) if start is not None else None,
        "snippet_end": (max(end - 10.0, 0.0), end + 10.0) if end is not None else None,
        "snippet_ending": (
            (max(start, end - 30.0), end) if start is not None and end is not None else None
        ),
    }


@router.get("/sermons/{sermon_id}")
def list_sermon_media(request: Request, sermon_id: str) -> dict[str, Any]:
    user = request_user(request)
    repo = get_repository()
    sermon = _load_owned_sermon(repo, sermon_id, user)
    roots = allowed_roots(user) if user is not None else []
    windows = _snippet_windows(sermon_id)

    items: list[dict[str, Any]] = []
    for kind in _MEDIA_KINDS:
        try:
            path = resolve_artifact(sermon, kind, roots, strict=False)
            size = path.stat().st_size
            items.append(
                {
                    "kind": kind,
                    "label": _LABELS[kind],
                    "available": True,
                    "content_type": content_type_for(path),
                    "size": size,
                }
            )
        except HTTPException:
            item: dict[str, Any] = {
                "kind": kind,
                "label": _LABELS[kind],
                "available": False,
                "content_type": None,
                "size": None,
            }
            window = windows.get(kind)
            if window is not None:
                item["start_sec"] = window[0]
                item["end_sec"] = window[1]
            items.append(item)

    def available(kind: str) -> bool:
        return any(item["kind"] == kind and item["available"] for item in items)

    primary = "processed" if available("processed") else "source" if available("source") else None
    audio: str | None = None
    for kind in ("keeper", "enhanced", "processed", "source"):
        if available(kind):
            audio = kind
            break
    return {"id": sermon_id, "items": items, "primary": primary, "audio": audio}


@router.api_route("/sermons/{sermon_id}/{kind}", methods=["GET", "HEAD"])
def stream_sermon_artifact(request: Request, sermon_id: str, kind: str) -> Response:
    user = request_user(request)
    repo = get_repository()
    sermon = _load_owned_sermon(repo, sermon_id, user)
    roots = allowed_roots(user) if user is not None else []
    path = resolve_artifact(sermon, kind, roots)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=404, detail=f"artifact not readable: {kind}") from exc

    media_type = content_type_for(path)
    try:
        parsed = parse_range(request.headers.get("range"), size)
    except RangeNotSatisfiable:
        return Response(
            status_code=416,
            headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes */{size}"},
        )

    if parsed is None:
        status = 200
        start, end = 0, size
    else:
        status = 206
        start, end = parsed

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start)}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end - 1}/{size}"

    if request.method == "HEAD":
        return Response(status_code=status, headers=headers, media_type=media_type)
    return StreamingResponse(
        _iter_file(path, start, end),
        status_code=status,
        headers=headers,
        media_type=media_type,
    )


async def _iter_file(path: Path, start: int, end: int) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start
        while remaining > 0:
            chunk = handle.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
