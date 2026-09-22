"""Single deletion policy: nothing recoverable is ever unlinked outright.

Every media deletion in SermonPilot routes through this module. A local path is
moved into a dated trash area (``<data>/_trash/<YYYY-MM-DD>/<item>/``) instead
of being unlinked, so a delete is always a move. A cloud reference
(``remote:<name>:<sub>``) is never destroyed: by default the remote object is
left in place, and when a remote change is genuinely required the module issues
an ``rclone moveto`` into ``_trash/<date>/`` on that same remote. ``rclone
purge`` is never used and the Google Drive trash semantics are never disabled.

Every move writes a small sidecar (``trash_record.json``) beside the moved item
recording why it moved and which sermon/job/stage it belonged to, so a restore
is traceable. Trash is bounded: items older than the retention window
(``$SERMONPILOT_TRASH_RETENTION_DAYS``, default 30 days) are swept by
:func:`sweep_trash`, which is the only place a permanent removal happens.

Layout::

    <data>/_trash/<YYYY-MM-DD>/<epoch-ms>-<token>/<original-name>
    <data>/_trash/<YYYY-MM-DD>/<epoch-ms>-<token>/trash_record.json

Retention::

    SERMONPILOT_TRASH_DIR            trash root override (default: cache/_trash)
    SERMONPILOT_TRASH_RETENTION_DAYS days before a trash item is swept (default 30;
                                     0 or less disables the sweep entirely)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TRASH_DIRNAME = "_trash"
TRASH_RECORD_FILENAME = "trash_record.json"
DEFAULT_TRASH_RETENTION_DAYS = 30.0
REMOTE_PREFIX = "remote:"

Runner = Callable[..., Any]

_APP_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class TrashRecord:
    """Where a deleted item went, and why.

    ``mode`` is ``local`` (moved into the local trash root), ``remote`` (moved
    into ``_trash/<date>/`` on the same cloud remote) or ``remote-kept`` (a
    cloud object deliberately left in place). ``moved`` is False when the item
    was left where it was, either by policy or because the move failed.
    """

    source: str
    destination: str
    mode: str
    reason: str
    deleted_at: str
    sermon_id: str | None = None
    job_id: str | None = None
    stage: str | None = None
    moved: bool = True
    recoverable: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        logger.warning("Invalid %s=%r, using %s", name, raw, default)
        return default


def is_remote_reference(value: object) -> bool:
    """True when ``value`` is a configured cloud reference (``remote:name:sub``)."""
    return isinstance(value, str) and value.strip().startswith(REMOTE_PREFIX)


def split_remote_reference(value: str) -> tuple[str, str] | None:
    """Split ``remote:<name>:<sub>`` into ``(name, sub)`` without importing the API."""
    if not is_remote_reference(value):
        return None
    rest = value.strip()[len(REMOTE_PREFIX):]
    name, _, sub = rest.partition(":")
    name = name.strip()
    if not name:
        return None
    return name, sub.strip("/")


def redact_remote_reference(value: str) -> str:
    """Return a log-safe form of a cloud reference that hides the folder trail.

    Cloud sub-paths identify the church, so logs carry only the remote name and
    the object basename: ``remote:<name>:…/<basename>``.
    """
    parsed = split_remote_reference(value)
    if parsed is None:
        return str(value)
    name, sub = parsed
    basename = Path(sub.rstrip("/")).name if sub else ""
    return f"remote:{name}:…/{basename}" if basename else f"remote:{name}:"


def trash_base_dir(config: dict[str, Any] | None = None) -> Path:
    """Resolve the trash root: env override, config key, then the cache root."""
    override = os.environ.get("SERMONPILOT_TRASH_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if isinstance(config, dict):
        configured = str(config.get("trash_directory") or "").strip()
        if configured:
            root = Path(configured).expanduser()
            if not root.is_absolute():
                root = _APP_ROOT / root
            return root
    try:
        from ui.config_utils import default_cache_root

        return default_cache_root() / TRASH_DIRNAME
    except Exception:
        return Path.home() / ".cache" / "sermonpilot" / TRASH_DIRNAME


def trash_retention_days(config: dict[str, Any] | None = None) -> float:
    """Trash retention window in days (<= 0 disables sweeping)."""
    env_raw = os.environ.get("SERMONPILOT_TRASH_RETENTION_DAYS")
    if env_raw is not None and str(env_raw).strip():
        return _env_float("SERMONPILOT_TRASH_RETENTION_DAYS", DEFAULT_TRASH_RETENTION_DAYS)
    if isinstance(config, dict) and config.get("trash_retention_days") is not None:
        try:
            return float(config["trash_retention_days"])
        except (TypeError, ValueError):
            pass
    return DEFAULT_TRASH_RETENTION_DAYS


def _date_stamp(when: float) -> str:
    return dt.datetime.fromtimestamp(when).strftime("%Y-%m-%d")


def _inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        anchor = root.resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == anchor or anchor in resolved.parents


def _write_record(item_dir: Path, record: TrashRecord) -> None:
    try:
        (item_dir / TRASH_RECORD_FILENAME).write_text(
            json.dumps(record.to_dict(), indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not write trash record in %s: %s", item_dir, exc)


def trash_local(
    path: Path | str,
    *,
    reason: str,
    sermon_id: str | None = None,
    job_id: str | None = None,
    stage: str | None = None,
    config: dict[str, Any] | None = None,
    now: float | None = None,
) -> TrashRecord | None:
    """Move a local file or directory into the dated trash root.

    Returns the record (with the destination) or ``None`` when there was
    nothing to move. Never unlinks: a failure to move leaves the source alone.
    """
    candidate = Path(path)
    try:
        if not candidate.exists() and not candidate.is_symlink():
            return None
    except OSError:
        return None
    if not candidate.name:
        return None

    base = trash_base_dir(config)
    if _inside(candidate, base):
        logger.info("Refusing to nest a trash item inside the trash root: %s", candidate)
        return None

    now_ts = time.time() if now is None else float(now)
    item_dir = base / _date_stamp(now_ts) / f"{int(now_ts * 1000)}-{secrets.token_hex(4)}"
    try:
        item_dir.mkdir(parents=True, exist_ok=True)
        destination = item_dir / candidate.name
        shutil.move(str(candidate), str(destination))
    except (OSError, shutil.Error) as exc:
        logger.warning("Could not move %s into trash: %s", candidate, exc)
        return None

    record = TrashRecord(
        source=str(candidate),
        destination=str(destination),
        mode="local",
        reason=reason,
        deleted_at=dt.datetime.fromtimestamp(now_ts).isoformat(),
        sermon_id=sermon_id,
        job_id=job_id,
        stage=stage,
    )
    _write_record(item_dir, record)
    logger.info("Trash: moved %s -> %s (reason=%s)", candidate, destination, reason)
    return record


def trash_remote(
    remote_ref: str,
    *,
    user_id: str | None,
    reason: str,
    sermon_id: str | None = None,
    job_id: str | None = None,
    stage: str | None = None,
    config: dict[str, Any] | None = None,
    now: float | None = None,
    runner: Runner | None = None,
    exe: str | None = None,
) -> TrashRecord:
    """Move a cloud object into ``_trash/<date>/`` on the same remote.

    Uses ``rclone moveto`` only. ``rclone purge`` is never issued and no
    ``--drive-use-trash=false`` flag is passed. On any failure the remote object
    is left untouched and ``moved`` is False.
    """
    parsed = split_remote_reference(remote_ref)
    if parsed is None:
        raise ValueError(f"not a cloud reference: {remote_ref!r}")
    name, sub = parsed
    if not sub:
        raise ValueError("cloud reference has no object path")

    now_ts = time.time() if now is None else float(now)
    basename = Path(sub.rstrip("/")).name or "item"
    destination_sub = f"{TRASH_DIRNAME}/{_date_stamp(now_ts)}/{basename}"
    destination = f"{REMOTE_PREFIX}{name}:{destination_sub}"
    record = TrashRecord(
        source=remote_ref,
        destination=destination,
        mode="remote",
        reason=reason,
        deleted_at=dt.datetime.fromtimestamp(now_ts).isoformat(),
        sermon_id=sermon_id,
        job_id=job_id,
        stage=stage,
        moved=False,
    )

    if exe is None:
        try:
            from server.api.routers.cloud import _rclone_exe

            exe = _rclone_exe()
        except Exception as exc:
            logger.warning(
                "Trash: cannot move %s, rclone unavailable: %s",
                redact_remote_reference(remote_ref),
                exc,
            )
            return record
    try:
        from server.api.routers.cloud import _config_path

        config_path = str(_config_path(user_id))
    except Exception:
        config_path = ""

    command = [exe, "moveto", f"{name}:{sub}", f"{name}:{destination_sub}"]
    if config_path:
        command += ["--config", config_path]
    run = runner or subprocess.run
    try:
        proc = run(command, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        logger.warning(
            "Trash: rclone move failed for %s: %s",
            redact_remote_reference(remote_ref),
            exc,
        )
        return record
    if getattr(proc, "returncode", 1) != 0:
        detail = (getattr(proc, "stderr", "") or getattr(proc, "stdout", "") or "").strip()
        logger.warning(
            "Trash: rclone could not move %s: %s",
            redact_remote_reference(remote_ref),
            detail[:300],
        )
        return record

    record.moved = True
    logger.info(
        "Trash: moved cloud object on %s to %s (reason=%s)", name, destination_sub, reason
    )
    return record


def keep_remote_media(
    remote_ref: str,
    *,
    reason: str,
    sermon_id: str | None = None,
    job_id: str | None = None,
    stage: str | None = None,
) -> TrashRecord:
    """Record that a cloud object is deliberately left in place.

    Cloud media is never deleted as a side effect of dropping a database row.
    The destination is the unchanged remote reference, which stays recoverable
    through the provider.
    """
    parsed = split_remote_reference(remote_ref)
    name = parsed[0] if parsed else remote_ref
    logger.info(
        "Trash: leaving cloud media on %s in place (reason=%s)",
        name,
        reason,
    )
    return TrashRecord(
        source=remote_ref,
        destination=remote_ref,
        mode="remote-kept",
        reason=reason,
        deleted_at=dt.datetime.now().isoformat(),
        sermon_id=sermon_id,
        job_id=job_id,
        stage=stage,
        moved=False,
    )


def trash_target(
    target: Path | str,
    *,
    reason: str,
    user_id: str | None = None,
    sermon_id: str | None = None,
    job_id: str | None = None,
    stage: str | None = None,
    config: dict[str, Any] | None = None,
    now: float | None = None,
    runner: Runner | None = None,
    exe: str | None = None,
) -> TrashRecord | None:
    """Route one path or cloud reference through the deletion policy."""
    if is_remote_reference(target):
        if user_id is None:
            logger.warning(
                "Refusing to touch a cloud object without a user id: %s",
                redact_remote_reference(str(target)),
            )
            return None
        return trash_remote(
            str(target),
            user_id=user_id,
            reason=reason,
            sermon_id=sermon_id,
            job_id=job_id,
            stage=stage,
            config=config,
            now=now,
            runner=runner,
            exe=exe,
        )
    return trash_local(
        target,
        reason=reason,
        sermon_id=sermon_id,
        job_id=job_id,
        stage=stage,
        config=config,
        now=now,
    )


def trash_sermon_media(
    file_paths: Sequence[str] | None,
    *,
    sermon_id: str,
    user_id: str | None = None,
    job_id: str | None = None,
    config: dict[str, Any] | None = None,
    now: float | None = None,
    runner: Runner | None = None,
    exe: str | None = None,
) -> list[TrashRecord]:
    """Apply the policy to a sermon's recorded files before the row is dropped.

    Local media is moved into the trash root. Cloud media is left in place and
    reported as recoverable at its original reference; it is never unlinked.
    """
    records: list[TrashRecord] = []
    seen: set[str] = set()
    for raw in file_paths or []:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        if is_remote_reference(value):
            records.append(
                keep_remote_media(
                    value,
                    reason="sermon_deleted",
                    sermon_id=sermon_id,
                    job_id=job_id,
                    stage="library_delete",
                )
            )
            continue
        record = trash_local(
            value,
            reason="sermon_deleted",
            sermon_id=sermon_id,
            job_id=job_id,
            stage="library_delete",
            config=config,
            now=now,
        )
        if record is not None:
            records.append(record)
    return records


def sweep_trash(
    config: dict[str, Any] | None = None,
    *,
    now: float | None = None,
    retention_days: float | None = None,
) -> dict[str, Any]:
    """Permanently remove trash items older than the retention window.

    This is the only intended permanent delete in the product. A retention of
    0 or less disables the sweep, so trash is never cleared unexpectedly.
    Safe to run repeatedly: the second run finds nothing past the window.

    Returns ``{"removed": [...], "kept": N, "bytes": total}``.
    """
    base = trash_base_dir(config)
    if not base.is_dir():
        return {"removed": [], "kept": 0, "bytes": 0}

    window_days = trash_retention_days(config) if retention_days is None else float(retention_days)
    if window_days <= 0:
        return {"removed": [], "kept": _count_items(base), "bytes": _dir_size(base)}

    now_ts = time.time() if now is None else float(now)
    cutoff = now_ts - window_days * 86400.0
    removed: list[str] = []
    kept = 0
    for date_dir in sorted(base.iterdir()):
        if not date_dir.is_dir():
            continue
        for item in sorted(date_dir.iterdir()):
            try:
                mtime = item.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                kept += 1
                continue
            try:
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not sweep trash item %s: %s", item, exc)
                kept += 1
                continue
            removed.append(str(item))
            logger.info("Trash: swept %s (older than %.1f days)", item, window_days)
        try:
            if not any(date_dir.iterdir()):
                date_dir.rmdir()
        except OSError:
            pass

    return {"removed": removed, "kept": kept, "bytes": _dir_size(base)}


def _count_items(base: Path) -> int:
    total = 0
    try:
        for date_dir in base.iterdir():
            if date_dir.is_dir():
                total += sum(1 for _ in date_dir.iterdir())
    except OSError:
        return total
    return total


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


def trash_summary(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Current trash root, retention window and item count, for UI captions."""
    base = trash_base_dir(config)
    return {
        "root": str(base),
        "retention_days": trash_retention_days(config),
        "items": _count_items(base),
        "bytes": _dir_size(base),
    }
