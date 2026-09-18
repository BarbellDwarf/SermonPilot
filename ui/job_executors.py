"""
Job Executors for Background Job Queue

Contains the actual execution logic for different types of background jobs.
Each executor is responsible for performing the work and updating job progress.
"""

import json
import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Add project paths for imports
ui_dir = Path(__file__).parent
project_root = ui_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

try:  # noqa: E402 - prefer package path so ui.* and top-level resolve to ONE module
    from ui.job_queue import Job, JobCancelledError, JobResult, JobStatus, JobType
except ImportError:  # Streamlit entrypoint runs from /app (top-level imports)
    from job_queue import Job, JobCancelledError, JobResult, JobStatus, JobType  # noqa: E402

# Belt-and-braces: coerce str/foreign-enum job types via value lookup so a dual-module
# import of job_queue (top-level vs ui.) can never produce a missing-executor lookup.
from ui.job_queue import JobType as _CanonicalJobType

from ui.config_utils import default_cache_root  # noqa: E402


def _canon(job_type):
    if isinstance(job_type, _CanonicalJobType):
        return job_type
    try:
        return _CanonicalJobType(getattr(job_type, "value", job_type))
    except ValueError:
        return job_type

logger = logging.getLogger(__name__)

# Bulky result keys that are stored elsewhere (sermon_content) and must not
# be copied into job results, which persist to the jobs table
_RESULT_TRIM_FIELDS = ('transcript',)


def _trim_result_payload(result: dict) -> dict:
    """Return a shallow copy of a processing result without bulky fields."""
    return {k: v for k, v in result.items() if k not in _RESULT_TRIM_FIELDS}


def _job_user_id(job: Job) -> str | None:
    params = job.parameters or {}
    return params.get("user_id") or getattr(job, "user_id", None)


def _stamp_sermon_owner(sermon_id: str | None, user_id: str | None) -> None:
    if not sermon_id or not user_id:
        return
    try:
        from ui.database import SermonRepository

        repo = SermonRepository()
        with repo.db.get_connection() as conn:
            try:
                cols = {row[1] for row in conn.execute("PRAGMA table_info(sermons)").fetchall()}
            except Exception:
                return
            if "user_id" not in cols:
                return
            conn.execute(
                "UPDATE sermons SET user_id = ? WHERE id = ? AND user_id IS NULL",
                (user_id, sermon_id),
            )
            conn.commit()
    except Exception as e:
        logger.warning("Failed to stamp sermon owner %s: %s", sermon_id, e)


def _raise_if_job_cancelled(job: Job) -> None:
    """cancel_check hook for process_new_sermon: raise when the job is cancelled."""
    if job.cancelled or job.status == JobStatus.CANCELLED:
        raise JobCancelledError("Job cancelled by user")


def _cleanup_job_files(config: dict, uploaded_file_path: str | None,
                       processing_dir: str | None, job: Job,
                       keep_upload: bool = False) -> None:
    """Delete the job's uploaded copy and per-job processing dir if still present.

    Only files inside the configured upload_dir are removed so a path pointing
    at real user media can never be deleted. Safe to run more than once.
    keep_upload=True retains the original uploaded copy (job failed or was
    cancelled: a retry re-processes it) while still removing the derived
    _enhanced/_cleaned siblings so a retry never reuses stale artifacts.
    """
    try:
        upload_dir = Path(
            config.get('upload_dir') or (default_cache_root() / "sermon_uploads")
        ).resolve()
        if uploaded_file_path:
            candidate = Path(uploaded_file_path).resolve()
            derived = (
                candidate,
                candidate.with_name(f"{candidate.stem}_enhanced{candidate.suffix}"),
                candidate.with_name(f"{candidate.stem}_cleaned.wav"),
            )
            for path in derived:
                if path.parent != upload_dir:
                    continue
                if keep_upload and path == candidate:
                    continue
                path.unlink(missing_ok=True)
                job.add_log(f"Removed uploaded copy {path.name}")
                logger.info("Removed uploaded copy %s", path)
        if processing_dir:
            shutil.rmtree(processing_dir, ignore_errors=True)
    except Exception as e:
        logger.warning("Failed to clean up job files: %s", e)


def _inject_sermon_updater_config(config: dict) -> None:
    """Point the sermon_updater module at this job's config.

    The module rebuilds all of its runtime constants from the given dict (or
    re-resolves the settings database when the job carries none), so settings
    saved in the UI apply to the job without a restart, and an empty job
    config can never wipe good values.
    """
    try:
        import sermon_updater

        sermon_updater.refresh_runtime_config(config or None)
    except Exception as e:
        logger.warning("Failed to refresh sermon_updater runtime config: %s", e)


