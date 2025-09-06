"""
Background Job Queue System for SermonAudio Processor

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

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class JobType(Enum):
    """Available job types"""
    VALIDATION = "validation"
    SERMON_PROCESSING = "sermon_processing"
    BATCH_PROCESSING = "batch_processing"
    SERMON_IMPORT = "sermon_import"
    AUDIO_ENHANCEMENT = "audio_enhancement"
    TRANSCRIPT_GENERATION = "transcript_generation"
    METADATA_UPDATE = "metadata_update"


class JobStatus(Enum):
    """Job execution status"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


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

    def __post_init__(self):
        if self.logs is None:
            self.logs = []

    def add_log(self, message: str):
        """Add a log message to the job"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def update_progress(self, progress: float, message: str = ""):
        """Update job progress"""
        self.progress = max(0, min(100, progress))
        if message:
            self.add_log(message)

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
    def from_dict(cls, data: dict[str, Any]) -> 'Job':
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
            data['result'] = JobResult(**data['result'])

        return cls(**data)


class JobQueue:
    """Thread-safe job queue manager"""

    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self._jobs: dict[str, Job] = {}
        self._queue_lock = threading.Lock()
        self._workers: list[threading.Thread] = []
        self._running = False
        self._shutdown_event = threading.Event()

        # Initialize database connection
        self._init_database()

    def _init_database(self):
        """Initialize job storage in database"""
        try:
            from database import get_db
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
                        priority INTEGER DEFAULT 5
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize job database: {e}")
            self.db = None

    def start(self):
        """Start the job queue workers"""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()

        # Load existing jobs from database
        self._load_jobs_from_db()

        # Start worker threads
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"JobWorker-{i+1}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)

        logger.info(f"Job queue started with {self.max_workers} workers")

    def stop(self):
        """Stop the job queue"""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        # Wait for workers to finish
        for worker in self._workers:
            worker.join(timeout=5.0)

        self._workers.clear()
        logger.info("Job queue stopped")

    def add_job(self, job_type: JobType, title: str, description: str,
                parameters: dict[str, Any] | None = None,
                priority: int = 5) -> str:
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
            priority=priority
        )

        with self._queue_lock:
            self._jobs[job_id] = job
            self._save_job_to_db(job)

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

        if status_filter:
            jobs = [job for job in jobs if job.status == status_filter]

        # Sort by priority (descending) then by created_at (ascending)
        jobs.sort(key=lambda j: (-j.priority, j.created_at))
        return jobs

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        with self._queue_lock:
            job = self._jobs.get(job_id)
            if not job or not job.can_cancel:
                return False

            if job.status in [JobStatus.QUEUED, JobStatus.RUNNING]:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now()
                job.add_log("Job cancelled by user")
                self._save_job_to_db(job)
                logger.info(f"Cancelled job {job_id}")
                return True

        return False

    def retry_job(self, job_id: str) -> bool:
        """Retry a failed job"""
        with self._queue_lock:
            job = self._jobs.get(job_id)
            if not job or not job.can_retry:
                return False

            if job.status == JobStatus.FAILED:
                job.status = JobStatus.QUEUED
                job.progress = 0.0
                job.started_at = None
                job.completed_at = None
                job.result = None
                job.add_log("Job queued for retry")
                self._save_job_to_db(job)
                logger.info(f"Retrying job {job_id}")
                return True

        return False

    def clear_completed_jobs(self) -> int:
        """Remove completed jobs from queue"""
        removed_count = 0
        with self._queue_lock:
            completed_jobs = [
                job_id for job_id, job in self._jobs.items()
                if job.status in [JobStatus.COMPLETED, JobStatus.CANCELLED]
            ]

            for job_id in completed_jobs:
                del self._jobs[job_id]
                removed_count += 1

            # Also remove from database
            if self.db and completed_jobs:
                try:
                    with self.db.get_connection() as conn:
                        placeholders = ','.join(['?' for _ in completed_jobs])
                        conn.execute(
                            f"DELETE FROM background_jobs WHERE id IN ({placeholders})",
                            completed_jobs
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
                # Find next job to process
                job = self._get_next_job()
                if not job:
                    time.sleep(1.0)  # No jobs available, wait
                    continue

                # Execute the job
                self._execute_job(job)

            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(1.0)

    def _get_next_job(self) -> Job | None:
        """Get the next job to process"""
        with self._queue_lock:
            # Find highest priority queued job
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
            next_job.add_log("Job started")
            self._save_job_to_db(next_job)

            return next_job

    def _execute_job(self, job: Job):
        """Execute a specific job"""
        try:
            job.add_log(f"Executing {job.type.value} job")

            # Get the appropriate job executor
            executor = self._get_job_executor(job.type)
            if not executor:
                raise ValueError(f"No executor found for job type: {job.type.value}")

            # Execute the job
            result = executor(job)

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

        except Exception as e:
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
            with self.db.get_connection() as conn:
                job_data = job.to_dict()
                conn.execute("""
                    INSERT OR REPLACE INTO background_jobs (
                        id, type, title, description, status, progress,
                        parameters, result, logs, created_at, started_at,
                        completed_at, can_cancel, can_retry, priority
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job.id, job.type.value, job.title, job.description,
                    job.status.value, job.progress,
                    json.dumps(job.parameters) if job.parameters else None,
                    json.dumps(asdict(job.result)) if job.result else None,
                    json.dumps(job.logs) if job.logs else None,
                    job.created_at.isoformat() if job.created_at else None,
                    job.started_at.isoformat() if job.started_at else None,
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.can_cancel, job.can_retry, job.priority
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save job {job.id} to database: {e}")

    def _load_jobs_from_db(self):
        """Load existing jobs from database"""
        if not self.db:
            return

        try:
            with self.db.get_connection() as conn:
                rows = conn.execute("SELECT * FROM background_jobs").fetchall()

                for row in rows:
                    try:
                        # Convert database row to job
                        job_data = {
                            'id': row['id'],
                            'type': JobType(row['type']),
                            'title': row['title'],
                            'description': row['description'],
                            'status': JobStatus(row['status']),
                            'progress': row['progress'],
                            'parameters': json.loads(row['parameters']) if row['parameters'] else {},
                            'logs': json.loads(row['logs']) if row['logs'] else [],
                            'created_at': datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                            'started_at': datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                            'completed_at': datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                            'can_cancel': bool(row['can_cancel']),
                            'can_retry': bool(row['can_retry']),
                            'priority': row['priority']
                        }

                        # Handle result
                        if row['result']:
                            result_data = json.loads(row['result'])
                            job_data['result'] = JobResult(**result_data)

                        job = Job(**job_data)
                        self._jobs[job.id] = job

                    except Exception as e:
                        logger.error(f"Failed to load job {row['id']}: {e}")

            logger.info(f"Loaded {len(self._jobs)} jobs from database")

        except Exception as e:
            logger.error(f"Failed to load jobs from database: {e}")


# Global job queue instance
_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Get the global job queue instance"""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
        _job_queue.start()
    return _job_queue


def initialize_job_queue():
    """Initialize the job queue system"""
    queue = get_job_queue()
    logger.info("Job queue system initialized")
    return queue


def shutdown_job_queue():
    """Shutdown the job queue system"""
    global _job_queue
    if _job_queue:
        _job_queue.stop()
        _job_queue = None
        logger.info("Job queue system shutdown")
