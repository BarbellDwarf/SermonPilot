"""
Background Job Queue System for SermonPilot

Provides asynchronous job execution with progress tracking, allowing users
to navigate away from pages while jobs continue running in the background.

Features:
- Thread-based job execution
- Job persistence in database
- Progress tracking and status updates
- Multiple job types (validation, processing, import, etc.)
- Job cancellation and retry capabilities
- UI-friendly status reporting
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

# Add project paths for imports
ui_dir = Path(__file__).parent
project_root = ui_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

logger = logging.getLogger(__name__)

_SECRET_KEY_SUFFIXES = ('_key', '_token', '_secret', '_password', '_passwd')
_SECRET_KEY_NAMES = frozenset({'password', 'passwd', 'token', 'secret', 'auth', 'authorization'})

# Result payload keys that are too bulky to persist with every job record
_RESULT_STRIP_FIELDS = frozenset({'transcript'})

# JobResult dataclass fields. Persisted result dicts with extra keys (e.g.
# self-managed edit-apply rows) are coerced: extras fold into data.
_RESULT_FIELDS = frozenset({'success', 'message', 'data', 'error'})

# Terminal jobs older than this are pruned from memory and the database
JOB_RETENTION_DAYS = 30

# Debounced persistence: a running job writes progress/logs at most once per
# this interval so high-frequency callbacks do not hammer SQLite. The queue
# flusher and every explicit terminal write bypass the window.
JOB_PERSIST_MIN_INTERVAL_SECONDS = 2.0
# The persistence flusher wakes this often and writes dirty jobs whose debounce
# window elapsed, so a separate sqlite connection observes a running job's
# progress and logs within ~5 seconds.
JOB_PERSIST_POLL_INTERVAL_SECONDS = 0.5
# Chunked executors poll the cancel check at least once per chunk. This is the
# documented worst-case delay between a cancel request and the worker noticing
# it when loop iterations sleep no longer than this value. The only longer case
# is a single uninterruptible native call (one CTranslate2 decode, one ffmpeg
# or DeepFilterNet call, one HTTP upload request); that delay is bounded by the
# call's own timeout, not by this poll interval.
JOB_CANCEL_POLL_INTERVAL_SECONDS = 1.0

# Exactly one process runs job workers against a given database. Ownership is a
# single row in ``job_worker_lease`` that the owner renews on a heartbeat. A
# lease whose heartbeat is older than this is treated as dead and may be taken
# over, and reconciliation only reaps an in-flight job whose recorded owner is
# not the live lease holder. The timeout must exceed the heartbeat interval by
# enough that a healthy owner is never declared dead between beats.
JOB_LEASE_TIMEOUT_SECONDS = 30.0
JOB_HEARTBEAT_INTERVAL_SECONDS = 5.0


def _is_secret_key(key: str) -> bool:
    """Return True if a parameter key should never be persisted."""
    lowered = key.lower()
    return lowered in _SECRET_KEY_NAMES or lowered.endswith(_SECRET_KEY_SUFFIXES)


def _strip_secrets(value: Any) -> Any:
    """Recursively remove secret keys from a nested structure."""
    if isinstance(value, dict):
        return {
            key: _strip_secrets(item)
            for key, item in value.items()
            if not _is_secret_key(key)
        }
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


_JOB_OPTIONAL_COLUMNS: dict[str, str] = {
    "user_id": "TEXT",
    "cancelled": "INTEGER DEFAULT 0",
    "owner_id": "TEXT",
    "heartbeat_at": "TIMESTAMP",
}

_JOB_LEASE_TABLE = "job_worker_lease"


def _ensure_lease_table(conn) -> bool:
    """Create the single-row worker lease table if it is missing."""
    try:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_JOB_LEASE_TABLE} ("
            " id INTEGER PRIMARY KEY CHECK (id = 1),"
            " worker_id TEXT NOT NULL,"
            " acquired_at TEXT NOT NULL,"
            " heartbeat_at TEXT NOT NULL)"
        )
        return True
    except Exception:
        return False


def _read_live_lease_owner(conn) -> str | None:
    """Return the worker id holding a fresh lease, or None when there is none."""
    try:
        row = conn.execute(
            f"SELECT worker_id, heartbeat_at FROM {_JOB_LEASE_TABLE} WHERE id = 1"
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    try:
        heartbeat = datetime.fromisoformat(row["heartbeat_at"])
    except (TypeError, ValueError):
        return None
    if datetime.now() - heartbeat > timedelta(seconds=JOB_LEASE_TIMEOUT_SECONDS):
        return None
    return row["worker_id"]



def _ensure_job_columns(conn) -> set[str]:
    """Add optional background_jobs columns on demand; return those present.

    Both columns are additive migrations for databases created before they
    existed. A caller that cannot read the schema (table absent) gets an empty
    set and must fall back to the baseline column list.
    """
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(background_jobs)").fetchall()}
    except Exception:
        return set()
    present = set(cols)
    for name, decl in _JOB_OPTIONAL_COLUMNS.items():
        if name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE background_jobs ADD COLUMN {name} {decl}")
            present.add(name)
        except Exception:
            pass
    if "user_id" in present:
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_background_jobs_user_id ON background_jobs(user_id)"
            )
        except Exception:
            pass
    return present


class JobType(Enum):
    """Available job types"""
    VALIDATION = "validation"
    SERMON_PROCESSING = "sermon_processing"
    BATCH_PROCESSING = "batch_processing"
    SERMON_IMPORT = "sermon_import"
    AUDIO_ENHANCEMENT = "audio_enhancement"
    TRANSCRIPT_GENERATION = "transcript_generation"
    METADATA_UPDATE = "metadata_update"
    AUTO_EDIT = "auto_edit"
    AUTO_EDIT_APPLY = "auto_edit_apply"
    SERMON_PUBLISH = "sermon_publish"


class JobStatus(Enum):
    """Job execution status"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class JobCancelledError(Exception):
    """Raised when a job is cancelled while it is executing."""