def execute_validation_job(job: Job) -> JobResult:
    """Execute a validation job"""
    try:
        job.update_progress(10, "Initializing validation...")

        # Get parameters
        sermon_ids = job.parameters.get('sermon_ids', [])
        if not sermon_ids:
            return JobResult(
                success=False,
                message="No sermon IDs provided for validation",
                error="Missing sermon_ids parameter"
            )

        if job.cancelled or job.status == JobStatus.CANCELLED:
            job.add_log("Validation cancelled by user")
            raise JobCancelledError("Job cancelled by user")

        job.update_progress(20, f"Starting validation of {len(sermon_ids)} sermons...")

        # Import validation components
        from ui_processor import UIProcessor
        processor = UIProcessor()

        # Track results
        results = {
            'total': len(sermon_ids),
            'completed': 0,
            'valid': 0,
            'invalid': 0,
            'errors': 0,
            'details': []
        }

        # Process each sermon
        for i, sermon_id in enumerate(sermon_ids):
            if job.cancelled or job.status == JobStatus.CANCELLED:
                job.add_log("Validation cancelled by user")
                raise JobCancelledError("Job cancelled by user")

            try:
                progress = 20 + (i / len(sermon_ids)) * 70  # 20-90% for processing
                job.update_progress(
                    progress, f"Validating sermon {sermon_id} ({i+1}/{len(sermon_ids)})"
                )

                # Get configuration from job parameters first, then resolve
                config = job.parameters.get('config', {})
                if not config:
                    job.add_log("No config in job parameters, resolving configuration...")
                    try:
                        from ui.config_utils import load_config_from_file

                        config = load_config_from_file()
                    except Exception as e:
                        job.add_log(f"Failed to resolve configuration: {e}")
                        raise ValueError(
                            f"No configuration available in job parameters and "
                            f"resolution failed: {e}"
                        ) from e

                if not config:
                    raise ValueError("No configuration available")

                # Import validation components here to avoid import issues
                from sermon_updater import DescriptionValidator

                validator = DescriptionValidator(config)
                validation_result = validator.validate_single_sermon(sermon_id)

                if validation_result:
                    # Save to database
                    processor.db.save_validation_result(
                        sermon_id,
                        validation_result.is_valid,
                        validation_result.validation_score,
                        validation_result.validation_reason,
                        validation_result.criteria_met,
                        validation_result.criteria_failed
                    )

                    results['details'].append({
                        'sermon_id': sermon_id,
                        'is_valid': validation_result.is_valid,
                        'score': validation_result.validation_score,
                        'reason': validation_result.validation_reason
                    })

                    if validation_result.is_valid:
                        results['valid'] += 1
                        job.add_log(
                            f"Sermon {sermon_id}: Valid "
                            f"(score: {validation_result.validation_score:.2f})"
                        )
                    else:
                        results['invalid'] += 1
                        job.add_log(
                            f"Sermon {sermon_id}: Invalid "
                            f"(score: {validation_result.validation_score:.2f})"
                        )
                else:
                    results['errors'] += 1
                    job.add_log(f"Sermon {sermon_id}: Validation failed")

                results['completed'] += 1

            except Exception as e:
                results['errors'] += 1
                job.add_log(f"Error validating sermon {sermon_id}: {str(e)}")
                logger.error(f"Validation error for sermon {sermon_id}: {e}")

        job.update_progress(95, "Finalizing validation results...")

        # Create summary message
        summary = (
            f"Validation completed: {results['valid']} valid, "
            f"{results['invalid']} invalid, {results['errors']} errors"
        )
        job.update_progress(100, summary)

        return JobResult(
            success=True,
            message=summary,
            data=results
        )

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Validation job failed: {str(e)}"
        job.add_log(error_msg)
        logger.error(error_msg)
        return JobResult(
            success=False,
            message="Validation job failed",
            error=str(e)
        )


def execute_sermon_import_job(job: Job) -> JobResult:
    """Execute a sermon import job"""
    try:
        job.update_progress(10, "Initializing sermon import...")

        # Get parameters
        processed_sermons_dir = job.parameters.get('processed_sermons_dir')
        force_reimport = job.parameters.get('force_reimport', False)
        refresh_api_data = job.parameters.get('refresh_api_data', False)

        if not processed_sermons_dir:
            return JobResult(
                success=False,
                message="No processed sermons directory specified",
                error="Missing processed_sermons_dir parameter"
            )

        if job.cancelled or job.status == JobStatus.CANCELLED:
            job.add_log("Sermon import cancelled by user")
            raise JobCancelledError("Job cancelled by user")

        job.update_progress(
            20, f"Scanning processed sermons directory... (force_reimport={force_reimport})"
        )

        # Import sermon importer
        from sermon_importer import SermonImporter

        from ui.database import SermonRepository

        importer = SermonImporter(processed_sermons_dir)
        repo = SermonRepository()

        # Scan for sermons
        job.update_progress(30, "Discovering sermon folders...")
        sermon_folders = importer.scan_processed_folder()

        if not sermon_folders:
            return JobResult(
                success=True,
                message="No new sermons found to import",
                data={'imported': 0, 'skipped': 0, 'errors': 0}
            )

        job.update_progress(40, f"Found {len(sermon_folders)} sermon folders to process...")

        # Track results
        results = {
            'imported': 0,
            'skipped': 0,
            'errors': 0,
            'details': []
        }

        # Process each sermon folder
        for i, sermon_id in enumerate(sermon_folders):
            if job.cancelled or job.status == JobStatus.CANCELLED:
                job.add_log("Sermon import cancelled by user")
                raise JobCancelledError("Job cancelled by user")

            try:
                progress = 40 + (i / len(sermon_folders)) * 50  # 40-90% for processing
                job.update_progress(
                    progress, f"Importing sermon {sermon_id} ({i+1}/{len(sermon_folders)})"
                )

                # Check if sermon already exists (skip check if force_reimport is True)
                existing_sermon = repo.get_sermon(sermon_id)
                if existing_sermon and not force_reimport:
                    results['skipped'] += 1
                    job.add_log(f"Sermon {sermon_id}: Already exists, skipping")
                    continue

                # Import or re-import the sermon
                if force_reimport and existing_sermon:
                    job.add_log(f"Sermon {sermon_id}: Force re-importing...")
                    # Delete existing sermon if force reimport
                    repo.delete_sermon(sermon_id)

                success = importer.import_sermon(sermon_id, refresh_api_data=refresh_api_data)
                if success:
                    # Get the imported sermon data for logging
                    imported_sermon = repo.get_sermon(sermon_id)
                    sermon_title = (
                        imported_sermon.get('title', 'Unknown') if imported_sermon else 'Unknown'
                    )

                    results['imported'] += 1
                    job.add_log(f"Sermon {sermon_id}: Imported successfully - {sermon_title}")
                    results['details'].append({
                        'sermon_id': sermon_id,
                        'status': 'imported',
                        'title': sermon_title
                    })
                else:
                    results['errors'] += 1
                    job.add_log(f"Sermon {sermon_id}: Failed to import")

            except Exception as e:
                results['errors'] += 1
                job.add_log(f"Error importing sermon {sermon_id}: {str(e)}")
                logger.error(f"Import error for sermon {sermon_id}: {e}")

        job.update_progress(95, "Finalizing import results...")

        # Create summary message
        summary = (
            f"Import completed: {results['imported']} imported, "
            f"{results['skipped']} skipped, {results['errors']} errors"
        )
        job.update_progress(100, summary)

        return JobResult(
            success=True,
            message=summary,
            data=results
        )

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Import job failed: {str(e)}"
        job.add_log(error_msg)
        logger.error(error_msg)
        return JobResult(
            success=False,
            message="Import job failed",
            error=str(e)
        )


