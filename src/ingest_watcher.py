"""Standalone ingest watcher over per-user cloud remotes (#283/#284/#285).

Polls a user's rclone remote through their isolated config
(``SERMONPILOT_RCLONE_DIR/<user_id>/config``, see
``server/api/routers/cloud.py``), detects new and stable recording files, and
sends a Signal notification. It never downloads, processes, or uploads
anything: detection and notification only.

Run as: ``python -m src.ingest_watcher``

Enable with the ``ingest_watcher.enabled`` config key or the
``INGEST_WATCHER_ENABLED`` environment variable (default off). The remote is
read with ``rclone lsf <remote>:<watch_subpath> --format stp --recursive`` and
nothing is assumed about the filenames beyond the extension allowlist.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.signal_notify import SignalNotifier, clean

logger = logging.getLogger(__name__)

DEFAULT_RCLONE_DIR = "/data/rclone"
DEFAULT_STATE_FILE = "/data/ingest_watcher_state.json"
DEFAULT_EXTENSIONS = [".mkv", ".mp4", ".mov", ".m4a", ".wav"]

_SESSION_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ _T](\d{2})[-:](\d{2})[-:](\d{2})")
_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_-]")
_TRUTHY = {"1", "true", "yes", "on"}


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    return default


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _config_path(user_id: str) -> Path:
    safe = _SAFE_SEGMENT_RE.sub("_", user_id or "anon") or "anon"
    return Path(os.environ.get("SERMONPILOT_RCLONE_DIR", DEFAULT_RCLONE_DIR)) / safe / "config"


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    mtime: str = ""

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@dataclass
class WatcherSettings:
    enabled: bool = False
    remote: str = ""
    user_id: str = ""
    poll_interval_seconds: int = 60
    stability_window_seconds: int = 300
    size_floor_mb: float = 50.0
    extension_allowlist: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    state_file: str = DEFAULT_STATE_FILE
    watch_subpath: str = ""
    signal_url: str = ""
    signal_sender: str = ""
    signal_recipients: str = ""

    @property
    def size_floor_bytes(self) -> int:
        return int(self.size_floor_mb * 1024 * 1024)

    @property
    def target(self) -> str:
        sub = self.watch_subpath.lstrip("/")
        return f"{self.remote}:{sub}"

    def state_key(self, path: str) -> str:
        return f"{self.remote}:{path}"


def parse_lsf(text: str) -> list[RemoteFile]:
    """Parse ``rclone lsf --format stp`` output (``size;modtime;path``).

    Directory rows carry size -1 and are skipped. A 2-column row (plain
    ``--format sp``) is accepted too, with an empty modtime.
    """
    files: list[RemoteFile] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line:
            continue
        parts = line.split(";")
        if len(parts) < 2:
            continue
        try:
            size = int(parts[0])
        except ValueError:
            continue
        if size < 0:
            continue
        if len(parts) == 2:
            path, mtime = parts[1], ""
        else:
            mtime = parts[1]
            path = ";".join(parts[2:])
        path = path.strip()
        if not path or path.endswith("/"):
            continue
        files.append(RemoteFile(path=path, size=size, mtime=mtime))
    return files


def suggested_date(path: str) -> str | None:
    """Best-effort date from a ``YYYY-MM-DD_HH-MM-SS`` filename segment."""
    match = _SESSION_RE.search(Path(path).name)
    if not match:
        return None
    date, hour, minute, second = match.groups()
    return f"{date} {hour}:{minute}:{second}"


def load_settings(config: dict | None = None) -> WatcherSettings:
    """Build watcher settings from the resolved app config plus env fallbacks."""
    if config is None:
        config = _resolve_config()
    block = config.get("ingest_watcher") if isinstance(config, dict) else None
    if not isinstance(block, dict):
        block = {}
    signal = block.get("signal") if isinstance(block.get("signal"), dict) else {}

    allowlist = block.get("extension_allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        allowlist = list(DEFAULT_EXTENSIONS)
    extensions: list[str] = []
    for entry in allowlist:
        ext = str(entry).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        extensions.append(ext)

    enabled = _as_bool(block.get("enabled")) or _as_bool(os.environ.get("INGEST_WATCHER_ENABLED"))
    return WatcherSettings(
        enabled=enabled,
        remote=clean(block.get("remote")),
        user_id=clean(block.get("user_id")),
        poll_interval_seconds=max(1, _as_int(block.get("poll_interval_seconds"), 60)),
        stability_window_seconds=max(0, _as_int(block.get("stability_window_seconds"), 300)),
        size_floor_mb=max(0.0, _as_float(block.get("size_floor_mb"), 50.0)),
        extension_allowlist=extensions,
        state_file=clean(block.get("state_file")) or DEFAULT_STATE_FILE,
        watch_subpath=clean(block.get("watch_subpath")),
        signal_url=clean(signal.get("url")) or clean(os.environ.get("INGEST_SIGNAL_URL")),
        signal_sender=clean(signal.get("sender")) or clean(os.environ.get("INGEST_SIGNAL_SENDER")),
        signal_recipients=clean(signal.get("recipients"))
        or clean(os.environ.get("INGEST_SIGNAL_RECIPIENTS")),
    )


def _resolve_config() -> dict:
    try:
        from ui.config_utils import resolve_config

        return resolve_config()
    except Exception as exc:  # noqa: BLE001 - a broken config must not stop polling
        logger.warning("ingest watcher: config resolution failed: %s", exc)
        return {}


def list_remote_files(settings: WatcherSettings, *, runner=subprocess.run) -> list[RemoteFile]:
    """List files on the user's remote via ``rclone lsf``; raises on failure."""
    exe = shutil.which("rclone")
    if not exe:
        raise RuntimeError("rclone is not installed")
    config = _config_path(settings.user_id)
    if not config.is_file():
        raise RuntimeError(f"rclone config not found: {config}")
    args = [
        exe,
        "--config",
        str(config),
        "lsf",
        settings.target,
        "--format",
        "stp",
        "--recursive",
    ]
    proc = runner(args, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "rclone lsf failed").strip()
        raise RuntimeError(detail[:500])
    return parse_lsf(proc.stdout)