_TERMINAL_JOB_STATUSES = frozenset({
    JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED,
})

# States where a worker owned the job. A worker thread is a daemon that dies
# with the process, so after a restart none of these can still be running.
# QUEUED is deliberately absent: a fresh worker can and should claim it.
IN_FLIGHT_JOB_STATUSES = frozenset({JobStatus.RUNNING, JobStatus.PAUSED})

# Stable phrase used in the result payload so the write-path guard can tell a
# restart-reconciled job from one that completed on its own.
INTERRUPTED_BY_RESTART_MARKER = "interrupted by app restart"
_INTERRUPTED_LOG_LINE = "Job interrupted by app restart"


def _interruption_result(cancelled: bool) -> JobResult:
    """Honest terminal outcome for a job whose worker died with the process.

    No artifact is registered: the result carries no output paths, so a
    partially written file is never recorded as finished work.
    """
    if cancelled:
        return JobResult(
            success=False,
            message=f"Job cancelled and {INTERRUPTED_BY_RESTART_MARKER}",
            error=(
                f"Job cancelled and {INTERRUPTED_BY_RESTART_MARKER}: a cancel was "
                "requested before the app restarted, so this job is marked cancelled. "
                "Any completed output was kept."
            ),
        )
    return JobResult(
        success=False,
        message=f"Job {INTERRUPTED_BY_RESTART_MARKER}",
        error=(
            f"Job {INTERRUPTED_BY_RESTART_MARKER}: the app restarted while this job "
            "was running and its worker no longer exists. Completed output was kept; "
            "a partially written output was not registered. Retry to run it again."
        ),
    )


def _append_log_line(existing_json: str | None, line: str) -> str:
    """Append a timestamped line to a persisted logs JSON array, never wiping it."""
    try:
        logs = json.loads(existing_json) if existing_json else []
    except (json.JSONDecodeError, TypeError):
        logs = []
    if not isinstance(logs, list):
        logs = []
    stamp = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{stamp}] {line}")
    return json.dumps(logs)


def _mark_job_interrupted(job: Job) -> None:
    """Flip an in-memory in-flight job to its restart-terminal state."""
    was_cancelled = bool(job.cancelled)
    job.status = JobStatus.CANCELLED if was_cancelled else JobStatus.FAILED
    job.completed_at = datetime.now()
    job.add_log(_INTERRUPTED_LOG_LINE)
    job.result = _interruption_result(was_cancelled)


def _resolve_reconcile_db_path(db_path: str | None = None) -> str:
    """Resolve the SQLite file to reconcile, tolerating a sqlite:/// URL."""
    raw = (
        db_path
        or os.environ.get("SERMONPILOT_DB")
        or os.environ.get("DATABASE_URL")
        or "sermon_processor.db"
    )
    if raw.startswith("sqlite:///"):
        remainder = raw[len("sqlite:///"):]
        if not remainder.startswith("/"):
            remainder = "/" + remainder
        return remainder
    return raw


def reconcile_interrupted_jobs(db_path: str | None = None) -> int:
    """Mark in-flight jobs whose owner is provably gone as terminal.

    This is the startup reconciliation for a process that does not hold the
    jobs in memory (the API bridge reads the store directly). It is idempotent:
    a second run finds no in-flight rows and changes nothing. Terminal rows are
    never touched. Existing logs are preserved and appended to, and the result
    is replaced with an interruption outcome that registers no artifact.

    Ownership is explicit: a live worker renews the ``job_worker_lease`` row on
    a heartbeat. An in-flight job whose ``owner_id`` is the live lease holder is
    left alone, however this process is started; only rows whose owner is gone
    (no live lease, a different worker id, or no recorded owner) are reaped.
    """
    path = _resolve_reconcile_db_path(db_path)
    if not os.path.isfile(path):
        return 0
    statuses = tuple(sorted(status.value for status in IN_FLIGHT_JOB_STATUSES))
    placeholders = ",".join("?" for _ in statuses)
    reconciled = 0
    try:
        conn = sqlite3.connect(path, timeout=30.0)
    except sqlite3.Error:
        logger.error("Could not open job store for reconciliation: %s", path)
        return 0
    try:
        conn.row_factory = sqlite3.Row
        present = _ensure_job_columns(conn)
        _ensure_lease_table(conn)
        live_owner = _read_live_lease_owner(conn)
        select_cols = "id, logs" + (", cancelled" if "cancelled" in present else "")
        if "owner_id" in present:
            select_cols += ", owner_id"
        rows = conn.execute(
            f"SELECT {select_cols} FROM background_jobs WHERE status IN ({placeholders})",
            statuses,
        ).fetchall()
        for row in rows:
            owner = row["owner_id"] if "owner_id" in present else None
            if live_owner is not None and owner == live_owner:
                logger.info(
                    "Leaving job %s running: it is owned by live worker %s",
                    row["id"],
                    live_owner,
                )
                continue
            cancelled = bool(row["cancelled"]) if "cancelled" in present else False
            target = JobStatus.CANCELLED.value if cancelled else JobStatus.FAILED.value
            result_json = json.dumps(_result_for_persistence(_interruption_result(cancelled)))
            logs_json = _append_log_line(row["logs"], _INTERRUPTED_LOG_LINE)
            guard = ""
            params: list[Any] = [
                target,
                datetime.now().isoformat(),
                result_json,
                logs_json,
                row["id"],
                *statuses,
            ]
            if "owner_id" in present and live_owner is not None:
                guard = " AND (owner_id IS NULL OR owner_id != ?)"
                params.append(live_owner)
            cursor = conn.execute(
                "UPDATE background_jobs SET status = ?, completed_at = ?, result = ?, logs = ?"
                f" WHERE id = ? AND status IN ({placeholders})" + guard,
                params,
            )
            reconciled += max(cursor.rowcount, 0)
        conn.commit()
    except sqlite3.OperationalError:
        return 0
    except Exception:
        logger.exception("Startup job reconciliation failed")
        return reconciled
    finally:
        conn.close()
    if reconciled:
        logger.warning(
            "Reconciled %d interrupted job(s) left by a previous restart.", reconciled
        )
    return reconciled