def execute_sermon_processing_job(job: Job) -> JobResult:
    """Execute a sermon processing job from an uploaded file (UI flow).

    This handles the 'new sermon' workflow where a user uploads an audio file
    via the Streamlit UI and it gets processed, transcribed, and uploaded
    to SermonAudio.

    Required job parameters:
        - uploaded_file_path: path to a saved copy of the uploaded audio
        - form_data: dict with keys: speaker_name, recorded_date, event_type,
                     bible_text, title, subtitle, description, hashtags,
                     skip_audio, skip_transcription, whisper_model, dry_run
        - config: full config dict (used to set globals in sermon_updater)
    """
    processing_temp_dir: str | None = None
    cleanup_state = {"keep_upload": True}
    try:
        if job.cancelled or job.status == JobStatus.CANCELLED:
            raise JobCancelledError("Job cancelled by user")

        job.update_progress(5, "Initializing sermon processing...")

        form_data = job.parameters.get('form_data') or {}
        config = job.parameters.get('config') or {}
        uploaded_file_path = (
            job.parameters.get('uploaded_file_path')
            or form_data.get('uploaded_file_path')
        )

        if not uploaded_file_path:
            return JobResult(
                success=False,
                message="No uploaded file path provided",
                error="Missing uploaded_file_path in job parameters"
            )

        if not Path(uploaded_file_path).exists():
            return JobResult(
                success=False,
                message=f"Uploaded file not found: {uploaded_file_path}",
                error="Uploaded audio file is missing on disk"
            )

        # Validate required form fields
        for required_key in ('speaker_name', 'recorded_date', 'event_type'):
            if not form_data.get(required_key):
                return JobResult(
                    success=False,
                    message=f"Missing required field: {required_key}",
                    error=f"Form data missing {required_key}"
                )

        auto_edit_enabled = job.parameters.get('auto_edit_enabled')
        auto_edit_mode = job.parameters.get('auto_edit_mode')
        if auto_edit_enabled is False:
            auto_edit_mode = None
        elif auto_edit_enabled is True and auto_edit_mode is None:
            auto_edit_mode = 'interactive'

        # Inject the config into the sermon_updater module so that its
        # module-level constants (api_key, broadcaster_id, LLM manager, etc.)
        # are correct for this job, and the sermonaudio library gets the
        # API key so Node.get_sermon() and similar calls work.
        _inject_sermon_updater_config(config)
        job.add_log("Config injected for this job")

        # Progress callback that updates the job
        def progress_cb(pct, msg):
            if job.cancelled or job.status == JobStatus.CANCELLED:
                raise JobCancelledError("Job cancelled by user")
            try:
                job.update_progress(pct, msg)
            except Exception:
                pass

        job.update_progress(10, f"Processing: {Path(uploaded_file_path).name}")
        job.add_log(f"Audio file: {uploaded_file_path}")

        # Call the real process_new_sermon
        from sermon_updater import process_new_sermon

        result = process_new_sermon(
            audio_file=uploaded_file_path,
            speaker_name=form_data.get('speaker_name'),
            recorded_date=form_data.get('recorded_date'),
            event_type=form_data.get('event_type', 'Sunday Service'),
            bible_text=form_data.get('bible_text') or None,
            title=form_data.get('title') or None,
            subtitle=form_data.get('subtitle') or None,
            series_title=form_data.get('series_title') or None,
            series_id=form_data.get('series_id'),
            description=form_data.get('description') or None,
            hashtags=form_data.get('hashtags') or None,
            dry_run=bool(form_data.get('dry_run', False)),
            publish=bool(form_data.get('publish', True)),
            skip_transcription=bool(form_data.get('skip_transcription', False)),
            skip_audio=bool(form_data.get('skip_audio', False)),
            skip_ai_generation=bool(form_data.get('skip_ai_generation', False)),
            whisper_model=form_data.get('whisper_model', 'large'),
            transcription_backend=form_data.get('transcription_backend', 'whisper_local'),
            use_clean_audio=bool(form_data.get('use_clean_audio', False)),
            clean_audio_script=form_data.get('clean_audio_script',
                                            '~/Documents/Repositories/deepfilternet/clean-audio.py'),
            clean_audio_device=form_data.get('clean_audio_device', 'auto'),
            generate_short_title=bool(form_data.get('generate_short_title', False)),
            force_validation=bool(form_data.get('validate_quality', False)),
            enhancement_method=form_data.get('enhancement_method'),
            custom_repo=form_data.get('custom_repo'),
            custom_file=form_data.get('custom_file'),
            config=config,
            progress_callback=progress_cb,
            auto_edit_mode=auto_edit_mode,
            cancel_check=lambda: _raise_if_job_cancelled(job),
        )
        processing_temp_dir = result.get('processing_temp_dir')

        if result.get('cancelled'):
            job.add_log("Sermon processing cancelled by user")
            raise JobCancelledError("Job cancelled by user")

        if result.get('success'):
            sermon_id = result.get('sermon_id')
            _stamp_sermon_owner(sermon_id, _job_user_id(job))
            plan_status = result.get('edit_plan_status')
            if plan_status == 'pending_review':
                job.add_log("Auto-edit cut awaits manual review")
                return JobResult(
                    success=True,
                    message=(f"Auto-edit cut awaiting manual review "
                             f"({sermon_id or 'dry run'})"),
                    data=_trim_result_payload(result),
                )
            job.add_log(f"Sermon created: {sermon_id or '(dry run)'}")
            cleanup_state["keep_upload"] = False
            return JobResult(
                success=True,
                message=f"Sermon processed successfully: {sermon_id or 'dry run'}",
                data=_trim_result_payload(result),
            )
        else:
            err = result.get('error') or 'Unknown processing error'
            job.add_log(err)
            return JobResult(
                success=False,
                message=f"Processing failed: {err}",
                error=err,
                data=_trim_result_payload(result),
            )

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Sermon processing job failed: {e}"
        job.add_log(error_msg)
        logger.exception(error_msg)
        return JobResult(
            success=False,
            message="Sermon processing job failed",
            error=str(e),
        )
    finally:
        parameters = job.parameters
        uploaded_file_path = (
            parameters.get('uploaded_file_path')
            or (parameters.get('form_data') or {}).get('uploaded_file_path')
        )
        _cleanup_job_files(
            parameters.get('config') or {}, uploaded_file_path, processing_temp_dir, job,
            keep_upload=cleanup_state["keep_upload"],
        )


