"""Upload-only routing for a sermon whose render already exists.

The operator can accept a render locally (a render-only apply) and later choose
to publish that same file. This module resolves the stored render, applies the
refusal guards, and hands the file to the existing uploader
(``sermon_updater.publish_dry_run_sermon``). It never calls
``process_new_sermon``, so enhancement, cut detection and rendering do not run.

Guard codes (returned as ``error_code`` here and as ``detail.code`` from the
API):

- ``not_found``: no sermon row for the id.
- ``already_published``: the sermon is already on SermonAudio.
- ``no_render``: no rendered output exists to upload.
- ``missing_description``: the description is empty; pass
  ``confirm_missing_description`` to upload anyway.

The resolution order for the render is the ``processed_file`` pointer recorded
in the review metadata, then the sermon's stored audio file when the row is in
a rendered state or the filename marks it as a processed artifact. A source
recording that was never rendered is never treated as a render.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RENDERED_EDIT_STATUSES = frozenset(
    {"rendered", "applied", "applied_local", "auto_applied"}
)

CODE_NOT_FOUND = "not_found"
CODE_ALREADY_PUBLISHED = "already_published"
CODE_NO_RENDER = "no_render"
CODE_MISSING_DESCRIPTION = "missing_description"

MESSAGE_NO_RENDER = (
    "No rendered output exists for this teaching, so there is nothing to "
    "upload. Render the approved cut first."
)
MESSAGE_MISSING_DESCRIPTION = (
    "The description is empty, so uploading would publish a SermonAudio entry "
    "without one. Regenerate the description from the transcript, then upload. "
    "To upload without a description anyway, confirm it explicitly."
)


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _read_metadata(sermon: dict[str, Any]) -> dict[str, Any]:
    file_paths = sermon.get("file_paths") or {}
    metadata_path = file_paths.get("metadata") or ""
    if not metadata_path:
        return {}
    path = Path(str(metadata_path))
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _looks_like_processed_artifact(value: str) -> bool:
    stem = Path(str(value)).stem.lower()
    return "processed" in stem and "_keeper" not in stem


def resolve_existing_render(sermon: dict[str, Any]) -> Path | None:
    """The rendered file already on disk, or None when there is not one."""
    metadata = _read_metadata(sermon)
    file_paths = sermon.get("file_paths") or {}
    edit_status = str(sermon.get("edit_status") or "")
    candidates: list[Path] = []
    processed = metadata.get("processed_file")
    if processed:
        candidates.append(Path(str(processed)))
    audio = file_paths.get("audio")
    if audio and (
        processed
        or edit_status in RENDERED_EDIT_STATUSES
        or _looks_like_processed_artifact(str(audio))
    ):
        candidates.append(Path(str(audio)))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _subject(sermon: dict[str, Any]) -> str:
    title = str(sermon.get("title") or "").strip() or "Untitled"
    speaker = str(sermon.get("speaker") or "").strip()
    if speaker:
        return f'"{title}" ({speaker})'
    return f'"{title}"'


def _publication_id(sermon: dict[str, Any]) -> str | None:
    info = sermon.get("upload_info") or {}
    value = info.get("sermonaudio_id")
    return str(value) if value else None


def _published_message(sermon: dict[str, Any]) -> str | None:
    status = str(sermon.get("status") or "")
    edit_status = str(sermon.get("edit_status") or "")
    if status != "processed" and edit_status != "uploaded":
        return None
    remote = _publication_id(sermon)
    if remote:
        return (
            f"This teaching is already published on SermonAudio ({remote}), so "
            "there is nothing to upload. Edit its details instead."
        )
    return (
        "This teaching is already published on SermonAudio, so there is "
        "nothing to upload. Edit its details instead."
    )


@dataclass
class UploadAssessment:
    """Whether a stored render can be uploaded, and why not when it cannot."""

    ok: bool
    code: str = "ok"
    message: str = ""
    can_regenerate: bool = False
    subject: str = ""
    render_path: Path | None = None
    render_name: str = ""
    render_size: int = 0
    render_size_human: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "can_regenerate": self.can_regenerate,
            "render_name": self.render_name,
            "render_size": self.render_size,
            "render_size_human": self.render_size_human,
        }


def assess_upload_only(
    repo: Any,
    sermon_id: str,
    *,
    confirm_missing_description: bool = False,
) -> UploadAssessment:
    """Classify an upload-only request against the stored sermon row."""
    sermon = repo.get_sermon(sermon_id)
    if not sermon:
        return UploadAssessment(
            ok=False,
            code=CODE_NOT_FOUND,
            message="This teaching is not in the library, so there is nothing to upload.",
        )
    published = _published_message(sermon)
    if published:
        return UploadAssessment(
            ok=False, code=CODE_ALREADY_PUBLISHED, message=published
        )
    subject = _subject(sermon)
    render = resolve_existing_render(sermon)
    if render is None:
        return UploadAssessment(
            ok=False, code=CODE_NO_RENDER, message=MESSAGE_NO_RENDER, subject=subject
        )
    content = sermon.get("content") or {}
    description = str(content.get("description") or sermon.get("description") or "").strip()
    if not description and not confirm_missing_description:
        return UploadAssessment(
            ok=False,
            code=CODE_MISSING_DESCRIPTION,
            message=MESSAGE_MISSING_DESCRIPTION,
            can_regenerate=True,
            subject=subject,
            render_path=render,
        )
    try:
        size = render.stat().st_size
    except OSError:
        size = 0
    return UploadAssessment(
        ok=True,
        subject=subject,
        render_path=render,
        render_name=render.name,
        render_size=size,
        render_size_human=human_size(size),
    )


def run_upload_existing(
    repo: Any,
    sermon_id: str,
    *,
    publish: bool = True,
    confirm_missing_description: bool = False,
    progress_callback: Callable[[float, str], None] | None = None,
    uploader: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Upload the stored render through the existing uploader.

    The guard is checked before the uploader is touched, so a refusal never
    falls back to a render. ``uploader`` is injectable for tests and defaults
    to ``sermon_updater.publish_dry_run_sermon``.
    """
    report = progress_callback or (lambda _pct, _msg: None)
    assessment = assess_upload_only(
        repo, sermon_id, confirm_missing_description=confirm_missing_description
    )
    if not assessment.ok:
        report(0, assessment.message)
        return {
            "success": False,
            "error": assessment.message,
            "error_code": assessment.code,
            "can_regenerate": assessment.can_regenerate,
        }

    report(10, f"Uploading the existing render for {assessment.subject}")
    report(20, f"Using {assessment.render_name} ({assessment.render_size_human})")

    if uploader is None:
        import sermon_updater

        uploader = sermon_updater.publish_dry_run_sermon

    result = dict(
        uploader(
            str(sermon_id),
            publish=publish,
            upload_path=str(assessment.render_path),
        )
    )
    result["render_path"] = str(assessment.render_path)
    result["render_name"] = assessment.render_name
    result["render_size"] = assessment.render_size
    result["render_size_human"] = assessment.render_size_human
    if result.get("success"):
        report(100, f"Uploaded {assessment.render_name} ({assessment.render_size_human})")
    else:
        report(100, result.get("error") or "Upload failed")
    return result
