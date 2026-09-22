"""Retention and cleanup of media staged for interactive auto-edit review.

Interactive auto-edit pauses the pipeline so a human can judge the proposed
cuts. That review needs the source media to stay readable: the review panel
streams the retained original/keeper and one preview clip per proposed cut
through the media API. This module owns the on-disk contract for that media.

Layout (per review):

    <review_root>/<speaker>/<series>/<title dir>/
        review_media.json                 marker: this dir is review media
        <...> - Original.<ext>            full-length source, re-edit input
        <...> - Processed.<ext>           enhanced/muxed render
        <...> - Keeper.mp4                optional compact video
        transcript.txt
        transcript_timestamps.json
        metadata.json
        snippets/snippet_start.mp4
        snippets/snippet_end.mp4
        snippets/snippet_ending.mp4

``review_root`` is ``<output_directory>/review_media`` unless overridden by
the ``review_media_directory`` config key or ``$SERMONPILOT_REVIEW_MEDIA_DIR``.
When the configured output resolves to ephemeral cloud staging, the root falls
back to the application's default ``processed_sermons`` tree so the media API's
allowed roots can still see it.

Retention is bounded. Reviews older than ``$SERMONPILOT_REVIEW_RETENTION_DAYS``
(default 7) or beyond ``$SERMONPILOT_REVIEW_RETENTION_MAX_GB`` (default 32 GiB)
are swept by :func:`sweep_abandoned_reviews`. One ordinary 55-minute service
retains roughly 10 GB (a multi-GB keeper plus its render), so the size cap has
to clear a single normal review before it can bound anything; the sweep also
never discards the review it was called for. Snippet clips are capped by
``$SERMONPILOT_REVIEW_SNIPPET_MAX_MB`` (default 64 MiB); the clip length is
bounded by construction at :data:`SNIPPET_MAX_SECONDS`.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

try:  # src package import (project root on sys.path)
    from src.safe_delete import trash_local
except ImportError:  # src dir placed directly on sys.path
    from safe_delete import trash_local  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

SNIPPET_MAX_SECONDS = 30.0
SNIPPET_FILES = ("snippet_start.mp4", "snippet_end.mp4", "snippet_ending.mp4")
MARKER_FILENAME = "review_media.json"

_APP_ROOT = Path(__file__).resolve().parents[1]


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        logger.warning("Invalid %s=%r, using %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(float(str(raw).strip()))
    except ValueError:
        logger.warning("Invalid %s=%r, using %s", name, raw, default)
        return default


def review_retention_days() -> float:
    """How long a paused review keeps its media, in days (0 disables the age cap)."""
    return _env_float("SERMONPILOT_REVIEW_RETENTION_DAYS", 7.0)


def review_retention_max_bytes() -> int:
    """Total review media size cap in bytes (0 disables the size cap).

    The 32 GiB default leaves room for an ordinary 55-minute service
    (~10 GB across keeper, enhanced audio and render) plus one or two older
    reviews, while a single review is never deleted just to satisfy the cap.
    """
    gigabytes = _env_float("SERMONPILOT_REVIEW_RETENTION_MAX_GB", 32.0)
    return max(0, int(gigabytes * 1024**3))


def snippet_max_bytes() -> int:
    """Per-snippet size cap in bytes (0 disables)."""
    megabytes = _env_float("SERMONPILOT_REVIEW_SNIPPET_MAX_MB", 64.0)
    return max(0, int(megabytes * 1024**2))


def default_output_root() -> Path:
    """Application default output tree, always inside the media API's roots."""
    return _APP_ROOT / "processed_sermons"


def _cloud_output_root() -> Path:
    override = os.environ.get("SERMONPILOT_CLOUD_OUTPUT_DIR")
    if override:
        return Path(override).expanduser()
    return Path(tempfile.gettempdir()) / "cloud_output"


def _staging_root() -> Path:
    override = os.environ.get("SERMONPILOT_CLOUD_STAGING_DIR")
    if override:
        return Path(override).expanduser()
    try:
        from ui.config_utils import default_cache_root

        return default_cache_root() / "cloud_ingest"
    except Exception:
        return Path.home() / ".cache" / "sermonpilot" / "cloud_ingest"


def _ephemeral_roots() -> list[Path]:
    return [_cloud_output_root(), _staging_root()]