def execute_auto_edit_job(job: Job) -> JobResult:
    """Execute an auto-edit job: run the pipeline with the auto-edit gate active.

    Required job parameters:
        - audio_file: path to the uploaded audio/video file
        - form_data: dict with keys: speaker_name, recorded_date, event_type,
                     bible_text, title, subtitle, description, hashtags,
                     skip_audio, skip_transcription, whisper_model, dry_run
        - config: full config dict (used to set globals in sermon_updater)

    Optional job parameters:
        - auto_edit_mode: 'auto' or 'interactive' (activates the gate when set)
        - edit_plan_file: path to a JSON edit plan (see _load_edit_plan_from_file)
    """
    try:
        if job.cancelled or job.status == JobStatus.CANCELLED:
            raise JobCancelledError("Job cancelled by user")

        job.update_progress(5, "Initializing auto-edit processing...")

        form_data = job.parameters.get('form_data') or {}
        config = job.parameters.get('config') or {}
        audio_file = job.parameters.get('audio_file') or form_data.get('audio_file')

        if not audio_file:
            return JobResult(
                success=False,
                message="No audio file path provided",
                error="Missing audio_file in job parameters"
            )

        if not Path(audio_file).exists():
            return JobResult(
                success=False,
                message=f"Audio file not found: {audio_file}",
                error="Audio file is missing on disk"
            )

        for required_key in ('speaker_name', 'recorded_date'):
            if not form_data.get(required_key):
                return JobResult(
                    success=False,
                    message=f"Missing required field: {required_key}",
                    error=f"Form data missing {required_key}"
                )

        auto_edit_enabled = job.parameters.get('auto_edit_enabled')
        auto_edit_mode = job.parameters.get('auto_edit_mode')
        edit_plan_file = job.parameters.get('edit_plan_file')

        if auto_edit_enabled is False and not edit_plan_file:
            auto_edit_mode = None
        elif auto_edit_mode is None:
            auto_edit_mode = 'interactive'

        _inject_sermon_updater_config(config)
        job.add_log("Config injected for this job")

        def progress_cb(pct, msg):
            if job.cancelled or job.status == JobStatus.CANCELLED:
                raise JobCancelledError("Job cancelled by user")
            try:
                job.update_progress(pct, msg)
            except Exception:
                pass

        job.update_progress(10, f"Processing: {Path(audio_file).name}")
        job.add_log(f"Audio file: {audio_file}")

        from sermon_updater import process_new_sermon

        kwargs: dict[str, Any] = {
            'audio_file': audio_file,
            'speaker_name': form_data.get('speaker_name'),
            'recorded_date': form_data.get('recorded_date'),
            'event_type': form_data.get('event_type', 'Sunday Service'),
            'bible_text': form_data.get('bible_text') or None,
            'title': form_data.get('title') or None,
            'subtitle': form_data.get('subtitle') or None,
            'series_title': form_data.get('series_title') or None,
            'series_id': form_data.get('series_id'),
            'description': form_data.get('description') or None,
            'hashtags': form_data.get('hashtags') or None,
            'dry_run': bool(form_data.get('dry_run', False)),
            'skip_transcription': bool(form_data.get('skip_transcription', False)),
            'skip_audio': bool(form_data.get('skip_audio', False)),
            'skip_ai_generation': bool(form_data.get('skip_ai_generation', False)),
            'whisper_model': form_data.get('whisper_model', 'large'),
            'transcription_backend': form_data.get('transcription_backend',
                                                    'whisper_local'),
            'use_clean_audio': bool(form_data.get('use_clean_audio', False)),
            'clean_audio_script': form_data.get(
                'clean_audio_script',
                '~/Documents/Repositories/deepfilternet/clean-audio.py'),
            'clean_audio_device': form_data.get('clean_audio_device', 'auto'),
            'generate_short_title': bool(form_data.get('generate_short_title', False)),
            'force_validation': bool(form_data.get('validate_quality', False)),
            'enhancement_method': form_data.get('enhancement_method'),
            'custom_repo': form_data.get('custom_repo'),
            'custom_file': form_data.get('custom_file'),
            'config': config,
            'progress_callback': progress_cb,
            'auto_edit_mode': auto_edit_mode,
            'edit_plan_file': edit_plan_file,
            'cancel_check': lambda: _raise_if_job_cancelled(job),
        }

        result = process_new_sermon(**kwargs)

        if result.get('cancelled'):
            job.add_log("Auto-edit processing cancelled by user")
            raise JobCancelledError("Job cancelled by user")

        if result.get('success'):
            sermon_id = result.get('sermon_id')
            _stamp_sermon_owner(sermon_id, _job_user_id(job))
            plan_status = result.get('edit_plan_status')
            if plan_status == 'pending_review':
                job.add_log("Auto-edit cut awaits manual review")
                return JobResult(
                    success=True,
                    message=(f"Auto-edit cut awaiting manual review "
                             f"({sermon_id or 'dry run'})"),
                    data=_trim_result_payload(result),
                )
            job.add_log(f"Sermon created: {sermon_id or '(dry run)'}")
            return JobResult(
                success=True,
                message=f"Auto-edit applied: {sermon_id or 'dry run'}",
                data=_trim_result_payload(result),
            )

        err = result.get('error') or 'Unknown processing error'
        job.add_log(err)
        return JobResult(
            success=False,
            message=f"Auto-edit processing failed: {err}",
            error=err,
            data=_trim_result_payload(result),
        )

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Auto-edit job failed: {e}"
        job.add_log(error_msg)
        logger.exception(error_msg)
        return JobResult(
            success=False,
            message="Auto-edit job failed",
            error=str(e),
        )