def is_candidate(file: RemoteFile, settings: WatcherSettings) -> bool:
    ext = Path(file.name).suffix.lower()
    return ext in settings.extension_allowlist and file.size >= settings.size_floor_bytes


class WatcherState:
    """First-seen/last-seen state per remote path, persisted atomically."""

    def __init__(self, path: Path, files: dict | None = None) -> None:
        self.path = Path(path)
        self.files: dict = files if files is not None else {}

    @classmethod
    def load(cls, path: str | Path) -> WatcherState:
        file_path = Path(path)
        if not file_path.is_file():
            return cls(file_path)
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("ingest watcher: unreadable state %s: %s", file_path, exc)
            return cls(file_path)
        files = data.get("files") if isinstance(data, dict) else None
        return cls(file_path, files if isinstance(files, dict) else {})

    def get(self, key: str) -> dict | None:
        return self.files.get(key)

    def save(self) -> bool:
        payload = {"version": 1, "files": self.files}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning("ingest watcher: could not persist state %s: %s", self.path, exc)
            return False
        return True


def run_cycle(
    settings: WatcherSettings,
    state: WatcherState,
    files: list[RemoteFile],
    now: float,
    notifier: SignalNotifier | None = None,
) -> list[str]:
    """Update state for one poll and notify on newly stable recordings.

    Stability requires the size and modtime to stay unchanged for
    ``stability_window_seconds`` and at least two consecutive sightings, so a
    file still being written is never announced. Returns the state keys that
    were newly handled this cycle.
    """
    handled: list[str] = []
    for file in files:
        if not is_candidate(file, settings):
            continue
        key = settings.state_key(file.path)
        entry = state.get(key)
        if entry is None:
            entry = {
                "size": file.size,
                "mtime": file.mtime,
                "first_seen": now,
                "stable_since": now,
                "sightings": 1,
                "notified": False,
            }
            state.files[key] = entry
        else:
            if entry.get("size") != file.size or entry.get("mtime") != file.mtime:
                entry["size"] = file.size
                entry["mtime"] = file.mtime
                entry["stable_since"] = now
                entry["sightings"] = 1
            else:
                entry["sightings"] = _as_int(entry.get("sightings"), 1) + 1
        entry["last_seen"] = now

        if entry.get("notified"):
            continue
        stable = (
            _as_int(entry.get("sightings"), 1) >= 2
            and (now - _as_float(entry.get("stable_since"), now))
            >= settings.stability_window_seconds
        )
        if not stable:
            continue
        sent = True
        if notifier is not None:
            sent = notifier.notify_recording(
                file.name, file.size, suggested_date=file.path
            )
        if sent:
            entry["notified"] = True
            handled.append(key)
    return handled


def run(
    settings: WatcherSettings | None = None,
    *,
    max_cycles: int | None = None,
    sleep=time.sleep,
    runner=subprocess.run,
) -> int:
    """Poll forever (or ``max_cycles`` times for tests).

    A disabled or unconfigured watcher returns immediately without touching
    rclone. Every per-cycle failure is logged and the loop continues.
    """
    settings = settings or load_settings()
    if not settings.enabled:
        logger.info(
            "ingest watcher: disabled (set ingest_watcher.enabled or INGEST_WATCHER_ENABLED=1)"
        )
        return 0
    if not settings.remote:
        logger.warning("ingest watcher: enabled but remote is empty; nothing to watch")
        return 0

    state = WatcherState.load(settings.state_file)
    notifier = SignalNotifier(
        url=settings.signal_url,
        sender=settings.signal_sender,
        recipients=settings.signal_recipients,
    )
    if not notifier.enabled:
        logger.info("ingest watcher: notify disabled (no signal sender/recipients); detection-only")

    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        try:
            files = list_remote_files(settings, runner=runner)
            handled = run_cycle(settings, state, files, time.time(), notifier)
            state.save()
            if handled:
                logger.info("ingest watcher: notified %d new recording(s)", len(handled))
        except Exception as exc:  # noqa: BLE001 - one bad poll must not stop the watcher
            logger.warning("ingest watcher: poll failed: %s", exc)
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep(settings.poll_interval_seconds)
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