def _is_under(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        anchor = root.resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == anchor or anchor in resolved.parents


def _is_ephemeral(path: Path) -> bool:
    return any(_is_under(path, root) for root in _ephemeral_roots())


def resolve_review_media_root(config: dict[str, Any] | None = None) -> Path:
    """Durable root that holds review media for every paused review.

    Resolution order: ``review_media_directory`` config key (settable through
    ``$SERMONPILOT_REVIEW_MEDIA_DIR``), then ``<output_directory>/review_media``.
    An ephemeral cloud output/staging base falls back to the application
    default so the media API can still stream the retained files.
    """
    config = config if isinstance(config, dict) else {}
    explicit = str(config.get("review_media_directory") or "").strip()
    if not explicit:
        explicit = os.environ.get("SERMONPILOT_REVIEW_MEDIA_DIR", "").strip()
    if explicit:
        root = Path(explicit).expanduser()
        if not root.is_absolute():
            root = _APP_ROOT / root
        return root

    base = Path(str(config.get("output_directory") or "processed_sermons")).expanduser()
    if not base.is_absolute():
        base = _APP_ROOT / base
    if _is_ephemeral(base):
        base = default_output_root()
    return base / "review_media"


def snippet_windows(start: float, end: float) -> dict[str, tuple[float, float]]:
    """Preview windows for the proposed start/end, mirroring the media router."""
    return {
        "snippet_start": (max(start - 10.0, 0.0), start + 10.0),
        "snippet_end": (max(end - 10.0, 0.0), end + 10.0),
        "snippet_ending": (max(start, end - SNIPPET_MAX_SECONDS), end),
    }


def render_bounded_snippets(
    source: Path | str,
    plan: Any,
    out_dir: Path | str,
    logo_path: Path | None = None,
    fade_out_tail_seconds: float = 2.0,
    max_bytes: int | None = None,
) -> list[Path]:
    """Render one preview clip per proposed cut, dropping clips over the caps.

    Reuses :func:`src.auto_edit.render_review_snippets` (clips are at most
    :data:`SNIPPET_MAX_SECONDS` by construction), then unlinks any result over
    the per-snippet size cap.
    """
    from src.auto_edit import render_review_snippets

    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered = render_review_snippets(
            Path(source),
            plan,
            out_dir,
            logo_path,
            fade_out_tail_seconds=fade_out_tail_seconds,
        )
    except Exception as exc:
        logger.warning("review snippets failed for %s: %s", plan, exc)
        return []

    cap = snippet_max_bytes() if max_bytes is None else max_bytes
    kept: list[Path] = []
    for path in rendered:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if cap > 0 and size > cap:
            trash_local(path, reason="review_snippet_over_cap", stage="review_snippet")
            logger.info("Dropped oversized review snippet %s (%d bytes)", path, size)
            continue
        kept.append(path)
    return kept


def write_review_marker(review_dir: Path | str, sermon_id: str) -> Path:
    """Stamp a directory as review media so cleanup never touches real output."""
    review_dir = Path(review_dir)
    marker = review_dir / MARKER_FILENAME
    payload = {"review": True, "sermon_id": str(sermon_id)}
    try:
        marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write review marker %s: %s", marker, exc)
    return marker


def is_review_dir(review_dir: Path | str) -> bool:
    return (Path(review_dir) / MARKER_FILENAME).is_file()


def snippet_paths(review_dir: Path | str) -> list[Path]:
    directory = Path(review_dir) / "snippets"
    return [directory / name for name in SNIPPET_FILES if (directory / name).is_file()]


def _read_metadata(review_dir: Path) -> dict[str, Any]:
    path = review_dir / "metadata.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _remove_staged_file(path: str | None) -> None:
    """Move a staged cloud download to trash, only when it really lives in staging.

    The staged file is a local copy of a cloud source; the cloud original stays
    in place. Even so the local copy is moved, never unlinked, so a mistaken
    cleanup can be recovered.
    """
    if not path:
        return
    candidate = Path(str(path))
    try:
        if candidate.parent != _staging_root().resolve():
            logger.info("Refusing to remove non-staged file %s", candidate)
            return
        for target in (
            candidate,
            candidate.with_name(f"{candidate.stem}_enhanced{candidate.suffix}"),
            candidate.with_name(f"{candidate.stem}_cleaned.wav"),
        ):
            trash_local(target, reason="review_staged_source_released", stage="review")
    except OSError as exc:
        logger.warning("Could not remove staged review source %s: %s", candidate, exc)


def finalize_review_media(review_dir: Path | str, outcome: str) -> bool:
    """Release review media once the review reaches a terminal outcome.

    ``approved`` and ``failed`` drop the preview snippets and the staged cloud
    copy while keeping the retained original/keeper for a later re-edit.
    ``discarded`` removes the whole review directory. Only directories carrying
    the review marker are touched.
    """
    review_dir = Path(review_dir)
    if not is_review_dir(review_dir):
        logger.info("Not a review media dir, nothing finalized: %s", review_dir)
        return False
    metadata = _read_metadata(review_dir)

    if outcome == "discarded":
        _remove_staged_file(metadata.get("staged_file"))
        trash_local(review_dir, reason="review_discarded", stage="review")
        logger.info("Discarded review media %s", review_dir)
        return True

    snippets = review_dir / "snippets"
    trash_local(snippets, reason="review_snippets_released", stage="review")
    _remove_staged_file(metadata.get("staged_file"))
    logger.info("Finalized review media %s (%s)", review_dir, outcome)
    return True


def review_dir_for_sermon(sermon_id: str, repo: Any = None) -> Path | None:
    """Locate the review directory recorded for a sermon, if any."""
    if repo is None:
        try:
            from ui.database import SermonRepository

            repo = SermonRepository()
        except Exception:
            return None
    try:
        sermon = repo.get_sermon(str(sermon_id))
    except Exception:
        return None
    if not isinstance(sermon, dict):
        return None
    metadata_path = (sermon.get("file_paths") or {}).get("metadata")
    if not metadata_path:
        return None
    candidate = Path(str(metadata_path)).parent
    return candidate if is_review_dir(candidate) else None


def finalize_review_media_for_sermon(sermon_id: str, outcome: str, repo: Any = None) -> bool:
    review_dir = review_dir_for_sermon(sermon_id, repo)
    if review_dir is None:
        return False
    return finalize_review_media(review_dir, outcome)


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def human_size(num_bytes: int | float) -> str:
    """Format a byte count for a log line (e.g. ``4.16 GB``)."""
    size = float(num_bytes)
    if size < 1024:
        return f"{int(size)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
    return f"{size:.2f} TB"


def retained_artifact_line(kind: str, path: Path | str) -> str:
    """One-line summary of a retained review artifact: kind, path and size."""
    candidate = Path(path)
    try:
        size = human_size(candidate.stat().st_size)
    except OSError:
        size = "size unavailable"
    return f"Retained review media: {kind} {candidate} ({size})"


def _same_path(left: Path, right: Path | str | None) -> bool:
    if right is None:
        return False
    try:
        return left.resolve() == Path(right).resolve()
    except (OSError, RuntimeError):
        return False


def sweep_abandoned_reviews(
    config: dict[str, Any] | None = None,
    repo: Any = None,
    now: float | None = None,
    protect_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Drop review media past the age or total-size cap.

    ``protect_dir`` is the review that was just written (or restored) and is
    never discarded, whatever the caps say: deleting the media a user is about
    to review is never the right outcome. A size cap also never removes the
    last remaining review, so a single review larger than the cap survives and
    a warning names its size against the cap.

    Returns ``{"removed": [...], "kept": int, "bytes": int}``. Safe to run
    repeatedly; only marked review directories are considered.
    """
    root = resolve_review_media_root(config)
    if not root.is_dir():
        return {"removed": [], "kept": 0, "bytes": 0}

    now_ts = time.time() if now is None else float(now)
    max_age_seconds = review_retention_days() * 86400.0
    max_bytes = review_retention_max_bytes()

    entries: list[dict[str, Any]] = []
    for marker in root.rglob(MARKER_FILENAME):
        review_dir = marker.parent
        try:
            mtime = marker.stat().st_mtime
        except OSError:
            continue
        entries.append({"dir": review_dir, "mtime": mtime, "size": _dir_size(review_dir)})

    entries.sort(key=lambda entry: entry["mtime"])
    removed: list[str] = []
    kept: list[dict[str, Any]] = []
    for entry in entries:
        if _same_path(entry["dir"], protect_dir):
            logger.info("Kept current review media (protected): %s", entry["dir"])
            kept.append(entry)
            continue
        age_days = (now_ts - entry["mtime"]) / 86400.0
        if max_age_seconds > 0 and now_ts - entry["mtime"] > max_age_seconds:
            logger.info(
                "Removing review media %s: age %.1f days over %.1f-day cap",
                entry["dir"],
                age_days,
                max_age_seconds / 86400.0,
            )
            finalize_review_media(entry["dir"], "discarded")
            removed.append(str(entry["dir"]))
            continue
        kept.append(entry)

    total = sum(entry["size"] for entry in kept)
    if max_bytes > 0:
        remaining: list[dict[str, Any]] = []
        survivors = len(kept)
        for entry in kept:
            protected = _same_path(entry["dir"], protect_dir)
            if total > max_bytes and not protected and survivors > 1:
                logger.info(
                    "Removing review media %s: %s over %s size cap (oldest first)",
                    entry["dir"],
                    human_size(total),
                    human_size(max_bytes),
                )
                finalize_review_media(entry["dir"], "discarded")
                removed.append(str(entry["dir"]))
                total -= entry["size"]
                survivors -= 1
                continue
            if total > max_bytes and protected:
                logger.info(
                    "Keeping current review media despite %s size cap: %s (%s)",
                    human_size(max_bytes),
                    entry["dir"],
                    human_size(entry["size"]),
                )
            remaining.append(entry)
        kept = remaining

    if max_bytes > 0 and total > max_bytes:
        largest = max(kept, key=lambda entry: entry["size"]) if kept else None
        logger.warning(
            "Review media over size cap: %d review(s) retained at %s against a %s cap. "
            "Keeping %s (%s) instead of deleting the only review; a user is about to "
            "review it.",
            len(kept),
            human_size(total),
            human_size(max_bytes),
            largest["dir"] if largest is not None else "no review",
            human_size(largest["size"]) if largest is not None else "n/a",
        )

    return {"removed": removed, "kept": len(kept), "bytes": total}


def retention_summary(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Current bounds and review-root location, for UI captions and tests."""
    return {
        "root": str(resolve_review_media_root(config)),
        "retention_days": review_retention_days(),
        "max_bytes": review_retention_max_bytes(),
        "snippet_max_bytes": snippet_max_bytes(),
        "snippet_max_seconds": SNIPPET_MAX_SECONDS,
    }
