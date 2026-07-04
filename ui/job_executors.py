"""
Job Executors for Background Job Queue

Contains the actual execution logic for different types of background jobs.
Each executor is responsible for performing the work and updating job progress.
"""

import logging
import sys
from collections.abc import Callable
from pathlib import Path

# Add project paths for imports
ui_dir = Path(__file__).parent
project_root = ui_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from job_queue import Job, JobResult, JobStatus, JobType

logger = logging.getLogger(__name__)


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
            try:
                progress = 20 + (i / len(sermon_ids)) * 70  # 20-90% for processing
                job.update_progress(progress, f"Validating sermon {sermon_id} ({i+1}/{len(sermon_ids)})")

                # Get configuration from job parameters first, then try loading from file as fallback
                config = job.parameters.get('config', {})
                if not config:
                    job.add_log("No config in job parameters, attempting to load from file...")
                    try:
                        # Try to load configuration from file as fallback
                        from pathlib import Path

                        import yaml

                        # Look for config.yaml in the project root
                        config_path = Path(__file__).parent.parent / "config.yaml"
                        if config_path.exists():
                            with open(config_path, encoding='utf-8') as f:
                                config = yaml.safe_load(f)
                            job.add_log(f"Loaded configuration from {config_path}")
                        else:
                            raise FileNotFoundError(f"Config file not found at {config_path}")
                    except Exception as e:
                        job.add_log(f"Failed to load config from file: {e}")
                        raise ValueError(f"No configuration available in job parameters and failed to load from file: {e}")

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
                        job.add_log(f"✅ Sermon {sermon_id}: Valid (score: {validation_result.validation_score:.2f})")
                    else:
                        results['invalid'] += 1
                        job.add_log(f"❌ Sermon {sermon_id}: Invalid (score: {validation_result.validation_score:.2f})")
                else:
                    results['errors'] += 1
                    job.add_log(f"⚠️ Sermon {sermon_id}: Validation failed")

                results['completed'] += 1

            except Exception as e:
                results['errors'] += 1
                job.add_log(f"❌ Error validating sermon {sermon_id}: {str(e)}")
                logger.error(f"Validation error for sermon {sermon_id}: {e}")

        job.update_progress(95, "Finalizing validation results...")

        # Create summary message
        summary = f"Validation completed: {results['valid']} valid, {results['invalid']} invalid, {results['errors']} errors"
        job.update_progress(100, summary)

        return JobResult(
            success=True,
            message=summary,
            data=results
        )

    except Exception as e:
        error_msg = f"Validation job failed: {str(e)}"
        job.add_log(f"❌ {error_msg}")
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

        job.update_progress(20, f"Scanning processed sermons directory... (force_reimport={force_reimport})")

        # Import sermon importer
        from database import SermonRepository
        from sermon_importer import SermonImporter

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
            try:
                progress = 40 + (i / len(sermon_folders)) * 50  # 40-90% for processing
                job.update_progress(progress, f"Importing sermon {sermon_id} ({i+1}/{len(sermon_folders)})")

                # Check if sermon already exists (skip check if force_reimport is True)
                existing_sermon = repo.get_sermon(sermon_id)
                if existing_sermon and not force_reimport:
                    results['skipped'] += 1
                    job.add_log(f"⏭️ Sermon {sermon_id}: Already exists, skipping")
                    continue

                # Import or re-import the sermon
                if force_reimport and existing_sermon:
                    job.add_log(f"🔄 Sermon {sermon_id}: Force re-importing...")
                    # Delete existing sermon if force reimport
                    repo.delete_sermon(sermon_id)

                success = importer.import_sermon(sermon_id, refresh_api_data=refresh_api_data)
                if success:
                    # Get the imported sermon data for logging
                    imported_sermon = repo.get_sermon(sermon_id)
                    sermon_title = imported_sermon.get('title', 'Unknown') if imported_sermon else 'Unknown'

                    results['imported'] += 1
                    job.add_log(f"✅ Sermon {sermon_id}: Imported successfully - {sermon_title}")
                    results['details'].append({
                        'sermon_id': sermon_id,
                        'status': 'imported',
                        'title': sermon_title
                    })
                else:
                    results['errors'] += 1
                    job.add_log(f"❌ Sermon {sermon_id}: Failed to import")

            except Exception as e:
                results['errors'] += 1
                job.add_log(f"❌ Error importing sermon {sermon_id}: {str(e)}")
                logger.error(f"Import error for sermon {sermon_id}: {e}")

        job.update_progress(95, "Finalizing import results...")

        # Create summary message
        summary = f"Import completed: {results['imported']} imported, {results['skipped']} skipped, {results['errors']} errors"
        job.update_progress(100, summary)

        return JobResult(
            success=True,
            message=summary,
            data=results
        )

    except Exception as e:
        error_msg = f"Import job failed: {str(e)}"
        job.add_log(f"❌ {error_msg}")
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
    try:
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

        # Inject the config into the sermon_updater module so that its
        # module-level constants (api_key, broadcaster_id, LLM manager, etc.)
        # are correct for this job.
        try:
            import sermon_updater
            from sermon_updater import ConfigManager, LLMManager
            sermon_updater.config = config
            sermon_updater.config_manager = ConfigManager()
            sermon_updater.llm_manager = LLMManager(config)
            sermon_updater.SERMON_AUDIO_API_KEY = config.get('api_key')
            sermon_updater.SERMON_AUDIO_BROADCASTER_ID = config.get('broadcaster_id')
            # Reload the sermonaudio library key
            try:
                import sermonaudio
                sermonaudio.set_api_key(sermon_updater.SERMON_AUDIO_API_KEY)
            except Exception:
                pass
            job.add_log("Config injected for this job")
        except Exception as e:
            job.add_log(f"⚠️ Failed to inject config (may still work): {e}")
            logger.warning(f"Config injection warning: {e}")

        # Progress callback that updates the job
        def progress_cb(pct, msg):
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
            description=form_data.get('description') or None,
            hashtags=form_data.get('hashtags') or None,
            dry_run=bool(form_data.get('dry_run', False)),
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
            progress_callback=progress_cb,
        )

        if result.get('success'):
            sermon_id = result.get('sermon_id')
            job.add_log(f"✅ Sermon created: {sermon_id or '(dry run)'}")
            return JobResult(
                success=True,
                message=f"Sermon processed successfully: {sermon_id or 'dry run'}",
                data=result,
            )
        else:
            err = result.get('error') or 'Unknown processing error'
            job.add_log(f"❌ {err}")
            return JobResult(
                success=False,
                message=f"Processing failed: {err}",
                error=err,
                data=result,
            )

    except Exception as e:
        error_msg = f"Sermon processing job failed: {e}"
        job.add_log(f"❌ {error_msg}")
        logger.exception(error_msg)
        return JobResult(
            success=False,
            message="Sermon processing job failed",
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

        # Set the global config in sermon_updater module
        sermon_updater.config = config

        # Process each sermon
        for i, sermon_id in enumerate(sermon_ids):
            try:
                # Check if job was cancelled
                if job.status == JobStatus.CANCELLED:
                    job.add_log("Batch processing cancelled by user")
                    break

                progress = 20 + (i / len(sermon_ids)) * 70  # 20-90% for processing
                job.update_progress(progress, f"Processing sermon {sermon_id} ({i+1}/{len(sermon_ids)})")

                sermon_result = {
                    'sermon_id': sermon_id,
                    'status': 'success',
                    'actions_performed': [],
                    'errors': []
                }

                # Perform selected actions
                if actions.get('generate_description') or actions.get('generate_hashtags'):
                    try:
                        job.add_log(f"Processing metadata for sermon {sermon_id}")
                        form_data = job.parameters.get('form_data', {})
                        # Use the existing sermon processing function with appropriate flags
                        sermon_updater.process_single_sermon(
                            sermon_id,
                            no_upload=bool(form_data.get('dry_run', False)),
                            verbose=False,
                            skip_audio=not actions.get('enhance_audio', False),
                            force_description=actions.get('generate_description', False),
                            force_hashtags=actions.get('generate_hashtags', False),
                            no_metadata=False,
                            transcription_backend=form_data.get('transcription_backend'),
                            audio_file=form_data.get('uploaded_file_path'),
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
                job.add_log(f"✅ Sermon {sermon_id}: {len(sermon_result['actions_performed'])} actions completed")

            except Exception as e:
                results['failed'] += 1
                error_result = {
                    'sermon_id': sermon_id,
                    'status': 'error',
                    'actions_performed': [],
                    'errors': [f"Processing error: {str(e)}"]
                }
                results['details'].append(error_result)
                job.add_log(f"❌ Error processing sermon {sermon_id}: {str(e)}")

        summary = f"Batch processing completed: {results['completed']} successful, {results['failed']} failed"
        job.update_progress(100, summary)

        return JobResult(
            success=True,
            message=summary,
            data=results
        )

    except Exception as e:
        error_msg = f"Batch processing job failed: {str(e)}"
        job.add_log(f"❌ {error_msg}")
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

        job.update_progress(10, f"Starting metadata update for {len(sermon_ids)} sermons...")

        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import sermon_updater
        from sermon_updater import DescriptionValidator

        sermon_updater.config = config

        results = {
            'total': len(sermon_ids),
            'completed': 0,
            'failed': 0,
            'details': []
        }

        for i, sermon_id in enumerate(sermon_ids):
            try:
                progress = 10 + (i / len(sermon_ids)) * 80
                job.update_progress(progress, f"Processing sermon {sermon_id} ({i+1}/{len(sermon_ids)})")

                sermon_updater.process_single_sermon(
                    sermon_id,
                    no_upload=False,
                    verbose=False,
                    skip_audio=True,
                    force_description=actions.get('generate_description', False),
                    force_hashtags=actions.get('generate_hashtags', False),
                    no_metadata=False
                )

                results['completed'] += 1
                job.add_log(f"✅ Sermon {sermon_id}: Updated")

            except Exception as e:
                results['failed'] += 1
                job.add_log(f"❌ Sermon {sermon_id}: {str(e)}")
                logger.error(f"Metadata update error for {sermon_id}: {e}")

        summary = f"Metadata update: {results['completed']} completed, {results['failed']} failed"
        job.update_progress(100, summary)

        return JobResult(success=True, message=summary, data=results)

    except Exception as e:
        error_msg = f"Metadata update job failed: {str(e)}"
        job.add_log(f"❌ {error_msg}")
        return JobResult(success=False, message="Metadata update job failed", error=str(e))


# Job executor registry
_EXECUTORS: dict[JobType, Callable[[Job], JobResult]] = {
    JobType.VALIDATION: execute_validation_job,
    JobType.SERMON_IMPORT: execute_sermon_import_job,
    JobType.SERMON_PROCESSING: execute_sermon_processing_job,
    JobType.BATCH_PROCESSING: execute_batch_processing_job,
    JobType.METADATA_UPDATE: execute_metadata_update_job,
}


def get_executor(job_type: JobType) -> Callable[[Job], JobResult] | None:
    """Get the executor function for a specific job type"""
    return _EXECUTORS.get(job_type)


def register_executor(job_type: JobType, executor: Callable[[Job], JobResult]):
    """Register a new job executor"""
    _EXECUTORS[job_type] = executor


def get_available_job_types() -> list[JobType]:
    """Get list of available job types"""
    return list(_EXECUTORS.keys())