def execute_batch_processing_job(job: Job) -> JobResult:
    """Execute a batch processing job"""
    try:
        job.update_progress(10, "Initializing batch processing...")

        sermon_ids = job.parameters.get('sermon_ids', [])
        if not sermon_ids:
            return JobResult(
                success=False,
                message="No sermon IDs provided for batch processing",
                error="Missing sermon_ids parameter"
            )

        actions = job.parameters.get('actions', {})
        config = job.parameters.get('config', {})

        if not config:
            return JobResult(
                success=False,
                message="No configuration provided for batch processing",
                error="Missing config parameter"
            )

        if job.cancelled or job.status == JobStatus.CANCELLED:
            job.add_log("Batch processing cancelled by user")
            raise JobCancelledError("Job cancelled by user")

        job.update_progress(20, f"Starting batch processing of {len(sermon_ids)} sermons...")

        results = {
            'total': len(sermon_ids),
            'completed': 0,
            'failed': 0,
            'details': []
        }

        # Import necessary modules
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import sermon_updater
        from sermon_updater import DescriptionValidator

        # Inject the full config so sermon_updater module-level constants
        # are correct and sermonaudio library gets the API key
        _inject_sermon_updater_config(config)

        # Process each sermon
        for i, sermon_id in enumerate(sermon_ids):
            if job.cancelled or job.status == JobStatus.CANCELLED:
                job.add_log("Batch processing cancelled by user")
                raise JobCancelledError("Job cancelled by user")

            try:
                progress = 20 + (i / len(sermon_ids)) * 70  # 20-90% for processing
                job.update_progress(
                    progress, f"Processing sermon {sermon_id} ({i+1}/{len(sermon_ids)})"
                )

                sermon_result = {
                    'sermon_id': sermon_id,
                    'status': 'success',
                    'actions_performed': [],
                    'errors': []
                }

                # Perform selected actions
                should_reprocess = (
                    actions.get('enhance_audio')
                    or actions.get('generate_description')
                    or actions.get('generate_hashtags')
                )
                if should_reprocess:
                    try:
                        job.add_log(f"Processing sermon {sermon_id}")
                        form_data = job.parameters.get('form_data', {})
                        force_update = job.parameters.get('force_update', False)
                        # Use the existing sermon processing function with appropriate flags
                        sermon_updater.process_single_sermon(
                            sermon_id,
                            no_upload=bool(form_data.get('dry_run', False)),
                            verbose=False,
                            skip_audio=not actions.get('enhance_audio', False),
                            force_description=(
                                actions.get('generate_description', False) or force_update
                            ),
                            force_hashtags=actions.get('generate_hashtags', False) or force_update,
                            no_metadata=False,
                            transcription_backend=form_data.get('transcription_backend'),
                            audio_file=form_data.get('uploaded_file_path'),
                            series_id=job.parameters.get('series_id'),
                            config=config,
                        )

                        if actions.get('generate_description'):
                            sermon_result['actions_performed'].append('description')
                        if actions.get('generate_hashtags'):
                            sermon_result['actions_performed'].append('hashtags')
                        if actions.get('enhance_audio'):
                            sermon_result['actions_performed'].append('audio')

                    except Exception as e:
                        sermon_result['errors'].append(f'Processing error: {str(e)}')

                if actions.get('validate_content'):
                    try:
                        job.add_log(f"Validating content for sermon {sermon_id}")
                        validator = DescriptionValidator(config)
                        validation_result = validator.validate_single_sermon(sermon_id)
                        if validation_result:
                            sermon_result['actions_performed'].append('validation')
                        else:
                            sermon_result['errors'].append('Failed to validate content')
                    except Exception as e:
                        sermon_result['errors'].append(f'Content validation error: {str(e)}')

                # Update result status
                if sermon_result['errors']:
                    sermon_result['status'] = 'error'
                    results['failed'] += 1
                else:
                    results['completed'] += 1

                results['details'].append(sermon_result)
                job.add_log(
                    f"Sermon {sermon_id}: "
                    f"{len(sermon_result['actions_performed'])} actions completed"
                )

            except Exception as e:
                results['failed'] += 1
                error_result = {
                    'sermon_id': sermon_id,
                    'status': 'error',
                    'actions_performed': [],
                    'errors': [f"Processing error: {str(e)}"]
                }
                results['details'].append(error_result)
                job.add_log(f"Error processing sermon {sermon_id}: {str(e)}")

        summary = (
            f"Batch processing completed: {results['completed']} successful, "
            f"{results['failed']} failed"
        )
        job.update_progress(100, summary)

        return JobResult(
            success=True,
            message=summary,
            data=results
        )

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Batch processing job failed: {str(e)}"
        job.add_log(error_msg)
        return JobResult(
            success=False,
            message="Batch processing job failed",
            error=str(e)
        )


def execute_metadata_update_job(job: Job) -> JobResult:
    """Execute a metadata update job (AI description/hashtag generation)"""
    try:
        sermon_ids = job.parameters.get('sermon_ids', [])
        actions = job.parameters.get('actions', {})
        config = job.parameters.get('config', {})

        if not sermon_ids:
            return JobResult(
                success=False,
                message="No sermon IDs provided",
                error="Missing sermon_ids parameter"
            )

        if not config:
            return JobResult(
                success=False,
                message="No configuration provided",
                error="Missing config parameter"
            )

        if job.cancelled or job.status == JobStatus.CANCELLED:
            job.add_log("Metadata update cancelled by user")
            raise JobCancelledError("Job cancelled by user")

        job.update_progress(10, f"Starting metadata update for {len(sermon_ids)} sermons...")

        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import sermon_updater

        _inject_sermon_updater_config(config)

        results = {
            'total': len(sermon_ids),
            'completed': 0,
            'failed': 0,
            'details': []
        }

        for i, sermon_id in enumerate(sermon_ids):
            if job.cancelled or job.status == JobStatus.CANCELLED:
                job.add_log("Metadata update cancelled by user")
                raise JobCancelledError("Job cancelled by user")

            try:
                progress = 10 + (i / len(sermon_ids)) * 80
                job.update_progress(
                    progress, f"Processing sermon {sermon_id} ({i+1}/{len(sermon_ids)})"
                )

                sermon_updater.process_single_sermon(
                    sermon_id,
                    no_upload=False,
                    verbose=False,
                    skip_audio=True,
                    force_description=actions.get('generate_description', False),
                    force_hashtags=actions.get('generate_hashtags', False),
                    no_metadata=False,
                    config=config,
                )

                results['completed'] += 1
                job.add_log(f"Sermon {sermon_id}: Updated")

            except Exception as e:
                results['failed'] += 1
                job.add_log(f"Sermon {sermon_id}: {str(e)}")
                logger.error(f"Metadata update error for {sermon_id}: {e}")

        summary = f"Metadata update: {results['completed']} completed, {results['failed']} failed"
        job.update_progress(100, summary)

        return JobResult(success=True, message=summary, data=results)

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Metadata update job failed: {str(e)}"
        job.add_log(error_msg)
        return JobResult(success=False, message="Metadata update job failed", error=str(e))


