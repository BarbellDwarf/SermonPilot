"""Human-readable labels for background jobs.

Job rows carry a title (the console headline) and a description (the second
line). Both are built from the sermon's own fields so the Jobs page reads like
a sentence instead of a sermon id. The raw id stays in the job parameters for
traceability.
"""

from __future__ import annotations

from typing import Any

LABEL_MAX_LENGTH = 60
UNTITLED_SERMON = "Untitled sermon"
SEPARATOR = " · "
ELLIPSIS = "…"

_TYPE_ACTIONS: dict[str, str] = {
    "sermon_processing": "Process sermon",
    "batch_processing": "Batch process",
    "sermon_import": "Import",
    "validation": "Validate descriptions",
    "audio_enhancement": "Enhance audio",
    "transcript_generation": "Transcribe",
    "metadata_update": "Generate metadata",
    "auto_edit": "Auto-edit",
    "auto_edit_apply": "Apply edit",
    "sermon_publish": "Upload",
}

_VARIANT_ACTIONS: dict[str, str] = {
    "auto_edit": "Process + auto-edit",
    "push": "Batch push",
    "batch_ai": "Batch AI",
    "reprocess": "Re-process",
    "re_detect": "Re-detect cuts",
    "refine": "Refine cuts",
    "force_import": "Re-import",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _type_value(job_type: Any) -> str:
    return str(getattr(job_type, "value", job_type) or "")


def _action(job_type: Any, variant: str | None) -> str:
    if variant and variant in _VARIANT_ACTIONS:
        return _VARIANT_ACTIONS[variant]
    return _TYPE_ACTIONS.get(_type_value(job_type), "Job")


def truncate_label(text: Any, limit: int = LABEL_MAX_LENGTH) -> str:
    """Collapse whitespace and cap the label, ending with an ellipsis."""
    collapsed = _text(text)
    if limit < 1:
        return ""
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + ELLIPSIS


def build_job_name(
    job_type: Any,
    *,
    title: Any = None,
    speaker: Any = None,
    count: int | None = None,
    variant: str | None = None,
) -> str:
    """A short headline: action, sermon title, speaker, then a batch hint."""
    action = _action(job_type, variant)
    title_text = _text(title)
    speaker_text = _text(speaker)
    if title_text:
        parts = [action, title_text]
        if speaker_text:
            parts.append(speaker_text)
        label = SEPARATOR.join(parts)
        if isinstance(count, int) and count > 1:
            label = f"{label} (+{count - 1} more)"
    elif isinstance(count, int) and count > 1:
        label = f"{action}{SEPARATOR}{count} sermons"
    else:
        label = f"{action}{SEPARATOR}{UNTITLED_SERMON}"
    return truncate_label(label)


def _prose_subject(title: Any, speaker: Any = None, recorded_date: Any = None) -> str:
    name = _text(title) or UNTITLED_SERMON
    meta = [value for value in (_text(speaker), _text(recorded_date)) if value]
    if meta:
        return f'"{name}" ({", ".join(meta)})'
    return f'"{name}"'


def build_job_description(
    job_type: Any,
    *,
    title: Any = None,
    speaker: Any = None,
    recorded_date: Any = None,
    count: int | None = None,
    variant: str | None = None,
    detail: Any = None,
) -> str:
    """A sentence describing what the job is doing right now."""
    kind = _type_value(job_type)
    subject = _prose_subject(title, speaker, recorded_date)
    many = isinstance(count, int) and count > 1

    if kind == "sermon_processing":
        if variant == "auto_edit":
            return f"Processing {subject} and auto-editing the video."
        return f"Running the processing pipeline for {subject}."
    if kind == "auto_edit":
        if variant == "re_detect":
            return f"Re-detecting the opening and closing cut for {subject}."
        if variant == "refine":
            return f"Refining the proposed cut for {subject} using your review notes."
        return f"Detecting the opening and closing cut for {subject}."
    if kind == "auto_edit_apply":
        if variant == "upload":
            return f"Rendering the approved cut for {subject} and uploading it to SermonAudio."
        return f"Rendering the approved cut for {subject}."
    if kind == "sermon_publish":
        return f"Uploading {subject} to SermonAudio."
    if kind == "metadata_update":
        if many:
            return f"Generating descriptions and hashtags for {count} sermons."
        return f"Generating the description and hashtags for {subject}."
    if kind == "batch_processing":
        if variant == "push":
            if many:
                return f"Pushing {count} sermons to the SermonAudio API."
            return f"Pushing {subject} to the SermonAudio API."
        if variant == "reprocess":
            return f"Re-processing {subject}."
        if many:
            steps = _text(detail) or "the selected actions"
            return f"Processing {count} sermons: {steps}."
        return f"Processing {subject}."
    if kind == "validation":
        if many:
            line = f"Checking the generated descriptions for {count} sermons"
            scope_text = _text(detail)
            if scope_text:
                return f"{line} ({scope_text})."
            return f"{line}."
        return f"Checking the generated description for {subject}."
    if kind == "sermon_import":
        if variant == "force_import":
            if count is not None:
                return f"Re-importing all {count} sermons from the processed_sermons folder."
            return "Re-importing sermons from the processed_sermons folder."
        if count is not None:
            return f"Importing {count} missing sermons from the processed_sermons folder."
        return "Importing missing sermons from the processed_sermons folder."
    if kind == "audio_enhancement":
        return f"Enhancing the audio for {subject}."
    if kind == "transcript_generation":
        return f"Transcribing {subject}."
    return f"Running {subject}."


def build_job_labels(
    job_type: Any,
    *,
    title: Any = None,
    speaker: Any = None,
    recorded_date: Any = None,
    count: int | None = None,
    variant: str | None = None,
    detail: Any = None,
) -> tuple[str, str]:
    """Return the (name, description) pair for a job row."""
    name = build_job_name(
        job_type, title=title, speaker=speaker, count=count, variant=variant
    )
    description = build_job_description(
        job_type,
        title=title,
        speaker=speaker,
        recorded_date=recorded_date,
        count=count,
        variant=variant,
        detail=detail,
    )
    return name, description


def sermon_fields_for(sermon_ids: Any, repo: Any = None) -> dict[str, Any]:
    """Best-effort title/speaker/date for the first id, for label building.

    Pass ``repo`` to read through a caller-owned repository. The API bridge
    supplies its read-only one so label lookup never opens the live database
    for writing.
    """
    try:
        ids = list(sermon_ids)
    except TypeError:
        return {}
    if not ids:
        return {}
    try:
        if repo is None:
            from ui.database import SermonRepository

            repo = SermonRepository()
        sermon = repo.get_sermon(str(ids[0]))
    except Exception:
        return {}
    if not sermon:
        return {}
    return {
        "title": sermon.get("title"),
        "speaker": sermon.get("speaker"),
        "recorded_date": sermon.get("recorded_date"),
    }


def variant_from_params(job_type: Any, params: Any) -> str | None:
    """Pick the label variant a persisted job's parameters imply."""
    if not isinstance(params, dict):
        return None
    kind = _type_value(job_type)
    form = params.get("form_data")
    if kind == "auto_edit_apply":
        return "upload" if not params.get("render_only") else "render_only"
    if kind == "auto_edit":
        if params.get("re_detect"):
            return "re_detect"
        if params.get("refine"):
            return "refine"
    if kind == "sermon_processing":
        if params.get("auto_edit_enabled"):
            return "auto_edit"
        if isinstance(form, dict) and form.get("auto_edit_enabled"):
            return "auto_edit"
    if kind == "sermon_import" and params.get("force_reimport"):
        return "force_import"
    return None


def labels_from_job(job: Any) -> tuple[str, str]:
    """Rebuild a job's labels from its type and parameters (used on retry)."""
    job_type = getattr(job, "type", None)
    params = getattr(job, "parameters", None)
    form = params.get("form_data") if isinstance(params, dict) else None
    if isinstance(form, dict):
        fields: dict[str, Any] = {
            "title": form.get("title"),
            "speaker": form.get("speaker_name"),
            "recorded_date": form.get("recorded_date"),
        }
    else:
        ids: list[Any] = []
        if isinstance(params, dict):
            if isinstance(params.get("sermon_ids"), list):
                ids = params["sermon_ids"]
            elif params.get("sermon_id"):
                ids = [params["sermon_id"]]
        fields = sermon_fields_for(ids)
    count = None
    if isinstance(params, dict) and isinstance(params.get("sermon_ids"), list):
        count = len(params["sermon_ids"])
    return build_job_labels(
        job_type, count=count, variant=variant_from_params(job_type, params), **fields
    )
