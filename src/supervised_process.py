"""Supervised external commands with cooperative cancellation.

The job queue cancels cooperatively: a running executor polls a cancel hook
(``ui.job_executors._raise_if_job_cancelled``, wrapped inside the pipeline by
``process_new_sermon``'s ``_check_cancelled``) and stops. ``subprocess.run``
blocks until the child exits, so a cancel during a long ffmpeg encode, an
rclone copy or an audio preprocessing script left the child running and the
single worker blocked until it finished on its own.

:func:`run_supervised` starts the child with :class:`subprocess.Popen` and
polls the hook every ``poll_interval`` seconds. On cancel it asks the child's
process group to stop (``terminate``), waits a short grace period, then kills
it, moves any partial output named in ``partial_paths`` into the trash area per
``src/safe_delete.py``, and raises :class:`ProcessCancelled` so the job goes
terminal as cancelled. If the child ignores ``terminate`` the hard kill is the
fallback, so the worker is never left blocked.

When no cancel hook, output callback, or activity context is supplied the call
is a plain ``subprocess.run``. The CLI and one-shot renders keep their existing
behaviour, and code that patches ``subprocess.run`` is unaffected.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_TERMINATE_GRACE_SECONDS = 10.0

_ACTIVITY_CALLBACK: ContextVar[Callable[[], None] | None] = ContextVar(
    "supervised_activity_callback", default=None
)

_TRASH_META_KEYS = ("sermon_id", "job_id", "stage", "config")


@contextmanager
def activity_context(callback: Callable[[], None] | None) -> Iterator[None]:
    """Publish liveness from supervised children in the current execution context."""
    token = _ACTIVITY_CALLBACK.set(callback)
    try:
        yield
    finally:
        _ACTIVITY_CALLBACK.reset(token)


def _notify_activity() -> None:
    callback = _ACTIVITY_CALLBACK.get()
    if callback is None:
        return
    try:
        callback()
    except Exception:
        logger.debug("Supervised activity callback failed", exc_info=True)


class ProcessCancelled(Exception):
    """Raised by :func:`run_supervised` after a cancelled child is stopped.

    A dedicated type lets a stage distinguish "the user cancelled" from an
    ordinary command failure, so a broad ``except Exception`` around a render
    cannot mistake a cancellation for a failed encode. ``original`` carries the
    exception the cancel hook raised, when there was one.
    """

    def __init__(self, message: str, *, original: BaseException | None = None) -> None:
        super().__init__(message)
        self.original = original


def _signal_process(proc: subprocess.Popen, pgid: int | None, sig: int) -> None:
    """Signal the child's whole process group, falling back to the child."""
    if pgid is not None:
        try:
            os.killpg(pgid, sig)
            return
        except ProcessLookupError:
            return
        except Exception:
            pass
    try:
        if sig == signal.SIGTERM:
            proc.terminate()
        else:
            proc.kill()
    except Exception:
        pass


def terminate_process(
    proc: subprocess.Popen, grace_seconds: float = DEFAULT_TERMINATE_GRACE_SECONDS
) -> bool:
    """Stop a child process, escalating from terminate to kill.

    The child runs in its own session (:func:`run_supervised` passes
    ``start_new_session``), so the signal reaches grandchildren a shell wrapper
    left behind rather than only the top process. Returns True when the process
    had to be hard-killed, False when it exited after ``terminate`` (or had
    already exited). Never raises.
    """
    if proc.poll() is not None:
        return False
    pgid: int | None = None
    if hasattr(os, "killpg"):
        try:
            pgid = os.getpgid(proc.pid)
        except Exception:
            pgid = None
    _signal_process(proc, pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace_seconds)
        return False
    except Exception:
        pass
    _signal_process(proc, pgid, signal.SIGKILL)
    try:
        proc.wait(timeout=5.0)
    except Exception:
        pass
    return True


def _drain(
    stream: Any,
    sink: list,
    on_output: Callable[[str], None] | None = None,
) -> None:
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            sink.append(chunk)
            _notify_activity()
            if on_output is not None:
                try:
                    text = (
                        chunk.decode("utf-8", errors="replace")
                        if isinstance(chunk, bytes)
                        else chunk
                    )
                    on_output(text)
                except Exception:
                    logger.debug("Supervised output callback failed", exc_info=True)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _trash_partials(
    partial_paths: Sequence[str | Path] | None,
    reason: str,
    meta: dict[str, Any] | None,
) -> None:
    if not partial_paths:
        return
    try:
        from src.safe_delete import trash_local
    except ImportError:  # src dir placed directly on sys.path
        from safe_delete import trash_local  # type: ignore[no-redef]

    kwargs = {key: (meta or {}).get(key) for key in _TRASH_META_KEYS if (meta or {}).get(key)}
    for raw in partial_paths:
        if not raw:
            continue
        candidate = Path(str(raw))
        try:
            if not candidate.exists() and not candidate.is_symlink():
                continue
        except OSError:
            continue
        try:
            trash_local(candidate, reason=reason, **kwargs)
        except Exception as exc:
            logger.warning("Could not move partial output %s to trash: %s", candidate, exc)