def execute_auto_edit_apply_job(job: Job) -> JobResult:
    """Execute an apply job: persist the reviewed cut and re-run the pipeline.

    Continuation of an AUTO_EDIT job whose plan ended up in 'pending_review'.

    Required job parameters:
        - sermon_id: draft sermon id from the pending-review pass
        - plan_id: edit_plans row id to approve
        - final_start: user-reviewed cut start (seconds)
        - final_end: user-reviewed cut end (seconds)
        - audio_file: path to the source media
        - form_data: same keys as execute_auto_edit_job
        - config: full config dict

    Optional job parameters:
        - logo_path: overrides config auto_edit.logo_path for this run
        - re_edit: true when the user re-edited an already applied plan;
          the pipeline saves revision N+1 via save_edit_plan_revision
    """
    try:
        if job.cancelled or job.status == JobStatus.CANCELLED:
            raise JobCancelledError("Job cancelled by user")

        job.update_progress(5, "Initializing auto-edit apply...")

        sermon_id = job.parameters.get('sermon_id')
        plan_id = job.parameters.get('plan_id')
        final_start = job.parameters.get('final_start')
        final_end = job.parameters.get('final_end')
        logo_path = job.parameters.get('logo_path')
        re_edit = bool(job.parameters.get('re_edit', False))
        form_data = job.parameters.get('form_data') or {}
        config = job.parameters.get('config') or {}
        audio_file = job.parameters.get('audio_file') or form_data.get('audio_file')

        if not sermon_id or not plan_id:
            return JobResult(
                success=False,
                message="Missing sermon_id or plan_id",
                error="Auto-edit apply requires sermon_id and plan_id"
            )

        for required_key in ('final_start', 'final_end'):
            if not isinstance(job.parameters.get(required_key), int | float):
                return JobResult(
                    success=False,
                    message=f"Missing required field: {required_key}",
                    error=f"Auto-edit apply requires a numeric {required_key}"
                )

        if not audio_file:
            return JobResult(
                success=False,
                message="No audio file path provided",
                error="Missing audio_file in job parameters"
            )

        for required_key in ('speaker_name', 'recorded_date'):
            if not form_data.get(required_key):
                return JobResult(
                    success=False,
                    message=f"Missing required field: {required_key}",
                    error=f"Form data missing {required_key}"
                )

        from ui.database import SermonRepository

        repo = SermonRepository()

        notes = (
            "re-edit approved by user" if re_edit else "approved by user"
        )
        if not repo.update_edit_plan_status(
            plan_id,
            'approved',
            notes=notes,
            final_start=float(final_start),
            final_end=float(final_end),
        ):
            return JobResult(
                success=False,
                message=f"Edit plan {plan_id} not found for sermon {sermon_id}",
                error="update_edit_plan_status matched no row"
            )
        job.add_log(f"Edit plan {plan_id} approved "
                    f"({final_start:.1f}s - {final_end:.1f}s)")

        run_config = config
        if logo_path:
            run_config = dict(config)
            auto_edit_cfg = dict(run_config.get('auto_edit') or {})
            auto_edit_cfg['logo_path'] = logo_path
            run_config['auto_edit'] = auto_edit_cfg

        plan_payload = {
            'start': float(final_start),
            'end': float(final_end),
            'fade_in': 1.0,
            'logo_hold': 3.0,
            'fade_to_black': True,
            'confidence': 1.0,
            'needs_review': False,
            'qa_judgment': 'approved',
        }
        plan_file = Path(tempfile.gettempdir()) / (
            f"sermon_edit_plan_{plan_id}_{os.getpid()}.json"
        )
        try:
            with open(plan_file, 'w', encoding='utf-8') as f:
                json.dump(plan_payload, f)
            job.add_log(f"Wrote approved plan overrides to {plan_file.name}")

            _inject_sermon_updater_config(run_config)
            job.add_log("Config injected for this job")

            def progress_cb(pct, msg):
                if job.cancelled or job.status == JobStatus.CANCELLED:
                    raise JobCancelledError("Job cancelled by user")
                try:
                    job.update_progress(pct, msg)
                except Exception:
                    pass

            _raise_if_job_cancelled(job)
            job.update_progress(10, f"Re-processing {Path(audio_file).name}")

            from sermon_updater import process_new_sermon

            result = process_new_sermon(
                audio_file=audio_file,
                speaker_name=form_data.get('speaker_name'),
                recorded_date=form_data.get('recorded_date'),
                event_type=form_data.get('event_type', 'Sunday Service'),
                bible_text=form_data.get('bible_text') or None,
                title=form_data.get('title') or None,
                subtitle=form_data.get('subtitle') or None,
                series_title=form_data.get('series_title') or None,
                series_id=form_data.get('series_id'),
                description=form_data.get('description') or None,
                hashtags=form_data.get('hashtags') or None,
                dry_run=bool(form_data.get('dry_run', False)),
                skip_transcription=bool(form_data.get('skip_transcription', False)),
                skip_audio=bool(form_data.get('skip_audio', False)),
                skip_ai_generation=bool(form_data.get('skip_ai_generation', False)),
                whisper_model=form_data.get('whisper_model', 'large'),
                transcription_backend=form_data.get('transcription_backend',
                                                    'whisper_local'),
                use_clean_audio=bool(form_data.get('use_clean_audio', False)),
                clean_audio_script=form_data.get(
                    'clean_audio_script',
                    '~/Documents/Repositories/deepfilternet/clean-audio.py'),
                clean_audio_device=form_data.get('clean_audio_device', 'auto'),
                generate_short_title=bool(form_data.get('generate_short_title', False)),
                force_validation=bool(form_data.get('validate_quality', False)),
                enhancement_method=form_data.get('enhancement_method'),
                custom_repo=form_data.get('custom_repo'),
                custom_file=form_data.get('custom_file'),
                config=run_config,
                progress_callback=progress_cb,
                auto_edit_mode='auto',
                edit_plan_file=str(plan_file),
                cancel_check=lambda: _raise_if_job_cancelled(job),
            )
            if result.get('cancelled'):
                job.add_log("Auto-edit apply cancelled by user")
                raise JobCancelledError("Job cancelled by user")

            if result.get('success') and result.get('edit_plan_status') == 'auto_applied':
                _stamp_sermon_owner(result.get('sermon_id') or sermon_id, _job_user_id(job))
                media_id = (
                    result.get('final_upload_path')
                    or result.get('output_dir')
                    or result.get('sermon_id')
                )
                repo.update_edit_plan_status(
                    plan_id,
                    'applied',
                    applied_media_id=media_id,
                )
                job.add_log(f"Edit plan {plan_id} applied to {media_id}")
                summary = (
                    f"Approved cut re-applied for {result.get('sermon_id') or sermon_id}"
                    + (" (new revision saved)" if re_edit else "")
                )
                return JobResult(
                    success=True,
                    message=summary,
                    data=_trim_result_payload(result),
                )

            if result.get('success'):
                err = ("Pipeline finished but the cut was not applied "
                       "(returned pending_review)")
                job.add_log(err)
                return JobResult(
                    success=False,
                    message=err,
                    error='edit_plan_status did not reach auto_applied',
                    data=_trim_result_payload(result),
                )

            err = result.get('error') or 'Unknown processing error'
            job.add_log(err)
            return JobResult(
                success=False,
                message=f"Auto-edit apply failed: {err}",
                error=err,
                data=_trim_result_payload(result),
            )
        finally:
            try:
                plan_file.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to remove edit plan file %s: %s", plan_file, e)

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Auto-edit apply job failed: {e}"
        job.add_log(error_msg)
        logger.exception(error_msg)
        return JobResult(
            success=False,
            message="Auto-edit apply job failed",
            error=str(e),
        )


