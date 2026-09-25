"""Run the job queue worker without a browser session."""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

from ui.job_queue import JobQueue

WORKER_STARTED_MESSAGE = "worker started, owns lease"

logger = logging.getLogger(__name__)


def build_worker_queue() -> JobQueue:
    """Build a queue that is allowed to claim and execute jobs."""
    return JobQueue(run_workers=True)


def _owns_lease(queue: JobQueue) -> bool:
    return bool(getattr(queue, "_owns_lease", True))


def run_worker(queue: JobQueue, shutdown: threading.Event) -> None:
    """Start a queue, wait for shutdown, and release its resources."""
    try:
        queue.start()
        while not _owns_lease(queue) and not shutdown.wait(0.1):
            pass
        if _owns_lease(queue) and not shutdown.is_set():
            logger.info(WORKER_STARTED_MESSAGE)
        shutdown.wait()
    finally:
        queue.stop()


def main() -> None:
    """Run the worker until SIGTERM or SIGINT requests shutdown."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    shutdown = threading.Event()
    previous_handlers: dict[signal.Signals, object] = {}

    def request_shutdown(signum: int, frame: FrameType | None) -> None:
        shutdown.set()

    for signal_number in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signal_number] = signal.getsignal(signal_number)
        signal.signal(signal_number, request_shutdown)

    try:
        run_worker(build_worker_queue(), shutdown)
    finally:
        for signal_number, handler in previous_handlers.items():
            signal.signal(signal_number, handler)


if __name__ == "__main__":
    main()
