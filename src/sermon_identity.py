"""Deterministic sermon identity.

A sermon's database id is derived from its stable identity: the normalised
speaker, recorded date and title, plus a source fingerprint when a source is
available. The same source processed again resolves to the same id, so an
upsert refreshes the existing record instead of inserting a duplicate.

The fingerprint is content based for local files (a sampled SHA-256 over the
size plus head and tail bytes), so re-staging a byte-identical file under a
new temporary name still lands on the same record. Remote sources that cannot
be read use their reference name plus reported size.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SAMPLE_BYTES = 1 << 20
_UNSAFE_CHARS = re.compile(r"[^a-z0-9]+")
_DIGEST_CHARS = 12


def normalize_part(value: str | None, fallback: str) -> str:
    text = _UNSAFE_CHARS.sub("_", str(value or "").strip().lower()).strip("_")
    return text or fallback


def normalize_date(value: str | None) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    return digits or "nodate"


def identity_key(
    speaker: str | None,
    recorded_date: str | None,
    title: str | None,
) -> str:
    """Stable grouping key for migration, independent of source and revision."""
    return "\x1f".join((
        normalize_part(speaker, "unknown"),
        normalize_date(recorded_date),
        normalize_part(title, "untitled"),
    ))


def content_digest(path: str | Path, sample_bytes: int = _SAMPLE_BYTES) -> str | None:
    """Sampled content hash: size plus head and tail bytes, or None if unreadable."""
    candidate = Path(path)
    try:
        size = candidate.stat().st_size
    except OSError:
        return None
    digest = hashlib.sha256()
    digest.update(str(size).encode("utf-8"))
    try:
        with open(candidate, "rb") as handle:
            digest.update(handle.read(sample_bytes))
            if size > sample_bytes:
                handle.seek(max(0, size - sample_bytes))
                digest.update(handle.read(sample_bytes))
    except OSError:
        return None
    return digest.hexdigest()


def source_fingerprint(
    path: str | Path | None = None,
    *,
    original_name: str | None = None,
    size: int | None = None,
    remote_ref: str | None = None,
) -> str:
    """Best-effort stable descriptor for the sermon's source media."""
    if remote_ref:
        name = str(original_name or Path(remote_ref).name)
        resolved_size = size if size is not None else "unknown"
        return f"remote:{name}:{resolved_size}"
    if path:
        candidate = Path(path)
        digest = content_digest(candidate)
        if digest is not None:
            return f"local:{digest}"
        name = original_name or candidate.name
        resolved_size = size if size is not None else 0
        return f"path:{name}:{resolved_size}"
    if original_name:
        resolved_size = size if size is not None else "unknown"
        return f"name:{original_name}:{resolved_size}"
    return ""


def derive_sermon_id(
    speaker: str | None,
    recorded_date: str | None,
    title: str | None,
    fingerprint: str | None = None,
) -> str:
    """URL-safe deterministic id for a sermon identity and source fingerprint.

    The digest covers the full normalised values, so two sermons that share a
    truncated human-readable prefix still differ. Different speakers, dates,
    titles or sources always produce different ids.
    """
    speaker_part = normalize_part(speaker, "unknown")
    date_part = normalize_date(recorded_date)
    title_part = normalize_part(title, "untitled")
    payload = "|".join((
        speaker_part,
        date_part,
        title_part,
        str(fingerprint or ""),
    ))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]
    safe = f"{speaker_part[:20]}_{date_part[:8]}_{title_part[:40]}"
    return f"draft_{safe}_{digest}"