def execute_auto_edit_refine_job(job: Job) -> JobResult:
    """Re-run cut detection for a sermon using rejection notes as refinement.

    Required job parameters:
        - sermon_id: the sermon whose current plan is being refined
        - notes: the user's refinement instructions (may be empty)
        - config: full config dict
    """
    try:
        if job.cancelled or job.status == JobStatus.CANCELLED:
            raise JobCancelledError("Job cancelled by user")

        sermon_id = job.parameters.get('sermon_id')
        notes = job.parameters.get('notes') or ''
        config = job.parameters.get('config') or {}

        if not sermon_id:
            return JobResult(
                success=False,
                message="Missing sermon_id for re-detection",
                error="Missing sermon_id in job parameters"
            )

        _inject_sermon_updater_config(config)
        job.update_progress(10, "Re-running cut detection with your notes...")

        from sermon_updater import refine_edit_plan

        result = refine_edit_plan(sermon_id, notes=notes, config=config)

        if not result.get('success'):
            err = result.get('error') or 'Re-detection failed'
            job.add_log(err)
            return JobResult(
                success=False,
                message=f"Re-detection failed: {err}",
                error=err,
            )

        job.update_progress(100, "New cut proposal ready for review")
        job.add_log(
            f"Re-detected plan: start={result.get('start')}, end={result.get('end')}, "
            f"confidence={result.get('confidence')}"
        )
        return JobResult(
            success=True,
            message=f"New cut proposal ready (confidence {result.get('confidence', 0):.2f})",
            data=result,
        )

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Auto-edit re-detection job failed: {e}"
        job.add_log(error_msg)
        logger.exception(error_msg)
        return JobResult(
            success=False,
            message="Auto-edit re-detection job failed",
            error=str(e),
        )