def _emit(log: Callable[[str], None] | None, message: str) -> None:
    logger.info("%s", message)
    if log is None:
        return
    try:
        log(message)
    except Exception:
        logger.debug("Cancel log callback failed", exc_info=True)


def _file_sizes(paths: Sequence[str | Path]) -> dict[Path, int | None]:
    sizes: dict[Path, int | None] = {}
    for raw_path in paths:
        path = Path(str(raw_path))
        try:
            sizes[path] = path.stat().st_size
        except OSError:
            sizes[path] = None
    return sizes


def _output_grew(paths: dict[Path, int | None]) -> bool:
    grew = False
    for path, previous in paths.items():
        try:
            current = path.stat().st_size
        except OSError:
            current = None
        if current is not None and (previous is None or current > previous):
            paths[path] = current
            grew = True
    return grew


def run_supervised(
    cmd: Sequence[str],
    *,
    cancel_check: Callable[[], None] | None = None,
    step: str | None = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    terminate_grace: float = DEFAULT_TERMINATE_GRACE_SECONDS,
    timeout: float | None = None,
    capture_output: bool = False,
    text: bool = False,
    check: bool = False,
    on_output: Callable[[str], None] | None = None,
    log: Callable[[str], None] | None = None,
    partial_paths: Sequence[str | Path] | None = None,
    partial_reason: str = "cancelled_process_partial",
    partial_meta: dict[str, Any] | None = None,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run ``cmd``, polling ``cancel_check`` and stopping the child on cancel.

    Without ``cancel_check``, ``on_output``, or an activity context this defers
    to :func:`subprocess.run`, so callers that never requested supervision keep
    their exact behaviour. With a hook, the child is supervised and the call
    raises :class:`ProcessCancelled` after the child is stopped. An activity
    context receives child output and growth of ``partial_paths``. Partial
    outputs are moved into the trash root on cancellation.
    """
    activity_callback = _ACTIVITY_CALLBACK.get()
    if cancel_check is None and on_output is None and activity_callback is None:
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            check=check,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )

    label = step or (Path(str(cmd[0])).name if cmd else "command")
    stdout_pipe = subprocess.PIPE if capture_output or on_output is not None else None
    stderr_pipe = subprocess.PIPE if capture_output else None

    proc = subprocess.Popen(
        cmd,
        stdout=stdout_pipe,
        stderr=stderr_pipe,
        text=text,
        cwd=cwd,
        env=env,
        start_new_session=(os.name == "posix"),
    )
    _notify_activity()

    out_chunks: list = []
    err_chunks: list = []
    readers: list[threading.Thread] = []
    if capture_output or on_output is not None:
        for stream, sink in ((proc.stdout, out_chunks), (proc.stderr, err_chunks)):
            if stream is None:
                continue
            stream_callback = on_output if stream is proc.stdout else None
            thread = threading.Thread(
                target=_drain,
                args=(stream, sink, stream_callback),
                daemon=True,
            )
            thread.start()
            readers.append(thread)

    tracked_sizes = _file_sizes(partial_paths or ())
    started = time.monotonic()
    timed_out = False
    while proc.poll() is None:
        if timeout is not None and time.monotonic() - started > timeout:
            timed_out = True
            break
        if cancel_check is not None:
            try:
                cancel_check()
            except BaseException as exc:  # re-raised verbatim after the child stops
                stop_started = time.monotonic()
                _emit(log, f"Cancel requested - stopping {label}")
                hard_killed = terminate_process(proc, terminate_grace)
                for thread in readers:
                    thread.join(timeout=5.0)
                _trash_partials(partial_paths, partial_reason, partial_meta)
                elapsed = time.monotonic() - stop_started
                suffix = " (hard kill)" if hard_killed else ""
                message = f"Cancelled during {label} (stopped after {elapsed:.0f}s){suffix}"
                _emit(log, message)
                raise ProcessCancelled(message, original=exc) from exc
        if _output_grew(tracked_sizes):
            _notify_activity()
        time.sleep(max(poll_interval, 0.0))

    if timed_out:
        terminate_process(proc, terminate_grace)
        for thread in readers:
            thread.join(timeout=5.0)
        stdout = "".join(out_chunks) if text else b"".join(out_chunks)
        stderr = "".join(err_chunks) if text else b"".join(err_chunks)
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)

    proc.wait()
    for thread in readers:
        thread.join(timeout=5.0)
    stdout = "".join(out_chunks) if text else b"".join(out_chunks)
    stderr = "".join(err_chunks) if text else b"".join(err_chunks)
    completed = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=stdout, stderr=stderr
        )
    return completed