@dataclass
class JobResult:
    """Job execution result"""
    success: bool
    message: str
    data: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class Job:
    """Background job definition"""
    id: str
    type: JobType
    title: str
    description: str
    status: JobStatus
    progress: float  # 0-100
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    parameters: dict[str, Any] | None = None
    result: JobResult | None = None
    logs: list[str] | None = None
    can_cancel: bool = True
    can_retry: bool = True
    priority: int = 5  # 1-10, higher is more priority
    cancelled: bool = False
    user_id: str | None = None

    def __post_init__(self):
        if self.logs is None:
            self.logs = []
        # Transient persistence coordination. These are plain instance
        # attributes rather than dataclass fields so Job.to_dict() and the
        # persisted background_jobs schema stay unchanged.
        self._on_update: Callable[[Job], None] | None = None
        self._dirty = False
        self._force_persist = False
        self._last_persist_at = 0.0
        # Ownership recorded in the store. Transient, like the persistence
        # coordination above, so the dataclass and persisted schema are
        # unchanged; reconciliation reads it to tell a live job from an orphan.
        self._owner_id: str | None = None

    def add_log(self, message: str):
        """Append a log line and notify the persister."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        self._notify_update()

    def update_progress(self, progress: float, message: str = ""):
        """Update job progress and notify the persister."""
        self.progress = max(0, min(100, progress))
        if message:
            self.add_log(message)
        else:
            self._notify_update()

    def request_persist(self):
        """Force an immediate write, e.g. before a long blocking stage.

        Debounced updates would otherwise leave the last log line invisible
        for the whole duration of a multi-minute call.
        """
        self._force_persist = True
        self._notify_update()

    def _notify_update(self):
        """Invoke the queue's persistence hook when one is registered."""
        hook = self._on_update
        if hook is None:
            return
        try:
            hook(self)
        except Exception:
            logger.debug("Job update hook failed for %s", self.id, exc_info=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary for storage/serialization"""
        data = asdict(self)
        # Convert enums to strings
        data['type'] = self.type.value
        data['status'] = self.status.value
        # Convert datetime to ISO string
        data['created_at'] = self.created_at.isoformat() if self.created_at else None
        data['started_at'] = self.started_at.isoformat() if self.started_at else None
        data['completed_at'] = self.completed_at.isoformat() if self.completed_at else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Create job from dictionary"""
        # Convert strings back to enums
        data['type'] = JobType(data['type'])
        data['status'] = JobStatus(data['status'])
        # Convert ISO strings back to datetime
        for field in ['created_at', 'started_at', 'completed_at']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # Handle result if present
        if data.get('result'):
            data['result'] = _coerce_job_result(data['result'])

        return cls(**data)


def _coerce_job_result(data: dict[str, Any]) -> JobResult:
    """Build a JobResult from a persisted dict, tolerating extra keys.

    Self-managed flows (edit applies) write compact result dicts such as
    {"success": ..., "render_only": ..., "elapsed_seconds": ...} straight
    to background_jobs.result. Unknown keys fold into data so the Jobs page
    parses those rows instead of logging a parse error per row per refresh.
    """
    known = {k: v for k, v in data.items() if k in _RESULT_FIELDS}
    extras = {k: v for k, v in data.items() if k not in _RESULT_FIELDS}
    payload = known.get('data')
    if extras:
        if isinstance(payload, dict):
            payload = {**payload, **extras}
        elif payload is None:
            payload = extras
        known['data'] = payload
    if 'success' not in known:
        known['success'] = False
    if 'message' not in known:
        known['message'] = ''
    return JobResult(**known)


def _result_for_persistence(result: JobResult) -> dict[str, Any]:
    """Serialize a JobResult without bulky payload fields (e.g. transcripts).

    Transcripts can be megabytes of text and are already stored in
    sermon_content; keeping them in background_jobs.result bloats the
    database forever since job rows have no size bound.
    """
    data = asdict(result)
    payload = data.get('data')
    if isinstance(payload, dict):
        data['data'] = {k: v for k, v in payload.items() if k not in _RESULT_STRIP_FIELDS}
    return data


class JobQueue:
    """Thread-safe job queue manager"""

    def __init__(self, max_workers: int = 1, run_workers: bool = True,
                 worker_id: str | None = None):
        self.max_workers = max_workers
        self.run_workers = run_workers
        self.worker_id = worker_id or uuid.uuid4().hex
        self._owns_lease = False
        self._jobs: dict[str, Job] = {}
        self._queue_lock = threading.Lock()
        self._workers: list[threading.Thread] = []
        self._running = False
        self._shutdown_event = threading.Event()
        self._resource_wait_logged_at = 0.0
        self._persist_lock = threading.Lock()
        self._persist_wake = threading.Event()
        self._persister: threading.Thread | None = None
        self._last_heartbeat_at = 0.0
        self._last_cancel_poll_at = 0.0

        # Initialize database connection
        self._init_database()

    def _init_database(self):
        """Initialize job storage in database"""
        try:
            from ui.database import get_db
            self.db = get_db()

            # Create jobs table if it doesn't exist
            with self.db.get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS background_jobs (
                        id TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT,
                        status TEXT NOT NULL,
                        progress REAL DEFAULT 0,
                        parameters TEXT,
                        result TEXT,
                        logs TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        can_cancel BOOLEAN DEFAULT 1,
                        can_retry BOOLEAN DEFAULT 1,
                        priority INTEGER DEFAULT 5,
                        cancelled INTEGER DEFAULT 0
                    )
                """)
                _ensure_job_columns(conn)
                _ensure_lease_table(conn)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize job database: {e}")
            self.db = None

    def start(self):
        """Start the job queue workers.

        A process only runs workers when it holds the single worker lease, so
        two processes over the same database can never both claim jobs. A
        submit-only queue (``run_workers=False``) starts nothing and only
        submits or reads jobs.
        """
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()

        # Prune terminal jobs past the retention window before loading
        self.prune_old_jobs()

        # Load existing jobs from database
        self._load_jobs_from_db()

        if not self.run_workers:
            self._owns_lease = False
            logger.info("Job queue started in submit-only mode (no worker)")
            return

        self._owns_lease = self._acquire_worker_lease()
        if not self._owns_lease:
            logger.warning(
                "Job queue did not start a worker: another live worker owns the lease"
            )
            return

        # Recover orphaned jobs left in RUNNING state by a previous owner
        self._recover_orphaned_jobs()

        # Start worker threads
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"JobWorker-{i+1}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)

        # Flush debounced job state while workers are blocked in a stage.
        self._persister = threading.Thread(
            target=self._persist_loop, name="JobPersister", daemon=True
        )
        self._persister.start()

        logger.info(f"Job queue started with {self.max_workers} workers")

    def _acquire_worker_lease(self) -> bool:
        """Take the single worker lease when no live worker holds it."""
        if not self.db:
            return True
        now = datetime.now()
        stale_before = now - timedelta(seconds=JOB_LEASE_TIMEOUT_SECONDS)
        try:
            with self.db.get_connection() as conn:
                _ensure_lease_table(conn)
                row = conn.execute(
                    f"SELECT worker_id, heartbeat_at FROM {_JOB_LEASE_TABLE} WHERE id = 1"
                ).fetchone()
                if row is not None:
                    try:
                        heartbeat = datetime.fromisoformat(row["heartbeat_at"])
                    except (TypeError, ValueError):
                        heartbeat = stale_before
                    if heartbeat > stale_before and row["worker_id"] != self.worker_id:
                        return False
                conn.execute(
                    f"INSERT OR REPLACE INTO {_JOB_LEASE_TABLE}"
                    " (id, worker_id, acquired_at, heartbeat_at) VALUES (1, ?, ?, ?)",
                    (self.worker_id, now.isoformat(), now.isoformat()),
                )
                conn.commit()
            self._last_heartbeat_at = time.monotonic()
            return True
        except Exception as e:
            logger.error("Failed to acquire worker lease: %s", e)
            return False

    def _renew_worker_lease(self) -> bool:
        """Refresh this worker's lease heartbeat; False when the lease was lost."""
        if not self._owns_lease or not self.db:
            return True
        now = datetime.now()
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    f"UPDATE {_JOB_LEASE_TABLE} SET heartbeat_at = ?"
                    " WHERE id = 1 AND worker_id = ?",
                    (now.isoformat(), self.worker_id),
                )
                conn.commit()
            self._last_heartbeat_at = time.monotonic()
            return cursor.rowcount > 0
        except Exception:
            return True

    def _release_worker_lease(self) -> None:
        """Drop this worker's lease so a successor can start immediately."""
        if not self._owns_lease or not self.db:
            self._owns_lease = False
            return
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    f"DELETE FROM {_JOB_LEASE_TABLE} WHERE id = 1 AND worker_id = ?",
                    (self.worker_id,),
                )
                conn.commit()
        except Exception:
            pass
        self._owns_lease = False

    def _recover_orphaned_jobs(self):
        """Reconcile in-flight jobs left by a previous owner.

        Only jobs whose recorded owner is not this worker are reaped: this
        worker has just taken the lease, so any other owner is gone. A job this
        worker itself owns cannot exist yet. Mark each orphan terminal, as
        CANCELLED when its cancel flag was already set, so the operator can
        review and retry from the Jobs page. Existing logs are appended to,
        never replaced.
        """
        recovered_jobs = []
        with self._queue_lock:
            for job in self._jobs.values():
                if (
                    job.status in IN_FLIGHT_JOB_STATUSES
                    and getattr(job, "_owner_id", None) != self.worker_id
                ):
                    _mark_job_interrupted(job)
                    recovered_jobs.append(job)

        for job in recovered_jobs:
            self._save_job_to_db(job)

        if recovered_jobs:
            logger.warning(
                f"Reconciled {len(recovered_jobs)} interrupted job(s) left by a "
                f"previous restart."
            )

    def prune_old_jobs(self, days: int = JOB_RETENTION_DAYS) -> int:
        """Delete terminal jobs older than the retention window.

        Removes completed/failed/cancelled jobs whose completed_at predates
        the cutoff from both the database and the in-memory dict, so startup
        never reloads an unbounded history of job rows.
        """
        if not self.db:
            return 0

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        status_values = [status.value for status in _TERMINAL_JOB_STATUSES]
        placeholders = ','.join(['?' for _ in status_values])
        removed = 0

        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(f"""
                    DELETE FROM background_jobs
                    WHERE status IN ({placeholders})
                      AND completed_at IS NOT NULL AND completed_at < ?
                """, (*status_values, cutoff))
                conn.commit()
                removed = max(cursor.rowcount, 0)
        except Exception as e:
            logger.error(f"Failed to prune old jobs from database: {e}")

        with self._queue_lock:
            stale_ids = [
                job_id for job_id, job in self._jobs.items()
                if job.status in _TERMINAL_JOB_STATUSES
                and job.completed_at is not None
                and job.completed_at.isoformat() < cutoff
            ]
            for job_id in stale_ids:
                del self._jobs[job_id]

        if removed or stale_ids:
            logger.info(f"Pruned {removed} database / {len(stale_ids)} memory "
                        f"job(s) older than {days} days")
        return removed

    def stop(self):
        """Stop the job queue"""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()
        self._persist_wake.set()

        if self._persister is not None:
            self._persister.join(timeout=5.0)
            self._persister = None

        # Wait for workers to finish
        for worker in self._workers:
            worker.join(timeout=5.0)

        self._workers.clear()
        self._release_worker_lease()
        logger.info("Job queue stopped")

    def add_job(self, job_type: JobType, title: str, description: str,
                parameters: dict[str, Any] | None = None,
                priority: int = 5, user_id: str | None = None) -> str:
        """Add a new job to the queue"""
        job_id = str(uuid.uuid4())

        job = Job(
            id=job_id,
            type=job_type,
            title=title,
            description=description,
            status=JobStatus.QUEUED,
            progress=0.0,
            created_at=datetime.now(),
            parameters=parameters or {},
            priority=priority,
            user_id=user_id,
        )

        # Persist before publishing to the queue so workers only ever see a
        # job whose initial state is already durable, and so the SQLite write
        # never happens under the queue lock.
        self._save_job_to_db(job)

        with self._queue_lock:
            self._jobs[job_id] = job

        job.add_log(f"Job created: {title}")
        logger.info(f"Added job {job_id}: {title}")

        return job_id

    def get_job(self, job_id: str) -> Job | None:
        """Get job by ID"""
        with self._queue_lock:
            return self._jobs.get(job_id)

    def get_all_jobs(self, status_filter: JobStatus | None = None) -> list[Job]:
        """Get all jobs, optionally filtered by status"""
        with self._queue_lock:
            jobs = list(self._jobs.values())

        jobs = self._merge_db_jobs(jobs)

        if status_filter:
            jobs = [job for job in jobs if job.status == status_filter]

        # Sort by priority (descending) then by created_at (ascending)
        jobs.sort(key=lambda j: (-j.priority, j.created_at))
        return jobs

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job from any process.

        The cancel is always recorded in the store first, so a worker running
        in another process sees the flag on its next poll. When the job lives
        in this instance the in-memory state is flipped too, which stops the
        running executor immediately; a submit-only queue never rewrites the
        whole row, it only flips the flag.
        """
        with self._queue_lock:
            job = self._jobs.get(job_id)
            local = bool(
                job
                and job.can_cancel
                and job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
            )
            if local:
                job.cancelled = True
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now()
                job.add_log("Job cancelled by user")
                logger.info(f"Cancelled job {job_id}")

        if local and job is not None and self._owns_lease:
            self._save_job_to_db(job)

        db_cancelled = self._cancel_job_in_db(job_id)
        return local or db_cancelled

    def _cancel_job_in_db(self, job_id: str) -> bool:
        """Flip the store's cancel flag for a queued/running job, if any."""
        if self.db is None:
            return False
        try:
            with self.db.get_connection() as conn:
                _ensure_job_columns(conn)
                cursor = conn.execute(
                    "UPDATE background_jobs SET cancelled = 1, status = 'cancelled',"
                    " completed_at = datetime('now')"
                    " WHERE id = ? AND status IN ('queued', 'running') AND can_cancel = 1",
                    (job_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"DB cancel failed for {job_id}: {e}")
            return False

    def retry_job(self, job_id: str) -> bool:
        """Retry a failed, cancelled, or completed job"""
        retried = False
        with self._queue_lock:
            job = self._jobs.get(job_id)
            if job and job.can_retry:
                if job.status in [JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED]:
                    job.cancelled = False
                    job.status = JobStatus.QUEUED
                    job.progress = 0.0
                    job.started_at = None
                    job.completed_at = None
                    job.result = None
                    job.add_log("Job queued for retry")
                    retried = True
                    logger.info(f"Retrying job {job_id}")

        if retried:
            self._save_job_to_db(job)
        return retried

    def clear_completed_jobs(self) -> int:
        """Remove terminal jobs (completed, cancelled, failed) from queue"""
        removed_count = 0
        with self._queue_lock:
            cleared_ids = [
                job_id for job_id, job in self._jobs.items()
                if job.status in _TERMINAL_JOB_STATUSES
            ]

            for job_id in cleared_ids:
                del self._jobs[job_id]
                removed_count += 1

        # Also remove from database
        if self.db and cleared_ids:
            try:
                with self.db.get_connection() as conn:
                    placeholders = ','.join(['?' for _ in cleared_ids])
                    conn.execute(
                        f"DELETE FROM background_jobs WHERE id IN ({placeholders})",
                        cleared_ids
                    )
                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to clear completed jobs from database: {e}")

        logger.info(f"Cleared {removed_count} completed jobs")
        return removed_count

    def _worker_loop(self):
        """Main worker loop that processes jobs"""
        while self._running and not self._shutdown_event.is_set():
            try:
                # Do not claim a job without headroom; leave it queued and wait.
                if not self._resources_available():
                    time.sleep(10.0)
                    continue

                # Find next job to process
                job = self._get_next_job()
                if not job:
                    time.sleep(1.0)  # No jobs available, wait
                    continue

                # Execute the job
                try:
                    self._execute_job(job)
                except BaseException as e:
                    logger.exception("Unhandled exception executing job %s", job.id)
                    self._force_fail_job(job, e)

            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(1.0)

    def _persist_loop(self):
        """Flush debounced job state while workers are blocked executing."""
        while not self._shutdown_event.is_set():
            self._persist_wake.wait(timeout=JOB_PERSIST_POLL_INTERVAL_SECONDS)
            self._persist_wake.clear()
            try:
                if time.monotonic() - self._last_heartbeat_at >= JOB_HEARTBEAT_INTERVAL_SECONDS:
                    if not self._renew_worker_lease():
                        logger.warning(
                            "Worker lease lost for %s; stopping this worker",
                            self.worker_id,
                        )
                        self._shutdown_event.set()
                        return
                now = time.monotonic()
                if now - self._last_cancel_poll_at >= JOB_CANCEL_POLL_INTERVAL_SECONDS:
                    self._last_cancel_poll_at = now
                    self._sync_cancel_flags()
                self._flush_dirty_jobs()
            except Exception as e:
                logger.error(f"Job persistence flush failed: {e}")

    def _sync_cancel_flags(self):
        """Adopt cancel flags recorded in the store by another process.

        A running executor polls ``job.cancelled``; this makes a cancel issued
        through a different process visible within the cancel poll interval.
        """
        if self.db is None:
            return
        with self._queue_lock:
            candidates = {
                job.id: job
                for job in self._jobs.values()
                if job.status in (JobStatus.QUEUED, JobStatus.RUNNING) and not job.cancelled
            }
        if not candidates:
            return
        try:
            placeholders = ",".join("?" for _ in candidates)
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, cancelled, status FROM background_jobs"
                    f" WHERE id IN ({placeholders})",
                    list(candidates),
                ).fetchall()
        except Exception:
            return
        for row in rows:
            job = candidates.get(row["id"])
            if job is None:
                continue
            if bool(row["cancelled"]) or row["status"] == JobStatus.CANCELLED.value:
                job.cancelled = True
                job.add_log("Cancel requested by another process")
                logger.info("Synced cross-process cancel for job %s", job.id)

    def _flush_dirty_jobs(self):
        """Write running jobs whose debounce window has elapsed."""
        now = time.monotonic()
        with self._queue_lock:
            ready = [
                job for job in self._jobs.values()
                if getattr(job, "_dirty", False)
                and (
                    job._force_persist
                    or now - job._last_persist_at >= JOB_PERSIST_MIN_INTERVAL_SECONDS
                )
            ]
        for job in ready:
            job._dirty = False
            job._force_persist = False
            job._last_persist_at = now
            self._save_job_to_db(job)

    def _on_job_update(self, job: Job):
        """Persistence hook registered by _execute_job for the running job."""
        if job._force_persist:
            job._force_persist = False
            job._dirty = False
            job._last_persist_at = time.monotonic()
            self._save_job_to_db(job)
            return
        job._dirty = True
        self._persist_wake.set()

    def _force_fail_job(self, job: Job, exc: BaseException):
        """Guarantee a terminal FAILED state when an executor escapes its guard."""
        job._on_update = None
        with self._queue_lock:
            if job.status in _TERMINAL_JOB_STATUSES:
                return
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            if job.result is None:
                job.result = JobResult(
                    success=False, message="Job execution failed", error=str(exc)
                )
            job.add_log(f"Job failed with unhandled exception: {exc}")
        self._save_job_to_db(job)
        logger.error("Job %s failed with unhandled exception: %s", job.id, exc)

    def _resources_available(self) -> bool:
        """Return True when RAM (and VRAM, if present) headroom can take a job.

        Thresholds come from config job_queue.min_free_ram_gb (default 3) and
        job_queue.min_free_vram_gb (default 1.5). Jobs stay QUEUED while the
        check fails, so the UI shows them waiting instead of failing.
        """
        min_ram_gb = 3.0
        min_vram_gb = 1.5
        try:
            from ui.config_utils import resolve_config

            queue_cfg = resolve_config().get("job_queue", {}) or {}
            min_ram_gb = float(queue_cfg.get("min_free_ram_gb", min_ram_gb))
            min_vram_gb = float(queue_cfg.get("min_free_vram_gb", min_vram_gb))
        except Exception:
            pass

        try:
            import psutil

            free_ram_gb = psutil.virtual_memory().available / 1e9
            if free_ram_gb < min_ram_gb:
                self._log_resource_wait(
                    f"free RAM {free_ram_gb:.1f} GB below the {min_ram_gb:.1f} GB threshold"
                )
                return False
        except Exception:
            pass

        if min_vram_gb > 0:
            try:
                import torch

                if torch.cuda.is_available():
                    free_vram, _total = torch.cuda.mem_get_info()
                    free_vram_gb = free_vram / 1e9
                    if free_vram_gb < min_vram_gb:
                        self._log_resource_wait(
                            f"free VRAM {free_vram_gb:.1f} GB below the "
                            f"{min_vram_gb:.1f} GB threshold"
                        )
                        return False
            except Exception:
                pass

        return True

    def _log_resource_wait(self, reason: str) -> None:
        now = time.time()
        if now - self._resource_wait_logged_at >= 60.0:
            self._resource_wait_logged_at = now
            logger.info("Job queue waiting for resources: %s", reason)

    def _get_next_job(self) -> Job | None:
        """Claim the next queued job.

        The store is the source of truth when persistence is available: the
        claim is a single conditional UPDATE so only one worker can win a job,
        even across processes. Without persistence (in-memory tests) the local
        dict is used.
        """
        if self.db is not None:
            return self._claim_next_job_from_db()

        with self._queue_lock:
            queued_jobs = [
                job for job in self._jobs.values()
                if job.status == JobStatus.QUEUED
            ]

            if not queued_jobs:
                return None

            # Sort by priority (descending) then by created_at (ascending)
            queued_jobs.sort(key=lambda j: (-j.priority, j.created_at))
            next_job = queued_jobs[0]

            # Mark as running
            next_job.status = JobStatus.RUNNING
            next_job.started_at = datetime.now()
            next_job._owner_id = self.worker_id
            next_job.add_log("Job started")

        self._save_job_to_db(next_job)
        return next_job

    def _claim_next_job_from_db(self) -> Job | None:
        """Atomically claim the highest-priority queued row for this worker."""
        now = datetime.now()
        try:
            with self.db.get_connection() as conn:
                present = _ensure_job_columns(conn)
                row = conn.execute(
                    "SELECT id FROM background_jobs WHERE status = 'queued'"
                    " ORDER BY priority DESC, created_at ASC LIMIT 1"
                ).fetchone()
                if row is None:
                    return None
                job_id = row["id"]
                fields = ["status = 'running'", "started_at = ?"]
                params: list[Any] = [now.isoformat()]
                if "owner_id" in present:
                    fields.append("owner_id = ?")
                    params.append(self.worker_id)
                if "heartbeat_at" in present:
                    fields.append("heartbeat_at = ?")
                    params.append(now.isoformat())
                params.append(job_id)
                cursor = conn.execute(
                    f"UPDATE background_jobs SET {', '.join(fields)}"
                    " WHERE id = ? AND status = 'queued'",
                    params,
                )
                conn.commit()
                if cursor.rowcount != 1:
                    return None
                loaded = conn.execute(
                    "SELECT * FROM background_jobs WHERE id = ?", (job_id,)
                ).fetchone()
        except Exception as e:
            logger.error("Failed to claim queued job from store: %s", e)
            return None

        job = self._job_from_row(loaded) if loaded is not None else None
        if job is None:
            return None
        job._owner_id = self.worker_id

        with self._queue_lock:
            existing = self._jobs.get(job.id)
            if existing is not None:
                existing.status = JobStatus.RUNNING
                existing.started_at = job.started_at
                existing._owner_id = self.worker_id
                existing.add_log("Job started")
                job = existing
            else:
                job.add_log("Job started")
                self._jobs[job.id] = job

        self._save_job_to_db(job)
        return job

    def _mark_cancelled(self, job: Job):
        """Mark a job as cancelled and record its completion time."""
        job.cancelled = True
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now()

    def _execute_job(self, job: Job):
        """Execute a specific job"""
        job._on_update = self._on_job_update
        try:
            if job.cancelled or job.status == JobStatus.CANCELLED:
                job.add_log("Job was cancelled before execution")
                self._mark_cancelled(job)
                return

            job.add_log(f"Executing {job.type.value} job")

            # Get the appropriate job executor
            executor = self._get_job_executor(job.type)
            if not executor:
                raise ValueError(f"No executor found for job type: {job.type.value}")

            # Execute the job
            result = executor(job)
            job._on_update = None

            with self._queue_lock:
                if job.cancelled or job.status == JobStatus.CANCELLED:
                    job.add_log("Job was cancelled during execution")
                    self._mark_cancelled(job)
                    return

                # Update job with result
                if result.success:
                    job.status = JobStatus.COMPLETED
                    job.progress = 100.0
                    job.add_log("Job completed successfully")
                else:
                    job.status = JobStatus.FAILED
                    job.add_log(f"Job failed: {result.error or result.message}")

                job.result = result
                job.completed_at = datetime.now()

        except JobCancelledError:
            job._on_update = None
            with self._queue_lock:
                self._mark_cancelled(job)
            job.add_log("Job cancelled by user")

        except MemoryError as e:
            job._on_update = None
            with self._queue_lock:
                job.status = JobStatus.FAILED
                job.result = JobResult(
                    success=False,
                    message="Job ran out of memory",
                    error=(
                        "The job hit a memory limit and was stopped. "
                        "The queue waits for free RAM/VRAM before starting jobs; "
                        "raise job_queue.min_free_ram_gb or min_free_vram_gb if this repeats."
                    ),
                )
                job.completed_at = datetime.now()
            job.add_log(f"Job ran out of memory: {e}")
            logger.error("Job %s ran out of memory", job.id)

        except Exception as e:
            job._on_update = None
            with self._queue_lock:
                if job.cancelled or job.status == JobStatus.CANCELLED:
                    job.add_log(f"Job cancelled: {e}")
                    self._mark_cancelled(job)
                    return
                job.status = JobStatus.FAILED
                job.result = JobResult(
                    success=False,
                    message="Job execution failed",
                    error=str(e)
                )
                job.completed_at = datetime.now()
            job.add_log(f"Job failed with exception: {e}")
            logger.error(f"Job {job.id} failed: {e}")

        finally:
            job._on_update = None
            job._dirty = False
            job._force_persist = False
            self._save_job_to_db(job)

    def _get_job_executor(self, job_type: JobType) -> Callable | None:
        """Get the appropriate executor function for a job type"""
        from job_executors import get_executor
        return get_executor(job_type)

    def _save_job_to_db(self, job: Job):
        """Save job to database"""
        if not self.db:
            return

        try:
            # Serialize writes so a debounced flush can never overwrite a newer
            # terminal state with a stale RUNNING row.
            with self._persist_lock:
                logs = list(job.logs or [])
                with self.db.get_connection() as conn:
                    parameters_json = (
                        json.dumps(_strip_secrets(job.parameters)) if job.parameters else None
                    )
                    present = _ensure_job_columns(conn)
                    user_id = job.user_id
                    owner_id = getattr(job, "_owner_id", None)
                    stored_cancelled = False
                    try:
                        existing = conn.execute(
                            "SELECT user_id, owner_id, cancelled FROM background_jobs WHERE id = ?",
                            (job.id,),
                        ).fetchone()
                    except Exception:
                        existing = None
                    if existing is not None:
                        if user_id is None:
                            user_id = existing["user_id"]
                        if owner_id is None:
                            owner_id = existing["owner_id"]
                        stored_cancelled = bool(existing["cancelled"])
                    # A cancel recorded by any process is sticky: a worker's
                    # periodic save must never clear it before its executor
                    # notices. Adopt it so the running executor stops too.
                    if stored_cancelled and not job.cancelled:
                        job.cancelled = True
                    fields = [
                        "id", "type", "title", "description", "status", "progress",
                        "parameters", "result", "logs", "created_at", "started_at",
                        "completed_at", "can_cancel", "can_retry", "priority",
                    ]
                    values: list[Any] = [
                        job.id, job.type.value, job.title, job.description,
                        job.status.value, job.progress,
                        parameters_json,
                        json.dumps(_result_for_persistence(job.result)) if job.result else None,
                        json.dumps(logs) if logs else None,
                        job.created_at.isoformat() if job.created_at else None,
                        job.started_at.isoformat() if job.started_at else None,
                        job.completed_at.isoformat() if job.completed_at else None,
                        job.can_cancel, job.can_retry, job.priority,
                    ]
                    if "user_id" in present:
                        fields.append("user_id")
                        values.append(user_id)
                    if "owner_id" in present:
                        fields.append("owner_id")
                        values.append(owner_id)
                    if "heartbeat_at" in present:
                        fields.append("heartbeat_at")
                        values.append(
                            datetime.now().isoformat() if owner_id else None
                        )
                    if "cancelled" in present:
                        fields.append("cancelled")
                        values.append(1 if job.cancelled else 0)
                    placeholders = ",".join("?" for _ in fields)
                    # Upsert with a sticky cancel: a worker's periodic save can
                    # race a cancel from another process, so the stored flag is
                    # the OR of the two. A plain replace could otherwise clear a
                    # cancel that arrived between the read and the write.
                    assignments = []
                    for field in fields:
                        if field == "id":
                            continue
                        if field == "cancelled":
                            assignments.append(
                                "cancelled = MAX(background_jobs.cancelled, excluded.cancelled)"
                            )
                        else:
                            assignments.append(f"{field} = excluded.{field}")
                    conn.execute(
                        f"INSERT INTO background_jobs ({','.join(fields)}) "
                        f"VALUES ({placeholders}) "
                        f"ON CONFLICT(id) DO UPDATE SET {', '.join(assignments)}",
                        values,
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Failed to save job {job.id} to database: {e}")
            job.add_log(f"Failed to save job to database: {e}")

    def _job_from_row(self, row) -> Job | None:
        """Convert a background_jobs row into a Job, None when unparsable."""
        try:
            try:
                owner = row["user_id"] if "user_id" in row.keys() else None
            except Exception:
                owner = None
            try:
                was_cancelled = bool(row["cancelled"]) if "cancelled" in row.keys() else False
            except Exception:
                was_cancelled = False
            try:
                recorded_owner = row["owner_id"] if "owner_id" in row.keys() else None
            except Exception:
                recorded_owner = None
            job_data = {
                "user_id": owner,
                "cancelled": was_cancelled,
                'id': row['id'],
                'type': JobType(row['type']),
                'title': row['title'],
                'description': row['description'],
                'status': JobStatus(row['status']),
                'progress': row['progress'],
                'parameters': (
                    json.loads(row['parameters']) if row['parameters'] else {}
                ),
                'logs': json.loads(row['logs']) if row['logs'] else [],
                'created_at': (
                    datetime.fromisoformat(row['created_at'])
                    if row['created_at'] else None
                ),
                'started_at': (
                    datetime.fromisoformat(row['started_at'])
                    if row['started_at'] else None
                ),
                'completed_at': (
                    datetime.fromisoformat(row['completed_at'])
                    if row['completed_at'] else None
                ),
                'can_cancel': bool(row['can_cancel']),
                'can_retry': bool(row['can_retry']),
                'priority': row['priority'],
            }
            if row['result']:
                result_data = json.loads(row['result'])
                job_data['result'] = _coerce_job_result(result_data)
            job = Job(**job_data)
            job._owner_id = recorded_owner
            return job
        except Exception as e:
            logger.error(f"Failed to parse job {row['id']}: {e}")
            return None

    def _merge_db_jobs(self, jobs: list[Job]) -> list[Job]:
        """Include DB rows not present in memory.

        Self-managed flows (edit applies) write job rows straight to the
        database; merging keeps them visible on the Jobs page without the
        worker treating them as queued work.
        """
        if not self.db:
            return jobs
        known = {job.id for job in jobs}
        merged = list(jobs)
        try:
            with self.db.get_connection() as conn:
                rows = conn.execute("SELECT * FROM background_jobs").fetchall()
        except Exception:
            return merged
        for row in rows:
            if row['id'] in known:
                continue
            job = self._job_from_row(row)
            if job is not None:
                merged.append(job)
        return merged

    def _load_jobs_from_db(self):
        """Load existing jobs from database"""
        if not self.db:
            return

        try:
            with self.db.get_connection() as conn:
                rows = conn.execute("SELECT * FROM background_jobs").fetchall()

                for row in rows:
                    job = self._job_from_row(row)
                    if job is not None:
                        self._jobs[job.id] = job

            logger.info(f"Loaded {len(self._jobs)} jobs from database")

        except Exception as e:
            logger.error(f"Failed to load jobs from database: {e}")


# Global job queue instance
_job_queue: JobQueue | None = None
_submit_queue: JobQueue | None = None
_job_queue_lock = threading.Lock()


def get_job_queue() -> JobQueue:
    """Get the global job queue instance, starting its single worker."""
    global _job_queue
    with _job_queue_lock:
        if _job_queue is None:
            _job_queue = JobQueue()
            _job_queue.start()
    return _job_queue


def get_submit_job_queue() -> JobQueue:
    """Get a submit/read-only queue for a process that must not run workers.

    The API bridge enqueues and cancels jobs but never owns the worker; a
    single worker process holds the lease. This queue writes job rows, reads
    status and logs, and flips cancel flags, without claiming or executing
    anything.
    """
    global _submit_queue
    with _job_queue_lock:
        if _submit_queue is None:
            _submit_queue = JobQueue(run_workers=False)
            _submit_queue.start()
    return _submit_queue


def initialize_job_queue():
    """Initialize the job queue system"""
    queue = get_job_queue()
    logger.info("Job queue system initialized")
    return queue


def shutdown_job_queue():
    """Shutdown the job queue system"""
    global _job_queue, _submit_queue
    with _job_queue_lock:
        if _job_queue:
            _job_queue.stop()
            _job_queue = None
            logger.info("Job queue system shutdown")
        if _submit_queue:
            _submit_queue.stop()
            _submit_queue = None