def execute_library_auto_edit_apply_job(job: Job) -> JobResult:
    """Execute a Library review-panel apply outside the page lifecycle.

    Job parameters (enqueued by the Library page, never built inline):
        - sermon_id, start, end, audio_offset, render_only, mode,
          plan_id, plan_revision, re_detect, config.

    The shared ``run_library_apply`` core performs the trim + encode via
    ``process_new_sermon`` (``dry_run=True`` when ``render_only``) and marks
    the plan ``applied_local`` on a local render. The worker's own
    ``background_jobs`` row is the single row per apply; progress flows
    through ``job.update_progress``.
    """
    try:
        if job.cancelled or job.status == JobStatus.CANCELLED:
            raise JobCancelledError("Job cancelled by user")

        params = job.parameters or {}
        sermon_id = params.get("sermon_id")
        start = params.get("start")
        end = params.get("end")
        audio_offset = params.get("audio_offset", 0.0) or 0.0
        render_only = bool(params.get("render_only", False))
        re_detect = bool(params.get("re_detect", False))
        plan_id = params.get("plan_id")
        config = params.get("config") or {}

        if not sermon_id:
            return JobResult(
                success=False,
                message="Missing sermon_id for library apply",
                error="Missing sermon_id in job parameters",
            )
        for key, value in (("start", start), ("end", end)):
            if not isinstance(value, int | float) or isinstance(value, bool):
                return JobResult(
                    success=False,
                    message=f"Missing required field: {key}",
                    error=f"Library apply requires a numeric {key}",
                )

        try:
            from auto_edit_apply import run_library_apply
        except ImportError:
            from ui.auto_edit_apply import run_library_apply

        job.update_progress(5, "Initializing library edit apply...")
        if config:
            _inject_sermon_updater_config(config)
            job.add_log("Config injected for this job")

        def progress_cb(pct, msg):
            if job.cancelled or job.status == JobStatus.CANCELLED:
                raise JobCancelledError("Job cancelled by user")
            try:
                job.update_progress(pct, msg)
            except Exception:
                pass

        job.update_progress(10, f"Applying approved edit for {sermon_id}")
        result = run_library_apply(
            __import__("ui.database", fromlist=["SermonRepository"]).SermonRepository(),
            str(sermon_id),
            float(start),
            float(end),
            audio_offset=float(audio_offset),
            render_only=render_only,
            re_detect=re_detect,
            plan_id=plan_id,
            progress_callback=progress_cb,
            cancel_check=lambda: _raise_if_job_cancelled(job),
            config=config or None,
        )

        if result.get("cancelled"):
            job.add_log("Library apply cancelled by user")
            raise JobCancelledError("Job cancelled by user")

        if render_only and result.get("success"):
            if bool(result.get("auto_edit_applied")) and result.get("edit_plan_status") in (
                "auto_applied",
                "applied_local",
            ):
                rendered_id = result.get("sermon_id") or ""
                _stamp_sermon_owner(result.get("sermon_id") or sermon_id, _job_user_id(job))
                job.add_log(f"Edit rendered locally, not uploaded ({rendered_id})")
                return JobResult(
                    success=True,
                    message=(
                        "Edit rendered locally; nothing was uploaded. Review the media, "
                        "then use Upload now when ready."
                    ),
                    data=_trim_result_payload(result),
                )
            err = result.get("error") or (
                "Pipeline finished without rendering the approved cut "
                f"(edit_plan_status={result.get('edit_plan_status')}); nothing was rendered."
            )
            job.add_log(err)
            return JobResult(
                success=False,
                message=f"Edit apply failed: {err}",
                error=err,
                data=_trim_result_payload(result),
            )

        if result.get("success"):
            _stamp_sermon_owner(result.get("sermon_id") or sermon_id, _job_user_id(job))
            applied_status = result.get("edit_plan_status") or "auto_applied"
            if applied_status == "auto_applied" and bool(result.get("auto_edit_applied")):
                job.add_log(f"Edit applied and uploaded ({result.get('sermon_id')})")
                return JobResult(
                    success=True,
                    message=(
                        f"Edit applied and uploaded ({result.get('sermon_id')})"
                    ),
                    data=_trim_result_payload(result),
                )
            err = (
                "Processing finished but the plan still needs review. "
                "Check the plan for the new sermon record."
            )
            job.add_log(err)
            return JobResult(
                success=False,
                message=err,
                error="edit_plan_status did not reach auto_applied",
                data=_trim_result_payload(result),
            )

        err = result.get("error") or "Unknown processing error"
        job.add_log(err)
        return JobResult(
            success=False,
            message=f"Edit apply failed: {err}",
            error=err,
            data=_trim_result_payload(result),
        )

    except JobCancelledError:
        raise
    except Exception as e:
        error_msg = f"Library apply job failed: {e}"
        job.add_log(error_msg)
        logger.exception(error_msg)
        return JobResult(
            success=False,
            message="Library apply job failed",
            error=str(e),
        )


def _execute_auto_edit_dispatch(job: Job) -> JobResult:
    """Route AUTO_EDIT jobs: refine, apply continuation, or fresh processing."""
    if job.parameters.get('refine'):
        return execute_auto_edit_refine_job(job)
    if job.parameters.get('plan_id') is not None:
        return execute_auto_edit_apply_job(job)
    return execute_auto_edit_job(job)


def execute_sermon_publish_job(job: Job) -> JobResult:
    """Upload a draft sermon to SermonAudio via publish_dry_run_sermon."""
    try:
        if job.cancelled or job.status == JobStatus.CANCELLED:
            raise JobCancelledError("Job cancelled by user")
        sermon_id = job.parameters.get("sermon_id")
        if not sermon_id:
            return JobResult(
                success=False,
                message="Missing sermon_id for publish",
                error="Missing sermon_id in job parameters",
            )
        job.update_progress(10, f"Publishing {sermon_id} to SermonAudio...")
        from sermon_updater import publish_dry_run_sermon

        result = publish_dry_run_sermon(str(sermon_id))
        if result.get("success"):
            _stamp_sermon_owner(result.get("sermon_id") or sermon_id, _job_user_id(job))
            job.update_progress(100, f"Published as {result.get('sermon_id')}")
            return JobResult(
                success=True,
                message=f"Published to SermonAudio as {result.get('sermon_id')}",
                data={"sermon_id": result.get("sermon_id")},
            )
        return JobResult(
            success=False,
            message="Publish failed",
            error=result.get("error") or "unknown error",
        )
    except JobCancelledError:
        raise
    except Exception as e:
        return JobResult(success=False, message="Publish failed", error=str(e))


# Job executor registry
_EXECUTORS: dict[JobType, Callable[[Job], JobResult]] = {
    JobType.VALIDATION: execute_validation_job,
    JobType.SERMON_IMPORT: execute_sermon_import_job,
    JobType.SERMON_PROCESSING: execute_sermon_processing_job,
    JobType.BATCH_PROCESSING: execute_batch_processing_job,
    JobType.METADATA_UPDATE: execute_metadata_update_job,
    JobType.AUTO_EDIT: _execute_auto_edit_dispatch,
    JobType.AUTO_EDIT_APPLY: execute_library_auto_edit_apply_job,
    JobType.SERMON_PUBLISH: execute_sermon_publish_job,
}


def get_executor(job_type: JobType) -> Callable[[Job], JobResult] | None:
    """Get the executor function for a specific job type"""
    return _EXECUTORS.get(_canon(job_type))


def register_executor(job_type: JobType, executor: Callable[[Job], JobResult]):
    """Register a new job executor"""
    _EXECUTORS[job_type] = executor


def get_available_job_types() -> list[JobType]:
    """Get list of available job types"""
    return list(_EXECUTORS.keys())
