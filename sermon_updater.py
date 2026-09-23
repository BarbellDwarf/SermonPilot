"""SermonAudio Updater & Processor

Core capabilities:
* List sermons with comprehensive filtering (all public API query params exposed).
* Process sermons: download audio, enhance, summarize, hashtag, update metadata, upload audio.
* Multi‑year support: ``--year`` (single) or ``--years`` (comma/range list).
* AI-powered description validation with automatic quality assessment and regeneration.

Examples:
    python sermon_updater.py --sermon-id 1234567890123
    python sermon_updater.py --since-days 14 --event-type "Sunday - AM" --require-audio --limit 5
    python sermon_updater.py --search-keyword grace --language-code eng --dry-run --list-only
    python sermon_updater.py --date-range 2024-01-01 2024-01-31 --auto-yes
    python sermon_updater.py --years 2022-2023,2025 --limit 10 --list-only

Validation examples (all validation tools now integrated):
    python sermon_updater.py --validate-descriptions --validation-report
    python sermon_updater.py --validate-and-regenerate --dry-run
    python sermon_updater.py --validate-descriptions --export-validation-csv results.csv
    python sermon_updater.py --validate-and-regenerate --validation-sermon-ids 123,456,789

Processing with validation (requires validator LLM configuration):
    python sermon_updater.py --sermon-id 1234567890123 --force-description
    (Automatically validates and may regenerate descriptions using fallback LLM if primary fails)

Config: resolved from the settings database (environment overrides win).
``--config`` still accepts an explicit file for one-off CLI runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
import warnings
from collections.abc import Callable, Iterable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

print("Initializing SermonPilot...")
print("   Loading dependencies...")

import requests  # noqa: E402
import sermonaudio  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from sermonaudio.node.requests import Node  # noqa: E402

from src.sermon_paths import (  # noqa: E402
    FILENAMES,
    discover_sermons,
    find_sermon_dir,
    get_file_path,
    get_sermon_dir,
    read_metadata,
    read_transcript_timestamps,
    save_transcript_timestamps,
)
from src.supervised_process import (  # noqa: E402
    ProcessCancelled,
    run_supervised,
)

print("   Loading AI components...")
# Suppress ML library import noise
with redirect_stdout(StringIO()), redirect_stderr(StringIO()), warnings.catch_warnings():
    warnings.simplefilter("ignore")
    os.environ["PYTHONWARNINGS"] = "ignore"
    # Suppress torchaudio warning specifically
    os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "1"
    # Suppress additional PyTorch audio warnings
    os.environ["TORCHAUDIO_ENABLE_BACKEND_DISPATCH"] = "1"
    os.environ["TORCHAUDIO_BACKEND"] = "soundfile"
    # Add src directory to Python path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

    # Pre-configure DF logging before import
    import logging
    logging.getLogger("df").setLevel(logging.CRITICAL)
    logging.getLogger("df").disabled = True
    # Also suppress torchaudio warnings in logging
    logging.getLogger("torchaudio").setLevel(logging.CRITICAL)
    logging.getLogger("torchaudio").disabled = True
    try:
        from audio_processing import process_sermon_audio
    except Exception:
        # Fallback no-op processor if dependencies missing
        def process_sermon_audio(*args, **kwargs):
            return False
    from auto_edit import (
        EditPlan,
        apply_edit,
        detect_cut_points,
        trash_original_after_edit,
        validate_plan,
    )
    from cli.parser import CLIParser, confirm
    from core.config import ConfigManager
    from llm_manager import (
        LLMManager,
        LLMModelNotConfiguredError,
        LLMModelNotFoundError,
        LLMTimeoutError,
    )
    from llm_manager import _call_with_deadline as _llm_call_with_deadline
    from metadata_cleanup import (
        clean_description,
        clean_description_with_retry,
        clean_hashtags,
        clean_title,
    )
    from processing.orchestrator import (
        ArgumentsNormalizer,
        ProcessingOrchestrator,
        SermonFilter,
    )
    from transcription import (
        TranscriptionError,
        log_cuda_memory,
        release_enhancement_gpu,
        transcribe_segments,
    )
    try:
        sys.path.insert(0, str(Path(__file__).parent / "ui"))
        from database import SermonRepository
        database_available = True
    except ImportError:
        database_available = False
        SermonRepository = None

# Guard module-level prints to avoid noise when importing as a library
_is_cli = __name__ == '__main__'

if _is_cli:
    print("   Configuring environment...")
load_dotenv()

if _is_cli:
    print("Initialization complete!")
    print("Retrieving Sermon List....")

# Configure logging
logger = logging.getLogger(__name__)

def setup_logging(verbose: bool = False):
    """Configure logging levels based on verbose flag."""
    level = logging.DEBUG if verbose else logging.ERROR
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s' if verbose else '%(message)s',
        force=True
    )

    # Set third-party loggers to ERROR unless in verbose mode
    if not verbose:
        for logger_name in [
            'requests', 'urllib3', 'audio_processing', 'llm_manager',
            'transformers', 'torch', 'torchaudio', 'deepspeed', 'df',
            'deepfilternet', 'DeepFilterNet'
        ]:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

        # Specifically suppress DF logger which is very verbose
        df_logger = logging.getLogger("df")
        df_logger.setLevel(logging.CRITICAL)
        df_logger.disabled = True
def load_config(path: str) -> dict:
    """Load an explicitly passed config file (CLI --config)."""
    config_manager = ConfigManager(path)
    return config_manager.get_raw_config()


CONFIG_PATH = os.environ.get("SA_UPDATER_CONFIG", "config.yaml")

try:
    from ui.config_utils import resolve_config

    config = resolve_config()
except Exception as exc:
    logger.error("Settings database unavailable, starting with defaults: %s", exc)
    config = {}

missing_settings = [key for key in ('api_key', 'broadcaster_id') if not config.get(key)]
if missing_settings:
    logger.warning(
        "Missing required configuration settings: %s. Set SERMONAUDIO_API_KEY and "
        "SERMONAUDIO_BROADCASTER_ID, or save them in the settings UI.",
        ', '.join(missing_settings)
    )

# For backward compatibility, provide config dict
def refresh_runtime_config(config_override: dict | None = None) -> dict:
    """Rebuild every module-level runtime constant from the settings database.

    UI edits land in the settings DB; the processing engine reads it fresh on
    every sermon run, so settings saved in the UI apply without a restart.
    Pass an explicit config dict to force those values instead.
    """
    global config, llm_manager, SERMON_AUDIO_API_KEY, SERMON_AUDIO_BROADCASTER_ID
    global DRY_RUN, DEBUG, AUDIO_PARAMS
    if config_override is None:
        try:
            from ui.config_utils import resolve_config

            config_override = resolve_config()
        except Exception as exc:
            logger.error("Settings database unavailable during refresh: %s", exc)
            return config
    llm_manager = LLMManager(config_override)
    SERMON_AUDIO_API_KEY = config_override.get('api_key')
    SERMON_AUDIO_BROADCASTER_ID = config_override.get('broadcaster_id')
    sermonaudio.set_api_key(SERMON_AUDIO_API_KEY)
    DRY_RUN = config_override.get('dry_run', False)
    DEBUG = config_override.get('debug', False)
    AUDIO_PARAMS = {
        'noise_reduction': config_override.get('audio_noise_reduction', True),
        'amplify': config_override.get('audio_amplify', True),
        'normalize': config_override.get('audio_normalize', True),
        'gain_db': config_override.get('audio_gain_db', 1.0),
        'target_level_db': config_override.get('audio_target_level_db', -22.0),
        'enhancement_method': config_override.get('audio_enhancement_method', 'deepfilternet'),
        'config': config_override
    }
    config = config_override
    return config


refresh_runtime_config()

BASE_URL = 'https://api.sermonaudio.com/v2/'


def _get_prompt_template(template_name: str, **kwargs) -> tuple[str, str] | None:
    """Read a prompt template from config and format it with the given kwargs.

    Returns (system_prompt, user_prompt) or None if the template is disabled
    or not found in config.
    """
    templates = config.get('prompt_templates', {})
    tmpl = templates.get(template_name)
    if not tmpl or not tmpl.get('enabled', True):
        return None
    system_text = tmpl.get('system', '')
    user_text = tmpl.get('user', '')
    try:
        user_text = user_text.format(**kwargs)
    except KeyError as e:
        logger.warning("Prompt template '%s' missing key: %s", template_name, e)
    return (system_text, user_text)


def _llm_target_label() -> str:
    """Human-readable identity of the active primary LLM for progress logs."""
    try:
        info = llm_manager.get_provider_info() or {}
    except Exception:
        return "unknown model"
    primary = info.get('primary') or {}
    provider = primary.get('type') or 'unknown'
    model = primary.get('model') or 'unknown'
    provider_obj = getattr(llm_manager, 'primary_provider', None)
    host = getattr(provider_obj, 'host', None) or getattr(provider_obj, 'base_url', None)
    if host:
        return f"{provider} model={model} @ {host}"
    return f"{provider} model={model}"


def _log_metadata_timeout(exc: LLMTimeoutError) -> None:
    logger.warning(
        "metadata generation timed out after %.0fs; continuing without it",
        float(getattr(exc, 'timeout', 0.0) or 0.0),
    )


def _log_metadata_model_missing(exc: LLMModelNotFoundError) -> None:
    model = getattr(exc, 'model', 'unknown')
    available = getattr(exc, 'available_models', None)
    if available:
        logger.warning(
            "metadata skipped: model '%s' is not available. Available models: %s",
            model,
            ", ".join(available),
        )
    else:
        logger.warning(
            "metadata skipped: model '%s' is not available; continuing without it", model
        )


_DEFAULT_METADATA_STAGE_BUDGET_SECONDS = 900.0


def _metadata_stage_budget_seconds() -> float:
    """Wall-clock budget for the whole metadata stage (title, description, hashtags)."""
    llm_config = config.get('llm', {}) if isinstance(config, dict) else {}
    return float(
        _positive_setting(
            llm_config.get('metadata_stage_budget_seconds'),
            _DEFAULT_METADATA_STAGE_BUDGET_SECONDS,
        )
    )


def _positive_setting(value, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def console_print(message: str, level: str = "info"):
    """Print messages to console with appropriate formatting.

    Args:
        message: Message to print
        level: Message level (info, warning, error, success)
    """
    if level == "error":
        print(f"ERROR: {message}")
    elif level == "warning":
        print(f"WARNING: {message}")
    elif level == "success":
        print(f"SUCCESS: {message}")
    else:
        print(f"INFO: {message}")


def is_content_missing_or_minimal(content: str | None, min_length: int) -> bool:
    """Check if content is missing or too minimal to be useful.

    Args:
        content: The content to check (description or hashtags)
        min_length: Minimum length threshold for substantial content

    Returns:
        True if content is missing or minimal, False otherwise
    """
    if content is None or content.strip() == "":
        return True
    return len(content.strip()) < min_length


def should_update_description(
    existing_description: str | None, config: dict, force_flag: bool = False
) -> bool:
    """Determine if description should be updated based on existing content and config.

    Args:
        existing_description: Current description from sermon
        config: Configuration dictionary
        force_flag: Whether to force update regardless of config

    Returns:
        True if description should be updated, False otherwise
    """
    if force_flag:
        return True

    metadata_config = config.get('metadata_processing', {})
    description_config = metadata_config.get('description', {})

    if not metadata_config.get('enabled', True):
        return False

    if description_config.get('force_update', False):
        return True

    min_length = description_config.get('min_length_threshold', 50)

    if is_content_missing_or_minimal(existing_description, min_length):
        return (description_config.get('update_if_missing', True) or
                description_config.get('update_if_minimal', True))

    return False


def should_update_hashtags(
    existing_hashtags: str | None, config: dict, force_flag: bool = False
) -> bool:
    """Determine if hashtags should be updated based on existing content and config.

    Args:
        existing_hashtags: Current hashtags from sermon
        config: Configuration dictionary
        force_flag: Whether to force update regardless of config

    Returns:
        True if hashtags should be updated, False otherwise
    """
    if force_flag:
        return True

    metadata_config = config.get('metadata_processing', {})
    hashtags_config = metadata_config.get('hashtags', {})

    if not metadata_config.get('enabled', True):
        return False

    if hashtags_config.get('force_update', False):
        return True

    min_length = hashtags_config.get('min_length_threshold', 10)

    if is_content_missing_or_minimal(existing_hashtags, min_length):
        return (hashtags_config.get('update_if_missing', True) or
                hashtags_config.get('update_if_minimal', True))

    return False


def get_sermon_transcript(sermon_id: str) -> str:
    """Retrieve transcript for a sermon from the SermonAudio API.

    Args:
        sermon_id: The sermon ID to get transcript for

    Returns:
        Transcript text if available, empty string otherwise
    """
    try:
        api_url = f"{BASE_URL}node/sermons/{sermon_id}"
        resp = requests.get(api_url, headers={'X-Api-Key': SERMON_AUDIO_API_KEY}, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            t_obj = data.get('transcript')
            if t_obj and t_obj.get('downloadURL'):
                t_resp = requests.get(t_obj['downloadURL'], timeout=60)
                if t_resp.status_code == 200:
                    logger.debug("Transcript retrieved successfully")
                    return t_resp.text
        logger.debug("No transcript available")
        return ""
    except Exception as e:
        logger.error("Transcript retrieval error: %s", e)
        return ""


def get_sermon_details(sermon_id: str) -> dict:
    """Retrieve full sermon details from the SermonAudio API.

    Args:
        sermon_id: The sermon ID to get details for

    Returns:
        Dictionary containing sermon metadata, empty dict if not found
    """
    try:
        api_url = f"{BASE_URL}node/sermons/{sermon_id}"
        resp = requests.get(api_url, headers={'X-Api-Key': SERMON_AUDIO_API_KEY}, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            logger.debug(f"Sermon details retrieved successfully for {sermon_id}")
            return data
        else:
            if resp.status_code == 404:
                logger.info(f"Sermon {sermon_id} not yet available on SermonAudio (404)")
            else:
                logger.warning(
                    f"Failed to get sermon details for {sermon_id}: HTTP {resp.status_code}"
                )
            return {}
    except Exception as e:
        logger.error(f"Error retrieving sermon details for {sermon_id}: {e}")
        return {}


def needs_metadata_processing(
    sermon_details, config: dict, force_description: bool = False, force_hashtags: bool = False
) -> tuple[bool, bool]:
    """Determine if metadata processing is needed for a sermon.

    Args:
        sermon_details: Sermon details from API
        config: Configuration dictionary
        force_description: Force description update
        force_hashtags: Force hashtags update

    Returns:
        Tuple of (needs_description_update, needs_hashtags_update)
    """
    if not config.get('metadata_processing', {}).get('enabled', True):
        return False, False

    existing_description = (getattr(sermon_details, 'moreInfoText', None) or
                           getattr(sermon_details, 'more_info_text', None))
    existing_hashtags = getattr(sermon_details, 'keywords', None)

    needs_description = should_update_description(existing_description, config, force_description)
    needs_hashtags = should_update_hashtags(existing_hashtags, config, force_hashtags)

    return needs_description, needs_hashtags


def needs_audio_processing(config: dict, skip_audio: bool = False) -> bool:
    """Determine if audio processing is needed.

    Args:
        config: Configuration dictionary
        skip_audio: CLI flag to skip audio processing

    Returns:
        True if audio should be processed, False otherwise
    """
    if skip_audio:
        return False

    return config.get('metadata_processing', {}).get('process_audio', True)


def get_api_headers() -> dict[str, str]:
    key = SERMON_AUDIO_API_KEY or os.environ.get('SERMONAUDIO_API_KEY', '')
    if not key:
        raise ValueError(
            "SermonAudio API key is not configured. Save it in Settings under "
            "SermonAudio Accounts, or set the SERMONAUDIO_API_KEY environment variable."
        )
    return {'X-Api-Key': key, 'Content-Type': 'application/json'}


# Validation Classes and Functions
@dataclass
class ValidationResult:
    """Result of a description validation check."""
    sermon_id: str
    title: str
    speaker: str
    description: str
    description_length: int
    is_valid: bool
    validation_reason: str
    validation_score: float
    criteria_met: list[str]
    criteria_failed: list[str]
    needs_regeneration: bool
    validated_at: str
    source: str  # 'local' or 'api'


@dataclass
class ValidationSummary:
    """Summary of validation results."""
    total_sermons: int
    valid_descriptions: int
    invalid_descriptions: int
    validation_rate: float
    needs_regeneration: int
    average_score: float
    criteria_performance: dict[str, float]


class DescriptionValidator:
    """Main class for validating sermon descriptions."""

    def __init__(self, config: dict):
        """Initialize the validator with configuration."""
        self.config = config
        self.llm_manager = llm_manager  # Use global LLM manager
        self.validation_criteria = self._get_validation_criteria()
        self.output_dir = config.get('output_directory', 'processed_sermons')

        # Validation thresholds
        metadata_config = config.get('metadata_processing', {})
        desc_config = metadata_config.get('description', {})
        validation_config = desc_config.get('validation', {})
        self.min_length = validation_config.get('min_length_threshold', 50)
        self.max_length = validation_config.get('max_length_threshold', 1600)
        self.regeneration_threshold = validation_config.get('regeneration_threshold', 0.6)

    def _get_validation_criteria(self) -> list[str]:
        """Get validation criteria from config."""
        metadata_config = self.config.get('metadata_processing', {})
        desc_config = metadata_config.get('description', {})
        validation_config = desc_config.get('validation', {})

        default_criteria = [
            "Contains specific theological content or Bible references",
            "Mentions the speaker's main message or key points",
            "Is written in a professional, engaging style",
            "Avoids generic Christian phrases without substance",
            "Has clear application or takeaway for listeners"
        ]

        return validation_config.get('criteria', default_criteria)

    def validate_description(
        self, description: str, context: dict = None
    ) -> tuple[bool, str, float, list[str], list[str]]:
        """
        Validate a single description against criteria.

        Args:
            description: The description text to validate
            context: Additional context (title, speaker, etc.)

        Returns:
            Tuple of (is_valid, reason, score, criteria_met, criteria_failed)
        """
        if not description or len(description.strip()) < self.min_length:
            return False, "Description too short or empty", 0.0, [], self.validation_criteria

        if len(description) > self.max_length:
            return False, "Description exceeds maximum length", 0.2, [], self.validation_criteria

        # Enhanced validation prompt for detailed analysis
        context_info = ""
        if context:
            if context.get('title'):
                context_info += f"Sermon Title: {context['title']}\n"
            if context.get('speaker'):
                context_info += f"Speaker: {context['speaker']}\n"

        criteria_text = "\n".join(
            [f"{i+1}. {criterion}" for i, criterion in enumerate(self.validation_criteria)]
        )

        validation_prompt = f"""You are a sermon description quality validator.
Evaluate the following description against specific criteria and provide a detailed assessment.

{context_info}
Validation Criteria:
{criteria_text}

Description to validate:
{description}

Please provide your assessment in this exact format:
SCORE: [0.0-1.0]
STATUS: [APPROVED/REJECTED]
REASON: [brief explanation]
CRITERIA_MET: [comma-separated list of criterion numbers that are met, e.g., "1,3,5"]
CRITERIA_FAILED: [comma-separated list of criterion numbers that failed, e.g., "2,4"]

Guidelines:
- Score 0.8+ = APPROVED (high quality)
- Score 0.6-0.79 = APPROVED but could be improved
- Score <0.6 = REJECTED (needs regeneration)
- Consider theological depth, specificity, professional tone, and practical application
- Be specific about which criteria are met or failed
"""

        try:
            if not llm_manager.validator_provider:
                logger.warning("No validator LLM configured, using primary provider")
                response = llm_manager.chat([{'role': 'user', 'content': validation_prompt}])
            else:
                response = _llm_call_with_deadline(
                    lambda: llm_manager.validator_provider.chat([
                        {'role': 'user', 'content': validation_prompt}
                    ]),
                    float(getattr(llm_manager, 'call_timeout_seconds', 120.0)),
                    'description_validation',
                )

            # Parse the structured response
            score, is_valid, reason, criteria_met, criteria_failed = (
                self._parse_validation_response(response)
            )

            return is_valid, reason, score, criteria_met, criteria_failed

        except Exception as e:
            logger.warning(f"Validation failed: {e}")
            # Fail closed: a configured validator that errors must not approve
            return False, f"Validation error: {e}", 0.5, [], []

    def _parse_validation_response(
        self, response: str
    ) -> tuple[float, bool, str, list[str], list[str]]:
        """Parse the LLM validation response into structured data."""
        lines = [line.strip() for line in response.strip().split('\n') if line.strip()]

        score = 0.5
        is_valid = True
        reason = "Parsed response"
        criteria_met = []
        criteria_failed = []

        for line in lines:
            if line.startswith('SCORE:'):
                try:
                    score = float(line.split(':', 1)[1].strip())
                    score = max(0.0, min(1.0, score))  # Clamp to 0-1
                except ValueError:
                    score = 0.5

            elif line.startswith('STATUS:'):
                status = line.split(':', 1)[1].strip().upper()
                is_valid = status == 'APPROVED'

            elif line.startswith('REASON:'):
                reason = line.split(':', 1)[1].strip()

            elif line.startswith('CRITERIA_MET:'):
                met_text = line.split(':', 1)[1].strip()
                if met_text and met_text != 'None':
                    try:
                        met_indices = [
                            int(x.strip()) - 1 for x in met_text.split(',') if x.strip().isdigit()
                        ]
                        criteria_met = [self.validation_criteria[i] for i in met_indices
                                      if 0 <= i < len(self.validation_criteria)]
                    except (ValueError, IndexError):
                        pass

            elif line.startswith('CRITERIA_FAILED:'):
                failed_text = line.split(':', 1)[1].strip()
                if failed_text and failed_text != 'None':
                    try:
                        failed_indices = [
                            int(x.strip()) - 1
                            for x in failed_text.split(',')
                            if x.strip().isdigit()
                        ]
                        criteria_failed = [self.validation_criteria[i] for i in failed_indices
                                         if 0 <= i < len(self.validation_criteria)]
                    except (ValueError, IndexError):
                        pass

        # If score is below threshold, ensure it's marked as invalid
        if score < self.regeneration_threshold:
            is_valid = False

        return score, is_valid, reason, criteria_met, criteria_failed

    def validate_local_sermons(self, sermon_ids: list[str] = None) -> list[ValidationResult]:
        """Validate descriptions from local processed sermon directories."""
        results = []

        if sermon_ids:
            for sid in sermon_ids:
                sermon_dir = find_sermon_dir(self.output_dir, sid)
                if sermon_dir:
                    result = self._validate_local_sermon(sermon_dir)
                    if result:
                        results.append(result)
                else:
                    logger.warning("Sermon %s not found in local directories", sid)
        else:
            sermon_dirs = discover_sermons(self.output_dir)
            logger.info("Validating %d local sermons...", len(sermon_dirs))
            for sermon_dir in sermon_dirs:
                try:
                    result = self._validate_local_sermon(sermon_dir)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error("Error validating sermon %s: %s", sermon_dir.name, e)

        return results

    def _validate_local_sermon(self, sermon_dir: Path) -> ValidationResult | None:
        """Validate a single local sermon directory."""
        meta = read_metadata(sermon_dir)
        sermon_id = (
            (meta.get("sermon_id") or meta.get("sermonID")) or sermon_dir.name
            if meta else sermon_dir.name
        )
        description_file = get_file_path(sermon_dir, "description")

        if not description_file.exists():
            logger.debug("No description file found for sermon %s", sermon_id)
            return None

        try:
            description = description_file.read_text(encoding='utf-8').strip()
            context = {'sermon_id': sermon_id}

            is_valid, reason, score, criteria_met, criteria_failed = (
                self.validate_description(description, context)
            )

            return ValidationResult(
                sermon_id=sermon_id,
                title=meta.get("title", f"Sermon {sermon_id}") if meta else f"Sermon {sermon_id}",
                speaker=meta.get("speaker", "Unknown") if meta else "Unknown",
                description=description,
                description_length=len(description),
                is_valid=is_valid,
                validation_reason=reason,
                validation_score=score,
                criteria_met=criteria_met,
                criteria_failed=criteria_failed,
                needs_regeneration=score < self.regeneration_threshold,
                validated_at=dt.datetime.now().isoformat(),
                source="local"
            )

        except Exception as e:
            logger.error(f"Error reading description for sermon {sermon_id}: {e}")
            return None

    def validate_single_sermon(self, sermon_id: str) -> ValidationResult | None:
        """
        Validate a single sermon by ID, either from local files or API.
        """
        try:
            sermon_dir = find_sermon_dir(self.output_dir, sermon_id)
            if sermon_dir:
                return self._validate_local_sermon(sermon_dir)

            logger.warning("Sermon %s not found in local processed directory", sermon_id)
            return None

        except Exception as e:
            logger.error("Error validating sermon %s: %s", sermon_id, e)
            return None

    def generate_summary(self, results: list[ValidationResult]) -> ValidationSummary:
        """Generate a summary of validation results."""
        if not results:
            return ValidationSummary(0, 0, 0, 0.0, 0, 0.0, {})

        total = len(results)
        valid = sum(1 for r in results if r.is_valid)
        invalid = total - valid
        validation_rate = (valid / total) * 100
        needs_regen = sum(1 for r in results if r.needs_regeneration)
        avg_score = sum(r.validation_score for r in results) / total

        # Calculate criteria performance
        criteria_performance = {}
        for criterion in self.validation_criteria:
            met_count = sum(1 for r in results if criterion in r.criteria_met)
            criteria_performance[criterion] = (met_count / total) * 100

        return ValidationSummary(
            total_sermons=total,
            valid_descriptions=valid,
            invalid_descriptions=invalid,
            validation_rate=validation_rate,
            needs_regeneration=needs_regen,
            average_score=avg_score,
            criteria_performance=criteria_performance
        )

    def print_detailed_report(self, results: list[ValidationResult], summary: ValidationSummary):
        """Print a detailed validation report to console."""
        print("\n" + "="*80)
        print("DESCRIPTION VALIDATION REPORT")
        print("="*80)

        # Summary section
        print("\nSUMMARY:")
        print(f"   Total Sermons Validated: {summary.total_sermons}")
        print(
            f"   Valid Descriptions: {summary.valid_descriptions} "
            f"({summary.validation_rate:.1f}%)"
        )
        print(f"   Invalid Descriptions: {summary.invalid_descriptions}")
        print(f"   Need Regeneration: {summary.needs_regeneration}")
        print(f"   Average Score: {summary.average_score:.2f}/1.0")

        # Criteria performance
        print("\nCRITERIA PERFORMANCE:")
        for criterion, performance in summary.criteria_performance.items():
            status_icon = "OK" if performance >= 80 else "WARN" if performance >= 60 else "FAIL"
            print(f"   {status_icon} {criterion}: {performance:.1f}%")

        # Individual results (failed validations)
        failed_results = [r for r in results if not r.is_valid]
        if failed_results:
            print(f"\nFAILED VALIDATIONS ({len(failed_results)} sermons):")
            for result in failed_results[:10]:  # Show first 10
                print(f"\n   Sermon ID: {result.sermon_id}")
                print(f"      Score: {result.validation_score:.2f}/1.0")
                print(f"      Reason: {result.validation_reason}")
                print(f"      Length: {result.description_length} chars")
                if result.criteria_failed:
                    print(f"      Failed Criteria: {', '.join(result.criteria_failed[:2])}...")
                print(f"      Description: {result.description[:100]}...")

            if len(failed_results) > 10:
                print(f"\n   ... and {len(failed_results) - 10} more failed validations")

        # Low scoring but passed validations
        low_score_passed = [r for r in results if r.is_valid and r.validation_score < 0.8]
        if low_score_passed:
            print(f"\nPASSED BUT LOW SCORING ({len(low_score_passed)} sermons):")
            for result in low_score_passed[:5]:  # Show first 5
                print(
                    f"   {result.sermon_id}: {result.validation_score:.2f}/1.0 "
                    f"- {result.validation_reason}"
                )

        print("\n" + "="*80)

    def export_to_csv(self, results: list[ValidationResult], filename: str):
        """Export validation results to CSV file."""
        import csv
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'sermon_id', 'title', 'speaker', 'description_length',
                'is_valid', 'validation_score', 'validation_reason',
                'needs_regeneration', 'criteria_met_count', 'criteria_failed_count',
                'validated_at', 'source'
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                writer.writerow({
                    'sermon_id': result.sermon_id,
                    'title': result.title,
                    'speaker': result.speaker,
                    'description_length': result.description_length,
                    'is_valid': result.is_valid,
                    'validation_score': result.validation_score,
                    'validation_reason': result.validation_reason,
                    'needs_regeneration': result.needs_regeneration,
                    'criteria_met_count': len(result.criteria_met),
                    'criteria_failed_count': len(result.criteria_failed),
                    'validated_at': result.validated_at,
                    'source': result.source
                })

        logger.info(f"Results exported to {filename}")

    def export_to_json(
        self, results: list[ValidationResult], summary: ValidationSummary, filename: str
    ):
        """Export detailed validation results to JSON file."""
        import json
        from dataclasses import asdict

        export_data = {
            'summary': asdict(summary),
            'validation_criteria': self.validation_criteria,
            'results': [asdict(result) for result in results],
            'exported_at': dt.datetime.now().isoformat(),
            'validator_config': {
                'min_length': self.min_length,
                'max_length': self.max_length,
                'regeneration_threshold': self.regeneration_threshold
            }
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Detailed results exported to {filename}")


def validate_and_regenerate_descriptions(
    validator: DescriptionValidator,
    sermon_ids: list[str] = None,
    regenerate_failed: bool = False,
    dry_run: bool = False,
    upload_to_sermonaudio: bool = True
) -> dict:
    """
    Validate existing descriptions and optionally regenerate failed ones.

    Args:
        validator: Description validator instance
        sermon_ids: Specific sermon IDs to process (None for all)
        regenerate_failed: Whether to regenerate descriptions that fail validation
        dry_run: If True, don't actually update descriptions locally or on SermonAudio
        upload_to_sermonaudio: If True, upload regenerated descriptions to SermonAudio

    Returns:
        Dictionary with processing results including links to changed sermons
    """
    console_print("Starting description validation and regeneration process...")

    # Validate existing descriptions
    console_print("Validating existing descriptions...")
    results = validator.validate_local_sermons(sermon_ids)

    if not results:
        console_print("No sermons found to validate", "error")
        return {'validated': 0, 'regenerated': 0, 'failed': 0}

    # Generate summary
    summary = validator.generate_summary(results)

    # Print validation summary
    console_print("Validation Results:")
    console_print(f"   Total validated: {summary.total_sermons}")
    console_print(f"   Valid: {summary.valid_descriptions} ({summary.validation_rate:.1f}%)")
    console_print(f"   Invalid: {summary.invalid_descriptions}")
    console_print(f"   Need regeneration: {summary.needs_regeneration}")

    regenerated_count = 0
    failed_regeneration = 0
    regenerated_sermons = []  # Track successfully regenerated sermons
    validation_failures = []  # Track double-validation failures

    if regenerate_failed and summary.invalid_descriptions > 0:
        console_print(f"Regenerating {summary.invalid_descriptions} failed descriptions...")

        failed_results = [r for r in results if not r.is_valid]

        for i, result in enumerate(failed_results, 1):
            sermon_id = result.sermon_id
            console_print(f"   [{i}/{len(failed_results)}] Processing sermon {sermon_id}...")

            try:
                if dry_run:
                    console_print(f"      DRY RUN: Would regenerate description for {sermon_id}")
                    regenerated_count += 1
                    continue

                # Get sermon transcript for regeneration
                transcript = get_sermon_transcript(sermon_id)
                if not transcript:
                    console_print(f"      Could not get transcript for {sermon_id}", "error")
                    failed_regeneration += 1
                    continue

                # Generate new description with validation
                console_print("      Generating new description...")
                new_description, validation_info = generate_validated_summary(
                    transcript,
                    event_type=None,  # Could enhance this with API data
                    speaker_name=None
                )

                # Double-validate the newly generated description
                console_print("      Double-validating new description...")
                is_valid, reason, score, criteria_met, criteria_failed = (
                    validator.validate_description(
                        new_description,
                        {'sermon_id': sermon_id}
                    )
                )

                # Check if the new description actually passes validation
                if not is_valid:
                    console_print(
                        "      WARNING: New description still fails validation!", "warning"
                    )
                    console_print(f"               Score: {score:.2f}, Reason: {reason}", "warning")
                    validation_failures.append({
                        'sermon_id': sermon_id,
                        'new_description': new_description,
                        'score': score,
                        'reason': reason,
                        'criteria_failed': criteria_failed
                    })

                if validation_info.get('final_status') == 'approved_primary':
                    status_icon = "OK"
                elif validation_info.get('final_status') == 'approved_fallback':
                    status_icon = "WARN"
                else:
                    status_icon = "FAIL"

                console_print(f"      {status_icon} Generated new description "
                      f"({len(new_description)} chars, score: {score:.2f})")

                # Save the new description locally
                sermon_dir = find_sermon_dir(validator.output_dir, sermon_id)
                if not sermon_dir:
                    console_print(
                        f"      Could not find sermon directory for {sermon_id}", "error"
                    )
                    failed_regeneration += 1
                    continue
                description_file = get_file_path(sermon_dir, "description")

                if description_file.exists():
                    # Backup old description
                    backup_file = sermon_dir / f"{sermon_id}_description_backup.txt"
                    description_file.rename(backup_file)
                    console_print(f"      Backed up original to {backup_file.name}")

                description_file.write_text(new_description, encoding='utf-8')

                # Update SermonAudio if not in dry run mode and upload is enabled
                upload_success = False
                if upload_to_sermonaudio and not dry_run:
                    console_print("      Uploading to SermonAudio...")
                    try:
                        upload_success = update_sermon_metadata(sermon_id, new_description, None)
                        if upload_success:
                            console_print("      Updated SermonAudio successfully", "success")
                        else:
                            console_print("      SermonAudio update failed", "warning")
                    except Exception as e:
                        console_print(f"      SermonAudio upload error: {e}", "error")

                regenerated_count += 1
                console_print(f"      Updated description for sermon {sermon_id}", "success")

            except Exception as e:
                console_print(
                    f"      Failed to regenerate description for {sermon_id}: {e}", "error"
                )
                failed_regeneration += 1

    return {
        'validated': summary.total_sermons,
        'regenerated': regenerated_count,
        'failed': failed_regeneration,
        'validation_rate': summary.validation_rate,
        'regenerated_sermons': regenerated_sermons,
        'validation_failures': validation_failures
    }


def update_sermon_metadata(sermon_id: str, description: str, hashtags: str | list[str] | None,
                          series_title: str = None, series_id: int | None = None) -> bool:
    url = BASE_URL + f'node/sermons/{sermon_id}'
    headers = get_api_headers()
    if hashtags is None:
        keywords = ""
    elif isinstance(hashtags, list | tuple):
        keywords = ','.join(str(tag) for tag in hashtags)
    else:
        keywords = str(hashtags)
    payload = {'moreInfoText': description, 'keywords': keywords}
    if series_id is None and series_title:
        series_id = resolve_series_id(series_title, create_missing=True)
    if series_id is not None:
        payload['seriesID'] = series_id
    resp = requests.patch(url, headers=headers, json=payload, timeout=60)
    logger.debug("Update sermon status: %d", resp.status_code)
    if resp.status_code not in (200, 204):
        # Check if we got an HTML error page instead of JSON
        content_type = resp.headers.get('content-type', '').lower()
        if 'html' in content_type:
            logger.error("Received HTML error page (likely auth/rate limit issue): %s",
                        resp.status_code)
            # Extract title or first part of HTML for context
            html_snippet = resp.text[:500]
            if '<title>' in html_snippet:
                import re
                title_match = re.search(r'<title>(.*?)</title>', html_snippet, re.IGNORECASE)
                if title_match:
                    logger.error("HTML page title: %s", title_match.group(1))
        else:
            logger.error("Update error: %s", resp.text[:200])
    return resp.status_code in (200, 204)


def upload_audio_file(sermon_id: str, audio_path: str) -> bool:
    logger.debug("Uploading audio for sermon %s from %s", sermon_id, audio_path)
    return upload_media_file(sermon_id, audio_path, "original-audio")


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v"}


def is_video_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _ffprobe_duration(path: str | Path) -> float | None:
    try:
        proc = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        return float(json.loads(proc.stdout).get('format', {}).get('duration', 0) or 0)
    except Exception:
        return None


def _probe_stream_bounds(path: str | Path, stream: str) -> tuple[float, float] | None:
    """Return the first and last packet PTS (seconds) for one stream, or None."""
    duration = _ffprobe_duration(path)
    if not duration:
        return None
    try:
        first = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-select_streams', stream,
             '-show_entries', 'packet=pts_time', '-of', 'csv=p=0',
             '-read_intervals', '%+#1', str(path)],
            capture_output=True, text=True, timeout=120,
        )
        tail_start = max(duration - 30.0, 0.0)
        tail = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-select_streams', stream,
             '-show_entries', 'packet=pts_time', '-of', 'csv=p=0',
             '-read_intervals', f'{tail_start:.3f}%+30', str(path)],
            capture_output=True, text=True, timeout=600,
        )
    except Exception:
        return None

    def _times(text: str) -> list[float]:
        values: list[float] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line == 'N/A':
                continue
            try:
                values.append(float(line))
            except ValueError:
                continue
        return values

    starts = _times(first.stdout)
    ends = _times(tail.stdout)
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def _verify_mux_av_sync(path: str | Path, tolerance: float = 0.2) -> list[str]:
    """Return human-readable A/V start/end offsets beyond tolerance for a muxed file."""
    video = _probe_stream_bounds(path, 'v:0')
    audio = _probe_stream_bounds(path, 'a:0')
    if not video or not audio:
        return ['could not probe A/V stream bounds']
    problems: list[str] = []
    start_delta = abs(video[0] - audio[0])
    if start_delta > tolerance:
        problems.append(f'stream start delta {start_delta:.3f}s')
    end_delta = abs(video[1] - audio[1])
    if end_delta > tolerance:
        problems.append(f'stream end delta {end_delta:.3f}s')
    return problems


_EDIT_PLAN_FILE_KEYS = {
    'start', 'end', 'fade_in', 'logo_hold', 'fade_to_black',
    'confidence', 'needs_review', 'evidence', 'qa_judgment', 'reasoning',
    'audio_offset', 'detection_status',
}


def _load_edit_plan_from_file(path: str | Path) -> EditPlan:
    with open(path, encoding='utf-8') as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Edit plan file must contain a JSON object: {path}")
    fields = {k: v for k, v in payload.items() if k in _EDIT_PLAN_FILE_KEYS}
    return EditPlan(
        start=float(fields.get('start', 0.0)),
        end=float(fields.get('end', 0.0)),
        fade_in=float(fields.get('fade_in', 1.0)),
        logo_hold=float(fields.get('logo_hold', 3.0)),
        fade_to_black=bool(fields.get('fade_to_black', True)),
        confidence=float(fields.get('confidence', 0.0)),
        needs_review=bool(fields.get('needs_review', True)),
        evidence=str(fields.get('evidence', '')),
        qa_judgment=str(fields.get('qa_judgment', 'cut')),
        reasoning=str(fields.get('reasoning', '')),
        audio_offset=float(fields.get('audio_offset', 0.0)),
        detection_status=str(fields.get('detection_status', 'ok')),
    )


def _auto_edit_confidence_threshold(auto_edit_cfg: dict[str, Any]) -> float:
    return min(float(auto_edit_cfg.get('auto_confidence_threshold', 0.8)), 0.99)


def _auto_edit_metadata_block(auto_edit_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Ending-card prefs persisted with a draft for deferred renders/snippets."""
    cfg = auto_edit_cfg if isinstance(auto_edit_cfg, dict) else {}
    logo_cfg = cfg.get("logo_path")
    logo_path = ""
    if logo_cfg:
        candidate = Path(str(logo_cfg)).expanduser()
        if candidate.exists():
            logo_path = str(candidate)
    return {
        "logo_path": logo_path,
        "logo_hold": float(cfg.get("logo_hold", 3.0)),
        "fade_to_black": bool(cfg.get("fade_to_black", True)),
        "fade_out_tail_seconds": float(cfg.get("fade_out_tail_seconds", 2.0)),
    }


_SYSTEM_PLAN_NOTE_PREFIXES = (
    'Detected cut points',
    'Plan loaded from',
    'apply failed',
    'values saved from Library',
)


def _is_user_rejection_note(note: str) -> bool:
    """True when a plan note is a publisher instruction, not engine bookkeeping."""
    return bool(note) and not note.startswith(_SYSTEM_PLAN_NOTE_PREFIXES)


def _accumulated_rejection_notes(history: list[dict[str, Any]]) -> list[str]:
    """Publisher rejection notes in revision order, deduplicated.

    Only the note that produced each revision is stored, so ordering by
    revision yields the instructions in the order they were given. Engine
    status strings sharing the ``notes`` column are skipped.
    """
    ordered = sorted(history, key=lambda row: int(row.get('revision') or 0))
    notes: list[str] = []
    for row in ordered:
        for part in str(row.get('notes') or '').split(';'):
            part = part.strip()
            if _is_user_rejection_note(part) and part not in notes:
                notes.append(part)
    return notes


def _merge_rejection_notes(prior: list[str], new_note: str) -> list[str]:
    merged = list(prior)
    if new_note and new_note not in merged:
        merged.append(new_note)
    return merged


def _review_dir_for_refine(sermon_id: str, repo: Any, config: dict[str, Any]) -> Path | None:
    """Locate a sermon's retained review media, falling back to the output tree."""
    try:
        from src.review_media import review_dir_for_sermon

        review_dir = review_dir_for_sermon(sermon_id, repo)
        if review_dir is not None:
            return review_dir
    except Exception as exc:
        logger.debug("Review directory lookup failed for %s: %s", sermon_id, exc)
    output_root = Path(config.get('output_directory', 'processed_sermons'))
    if not output_root.is_absolute():
        output_root = Path(__file__).parent / output_root
    return find_sermon_dir(output_root, sermon_id)


def _rerender_review_snippets(review_dir: Path, plan: EditPlan, meta: dict[str, Any]) -> None:
    """Re-render the review preview clips from the retained source media.

    Reuses the same snippet file names the media API globs, so the panel picks
    up the new cuts without a metadata rewrite. A failed detection releases the
    stale clips to trash so no preview suggests cut points that were not
    returned.
    """
    from src.review_media import render_bounded_snippets

    try:
        from src.safe_delete import trash_local
    except ImportError:
        from safe_delete import trash_local  # type: ignore[no-redef]

    snippets_dir = review_dir / "snippets"
    if plan.detection_status != 'ok':
        trash_local(snippets_dir, reason="review_snippets_rerender", stage="review")
        return
    if not bool(meta.get('is_video')):
        return
    keeper = meta.get('keeper_file')
    source = keeper if keeper and Path(str(keeper)).exists() else meta.get('original_file')
    if not source or not Path(str(source)).exists():
        logger.info("Review snippet re-render skipped for %s: no retained video source", review_dir)
        return
    auto_edit_meta = meta.get('auto_edit') if isinstance(meta.get('auto_edit'), dict) else {}
    logo = auto_edit_meta.get('logo_path')
    logo_path = Path(str(logo)).expanduser() if logo else None
    if logo_path is not None and not logo_path.exists():
        logo_path = None
    trash_local(snippets_dir, reason="review_snippets_rerender", stage="review")
    try:
        render_bounded_snippets(
            Path(str(source)),
            plan,
            snippets_dir,
            logo_path=logo_path,
            fade_out_tail_seconds=float(auto_edit_meta.get('fade_out_tail_seconds', 2.0)),
        )
    except Exception as exc:
        logger.warning("Review snippet re-render failed for %s: %s", review_dir, exc)


def refine_edit_plan(
    sermon_id: str,
    notes: str = "",
    config: dict | None = None,
    re_detect: bool = False,
) -> dict[str, Any]:
    """Re-run cut detection for a sermon under review.

    A refine run carries the previous proposal, every prior rejection note in
    revision order, and the new note, so the model can redefine the scope (for
    example, keep only the second of two back-to-back classes). A re-detect run
    starts clean: no previous proposal and no notes, while earlier revisions
    stay in the history. Both reuse the retained review media and never re-run
    enhancement or transcription.
    """
    config = config or globals().get('config') or {}
    result: dict[str, Any] = {'success': False, 'sermon_id': sermon_id, 'error': None}

    try:
        from ui.database import SermonRepository

        repo = SermonRepository()
        current = repo.get_current_edit_plan(sermon_id)
        history = repo.get_edit_plan_history(sermon_id)

        new_note = str(notes or '').strip()
        accumulated = _accumulated_rejection_notes(history)
        if not re_detect:
            accumulated = _merge_rejection_notes(accumulated, new_note)
        else:
            accumulated = []

        review_dir = _review_dir_for_refine(sermon_id, repo, config)
        if review_dir is None:
            result['error'] = f"Sermon directory not found for {sermon_id}"
            return result

        segments = read_transcript_timestamps(review_dir)
        if not segments:
            result['error'] = "No timestamped transcript available for re-detection"
            return result

        source_path = str((current or {}).get('source_path') or '')
        meta = read_metadata(review_dir) or {}
        duration = None
        if source_path and Path(source_path).exists():
            duration = _ffprobe_duration(source_path)
        if not duration:
            duration = float(meta.get('duration') or 0) or None
        if not duration:
            for candidate in (
                meta.get('keeper_file'),
                meta.get('processed_file'),
                meta.get('original_file'),
            ):
                if candidate and Path(str(candidate)).exists():
                    duration = _ffprobe_duration(str(candidate))
                    if duration:
                        break

        previous_plan = None
        if current and not re_detect:
            previous_plan = {
                'start': current.get('proposed_start'),
                'end': current.get('proposed_end'),
                'evidence': current.get('evidence') or '',
            }

        plan = detect_cut_points(
            segments,
            llm_manager,
            config,
            duration,
            previous_plan=previous_plan,
            rejection_notes='; '.join(accumulated) or None,
        )

        stored_note = '' if re_detect else new_note
        repo.save_edit_plan_revision(sermon_id, {
            'proposed_start': float(plan.start),
            'proposed_end': float(plan.end),
            'final_start': None,
            'final_end': None,
            'confidence': float(plan.confidence),
            'needs_review': True,
            'evidence': plan.evidence,
            'qa_judgment': plan.qa_judgment,
            'reasoning': plan.reasoning,
            'detection_status': plan.detection_status,
            'status': 'pending_review',
            'source_path': source_path or None,
            'notes': stored_note,
        })

        _rerender_review_snippets(review_dir, plan, meta)

        result.update({
            'success': plan.detection_status == 'ok',
            'start': plan.start,
            'end': plan.end,
            'confidence': plan.confidence,
            'needs_review': plan.needs_review,
            'evidence': plan.evidence,
            'qa_judgment': plan.qa_judgment,
            'reasoning': plan.reasoning,
            'detection_status': plan.detection_status,
            'notes': stored_note,
            'accumulated_notes': accumulated,
            're_detect': re_detect,
            'duration': duration,
        })
        if plan.detection_status != 'ok':
            result['error'] = (
                "Cut detection failed; no usable cut points were returned. "
                "Set the cuts manually or re-run detection."
            )
    except Exception as e:
        logger.exception("Edit plan refinement failed for %s", sermon_id)
        result['error'] = str(e)
    return result


def _media_type_for_ext(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    return "video/mp4" if ext == ".mp4" else "video/mp4" if is_video_file(path) else "audio/mpeg"


def upload_media_file(sermon_id: str, file_path: str,
                       upload_type: str = "original-audio") -> bool:
    """Upload a media file (audio or video) to SermonAudio.

    POSTs to /v2/media with the given uploadType to get an upload URL,
    then POSTs the file to that URL.
    """
    logger.debug("Uploading media for sermon %s from %s (type=%s)",
                 sermon_id, file_path, upload_type)
    url = BASE_URL + "media"
    headers = get_api_headers()
    payload = {"uploadType": upload_type, "sermonID": sermon_id}
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    logger.debug("Media upload initiation status: %d", resp.status_code)
    if resp.status_code != 201:
        logger.error("Failed to initiate media upload: %s", resp.text[:200])
        return False
    data = resp.json()
    upload_url = data.get("uploadURL")
    if not upload_url:
        logger.error("No upload URL returned.")
        return False
    content_type = _media_type_for_ext(file_path)
    try:
        with open(file_path, "rb") as fh:
            up = requests.post(upload_url, data=fh,
                               headers={"Content-Type": content_type},
                               timeout=600)
        logger.debug("Direct upload status: %d", up.status_code)
        return up.status_code in (200, 201, 204)
    except Exception as e:
        logger.error("Error uploading file: %s", e)
        return False


def set_sermon_published(sermon_id: str, published: bool) -> bool:
    """Publish or unpublish a sermon on SermonAudio.

    Publishing sets the publish timestamp to now ({"publishNow": true}).
    Unpublishing clears it ({"publishTimestamp": null}), returning the sermon
    to draft so it disappears from public listings.
    """
    payload = {"publishNow": True} if published else {"publishTimestamp": None}
    action = "publish" if published else "unpublish"
    try:
        resp = requests.patch(
            f"{BASE_URL}node/sermons/{sermon_id}",
            headers=get_api_headers(),
            json=payload,
            timeout=30,
        )
        success = resp.status_code in (200, 204)
        if success:
            logger.info("Sermon %s %sed on SermonAudio", sermon_id, action)
        else:
            logger.warning(
                "Failed to %s sermon %s: HTTP %s %s",
                action, sermon_id, resp.status_code, resp.text[:200],
            )
        return success
    except Exception as e:
        logger.error("Failed to %s sermon %s: %s", action, sermon_id, e)
        return False


def generate_title(transcript: str, speaker_name: str = None, event_type: str = None,
                  bible_text: str = None) -> str:
    """Generate a sermon title using the LLM based on transcript content.

    Args:
        transcript: The sermon transcript
        speaker_name: Name of the speaker (optional)
        event_type: Type of event (optional)
        bible_text: Bible reference (optional)

    Returns:
        Generated title string
    """
    # Build context information
    context_parts = []
    if speaker_name:
        context_parts.append(f"Speaker: {speaker_name}")
    if event_type:
        context_parts.append(f"Event: {event_type}")
    if bible_text:
        context_parts.append(f"Bible Text: {bible_text}")

    context = "\n".join(context_parts) if context_parts else ""

    # Sample beginning, middle, and end: the opening alone is often
    # announcements and misses the sermon's actual message.
    title_sample = (
        f"{transcript[:1200]}\n\n[...]\n\n"
        f"{transcript[len(transcript) // 2:(len(transcript) // 2) + 800]}\n\n[...]\n\n"
        f"{transcript[-800:]}"
        if len(transcript) > 2800 else transcript
    )

    tmpl = _get_prompt_template("title", context=context, transcript=title_sample)
    if tmpl:
        system_prompt, user_prompt = tmpl
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
    else:
        prompt = f"""You are a sermon title generator.
Create a compelling, descriptive title for this sermon.

{context}

Guidelines for the title:
- Maximum 85 characters (STRICT LIMIT for API)
- Capture the main theme or message
- Be specific and engaging, not generic
- Avoid cliché Christian phrases
- Focus on the practical application or key insight
- If a Bible reference is given, you may include it briefly
- Do not use quotation marks around the title
- Return ONLY the title, no explanation or commentary

Sermon content (first 1000 characters):
{title_sample}...

Generate a compelling sermon title:"""
        messages = [{'role': 'user', 'content': prompt}]

    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating title using %s LLM...", primary_provider)

        response = llm_manager.chat(messages)

        # Clean up the response
        title = clean_title(response)

        # Ensure title doesn't exceed API limit
        if len(title) > 85:
            logger.warning("Generated title too long (%d chars), truncating to 85", len(title))
            # Try to truncate at word boundary
            truncated = title[:82]
            last_space = truncated.rfind(' ')
            if last_space > 60:  # Reasonable word boundary
                title = truncated[:last_space] + "..."
            else:
                title = title[:85]

        logger.debug("Generated title (%d chars): %s", len(title), title)
        return title

    except (LLMTimeoutError, LLMModelNotFoundError, LLMModelNotConfiguredError):
        raise
    except Exception as e:
        logger.error("Title generation failed: %s", e)
        # Fallback title
        fallback = f"Sermon by {speaker_name}" if speaker_name else "New Sermon"
        if bible_text:
            fallback += f" - {bible_text}"
        return fallback[:85]


def generate_short_display_title(full_title: str) -> str:
    """Generate a short display title (≤30 chars) from the full title using LLM.

    Args:
        full_title: The full sermon title

    Returns:
        Shortened display title string
    """
    if len(full_title) <= 30:
        return full_title

    tmpl = _get_prompt_template("short_title", full_title=full_title)
    if tmpl:
        system_prompt, user_prompt = tmpl
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
    else:
        prompt = f"""Shorten this sermon title to a concise version
(maximum 30 characters, STRICT LIMIT).
Keep the core meaning but make it brief. No quotes, no explanation, just the shortened title.

Original title: {full_title}

Shortened title (max 30 chars):"""
        messages = [{'role': 'user', 'content': prompt}]

    try:
        response = llm_manager.chat(messages)
        short_title = clean_title(response)
        if len(short_title) > 30:
            short_title = short_title[:27] + "..."
        if short_title:
            logger.debug(
                "Generated short display title (%d chars): %s", len(short_title), short_title
            )
            return short_title
    except (LLMTimeoutError, LLMModelNotFoundError, LLMModelNotConfiguredError):
        raise
    except Exception as e:
        logger.warning("Short title generation failed: %s", e)

    return full_title[:27] + "..." if len(full_title) > 30 else full_title


def parse_bible_reference(text: str | None) -> dict | None:
    """Parse a bible reference string into structured fields.

    Understands formats like:
      "John 3:16"       -> {book: "John", chapter: 3, verse_start: 16, verse_end: 16}
      "Genesis 1:1-10"  -> {book: "Genesis", chapter: 1, verse_start: 1, verse_end: 10}
      "Psalm 23"        -> {book: "Psalm", chapter: 23, verse_start: None, verse_end: None}
      "Romans 8:28-39"  -> {book: "Romans", chapter: 8, verse_start: 28, verse_end: 39}

    Returns the raw text keyed as 'bibleText' and structured fields, or None if parsing fails.
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    result = {"bibleText": text}
    # Try to match "Book Chapter:Verse-Verse"
    # Use a pattern that handles book names starting with a number (e.g. "1 Peter 3:16")
    m = re.match(r'^(\d*\s*\D+?)\s*(\d+)\s*:\s*(\d+)\s*-\s*(\d+)$', text)
    if m:
        result["book"] = m.group(1).strip()
        result["chapter"] = int(m.group(2))
        result["verseStart"] = int(m.group(3))
        result["verseEnd"] = int(m.group(4))
    else:
        m = re.match(r'^(\d*\s*\D+?)\s*(\d+)\s*:\s*(\d+)$', text)
        if m:
            result["book"] = m.group(1).strip()
            result["chapter"] = int(m.group(2))
            result["verseStart"] = int(m.group(3))
            result["verseEnd"] = int(m.group(3))
        else:
            m = re.match(r'^(\d*\s*\D+?)\s*(\d+)$', text)
            if m:
                result["book"] = m.group(1).strip()
                result["chapter"] = int(m.group(2))
    return result


def resolve_speaker_id(speaker_name: str) -> int | None:
    """Resolve a speaker name to a numeric speaker ID via the SermonAudio API.

    Queries /v2/node/speakers for exact (case-insensitive) name match.
    Returns None if not found or API unavailable.
    """
    try:
        headers = get_api_headers()
        url = BASE_URL + 'node/speakers'
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.warning("Failed to fetch speakers list: %d", resp.status_code)
            return None
        speakers = resp.json()
        if not isinstance(speakers, list):
            speakers = speakers.get('results', speakers) if isinstance(speakers, dict) else []
        for sp in speakers:
            display = sp.get('displayName', '')
            if display.strip().lower() == speaker_name.strip().lower():
                sp_id = sp.get('speakerID')
                logger.info("Resolved speaker '%s' -> ID %s", speaker_name, sp_id)
                return sp_id
        logger.info("Speaker '%s' not found in SermonAudio directory", speaker_name)
        return None
    except Exception as e:
        logger.warning("Error resolving speaker ID for '%s': %s", speaker_name, e)
        return None


class ProcessingCancelledError(RuntimeError):
    """Raised at a cancellation checkpoint when the cancel_check hook fires."""


_TRANSCODE_CODEC_ARGS = {
    '.mp3': ['-codec:a', 'libmp3lame', '-q:a', '2'],
    '.m4a': ['-c:a', 'aac', '-b:a', '192k'],
    '.aac': ['-c:a', 'aac', '-b:a', '192k'],
    '.mp4': ['-c:a', 'aac', '-b:a', '192k'],
    '.ogg': ['-c:a', 'libvorbis', '-q:a', '4'],
    '.flac': ['-c:a', 'flac'],
}


def _mux_audio_codec_args(audio_path: str | Path) -> list[str]:
    """Codec arguments for muxing an enhanced audio track into a video.

    Audio already in an AAC-compatible container is stream-copied so the mux
    never re-encodes (and never falls back to ffmpeg's low default bitrate).
    Anything else is encoded once at 192k, matching the rest of the pipeline.
    """
    suffix = Path(audio_path).suffix.lower()
    if suffix in ('.mp4', '.m4a', '.aac'):
        return ['-c:a', 'copy']
    return ['-c:a', 'aac', '-b:a', '192k']


def _transcode_media(
    src: Path,
    dst: Path,
    *,
    cancel_check: Callable[[], None] | None = None,
    cancel_log: Callable[[str], None] | None = None,
) -> bool:
    """Transcode an audio file into the container implied by dst's extension.

    Returns True when the converted file exists. Falls back to ffmpeg's
    default encoder for the container, then gives up (caller keeps src).
    """
    codec_args = _TRANSCODE_CODEC_ARGS.get(dst.suffix.lower(), [])
    attempts: list[list[str]] = []
    if codec_args:
        attempts.append(["ffmpeg", "-y", "-i", str(src), *codec_args, str(dst)])
    attempts.append(["ffmpeg", "-y", "-i", str(src), str(dst)])
    last_err: Exception | None = None
    for cmd in attempts:
        try:
            run_supervised(
                cmd,
                cancel_check=cancel_check,
                log=cancel_log,
                step="audio transcode",
                partial_paths=[dst],
                partial_reason="cancelled_render_partial",
                capture_output=True,
                text=True,
                timeout=3600,
                check=True,
            )
            if dst.exists() and dst.stat().st_size > 0:
                return True
        except ProcessCancelled:
            raise
        except Exception as e:
            last_err = e
    logger.warning("Transcoding %s to %s failed: %s", src.name, dst.name, last_err)
    return False


def _resolve_api_language_code(cfg: dict | None) -> str:
    """Pick a SermonAudio languageCode from the configured transcription language."""
    try:
        trans_cfg = (cfg or {}).get('transcription') or {}
        for section in (
            'whisper_local',
            'faster_whisper_local',
            'whisper_openai',
            'whisper_openrouter',
        ):
            lang = (trans_cfg.get(section) or {}).get('language')
            if lang:
                return str(lang)
        top_level = trans_cfg.get('language')
        if top_level:
            return str(top_level)
    except Exception as e:
        logger.debug("Could not resolve transcription language: %s", e)
    return 'eng'


_EPOCH_STEM_RE = re.compile(r'^\d{10,}_')


def _normalized_file_stem(path: str | Path) -> str:
    """Strip a leading epoch-milliseconds upload prefix from a filename stem."""
    return _EPOCH_STEM_RE.sub('', Path(path).stem).strip('_')


def _find_existing_processed_sermon_id(title: str | None, speaker_name: str | None,
                                       recorded_date: str | None) -> str | None:
    """Find a previously uploaded processed sermon with identical identity fields.

    Used to avoid creating duplicate remote sermons when a job is retried
    after dying mid-upload.
    """
    if not title or not speaker_name:
        return None
    try:
        from ui.database import SermonRepository
        repo = SermonRepository()
        with repo.db.get_connection() as conn:
            row = conn.execute("""
                SELECT s.id FROM sermons s
                LEFT JOIN upload_info ui ON ui.sermon_id = s.id
                WHERE s.title = ? AND s.speaker = ? AND s.recorded_date = ?
                  AND s.status = 'processed'
                  AND s.id NOT LIKE 'draft\\_%' ESCAPE '\\'
                  AND (ui.upload_status IS NULL OR ui.upload_status != 'failed')
                ORDER BY s.updated_at DESC
                LIMIT 1
            """, (title, speaker_name, recorded_date or '')).fetchone()
            if row:
                return row['id']
    except Exception as e:
        logger.debug("Existing processed sermon lookup failed: %s", e)
    return None


def _resolve_identity_id(
    speaker_name: str | None,
    recorded_date: str | None,
    title: str | None,
    source_path: str | Path | None,
    existing_sermon_id: str | None = None,
) -> str:
    """Deterministic id for a local record, or the caller's existing id.

    Passing ``existing_sermon_id`` is how a render or re-run updates the
    record it came from rather than minting a second one.
    """
    if existing_sermon_id:
        return str(existing_sermon_id)
    from src.sermon_identity import derive_sermon_id, source_fingerprint

    return derive_sermon_id(
        speaker_name, recorded_date, title, source_fingerprint(source_path)
    )


def _remote_sermon_exists(sermon_id: str) -> bool:
    """Check a candidate reuse id still exists on SermonAudio.

    Wraps get_sermon_details: 404/empty means not reusable, and any API
    error fails safe to not reusable so the caller falls through to the
    normal create path (a duplicate is recoverable; a shadowed publish
    is not).
    """
    try:
        return bool(get_sermon_details(str(sermon_id)))
    except Exception as e:
        logger.warning(
            "Remote existence check failed for %s; not reusing: %s",
            sermon_id, e,
        )
        return False


def _record_publication_id(repo: Any, draft_id: str, remote_sermon_id: str) -> None:
    """Best-effort record of the remote ID a draft was already published under."""
    try:
        with repo.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO upload_info
                (sermon_id, sermonaudio_id, upload_status, upload_message)
                VALUES (?, ?, ?, ?)
            """, (draft_id, remote_sermon_id, 'publishing',
                  f'Created on SermonAudio as {remote_sermon_id}'))
            conn.commit()
    except Exception as e:
        logger.debug("Could not record publication id for %s: %s", draft_id, e)


def validate_event_type_for_api(event_type: str | None) -> None:
    """Reject an event_type the SermonAudio API would refuse with 422.

    Compares against get_event_types() (API-backed cache with a hardcoded
    fallback). Raises ValueError naming the allowed options when that list
    is non-empty and the value is not in it. Skips the guard when the
    allowed list is empty or unavailable, never blocking on unknown.
    """
    try:
        from ui.sermon_metadata import get_event_types
        allowed = get_event_types()
    except Exception as e:
        logger.warning(
            "Could not load allowed event types; skipping event-type guard: %s", e
        )
        return
    if not allowed:
        return
    if event_type not in allowed:
        raise ValueError(
            f"Invalid event_type {event_type!r}: SermonAudio accepts only "
            f"{', '.join(allowed)}"
        )


def create_new_sermon_api(title: str, speaker_name: str, recorded_date: str,
                         event_type: str = "Sunday Service", bible_text: str = None,
                         subtitle: str = None, description: str = None,
                         hashtags: str = None, speaker_id: int | None = None,
                         display_title: str = None) -> str:
    """Create a new sermon via the SermonAudio API.

    Args:
        title: Full sermon title (max 85 chars)
        speaker_name: Name of the speaker (max 50 chars)
        recorded_date: Date recorded (YYYY-MM-DD format)
        event_type: Type of event (default "Sunday Service")
        bible_text: Bible reference text (optional)
        subtitle: Sermon subtitle (max 30 chars, optional)
        description: Sermon description (optional)
        hashtags: Hashtags/keywords (optional)
        speaker_id: Numeric speaker ID (optional, preferred over speaker_name)
        display_title: Short display title (max 30 chars, optional). If not provided,
                       generated from full title by truncation.

    Series is intentionally not sent here: the API ignores it during creation,
    so callers apply it once via set_sermon_series() after creation.

    Raises:
        ValueError: If event_type is not one of the allowed options from
            get_event_types(). Never fires a create the API would 422.

    Returns:
        Created sermon ID if successful, None if failed
    """
    validate_event_type_for_api(event_type)

    url = BASE_URL + 'node/sermons'
    headers = get_api_headers()

    # Build payload
    payload = {
        'acceptCopyright': True,
        'fullTitle': title[:85],  # Ensure limit
        'speakerName': speaker_name[:50],  # Ensure limit
        'preachDate': recorded_date,
        'eventType': event_type,
        'languageCode': _resolve_api_language_code(globals().get('config'))
    }

    # Use numeric speakerID if available (more reliable)
    if speaker_id is not None:
        payload['speakerID'] = speaker_id

    # Add optional fields
    if bible_text:
        payload['bibleText'] = bible_text
    if subtitle:
        payload['subtitle'] = subtitle[:30]  # Ensure limit
    if description:
        payload['moreInfoText'] = description
    if hashtags:
        payload['keywords'] = hashtags

    # Use provided display_title or generate from full title
    if display_title:
        payload['displayTitle'] = display_title[:30]
    else:
        payload['displayTitle'] = title[:30] if len(title) <= 30 else title[:27] + "..."

    try:
        logger.debug("Creating new sermon with title: %s", title)
        resp = requests.post(url, headers=headers, json=payload, timeout=60)

        if resp.status_code == 201:
            sermon_data = resp.json()
            sermon_id = sermon_data.get('sermonID')
            logger.info("Successfully created sermon with ID: %s", sermon_id)
            return sermon_id
        else:
            logger.error("Failed to create sermon: %d - %s", resp.status_code, resp.text[:200])
            return None

    except Exception as e:
        logger.error("Error creating sermon: %s", e)
        return None


def process_new_sermon(audio_file: str, speaker_name: str, recorded_date: str,
                      event_type: str = "Sunday Service", bible_text: str = None,
                      title: str = None, subtitle: str = None,
                      series_title: str = None, description: str = None, hashtags: str = None,
                      dry_run: bool = False, skip_transcription: bool = False,
                      skip_audio: bool = False, skip_ai_generation: bool = False,
                      whisper_model: str = "large",
                      transcription_backend: str | None = None,
                      use_clean_audio: bool = False,
                      clean_audio_script: str = (
                          "~/Documents/Repositories/deepfilternet/clean-audio.py"
                      ),
                      clean_audio_device: str = "auto",
                      generate_short_title: bool = False,
                      force_validation: bool = False,
                      enhancement_method: str | None = None,
                      custom_repo: str | None = None,
                      custom_file: str | None = None,
                      series_id: int | None = None,
                      config: dict | None = None,
                      progress_callback=None,
                      auto_edit_mode: str | None = None,
                      edit_plan_file: str | None = None,
                      audio_offset: float | None = None,
                      cancel_check: Callable[[], None] | None = None,
                      cancel_log: Callable[[str], None] | None = None,
                      publish: bool = True,
                      existing_sermon_id: str | None = None,
                      reuse_transcript: str | None = None,
                      reuse_transcript_segments: list | None = None,
                      keeper_prepared: bool = False,
                      enhanced_audio_file: str | None = None,
                      require_enhancement: bool = False) -> dict:
    """Process a new sermon from audio file with automatic metadata generation.

    Args:
        audio_file: Path to audio file
        speaker_name: Name of the speaker
        recorded_date: Date recorded (YYYY-MM-DD format)
        event_type: Type of event (default "Sunday Service")
        bible_text: Bible reference text (optional)
        title: Sermon title (optional, will be generated if not provided)
        subtitle: Sermon subtitle (optional)
        description: Sermon description (optional, will be generated if not provided)
        hashtags: Hashtags/keywords (optional, will be generated if not provided)
        dry_run: If True, process but don't upload
        skip_transcription: If True, skip audio transcription for faster processing
        skip_audio: If True, skip audio enhancement (use file as-is, e.g.
            already cleaned in kdenlive)
        whisper_model: Whisper model size for transcription
        progress_callback: Optional callable(progress_pct: float, message: str)
            for progress reporting
        cancel_check: Optional zero-argument callable invoked at cancellation
            checkpoints (before the remote create and before the local save).
            Any exception it raises is converted to ProcessingCancelledError.
        cancel_log: Optional callable(str) the supervised child stages use to
            report "Cancel requested - stopping <step>" and the stop timing on
            the owning job's log.
        existing_sermon_id: When set, every save upserts this row instead of
            deriving a new deterministic id.
        reuse_transcript: A transcript retained from an earlier review pass.
            When provided the transcription model is not run; an empty string
            is a valid retained transcript.
        reuse_transcript_segments: Timestamped segments for the reused
            transcript, persisted alongside it.
        keeper_prepared: True when ``audio_file`` is already the retained
            keeper, so the keeper transcode is skipped without touching the
            enhancement decision.
        enhanced_audio_file: A retained, full-length enhancement to reuse
            instead of running the enhancer. Used only when it exists.
        require_enhancement: When True an enhancement run that fails is a
            hard error, not a silent fallback to the un-enhanced source.

    Returns:
        Dict with keys: success, sermon_id, title, description, hashtags,
                        enhanced_audio_path, transcript_length, error
    """
    def _report(progress, msg):
        # Every progress report is also a cancellation checkpoint. Long stages
        # that report progress (transcription segments, metadata, upload) then
        # poll the cancel hook at the same cadence as their own progress.
        _check_cancelled()
        if progress_callback is not None:
            try:
                progress_callback(progress, msg)
            except ProcessingCancelledError:
                raise
            except Exception:
                pass

    def _check_cancelled():
        if cancel_check is None:
            return
        try:
            cancel_check()
        except Exception as cancel_exc:
            raise ProcessingCancelledError(
                str(cancel_exc) or "Processing cancelled"
            ) from cancel_exc

    if config is None:
        config = globals().get('config') or {}
    if not config:
        refresh_runtime_config()
        config = globals()['config']
    auto_edit_cfg: dict[str, Any] = {}
    gate_active = False
    if series_id is None and series_title:
        series_id = resolve_series_id(series_title, create_missing=not dry_run)

    result = {
        'success': False,
        'sermon_id': None,
        'title': None,
        'description': None,
        'hashtags': None,
        'subtitle': subtitle,
        'speaker': speaker_name,
        'event_type': event_type,
        'bible_text': bible_text,
        'recorded_date': recorded_date,
        'enhanced_audio_path': None,
        'is_video': False,
        'final_upload_path': None,
        'upload_type': "original-audio",
        'transcript_length': 0,
        'transcript': None,
        'transcript_segments': [],
        'edit_plan_status': None,
        'auto_edit_applied': False,
        'output_dir': None,
        'processing_temp_dir': None,
        'error': None,
    }

    try:
        validate_event_type_for_api(event_type)
    except ValueError as e:
        result['error'] = str(e)
        return result

    from pathlib import Path

    try:
        from src.audio_processing import AudioProcessor
        audio_processor_available = True
    except Exception as e:
        logger.warning(f"AudioProcessor unavailable: {e}")
        audio_processor_available = False

    audio_path = Path(audio_file)
    original_input_path = audio_path  # keep for video muxing
    if not audio_path.exists():
        logger.error("Audio file not found: %s", audio_file)
        result['error'] = f"Audio file not found: {audio_file}"
        return result

    input_is_video = is_video_file(str(audio_path))

    keeper_used = False

    if input_is_video:
        keeper_cfg = config.get('auto_edit', {}).get('keeper', {})
        if skip_audio or keeper_prepared:
            console_print(
                "⏭️ Keeper skipped for apply render "
                "(source is already the prepared keeper)"
            )
            logger.info("Keeper transcode skipped: apply render source is prepared")
        elif bool(keeper_cfg.get('enabled', True)):
            min_source_gb = float(keeper_cfg.get('min_source_gb', 2.0))
            keeper_root = Path(config.get('output_directory', 'processed_sermons'))
            if not keeper_root.is_absolute():
                keeper_root = Path(__file__).parent / keeper_root
            keeper_path = keeper_root / "keepers" / f"{audio_path.stem}_keeper.mp4"
            _report(6, "Preparing keeper transcode...")
            from src.auto_edit import transcode_to_keeper

            try:
                kept_path = transcode_to_keeper(
                    audio_path,
                    keeper_path,
                    config,
                    cancel_check=_check_cancelled,
                    cancel_log=cancel_log,
                )
            except ProcessCancelled:
                result['error'] = "Processing cancelled"
                result['cancelled'] = True
                return result
            if kept_path == audio_path:
                if audio_path.stat().st_size >= min_source_gb * 1024**3:
                    console_print("⚠️ Keeper transcode failed, using original video")
                else:
                    console_print("⏭️ Keeper skipped, source below min_source_gb")
            else:
                audio_path = kept_path
                keeper_used = True
                console_print(f"🗜️ Keeper transcode complete: {kept_path.name}")
        else:
            console_print("⏭️ Keeper disabled by config, using original video")

    # Preprocessing: optional clean-audio.py step (runs before enhancement)
    if use_clean_audio:
        console_print("Running external clean-audio.py preprocessing...")
        _report(3, "Running clean-audio.py (Audacity macro + DeepFilterNet)...")
        import subprocess
        clean_script = Path(clean_audio_script).expanduser()
        if not clean_script.exists():
            logger.error("clean-audio.py not found: %s", clean_script)
            result['error'] = f"clean-audio.py not found: {clean_script}"
            return result
        clean_output = audio_path.with_name(f"{audio_path.stem}_cleaned.wav")
        cmd = [
            sys.executable, str(clean_script),
            str(audio_path),
            str(clean_output),
            "--device", clean_audio_device,
        ]
        logger.info("Running: %s", " ".join(cmd))
        try:
            proc = run_supervised(
                cmd,
                cancel_check=_check_cancelled,
                log=cancel_log,
                step="clean-audio",
                partial_paths=[clean_output],
                partial_reason="cancelled_render_partial",
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if proc.returncode != 0:
                logger.error("clean-audio.py failed: %s", proc.stderr)
                result['error'] = f"clean-audio.py failed: {proc.stderr[:200]}"
                return result
            if not clean_output.exists():
                logger.error("clean-audio.py did not produce output: %s", clean_output)
                result['error'] = "clean-audio.py produced no output"
                return result
            # Replace audio_path with cleaned file (enhancements will still run on it)
            audio_path = clean_output
            console_print(f"clean-audio.py done: {clean_output.name}")
            _report(7, "clean-audio.py complete")
        except ProcessCancelled:
            logger.info("clean-audio.py cancelled by user request")
            result['error'] = "Processing cancelled"
            result['cancelled'] = True
            return result
        except subprocess.TimeoutExpired:
            logger.error("clean-audio.py timed out after 30 minutes")
            result['error'] = "clean-audio.py timed out"
            return result
        except FileNotFoundError:
            logger.error("clean-audio.py cannot be executed (Python not found?)")
            result['error'] = "clean-audio.py not executable"
            return result

    logger.info("Processing new sermon from audio file: %s", audio_file)
    _report(5, f"Loaded audio file: {audio_path.name}")

    temp_dir = None
    import uuid as _uuid

    from ui.config_utils import default_cache_root

    try:
        # Step 1: reuse a retained enhancement, run the enhancer, or skip.
        reused_enhancement = False
        if enhanced_audio_file:
            reuse_candidate = Path(enhanced_audio_file)
            if reuse_candidate.exists():
                enhanced_audio_path = reuse_candidate
                reused_enhancement = True
                console_print(
                    f"Reusing retained audio enhancement ({reuse_candidate.name})"
                )
                logger.info("Reusing retained audio enhancement %s", reuse_candidate)
                _report(
                    20,
                    f"Reusing retained enhancement ({reuse_candidate.name}, full length)",
                )

        if not reused_enhancement and skip_audio and not require_enhancement:
            console_print("Skipping audio enhancement (not requested)")
            logger.info("Skipping audio enhancement (not requested)")
            _report(20, "Skipping audio enhancement (using file as-is)")
            enhanced_audio_path = audio_path
        elif not reused_enhancement:
            console_print("Processing audio...")
            _report(10, "Initializing audio processor...")
            if audio_processor_available:
                # Per-job temp dir: processing_temp_dir config key or the
                # disk-backed cache root, so jobs never share a tmpfs folder.
                processing_root = Path(
                    config.get('processing_temp_dir')
                    or (default_cache_root() / "sermon_processing")
                )
                temp_dir = processing_root / _uuid.uuid4().hex
                temp_dir.mkdir(parents=True, exist_ok=True)
                result['processing_temp_dir'] = str(temp_dir)

                # For video inputs, extract audio to WAV first
                process_input = audio_path
                if input_is_video:
                    _report(12, "Extracting audio from video...")
                    extracted_wav = temp_dir / "extracted_audio.wav"
                    try:
                        run_supervised(
                            ["ffmpeg", "-y", "-i", str(audio_path),
                             "-vn", "-acodec", "pcm_s16le", "-ar", "48000",
                             "-ac", "1", str(extracted_wav)],
                            cancel_check=_check_cancelled,
                            log=cancel_log,
                            step="audio extraction",
                            partial_paths=[extracted_wav],
                            partial_reason="cancelled_render_partial",
                            capture_output=True, text=True, timeout=300, check=True
                        )
                        process_input = extracted_wav
                        _report(14, "Audio extracted from video")
                    except ProcessCancelled:
                        raise
                    except Exception as e:
                        logger.warning("Failed to extract audio from video: %s", e)
                        _report(14, "Audio extraction failed, using original file")

                processor = AudioProcessor(
                    enhancement_method=(
                        enhancement_method
                        or config.get('audio_enhancement_method', 'deepfilternet')
                    ),
                    config=config,
                )
                if enhancement_method == "custom" and custom_repo and custom_file:
                    processor.config['clear_custom_repo'] = custom_repo
                    processor.config['clear_custom_file'] = custom_file
                enhanced_audio_path = temp_dir / "enhanced_audio.wav"
                _report(15, f"Running audio enhancement ({processor.enhancement_method})...")
                # Cancellation bound: DeepFilterNet/Clear process_sermon_audio is
                # one native call that cannot be interrupted mid-flight. The
                # cancel hook is checked immediately before and after it, so a
                # cancel during enhancement is observed when the call returns,
                # bounded by the enhancement call itself, not by the queue poll.
                success, proc_result = processor.process_sermon_audio(
                    str(process_input),
                    str(enhanced_audio_path)
                )
                if not success or not enhanced_audio_path.exists():
                    if require_enhancement:
                        logger.error(
                            "Audio enhancement failed for a render that required it"
                        )
                        result['error'] = "Audio enhancement failed"
                        return result
                    logger.warning("Audio processing failed, using original file")
                    _report(20, "Audio processing failed, falling back to original")
                    enhanced_audio_path = audio_path
                else:
                    _report(30, "Audio enhancement complete")
                    log_cuda_memory("after audio enhancement")
                try:
                    processor.release_gpu()
                    del processor
                except Exception:
                    pass
            else:
                if require_enhancement:
                    logger.error(
                        "Audio enhancement required but AudioProcessor is unavailable"
                    )
                    result['error'] = (
                        "Audio enhancement required but AudioProcessor is unavailable"
                    )
                    return result
                logger.warning("AudioProcessor unavailable, skipping enhancement")
                enhanced_audio_path = audio_path

        # The enhancer writes WAV regardless of the input container; transcode
        # back to the input's format so saved/uploaded files match their
        # extension and MIME type instead of shipping a 500MB "mp3".
        if (
            enhanced_audio_path != audio_path
            and enhanced_audio_path.exists()
            and temp_dir is not None
        ):
            target_ext = audio_path.suffix.lower()
            if target_ext and enhanced_audio_path.suffix.lower() != target_ext:
                converted_path = temp_dir / f"enhanced_audio{target_ext}"
                if _transcode_media(
                    Path(enhanced_audio_path),
                    converted_path,
                    cancel_check=_check_cancelled,
                    cancel_log=cancel_log,
                ):
                    console_print(
                        f"Converted enhanced audio to {target_ext.lstrip('.').upper()}"
                    )
                    enhanced_audio_path = converted_path

        result['enhanced_audio_path'] = str(enhanced_audio_path)

        # If the original input was a video, mux the enhanced audio back in
        final_upload_path = enhanced_audio_path
        upload_type = "original-audio"
        if input_is_video:
            audio_was_enhanced = enhanced_audio_path != audio_path and enhanced_audio_path.exists()
            if audio_was_enhanced:
                try:
                    final_video = original_input_path.with_name(
                        f"{original_input_path.stem}_enhanced{original_input_path.suffix}"
                    )
                    # Encode the enhancer's WAV directly rather than remuxing
                    # the AAC upload copy: a second AAC generation carries
                    # encoder priming delay the mux would not compensate.
                    mux_audio_input = Path(enhanced_audio_path)
                    if temp_dir is not None:
                        wav_candidate = temp_dir / "enhanced_audio.wav"
                        if wav_candidate.exists():
                            mux_audio_input = wav_candidate

                    correction = 0.0
                    av_cfg = config.get('av_sync') or {}
                    if av_cfg.get('enabled', True):
                        max_offset = float(av_cfg.get('max_offset_seconds', 2.0))
                        min_confidence = float(av_cfg.get('min_confidence', 0.12))
                        auto_correct = bool(av_cfg.get('auto_correct', False))
                        try:
                            from src.av_sync import (
                                measure_content_offset,
                                measure_waveform_offset,
                                resolve_audio_correction,
                            )
                            input_offset = measure_content_offset(
                                original_input_path,
                                model_dir=Path(av_cfg.get('model_dir') or '/tmp/av_sync_models'),
                                cancel_check=_check_cancelled,
                                cancel_log=cancel_log,
                            )
                            if input_offset.available and input_offset.offset_seconds is not None:
                                console_print(
                                    f"🎯 Input A/V offset: "
                                    f"{input_offset.offset_seconds:+.2f}s "
                                    f"(confidence {input_offset.confidence:.2f}, "
                                    f"{input_offset.detail})"
                                )
                                logger.info("av_sync input: %s", input_offset)
                            else:
                                console_print(
                                    f"🎯 Input A/V offset not measured ({input_offset.detail})"
                                )
                            enh_offset = measure_waveform_offset(
                                original_input_path,
                                mux_audio_input,
                                cancel_check=_check_cancelled,
                                cancel_log=cancel_log,
                            )
                            if enh_offset.available and enh_offset.offset_seconds is not None:
                                console_print(
                                    f"🎧 Enhancement audio offset: "
                                    f"{enh_offset.offset_seconds:+.3f}s"
                                )
                                logger.info("av_sync enhancement: %s", enh_offset)
                            measured = 0.0
                            if input_offset.available and input_offset.offset_seconds is not None:
                                measured += input_offset.offset_seconds
                            if enh_offset.available and enh_offset.offset_seconds is not None:
                                measured += enh_offset.offset_seconds
                            manual_offset = float(audio_offset or 0.0)
                            if abs(manual_offset) <= 1e-6 and edit_plan_file:
                                try:
                                    manual_offset = float(
                                        _load_edit_plan_from_file(
                                            edit_plan_file
                                        ).audio_offset or 0.0
                                    )
                                except Exception:
                                    manual_offset = 0.0
                            correction, av_reason = resolve_audio_correction(
                                manual_offset,
                                measured,
                                input_offset.confidence,
                                auto_correct=auto_correct,
                                min_confidence=min_confidence,
                                max_offset=max_offset,
                            )
                            if "exceeds" in av_reason:
                                result['av_sync_needs_review'] = True
                            if abs(measured) > 0.1 or abs(manual_offset) > 1e-6:
                                console_print(
                                    f"🎯 A/V decision: measured {measured:+.2f}s, "
                                    f"manual {manual_offset:+.2f}s -> {av_reason}"
                                )
                            result['av_sync_offset_seconds'] = correction
                        except ProcessCancelled:
                            raise
                        except Exception as e:
                            logger.warning("av_sync measurement failed: %s", e)

                    mux_cmd = ["ffmpeg", "-y", "-i", str(original_input_path)]
                    if abs(correction) > 1e-6:
                        mux_cmd += ["-itsoffset", f"{correction:.3f}"]
                    mux_cmd += [
                        "-i", str(mux_audio_input),
                        "-c:v", "copy",
                        *_mux_audio_codec_args(enhanced_audio_path),
                        "-map", "0:v:0",
                        "-map", "1:a:0",
                        "-shortest",
                        str(final_video),
                    ]
                    logger.info("Muxing enhanced audio into video: %s", " ".join(mux_cmd))
                    run_supervised(
                        mux_cmd,
                        cancel_check=_check_cancelled,
                        log=cancel_log,
                        step="video mux",
                        partial_paths=[final_video],
                        partial_reason="cancelled_render_partial",
                        capture_output=True,
                        text=True,
                        timeout=600,
                        check=True,
                    )
                    sync_problems = _verify_mux_av_sync(final_video)
                    if sync_problems:
                        logger.warning(
                            "A/V sync check on %s: %s", final_video, "; ".join(sync_problems)
                        )
                        console_print(f"⚠️  A/V sync check: {'; '.join(sync_problems)}")
                    else:
                        logger.info("A/V sync check passed for %s", final_video)
                        console_print("✅ A/V sync check passed (A/V within 0.2s)")
                    final_upload_path = final_video
                    upload_type = "original-video"
                    console_print(f"Muxed enhanced audio into video: {final_video.name}")
                except ProcessCancelled:
                    raise
                except Exception as e:
                    logger.warning("Video muxing failed, falling back to audio upload: %s", e)
                    console_print("Video mux failed, uploading audio only")
            else:
                console_print("Uploading original video (no audio enhancement)")
                final_upload_path = original_input_path
                upload_type = "original-video"

        # Step 2: Transcribe audio for metadata generation
        transcript = ""
        transcript_segments: list[dict[str, float | str]] = []
        if reuse_transcript is not None:
            # Apply/re-render path: the review step already transcribed this
            # sermon, so reuse the retained transcript instead of re-running
            # the model.
            transcript = reuse_transcript
            transcript_segments = list(reuse_transcript_segments or [])
            console_print(
                f"Reusing retained transcript ({len(transcript)} characters)"
            )
            logger.info(
                "Reusing retained transcript for apply (%d characters)",
                len(transcript),
            )
            _report(55, f"Reusing retained transcript ({len(transcript)} characters)")
        elif (not title or not description or not hashtags) and not skip_transcription:
            transcript = _reuse_existing_transcript(
                original_input_path, speaker_name, series_title, title, config
            )
            if transcript:
                console_print(f"Reusing existing transcript ({len(transcript)} characters)")
                _report(55, f"Reusing existing transcript ({len(transcript)} characters)")
                transcript_segments = _reuse_existing_transcript_segments(
                    original_input_path, speaker_name, series_title, title, config
                )
            else:
                release_enhancement_gpu()
                _report(35, f"Starting transcription ({whisper_model} model)...")
                try:
                    transcript_segments = transcribe_segments(
                        str(enhanced_audio_path),
                        model_size=whisper_model,
                        config=config,
                        backend_override=transcription_backend,
                        progress_callback=_report,
                        cancel_check=_check_cancelled,
                    )
                    transcript = _join_segment_texts(transcript_segments)
                    if not transcript:
                        _report(
                            45,
                            "First transcription attempt produced no result, "
                            "retrying with original audio...",
                        )
                        transcript_segments = transcribe_segments(
                            str(audio_path),
                            model_size=whisper_model,
                            config=config,
                            backend_override=transcription_backend,
                            progress_callback=_report,
                            cancel_check=_check_cancelled,
                        )
                        transcript = _join_segment_texts(transcript_segments)
                except ProcessingCancelledError:
                    raise
                except TranscriptionError as e:
                    logger.error("Transcription failed: %s", e)
                    raise RuntimeError(f"Transcription failed: {e}") from e
                except Exception as e:
                    logger.warning("Transcription attempt produced no result: %s", e)
                    transcript = ""
                    transcript_segments = []
                _report(55, f"Transcription complete: {len(transcript)} characters")
        elif skip_transcription:
            console_print("Skipping transcription (--skip-transcription enabled)")
            _report(55, "Skipped transcription")

        result['transcript'] = transcript
        result['transcript_segments'] = transcript_segments
        result['transcript_length'] = len(transcript) if transcript else 0

        auto_edit_state: dict[str, Any] | None = None

        def _persist_auto_edit_pending_review() -> dict:
            import json as review_json
            import shutil

            from src.sermon_paths import build_output_filename

            review_title = title or f"Sermon by {speaker_name}"
            review_description = description or ''
            review_hashtags = hashtags or ''
            review_id = _resolve_identity_id(
                speaker_name,
                recorded_date,
                review_title,
                original_input_path or audio_path,
                existing_sermon_id,
            )
            from src.review_media import (
                render_bounded_snippets,
                resolve_review_media_root,
                retained_artifact_line,
                sweep_abandoned_reviews,
                write_review_marker,
            )

            review_dir = get_sermon_dir(
                resolve_review_media_root(config),
                speaker_name,
                series_title,
                review_title,
                review_id,
            )
            review_dir.mkdir(parents=True, exist_ok=True)

            ext = Path(final_upload_path).suffix if final_upload_path else Path(audio_path).suffix

            original_ext = Path(original_input_path).suffix
            original_path = review_dir / build_output_filename(
                review_title, series_title, speaker_name, recorded_date, "Original", original_ext
            )
            if (
                Path(original_input_path).exists()
                and not original_path.exists()
                and Path(original_input_path).resolve() != original_path.resolve()
            ):
                shutil.copy2(original_input_path, original_path)

            keeper_path: Path | None = None
            if keeper_used and Path(audio_path).exists():
                keeper_path = review_dir / build_output_filename(
                    review_title,
                    series_title,
                    speaker_name,
                    recorded_date,
                    "Keeper",
                    Path(audio_path).suffix or ".mp4",
                )
                if (
                    not keeper_path.exists()
                    and Path(audio_path).resolve() != keeper_path.resolve()
                ):
                    shutil.copy2(audio_path, keeper_path)

            # A post-approval render is the only thing worth copying as the
            # processed media. The interactive pause happens before the render,
            # so its multi-GB pre-edit mux/enhanced artifact is not duplicated
            # into the review directory: the keeper and the transcript are what
            # the review panel needs, and a re-edit re-derives the render.
            render_source: Path | None = None
            if isinstance(auto_edit_state, dict):
                edited = auto_edit_state.get('edited_path')
                if edited and Path(str(edited)).exists():
                    render_source = Path(str(edited))
            processed_path: Path | None = None
            if render_source is not None and (
                keeper_path is None or render_source.resolve() != keeper_path.resolve()
            ):
                processed_path = review_dir / build_output_filename(
                    review_title, series_title, speaker_name, recorded_date, "Processed", ext
                )
                if render_source.resolve() != processed_path.resolve():
                    shutil.copy2(render_source, processed_path)

            enhanced_path: Path | None = None
            if (
                enhanced_audio_path is not None
                and Path(enhanced_audio_path).exists()
                and Path(enhanced_audio_path).resolve() != Path(original_input_path).resolve()
            ):
                enhanced_path = review_dir / build_output_filename(
                    review_title,
                    series_title,
                    speaker_name,
                    recorded_date,
                    "Enhanced",
                    Path(enhanced_audio_path).suffix,
                )
                if Path(enhanced_audio_path).resolve() != enhanced_path.resolve():
                    shutil.copy2(enhanced_audio_path, enhanced_path)

            transcript_file = get_file_path(review_dir, "transcript")
            timestamps_file = get_file_path(review_dir, "transcript_timestamps")

            snippet_logo: Path | None = None
            review_logo_cfg = (
                auto_edit_cfg.get('logo_path') if isinstance(auto_edit_cfg, dict) else None
            )
            if review_logo_cfg and Path(str(review_logo_cfg)).expanduser().exists():
                snippet_logo = Path(str(review_logo_cfg)).expanduser()

            snippet_files: list[Path] = []
            snippet_source = keeper_path if keeper_path is not None else original_path
            if input_is_video and Path(snippet_source).exists():
                snippet_files = render_bounded_snippets(
                    snippet_source,
                    gate_plan,
                    review_dir / "snippets",
                    logo_path=snippet_logo,
                )

            metadata = {
                'sermon_id': review_id,
                'sermonID': review_id,
                'title': review_title,
                'speaker': speaker_name,
                'series_title': series_title or '',
                'recorded_date': recorded_date,
                'event_type': event_type,
                'bible_text': bible_text,
                'subtitle': subtitle,
                'description': review_description,
                'hashtags': review_hashtags,
                'original_file': str(original_path),
                'is_video': input_is_video,
                'upload_type': upload_type,
                'transcript_length': len(transcript) if transcript else 0,
                'has_transcript': bool(transcript),
                'dry_run': bool(dry_run),
                'edit_plan_status': 'pending_review',
                'staged_file': str(original_input_path) if original_input_path else None,
                "auto_edit": _auto_edit_metadata_block(auto_edit_cfg),
            }
            if keeper_path is not None:
                metadata['keeper_file'] = str(keeper_path)
            if processed_path is not None:
                metadata['processed_file'] = str(processed_path)
            if enhanced_path is not None:
                metadata['enhanced_file'] = str(enhanced_path)
            if transcript:
                metadata['transcript_file'] = str(transcript_file)
                if transcript_segments:
                    metadata['transcript_timestamps_file'] = str(timestamps_file)
            for snippet in snippet_files:
                metadata[snippet.stem] = str(snippet)
            with open(get_file_path(review_dir, "metadata"), 'w') as f:
                review_json.dump(metadata, f, indent=2)
            if transcript:
                with open(transcript_file, 'w', encoding='utf-8') as f:
                    f.write(transcript)
                if transcript_segments:
                    save_transcript_timestamps(review_dir, transcript_segments)

            playable_media = processed_path or keeper_path or original_path
            review_file_paths: dict[str, str] = {
                'audio': str(playable_media),
                'metadata': str(get_file_path(review_dir, "metadata")),
            }
            if enhanced_path is not None:
                review_file_paths['enhanced_audio'] = str(enhanced_path)
            if keeper_path is not None:
                review_file_paths['keeper_audio'] = str(keeper_path)
            if input_is_video:
                review_file_paths['original_video'] = str(original_path)
            if transcript:
                review_file_paths['transcript'] = str(transcript_file)
                if transcript_segments:
                    review_file_paths['transcript_timestamps'] = str(timestamps_file)
            for snippet in snippet_files:
                review_file_paths[snippet.stem] = str(snippet)

            try:
                from ui.database import SermonRepository
                repo = SermonRepository()
                repo.save_sermon({
                    'id': review_id,
                    'title': review_title,
                    'subtitle': subtitle or '',
                    'series_title': series_title or '',
                    'description': review_description,
                    'scripture_reference': bible_text or '',
                    'speaker': speaker_name or '',
                    'recorded_date': recorded_date or '',
                    'event_type': event_type or '',
                    'bible_text': bible_text or '',
                    'duration': int(_ffprobe_duration(playable_media) or 0),
                    'status': 'draft',
                    'edit_status': 'pending_review',
                    'file_paths': review_file_paths,
                    'content': {
                        'transcript_text': transcript or '',
                        'description': review_description,
                        'hashtags': review_hashtags,
                    },
                })
                console_print("💾 Sermon saved locally for review (status: draft)")
            except Exception as e:
                logger.warning(f"Failed to save pending review sermon to local database: {e}")

            retained_media: list[tuple[str, Path]] = [("original", original_path)]
            if keeper_path is not None:
                retained_media.append(("keeper", keeper_path))
            if enhanced_path is not None:
                retained_media.append(("enhanced", enhanced_path))
            if processed_path is not None:
                retained_media.append(("processed", processed_path))
            for snippet in snippet_files:
                retained_media.append((snippet.stem, snippet))
            if transcript:
                retained_media.append(("transcript", transcript_file))
                if transcript_segments:
                    retained_media.append(("transcript_timestamps", timestamps_file))
            for kind, artifact in retained_media:
                line = retained_artifact_line(kind, artifact)
                console_print(line)
                logger.info(line)
            if keeper_used and (keeper_path is None or not keeper_path.exists()):
                console_print(
                    "Review media: keeper transcode existed but was not retained in "
                    f"{review_dir}",
                    level="warning",
                )

            write_review_marker(review_dir, review_id)
            try:
                sweep_abandoned_reviews(config, protect_dir=review_dir)
            except Exception as e:
                logger.warning(f"Review media sweep failed: {e}")

            try:
                _save_edit_plan_row(
                    review_id, gate_plan, 'pending_review', str(edit_source), gate_notes
                )
            except Exception as e:
                logger.warning(f"Failed to save edit plan revision: {e}")

            console_print(f"✂️  Edit plan saved for review: {review_id}")
            _report(100, "Auto-edit plan saved for review")
            result.update({
                'success': True,
                'sermon_id': review_id,
                'title': review_title,
                'description': review_description,
                'hashtags': review_hashtags,
                'output_dir': str(review_dir),
                'edit_plan_status': 'pending_review',
                'auto_edit_applied': False,
            })
            return result

        def _log_auto_edit_applied(passed_sermon_id: str, upload_failed: bool = False) -> None:
            confidence = auto_edit_state['plan'].confidence
            if upload_failed:
                console_print(
                    f"✂️  Auto edit applied for sermon {passed_sermon_id} "
                    f"(confidence {confidence:.2f}) but media upload failed"
                )
                return
            console_print(
                f"✂️  Auto edit applied for sermon {passed_sermon_id} "
                f"(confidence {confidence:.2f})"
            )

        def _persist_auto_edit_applied_plan(
            passed_sermon_id: str, upload_failed: bool = False
        ) -> None:
            assert auto_edit_state is not None
            _log_auto_edit_applied(passed_sermon_id, upload_failed)
            try:
                _save_edit_plan_row(
                    passed_sermon_id,
                    auto_edit_state['plan'],
                    'auto_applied',
                    auto_edit_state['source_path'],
                    auto_edit_state['notes'],
                )
            except Exception as e:
                logger.warning(f"Failed to save applied edit plan: {e}")

        def _auto_edit_output_root() -> Path:
            root = Path(config.get('output_directory', 'processed_sermons'))
            if not root.is_absolute():
                root = Path(__file__).parent / root
            return root

        def _save_edit_plan_row(sermon_id_value: str, plan: EditPlan, status: str,
                                source_path: str, notes: str) -> None:
            from ui.database import SermonRepository
            repo = SermonRepository()
            repo.save_edit_plan_revision(sermon_id_value, {
                'proposed_start': float(plan.start),
                'proposed_end': float(plan.end),
                'final_start': float(plan.start),
                'final_end': float(plan.end),
                'confidence': float(plan.confidence),
                'needs_review': bool(plan.needs_review),
                'evidence': plan.evidence,
                'qa_judgment': plan.qa_judgment,
                'reasoning': plan.reasoning,
                'audio_offset': float(plan.audio_offset or 0.0),
                'detection_status': plan.detection_status,
                'status': status,
                'source_path': source_path,
                'notes': notes,
                'actions': {
                    'enhance_audio': bool(enhanced_audio_file)
                    or enhanced_audio_path != audio_path,
                },
            })

        if auto_edit_mode is not None:
            auto_edit_cfg = config.get('auto_edit', {}) if isinstance(config, dict) else {}
            gate_active = True
            gate_mode = auto_edit_mode
        else:
            auto_edit_cfg = config.get('auto_edit', {}) if isinstance(config, dict) else {}
            gate_active = bool(auto_edit_cfg.get('enabled', False)) or bool(edit_plan_file)
            gate_mode = auto_edit_cfg.get('mode') or (
                'interactive' if bool(auto_edit_cfg.get('require_review', False)) else 'auto'
            )

        if gate_active and not input_is_video:
            console_print("⏭️  Auto-edit applies to video inputs only, skipping")
            gate_active = False

        if gate_active:
            edit_source = audio_path if keeper_used else original_input_path
            plan_duration = _ffprobe_duration(edit_source)

            if edit_plan_file:
                try:
                    gate_plan = _load_edit_plan_from_file(edit_plan_file)
                    gate_notes = "Plan loaded from --edit-plan-file"
                except Exception as e:
                    logger.error("Failed to load edit plan file %s: %s", edit_plan_file, e)
                    result['error'] = f"Failed to load edit plan file: {e}"
                    return result
            else:
                _report(56, "Detecting cut points...")
                gate_plan = detect_cut_points(
                    transcript_segments, llm_manager, config, plan_duration
                )
                gate_notes = f"Detected cut points (mode: {gate_mode})"

            if audio_offset is not None:
                gate_plan.audio_offset = float(audio_offset)

            confidence_threshold = _auto_edit_confidence_threshold(auto_edit_cfg)
            min_sermon_seconds = float(auto_edit_cfg.get('min_sermon_seconds', 600))

            if gate_plan.detection_status != 'ok':
                detail = gate_plan.reasoning or "no usable cut points returned"
                logger.error(
                    "Auto-edit cut detection failed for %s: %s",
                    edit_source,
                    detail,
                )
                console_print(
                    "⚠️  Cut detection failed; nothing will be applied. "
                    "The plan is saved for manual review."
                )

            gate_apply = (
                gate_mode == 'auto'
                and gate_plan.detection_status == 'ok'
                and not gate_plan.needs_review
                and gate_plan.confidence >= confidence_threshold
                and not validate_plan(gate_plan, plan_duration, min_sermon_seconds)
            )

            if edit_plan_file and not gate_apply:
                problems = validate_plan(gate_plan, plan_duration, min_sermon_seconds)
                detail = "; ".join(problems) if problems else (
                    "plan did not meet the auto-apply gate"
                )
                duration_text = (
                    f"{plan_duration:.1f}s" if plan_duration is not None else "unknown"
                )
                logger.error(
                    "Approved edit plan invalid (%s); nothing was rendered", detail
                )
                console_print(f"❌ Approved edit plan invalid ({detail}); nothing rendered")
                result['success'] = False
                result['auto_edit_applied'] = False
                result['edit_plan_status'] = None
                result['error'] = (
                    f"Approved edit plan end {gate_plan.end:.1f}s is not applicable to "
                    f"source duration {duration_text} ({detail}); nothing was rendered."
                )
                return result

            if not gate_apply:
                return _persist_auto_edit_pending_review()

            _report(58, "Applying automatic edit...")
            logo_cfg = auto_edit_cfg.get('logo_path')
            edit_logo_path = (
                Path(logo_cfg).expanduser()
                if logo_cfg and Path(str(logo_cfg)).expanduser().exists() else None
            )
            gate_plan.logo_hold = float(
                auto_edit_cfg.get('logo_hold', gate_plan.logo_hold)
            )
            edit_fade_to_black = bool(auto_edit_cfg.get('fade_to_black', True))
            edit_fade_out_tail = float(auto_edit_cfg.get('fade_out_tail_seconds', 2.0))
            edited_path = _auto_edit_output_root() / "edited" / (
                f"{original_input_path.stem}_edited{original_input_path.suffix or '.mp4'}"
            )
            try:
                edited_path = apply_edit(
                    Path(edit_source),
                    gate_plan,
                    edited_path,
                    logo_path=edit_logo_path,
                    fade_to_black=edit_fade_to_black,
                    fade_out_tail_seconds=edit_fade_out_tail,
                    cancel_check=_check_cancelled,
                    cancel_log=cancel_log,
                )
            except ProcessCancelled:
                raise
            except Exception as e:
                logger.error("Auto edit apply failed: %s", e)
                if edit_plan_file:
                    console_print(f"❌ Approved edit render failed ({e}); nothing was rendered")
                    result['success'] = False
                    result['auto_edit_applied'] = False
                    result['edit_plan_status'] = None
                    result['error'] = (
                        f"Approved edit render failed ({e}); nothing was rendered."
                    )
                    return result
                console_print(f"⚠️  Auto edit apply failed ({e}); saving plan for review")
                gate_plan.needs_review = True
                gate_notes = f"{gate_notes}; apply failed: {e}".strip("; ")
                return _persist_auto_edit_pending_review()

            final_upload_path = edited_path
            upload_type = "original-video"
            auto_edit_state = {
                'plan': gate_plan,
                'source_path': str(edit_source),
                'edited_path': str(edited_path),
                'notes': gate_notes,
            }
            result['final_upload_path'] = str(edited_path)
            result['upload_type'] = upload_type
            result['auto_edit_applied'] = True
            result['edit_plan_status'] = 'auto_applied'
            console_print(f"✂️ Auto edit ready: {edited_path.name}")

        # Step 3: Generate metadata using transcript or fallback
        metadata_notes: dict = {}
        if transcript and not skip_ai_generation:
            console_print("Generating metadata from transcript...")

            def _generate_metadata_stage():
                stage_title = title
                stage_description = description
                stage_hashtags = hashtags

                if not stage_title:
                    try:
                        logger.info(
                            "Metadata field 'title' is empty; generating from transcript"
                        )
                        _report(60, f"Generating title with {_llm_target_label()}...")
                        _started = time.time()
                        stage_title = generate_title(
                            transcript=transcript,
                            speaker_name=speaker_name,
                            event_type=event_type,
                            bible_text=bible_text
                        )
                        _report(62, f"Title generated in {time.time() - _started:.1f}s")
                    except LLMModelNotFoundError as e:
                        _log_metadata_model_missing(e)
                    except LLMModelNotConfiguredError as e:
                        logger.warning("metadata skipped: %s", e)
                    except LLMTimeoutError as e:
                        _log_metadata_timeout(e)
                    except Exception as e:
                        logger.warning("LLM title generation failed: %s", e)

                if not stage_description:
                    try:
                        logger.info(
                            "Metadata field 'description' is empty; "
                            "generating from transcript"
                        )
                        _report(70, f"Generating description with {_llm_target_label()}...")
                        _started = time.time()
                        if force_validation and transcript:
                            _report(70, "Generating description with validation...")
                            validator = DescriptionValidator(config)
                            stage_description, validation_info = generate_validated_summary(
                                transcript,
                                event_type=event_type,
                                speaker_name=speaker_name
                            )
                            if validation_info:
                                metadata_notes['description_needs_review'] = bool(
                                    validation_info.get('description_needs_review')
                                )
                            is_valid, reason, score, _, _ = validator.validate_description(
                                stage_description, {'sermon_id': None}
                            )
                            if not is_valid:
                                logger.warning(
                                    "Generated description failed validation (%s); "
                                    "regenerating without validation as fallback", reason,
                                )
                                stage_description = generate_summary(
                                    transcript,
                                    event_type=event_type,
                                    speaker_name=speaker_name,
                                    notes=metadata_notes,
                                )
                        else:
                            stage_description = generate_summary(
                                transcript,
                                event_type=event_type,
                                speaker_name=speaker_name,
                                notes=metadata_notes,
                            )
                        _report(72, f"Description generated in {time.time() - _started:.1f}s")
                    except DescriptionGenerationError as e:
                        metadata_notes['description_needs_review'] = True
                        metadata_notes['description_error'] = str(e)
                        logger.warning(
                            "Description generation failed (provider=%s, "
                            "elapsed=%s, attempts=%s); leaving the field empty "
                            "and marking it for review: %s",
                            getattr(e, 'provider', None),
                            getattr(e, 'elapsed_seconds', None),
                            getattr(e, 'attempts', None),
                            e,
                        )
                        stage_description = None
                    except LLMModelNotFoundError as e:
                        _log_metadata_model_missing(e)
                        metadata_notes['description_needs_review'] = True
                        metadata_notes['description_error'] = str(e)
                        stage_description = None
                    except LLMModelNotConfiguredError as e:
                        logger.warning("metadata skipped: %s", e)
                        metadata_notes['description_needs_review'] = True
                        metadata_notes['description_error'] = str(e)
                        stage_description = None
                    except LLMTimeoutError as e:
                        _log_metadata_timeout(e)
                        metadata_notes['description_needs_review'] = True
                        metadata_notes['description_error'] = str(e)
                        stage_description = None
                    except Exception as e:
                        logger.warning(
                            "LLM description generation failed; leaving the field "
                            "empty and marking it for review: %s",
                            e,
                        )
                        metadata_notes['description_needs_review'] = True
                        metadata_notes['description_error'] = str(e)
                        stage_description = None

                    if stage_description:
                        logger.info(
                            "Description ready (%d chars); stored in "
                            "sermons.description and sermon_content.description",
                            len(stage_description),
                        )
                    elif metadata_notes.get('description_error'):
                        logger.warning(
                            "Description generation failed; the field is left "
                            "empty and marked for review (description_needs_review)"
                        )
                    else:
                        logger.warning(
                            "Description generation returned nothing; "
                            "the template fallback will be used"
                        )

                if not stage_hashtags:
                    try:
                        logger.info(
                            "Metadata field 'hashtags' is empty; "
                            "generating from transcript"
                        )
                        _report(80, f"Generating hashtags with {_llm_target_label()}...")
                        _started = time.time()
                        stage_hashtags = generate_hashtags(transcript)
                        _report(82, f"Hashtags generated in {time.time() - _started:.1f}s")
                    except LLMModelNotFoundError as e:
                        _log_metadata_model_missing(e)
                        stage_hashtags = None
                    except LLMModelNotConfiguredError as e:
                        logger.warning("metadata skipped: %s", e)
                        stage_hashtags = None
                    except LLMTimeoutError as e:
                        _log_metadata_timeout(e)
                        stage_hashtags = None
                    except Exception as e:
                        logger.warning("LLM hashtag generation failed: %s", e)
                        stage_hashtags = None

                return stage_title, stage_description, stage_hashtags

            try:
                title, description, hashtags = _llm_call_with_deadline(
                    _generate_metadata_stage,
                    _metadata_stage_budget_seconds(),
                    "metadata-stage",
                )
            except LLMTimeoutError:
                logger.warning(
                    "metadata stage exceeded its budget; continuing without metadata"
                )
            except LLMModelNotFoundError as e:
                _log_metadata_model_missing(e)
                title = description = hashtags = None
            except LLMModelNotConfiguredError as e:
                logger.warning(
                    "metadata stage skipped: %s; continuing without metadata", e
                )
                title = description = hashtags = None
            except Exception as e:
                logger.warning("metadata stage failed (%s); continuing without metadata", e)
                title = description = hashtags = None
        elif skip_ai_generation:
            console_print("Skipping AI metadata generation")
        else:
            console_print("No transcript available, using basic metadata...")

        result['description_needs_review'] = bool(
            metadata_notes.get('description_needs_review')
        )

        # Fallback metadata generation for any missing fields
        if skip_ai_generation:
            if not title:
                title = title or speaker_name or recorded_date
            if not description:
                description = description or ''
            if not hashtags:
                hashtags = hashtags or ''
        else:
            if not title:
                title = f"Sermon by {speaker_name}"
                if bible_text:
                    title += f" - {bible_text}"

            description_failed = bool(metadata_notes.get('description_error'))
            if not description and not description_failed:
                description = f"A sermon by {speaker_name}"
                if bible_text:
                    description += f" on {bible_text}"
                description += f" from {event_type} on {recorded_date}."

            if not hashtags:
                base_tags = [
                    "#sermon",
                    f"#{speaker_name.replace(' ', '')}",
                    f"#{event_type.replace(' ', '').replace('-', '')}",
                ]
                if bible_text:
                    book = bible_text.split()[0] if bible_text else ""
                    if book:
                        base_tags.append(f"#{book}")
                hashtags = " ".join(base_tags[:5])

        result['title'] = title
        result['description'] = description
        result['hashtags'] = hashtags
        if metadata_notes.get('description_error'):
            result['description_error'] = metadata_notes['description_error']

        # Generate short display title if requested
        short_display_title = None
        if generate_short_title and title:
            try:
                short_display_title = generate_short_display_title(title)
                console_print(f"Short display title: {short_display_title}")
            except LLMTimeoutError as e:
                _log_metadata_timeout(e)
            except Exception as e:
                logger.warning("Short title generation failed: %s", e)

        console_print(f"Generated title: {title}")
        if metadata_notes.get('description_error'):
            console_print("Description generation failed - retry", level="warning")
        else:
            console_print(f"Generated description: {description[:100]}...")
        if hashtags:
            console_print(f"Generated hashtags: {hashtags}")

        if dry_run:
            console_print("DRY RUN - Would create sermon with:")
            console_print(f"  Title: {title}")
            console_print(f"  Speaker: {speaker_name}")
            console_print(f"  Date: {recorded_date}")
            console_print(f"  Event: {event_type}")
            console_print(f"  Bible Text: {bible_text}")
            if metadata_notes.get('description_error'):
                console_print("  Description: description generation failed - retry")
            else:
                console_print(f"  Description: {description[:100]}...")
            console_print(f"  Hashtags: {hashtags}")
            console_print(f"  Audio: {enhanced_audio_path}")
            if input_is_video:
                console_print(f"  Video: {final_upload_path}")
            console_print(f"  Upload type: {upload_type}")
            if short_display_title:
                console_print(f"  Display Title: {short_display_title}")
            console_print(
                f"  Transcript: {len(transcript)} characters"
                if transcript else "  Transcript: None"
            )

            # Save dry run results for visibility in the Library page
            sermon_id = _resolve_identity_id(
                speaker_name,
                recorded_date,
                title or 'Untitled',
                original_input_path,
                existing_sermon_id,
            )
            result['sermon_id'] = sermon_id


            output_root = Path(config.get('output_directory', 'processed_sermons'))
            if not output_root.is_absolute():
                output_root = Path(__file__).parent / output_root
            output_dir = get_sermon_dir(output_root, speaker_name, series_title, title, sermon_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            result['output_dir'] = str(output_dir)

            # Copy processed file to output directory
            import shutil

            from src.sermon_paths import build_output_filename

            ext = Path(audio_path).suffix
            if input_is_video and upload_type == "original-video":
                final_output_path = output_dir / build_output_filename(
                    title, series_title, speaker_name, recorded_date, "Processed", ext
                )
                if final_upload_path.exists():
                    if final_upload_path.resolve() != final_output_path.resolve():
                        shutil.copy2(final_upload_path, final_output_path)
                else:
                    if enhanced_audio_path.resolve() != final_output_path.resolve():
                        shutil.copy2(enhanced_audio_path, final_output_path)
            else:
                final_output_path = output_dir / build_output_filename(
                    title, series_title, speaker_name, recorded_date, "Processed", ext
                )
                source = enhanced_audio_path if enhanced_audio_path != audio_path else audio_path
                if source.resolve() != final_output_path.resolve():
                    shutil.copy2(source, final_output_path)

            # Save original file for future reprocessing
            original_save_path = output_dir / build_output_filename(
                title, series_title, speaker_name, recorded_date, "Original", ext
            )
            if not original_save_path.exists():
                shutil.copy2(audio_path, original_save_path)
                logger.info("Saved original file to %s", original_save_path)

            # Save metadata
            # For apply renders (auto_edit_state set) the output directory can
            # collide with the source sermon's directory (get_sermon_dir ignores
            # the sermon id, and the Processed filename is stable), so never
            # repoint metadata original_file at the trimmed render: retain the
            # existing on-disk full-length source for the next apply.
            retained_original: str | None = None
            if auto_edit_state:
                try:
                    import json as _retain_json
                    existing_meta_path = get_file_path(output_dir, "metadata")
                    if existing_meta_path.exists():
                        existing_meta = _retain_json.loads(
                            existing_meta_path.read_text(encoding='utf-8')
                        )
                        candidate = (existing_meta or {}).get('original_file')
                        if candidate and Path(str(candidate)).exists():
                            retained_original = str(candidate)
                except Exception:
                    retained_original = None
            metadata = {
                'sermon_id': sermon_id,
                'sermonID': sermon_id,
                'title': title,
                'speaker': speaker_name,
                'series_title': series_title or '',
                'recorded_date': recorded_date,
                'event_type': event_type,
                'bible_text': bible_text,
                'subtitle': subtitle,
                'description': description,
                'hashtags': hashtags,
                'original_file': retained_original or str(audio_path),
                'processed_file': str(final_output_path),
                'is_video': input_is_video,
                'upload_type': upload_type,
                'transcript_length': len(transcript) if transcript else 0,
                'has_transcript': bool(transcript),
                'dry_run': True,
            }
            import json
            if gate_active:
                metadata["auto_edit"] = _auto_edit_metadata_block(auto_edit_cfg)
            with open(get_file_path(output_dir, "metadata"), 'w') as f:
                json.dump(metadata, f, indent=2)

            if transcript:
                with open(get_file_path(output_dir, "transcript"), 'w', encoding='utf-8') as f:
                    f.write(transcript)
                if transcript_segments:
                    save_transcript_timestamps(output_dir, transcript_segments)

            # Save to local database for UI visibility
            try:
                from ui.database import SermonRepository
                repo = SermonRepository()
                duration = 0
                try:
                    import json as _json
                    import subprocess
                    r = subprocess.run(
                        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format',
                         str(enhanced_audio_path)],
                        capture_output=True, text=True, timeout=30,
                    )
                    if r.returncode == 0:
                        info = _json.loads(r.stdout)
                        duration = float(info.get('format', {}).get('duration', 0))
                except Exception:
                    pass
                repo.save_sermon({
                    'id': sermon_id,
                    'title': title or '',
                    'subtitle': subtitle or '',
                    'series_title': series_title or '',
                    'description': description or '',
                    'scripture_reference': bible_text or '',
                    'speaker': speaker_name or '',
                    'recorded_date': recorded_date or '',
                    'event_type': event_type or '',
                    'bible_text': bible_text or '',
                    'duration': duration,
                    'status': 'draft',
                    'edit_status': 'rendered' if auto_edit_state else None,
                    'description_needs_review': bool(
                        metadata_notes.get('description_needs_review')
                    ),
                    'file_paths': {
                        'audio': str(final_output_path),
                        'metadata': str(get_file_path(output_dir, "metadata")),
                    },
                    'content': {
                        'transcript_text': transcript or '',
                        'description': description or '',
                        'hashtags': hashtags or '',
                    },
                })
                console_print("Dry run sermon saved to local database (status: draft)")
            except Exception as e:
                logger.warning(f"Failed to save dry run sermon to local database: {e}")

            if auto_edit_state:
                _persist_auto_edit_applied_plan(sermon_id)

            console_print(f"Dry run files saved to: {output_dir}")
            _report(100, "Dry run complete")
            result['success'] = True
            return result

        # Step 4: Create sermon via API
        _check_cancelled()

        # Reuse an already-uploaded sermon with identical identity fields so a
        # retry after dying mid-upload cannot create a duplicate remote sermon.
        reusable_sermon_id = _find_existing_processed_sermon_id(
            title, speaker_name, recorded_date
        )

        recovery_draft_id: str | None = None
        recovery_output_dir: Path | None = None
        if reusable_sermon_id and not _remote_sermon_exists(reusable_sermon_id):
            logger.warning(
                "Local sermon %s matches '%s' by %s (%s) but was not found "
                "on SermonAudio; ignoring it and creating a new sermon",
                reusable_sermon_id, title, speaker_name, recorded_date,
            )
            console_print(
                f"⚠️  Local sermon {reusable_sermon_id} not found on SermonAudio; "
                "creating a new sermon instead of reusing it"
            )
            reusable_sermon_id = None
        if reusable_sermon_id:
            sermon_id = reusable_sermon_id
            console_print(
                f"Existing processed sermon {sermon_id} matches "
                f"'{title}' by {speaker_name} ({recorded_date}); reusing it"
            )
            _report(88, f"Reusing existing sermon: {sermon_id}")
        else:
            # Persist everything generated so far as a local draft BEFORE the
            # API create so a failed create loses no work.
            try:
                import json as _json
                import shutil as _shutil

                from src.sermon_paths import build_output_filename

                recovery_draft_id = _resolve_identity_id(
                    speaker_name,
                    recorded_date,
                    title or 'Untitled',
                    original_input_path,
                    existing_sermon_id,
                )
                output_root = Path(config.get('output_directory', 'processed_sermons'))
                if not output_root.is_absolute():
                    output_root = Path(__file__).parent / output_root
                recovery_output_dir = get_sermon_dir(
                    output_root, speaker_name, series_title, title, recovery_draft_id
                )
                recovery_output_dir.mkdir(parents=True, exist_ok=True)

                ext = Path(audio_path).suffix
                if input_is_video and upload_type == "original-video":
                    draft_source = (
                        final_upload_path
                        if Path(final_upload_path).exists()
                        else enhanced_audio_path
                    )
                else:
                    draft_source = (
                        enhanced_audio_path
                        if enhanced_audio_path != audio_path
                        else audio_path
                    )
                draft_processed_path = recovery_output_dir / build_output_filename(
                    title, series_title, speaker_name, recorded_date, "Processed", ext
                )
                if Path(draft_source).resolve() != draft_processed_path.resolve():
                    _shutil.copy2(draft_source, draft_processed_path)
                draft_original_path = recovery_output_dir / build_output_filename(
                    title, series_title, speaker_name, recorded_date, "Original", ext
                )
                if not draft_original_path.exists():
                    _shutil.copy2(audio_path, draft_original_path)

                draft_metadata = {
                    'sermon_id': recovery_draft_id,
                    'sermonID': recovery_draft_id,
                    'title': title,
                    'speaker': speaker_name,
                    'series_title': series_title or '',
                    'recorded_date': recorded_date,
                    'event_type': event_type,
                    'bible_text': bible_text,
                    'subtitle': subtitle,
                    'description': description,
                    'hashtags': hashtags,
                    'original_file': str(audio_path),
                    'processed_file': str(draft_processed_path),
                    'is_video': input_is_video,
                    'upload_type': upload_type,
                    'transcript_length': len(transcript) if transcript else 0,
                    'has_transcript': bool(transcript),
                    'dry_run': False,
                    'recovery_draft': True,
                }
                with open(get_file_path(recovery_output_dir, "metadata"), 'w') as f:
                    _json.dump(draft_metadata, f, indent=2)
                if transcript:
                    with open(
                        get_file_path(recovery_output_dir, "transcript"),
                        'w',
                        encoding='utf-8',
                    ) as f:
                        f.write(transcript)
                    if transcript_segments:
                        save_transcript_timestamps(recovery_output_dir, transcript_segments)

                try:
                    from ui.database import SermonRepository
                    repo = SermonRepository()
                    repo.save_sermon({
                        'id': recovery_draft_id,
                        'title': title or '',
                        'subtitle': subtitle or '',
                        'series_title': series_title or '',
                        'description': description or '',
                        'scripture_reference': bible_text or '',
                        'speaker': speaker_name or '',
                        'recorded_date': recorded_date or '',
                        'event_type': event_type or '',
                        'bible_text': bible_text or '',
                        'status': 'draft',
                        'description_needs_review': bool(
                            metadata_notes.get('description_needs_review')
                        ),
                        'file_paths': {
                            'audio': str(draft_processed_path),
                            'metadata': str(
                                get_file_path(recovery_output_dir, "metadata")
                            ),
                        },
                        'content': {
                            'transcript_text': transcript or '',
                            'description': description or '',
                            'hashtags': hashtags or '',
                        },
                    })
                    console_print(f"Draft saved locally before upload: {recovery_draft_id}")
                except Exception as db_err:
                    logger.warning("Failed to save pre-upload draft to database: %s", db_err)
            except Exception as draft_err:
                logger.warning("Failed to persist pre-upload draft: %s", draft_err)
                recovery_draft_id = None

            _report(83, "Resolving speaker...")
            console_print("Resolving speaker...")
            speaker_id = resolve_speaker_id(speaker_name)
            if speaker_id:
                console_print(f"Resolved speaker '{speaker_name}' to ID {speaker_id}")
            else:
                console_print(f"Using speaker name '{speaker_name}' as-is (no numeric ID found)")

            _report(85, "Creating sermon on SermonAudio...")
            console_print("Creating sermon on SermonAudio...")
            sermon_id = create_new_sermon_api(
                title=title,
                speaker_name=speaker_name,
                recorded_date=recorded_date,
                event_type=event_type,
                bible_text=bible_text,
                subtitle=subtitle,
                description=description,
                hashtags=hashtags,
                speaker_id=speaker_id,
                display_title=short_display_title,
            )

            if not sermon_id:
                logger.error("Failed to create sermon")
                result['error'] = "Failed to create sermon on SermonAudio API"
                if recovery_draft_id:
                    result['sermon_id'] = recovery_draft_id
                    result['output_dir'] = str(recovery_output_dir)
                    result['draft_saved'] = True
                    result['error'] += (
                        f"; progress preserved locally as draft {recovery_draft_id}"
                    )
                    console_print(
                        f"Create failed - progress saved as draft {recovery_draft_id}"
                    )
                return result

        result['sermon_id'] = sermon_id
        if auto_edit_state:
            _log_auto_edit_applied(sermon_id)
        _report(90, f"Created sermon: {sermon_id}")

        # Single application path for series: the API ignores it during
        # creation, so always PATCH it onto the sermon afterwards
        if series_id is not None:
            if set_sermon_series(sermon_id, series_id):
                console_print(f"Series set: {series_title} (ID {series_id})")
            else:
                console_print(
                    f"Failed to set series '{series_title}' on sermon {sermon_id}"
                )
                logger.error(
                    "set_sermon_series failed: sermon %s, seriesID %s (%s)",
                    sermon_id, series_id, series_title,
                )

        # Step 5: Upload the media (audio or video)
        media_label = "video" if upload_type == "original-video" else "audio"
        console_print(f"Uploading {media_label} for sermon {sermon_id}...")
        _report(92, f"Uploading {media_label} to SermonAudio...")
        upload_success = upload_media_file(sermon_id, str(final_upload_path), upload_type)

        if upload_success:
            console_print(
                f"Successfully created and uploaded {media_label} for sermon {sermon_id}"
            )
            _report(95, f"{media_label.capitalize()} uploaded successfully")
            if publish:
                if set_sermon_published(sermon_id, True):
                    console_print("Published on SermonAudio")
                else:
                    console_print("Upload complete, but publishing failed")
            else:
                console_print("Left unpublished on SermonAudio (publish disabled for this run)")

            # Create local output directory
            output_root = Path(config.get('output_directory', 'processed_sermons'))
            if not output_root.is_absolute():
                output_root = Path(__file__).parent / output_root
            output_dir = get_sermon_dir(output_root, speaker_name, series_title, title, sermon_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            result['output_dir'] = str(output_dir)

            # Copy processed file to output directory
            import shutil

            from src.sermon_paths import build_output_filename

            ext = Path(audio_path).suffix
            if input_is_video and upload_type == "original-video":
                final_output_path = output_dir / build_output_filename(
                    title, series_title, speaker_name, recorded_date, "Processed", ext
                )
                if final_upload_path.exists():
                    shutil.copy2(final_upload_path, final_output_path)
                else:
                    shutil.copy2(enhanced_audio_path, final_output_path)
            else:
                final_output_path = output_dir / build_output_filename(
                    title, series_title, speaker_name, recorded_date, "Processed", ext
                )
                source = enhanced_audio_path if enhanced_audio_path != audio_path else audio_path
                shutil.copy2(source, final_output_path)

            # Save original file for future reprocessing
            original_save_path = output_dir / build_output_filename(
                title, series_title, speaker_name, recorded_date, "Original", ext
            )
            if not original_save_path.exists():
                shutil.copy2(audio_path, original_save_path)
                logger.info("Saved original file to %s", original_save_path)

            # Save metadata
            # For apply renders (auto_edit_state set) the output directory can
            # collide with the source sermon's directory (get_sermon_dir ignores
            # the sermon id, and the Processed filename is stable), so never
            # repoint metadata original_file at the trimmed render: retain the
            # existing on-disk full-length source for the next apply.
            retained_original: str | None = None
            if auto_edit_state:
                try:
                    import json as _retain_json
                    existing_meta_path = get_file_path(output_dir, "metadata")
                    if existing_meta_path.exists():
                        existing_meta = _retain_json.loads(
                            existing_meta_path.read_text(encoding='utf-8')
                        )
                        candidate = (existing_meta or {}).get('original_file')
                        if candidate and Path(str(candidate)).exists():
                            retained_original = str(candidate)
                except Exception:
                    retained_original = None
            metadata = {
                'sermon_id': sermon_id,
                'sermonID': sermon_id,
                'title': title,
                'speaker': speaker_name,
                'series_title': series_title or '',
                'recorded_date': recorded_date,
                'event_type': event_type,
                'bible_text': bible_text,
                'subtitle': subtitle,
                'description': description,
                'hashtags': hashtags,
                'original_file': retained_original or str(audio_path),
                'processed_file': str(final_output_path),
                'is_video': input_is_video,
                'upload_type': upload_type,
                'transcript_length': len(transcript) if transcript else 0,
                'has_transcript': bool(transcript)
            }

            import json
            if gate_active:
                metadata["auto_edit"] = _auto_edit_metadata_block(auto_edit_cfg)
            with open(get_file_path(output_dir, "metadata"), 'w') as f:
                json.dump(metadata, f, indent=2)

            # Save transcript if available
            if transcript:
                with open(get_file_path(output_dir, "transcript"), 'w', encoding='utf-8') as f:
                    f.write(transcript)
                if transcript_segments:
                    save_transcript_timestamps(output_dir, transcript_segments)
                console_print(f"Transcript saved ({len(transcript)} characters)")

            # Cancellation checkpoint: stop before persisting the local record
            # as 'processed' if the user cancelled while uploading
            _check_cancelled()

            # Save to local database for UI visibility
            try:
                from ui.database import SermonRepository
                repo = SermonRepository()
                duration = 0
                try:
                    import json
                    import subprocess
                    r = subprocess.run(
                        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format',
                         str(enhanced_audio_path)],
                        capture_output=True, text=True, timeout=30,
                    )
                    if r.returncode == 0:
                        info = json.loads(r.stdout)
                        duration = float(info.get('format', {}).get('duration', 0))
                except Exception:
                    pass
                repo.save_sermon({
                    'id': sermon_id,
                    'title': title or '',
                    'subtitle': subtitle or '',
                    'series_title': series_title or '',
                    'description': description or '',
                    'scripture_reference': bible_text or '',
                    'speaker': speaker_name or '',
                    'recorded_date': recorded_date or '',
                    'event_type': event_type or '',
                    'bible_text': bible_text or '',
                    'duration': duration,
                    'status': 'processed',
                    'description_needs_review': bool(
                        metadata_notes.get('description_needs_review')
                    ),
                    'upload_info': {
                        'sermonaudio_id': str(sermon_id),
                        'upload_date': dt.datetime.now(),
                        'upload_status': 'completed',
                        'upload_message': 'Media uploaded successfully',
                    },
                    'file_paths': {
                        'audio': str(final_output_path),
                        'metadata': str(get_file_path(output_dir, "metadata")),
                    },
                    'content': {
                        'transcript_text': transcript or '',
                        'description': description or '',
                        'hashtags': hashtags or '',
                    },
                })

                # Remove the pre-upload recovery draft now that the real
                # sermon record is saved
                if recovery_draft_id:
                    try:
                        repo.delete_sermon(recovery_draft_id)
                    except Exception as cleanup_err:
                        logger.warning(
                            "Could not remove pre-upload draft %s: %s",
                            recovery_draft_id, cleanup_err,
                        )

                console_print("Sermon saved to local database")
            except Exception as e:
                logger.warning(f"Failed to save sermon to local database: {e}")

            console_print(f"Sermon files saved to: {output_dir}")

            if auto_edit_state:
                _persist_auto_edit_applied_plan(sermon_id)
                edit_original = Path(auto_edit_state['source_path'])
                edit_keeper = audio_path if keeper_used else edit_original
                try:
                    record = trash_original_after_edit(
                        edit_original, edit_keeper, config, True,
                        sermon_id=sermon_id, stage="post_publish",
                    )
                    if record is not None:
                        console_print(
                            f"Moved original to trash after applied edit: "
                            f"{record.destination}"
                        )
                except Exception as e:
                    logger.warning("Original removal after auto edit failed: %s", e)

            _report(100, f"Done - sermon {sermon_id} created and uploaded")
            result['success'] = True
            return result
        else:
            logger.error("Failed to upload audio")
            result['error'] = "Sermon created but audio upload failed"
            # Save to local DB so user can retry upload from Library
            try:
                from ui.database import SermonRepository
                repo = SermonRepository()
                repo.save_sermon({
                    'id': sermon_id,
                    'title': title or '',
                    'subtitle': subtitle or '',
                    'series_title': series_title or '',
                    'description': description or '',
                    'scripture_reference': bible_text or '',
                    'speaker': speaker_name or '',
                    'recorded_date': recorded_date or '',
                    'event_type': event_type or '',
                    'bible_text': bible_text or '',
                    'status': 'error',
                    'description_needs_review': bool(
                        metadata_notes.get('description_needs_review')
                    ),
                    'upload_info': {
                        'sermonaudio_id': str(sermon_id),
                        'upload_date': dt.datetime.now(),
                        'upload_status': 'failed',
                        'upload_message': 'Sermon created but audio upload failed',
                    },
                    'file_paths': {
                        'audio': str(final_upload_path),
                    },
                    'content': {
                        'transcript_text': transcript or '',
                        'description': description or '',
                        'hashtags': hashtags or '',
                    },
                })
            except Exception as e:
                logger.warning(f"Failed to save failed-upload sermon to DB: {e}")
            if auto_edit_state:
                _persist_auto_edit_applied_plan(sermon_id, upload_failed=True)
            return result

    except (ProcessingCancelledError, ProcessCancelled):
        logger.info("Sermon processing cancelled by user request")
        result['error'] = "Processing cancelled"
        result['cancelled'] = True
        return result

    except Exception as e:
        logger.error("Error processing new sermon: %s", e)
        result['error'] = str(e)
        return result
    finally:
        # Clean up temporary files
        if temp_dir is not None and temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass  # Ignore cleanup errors


def publish_dry_run_sermon(dry_run_id: str, publish: bool = True) -> dict[str, Any]:
    """Publish a locally-saved dry run sermon to SermonAudio.

    Creates a new sermon via the SermonAudio API using the dry run's stored
    metadata, uploads the audio, and migrates the local database entry from
    the dry-run ID to the real SermonAudio ID.

    Args:
        dry_run_id: The local dry run sermon ID (e.g. ``draft_<speaker>_<date>_<title>``).

    Returns:
        Dict with keys: ``success``, ``sermon_id`` (new), ``error``.
    """
    result: dict[str, Any] = {'success': False, 'sermon_id': None, 'error': None}

    try:
        from ui.database import SermonRepository
        repo = SermonRepository()
        sermon_data = repo.get_sermon(dry_run_id)

        if not sermon_data:
            result['error'] = f"Dry run sermon {dry_run_id} not found in database"
            return result

        title = sermon_data.get('title', '') or ''
        speaker_name = sermon_data.get('speaker', '') or ''
        recorded_date = sermon_data.get('recorded_date', '') or ''
        event_type = sermon_data.get('event_type', 'Sunday Service') or 'Sunday Service'
        try:
            validate_event_type_for_api(event_type)
        except ValueError as e:
            result['error'] = str(e)
            return result
        bible_text = sermon_data.get('bible_text') or sermon_data.get('scripture_reference') or ''
        subtitle = sermon_data.get('subtitle', '') or ''
        series_title = sermon_data.get('series_title', '') or ''
        series_id = resolve_series_id(series_title, create_missing=True) if series_title else None

        content = sermon_data.get('content', {}) or {}
        description = content.get('description', '') or sermon_data.get('description', '') or ''
        hashtags = content.get('hashtags', '') or ''
        transcript = content.get('transcript_text', '') or ''

        file_paths = sermon_data.get('file_paths', {}) or {}
        audio_path_str = file_paths.get('audio', '') or ''
        if not audio_path_str or not Path(audio_path_str).exists():
            # Fall back to looking in processed_sermons/{speaker}/{series}/{title}/ directory
            output_root = Path(config.get('output_directory', 'processed_sermons'))
            if not output_root.is_absolute():
                output_root = Path(__file__).parent / output_root
            fallback_dir = find_sermon_dir(output_root, dry_run_id)
            if fallback_dir:
                for f in fallback_dir.iterdir():
                    if f.suffix.lower() in (
                        '.mp3', '.wav', '.mp4', '.m4a', '.ogg', '.flac', '.mov', '.mkv', '.webm'
                    ):
                        audio_path_str = str(f)
                        break
        if not audio_path_str or not Path(audio_path_str).exists():
            result['error'] = f"Audio file not found: {audio_path_str}"
            return result

        console_print(f"Publishing dry run sermon: {title}")
        console_print(f"   Speaker: {speaker_name}, Date: {recorded_date}")

        speaker_id = resolve_speaker_id(speaker_name)
        if speaker_id:
            console_print(f"Resolved speaker '{speaker_name}' to ID {speaker_id}")

        # If a previous publish attempt already created the remote sermon
        # (e.g. it died mid-upload), reuse that ID instead of creating a
        # duplicate.
        existing_publication_id = (sermon_data.get('upload_info') or {}).get(
            'sermonaudio_id'
        )
        if existing_publication_id:
            new_sermon_id = str(existing_publication_id)
            console_print(
                f"Draft was already created on SermonAudio as {new_sermon_id}; "
                "skipping creation"
            )
        else:
            console_print("Creating sermon on SermonAudio...")
            new_sermon_id = create_new_sermon_api(
                title=title,
                speaker_name=speaker_name,
                recorded_date=recorded_date,
                event_type=event_type,
                bible_text=bible_text or None,
                subtitle=subtitle or None,
                description=description or None,
                hashtags=hashtags or None,
                speaker_id=speaker_id,
            )

            if not new_sermon_id:
                result['error'] = "Failed to create sermon on SermonAudio API"
                return result

            # Record immediately so a retried publish cannot create a duplicate
            _record_publication_id(repo, dry_run_id, str(new_sermon_id))

            console_print(f"Sermon created with ID: {new_sermon_id}")

        # The API ignores seriesTitle during creation, so PATCH it after
        if series_id is not None:
            set_sermon_series(new_sermon_id, series_id)

        # Determine upload type from metadata.json (stored during dry run)
        upload_type = "original-audio"
        upload_path = Path(audio_path_str)
        metadata_path_str = file_paths.get('metadata', '')
        if metadata_path_str and Path(metadata_path_str).exists():
            import json as _json
            try:
                with open(metadata_path_str) as _f:
                    meta = _json.load(_f)
                if meta.get('is_video') and meta.get('upload_type') == 'original-video':
                    upload_type = "original-video"
                    processed = meta.get('processed_file')
                    if processed and Path(processed).exists():
                        upload_path = Path(processed)
                elif meta.get('upload_type') == 'original-video':
                    upload_type = "original-video"
                    original = meta.get('original_file')
                    if original and Path(original).exists():
                        upload_path = Path(original)
                    else:
                        processed = meta.get('processed_file')
                        if processed and Path(processed).exists():
                            upload_path = Path(processed)
                elif is_video_file(audio_path_str):
                    upload_type = "original-video"
            except Exception:
                pass

        media_label = "video" if upload_type == "original-video" else "audio"
        console_print(f"Uploading {media_label}...")
        upload_success = upload_media_file(new_sermon_id, str(upload_path), upload_type)

        if upload_success:
            console_print(f"{media_label.capitalize()} uploaded successfully")
            if publish and set_sermon_published(new_sermon_id, True):
                console_print("Published on SermonAudio")
        else:
            console_print(f"Sermon created but {media_label} upload failed")

        # Update local database: save with real ID, delete old dry run entry
        # in a single transaction so a failure cannot leave duplicates or neither
        duration = sermon_data.get('duration', 0)
        new_file_paths = {
            'audio': str(upload_path),
            'metadata': str(file_paths.get('metadata', '')),
        }
        try:
            with repo.db.get_connection() as conn:
                sermons_cols = [
                    row[1] for row in conn.execute("PRAGMA table_info(sermons)")
                ]
                col_values: dict[str, Any] = {
                    'id': new_sermon_id,
                    'title': title,
                    'subtitle': subtitle,
                    'speaker': speaker_name,
                    'recorded_date': recorded_date,
                    'event_type': event_type,
                    'bible_text': bible_text,
                    'series_title': series_title,
                    'scripture_reference': bible_text,
                    'description': description,
                    'duration': duration,
                    'status': 'processed' if upload_success else 'error',
                    'edit_status': 'uploaded' if upload_success else 'failed',
                    'updated_at': dt.datetime.now(),
                }
                original_created_at = sermon_data.get('created_at')
                if original_created_at and 'created_at' in sermons_cols:
                    col_values['created_at'] = original_created_at
                columns = [c for c in col_values if c in sermons_cols]
                placeholders = ", ".join("?" for _ in columns)
                conn.execute(
                    f"INSERT OR REPLACE INTO sermons ({', '.join(columns)}) "
                    f"VALUES ({placeholders})",
                    [col_values[c] for c in columns],
                )
                for file_type, file_path in new_file_paths.items():
                    if not file_path:
                        continue
                    file_size = 0
                    try:
                        p = Path(file_path)
                        if p.exists():
                            file_size = p.stat().st_size
                    except (TypeError, OSError, ValueError):
                        file_size = 0
                    conn.execute("""
                        INSERT OR REPLACE INTO sermon_files
                        (sermon_id, file_type, file_path, file_size)
                        VALUES (?, ?, ?, ?)
                    """, (new_sermon_id, file_type, file_path, file_size))
                conn.execute("""
                    INSERT OR REPLACE INTO sermon_content
                    (sermon_id, transcript_text, description, hashtags, key_topics, summary)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    new_sermon_id, transcript or '', description or '', hashtags or '',
                    '[]', None
                ))
                try:
                    upload_cols = [
                        row[1] for row in conn.execute("PRAGMA table_info(upload_info)")
                    ]
                    if 'sermonaudio_id' in upload_cols and 'upload_status' in upload_cols:
                        conn.execute("""
                            INSERT OR REPLACE INTO upload_info
                            (sermon_id, sermonaudio_id, upload_date, upload_status,
                             upload_message)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            new_sermon_id, str(new_sermon_id), dt.datetime.now(),
                            'completed' if upload_success else 'failed',
                            'Media uploaded successfully' if upload_success
                            else 'Sermon created but media upload failed',
                        ))
                except Exception as upload_err:
                    logger.debug(
                        "Could not record upload_info for %s: %s",
                        new_sermon_id, upload_err,
                    )
                # Rebuild the FTS row across every column the table actually
                # has, carrying over indexed topics/summary from the draft row
                fts_cols = [
                    row[1] for row in conn.execute("PRAGMA table_info(sermon_search)")
                ]
                conn.execute(
                    "DELETE FROM sermon_search WHERE sermon_id = ?", (new_sermon_id,)
                )
                if fts_cols:
                    fts_cursor = conn.execute(
                        "SELECT * FROM sermon_search WHERE sermon_id = ?", (dry_run_id,)
                    )
                    old_fts = fts_cursor.fetchone()
                    carried: dict[str, Any] = {}
                    if old_fts is not None:
                        carried = dict(zip(
                            [d[0] for d in fts_cursor.description], old_fts,
                            strict=False,
                        ))
                    carried.update({
                        'title': title,
                        'speaker': speaker_name,
                        'transcript_text': transcript or '',
                        'description': description or '',
                        'hashtags': hashtags or '',
                    })
                    insert_cols = [c for c in fts_cols if c != 'sermon_id']
                    conn.execute(
                        f"INSERT INTO sermon_search "
                        f"(sermon_id, {', '.join(insert_cols)}) "
                        f"VALUES (?, {', '.join('?' for _ in insert_cols)})",
                        [new_sermon_id] + [carried.get(c) for c in insert_cols],
                    )
                conn.execute("DELETE FROM sermon_search WHERE sermon_id = ?", (dry_run_id,))
                try:
                    max_plan_revision = conn.execute(
                        "SELECT MAX(revision) FROM edit_plans WHERE sermon_id = ?",
                        (new_sermon_id,),
                    ).fetchone()[0] or 0
                    for plan in conn.execute(
                        "SELECT * FROM edit_plans WHERE sermon_id = ? ORDER BY revision",
                        (dry_run_id,),
                    ).fetchall():
                        plan_dict = dict(plan)
                        max_plan_revision += 1
                        plan_columns = [
                            column for column in plan_dict
                            if column not in ('id', 'sermon_id', 'revision')
                        ]
                        plan_placeholders = ", ".join("?" for _ in plan_columns)
                        conn.execute(
                            f"INSERT INTO edit_plans "
                            f"(sermon_id, revision, {', '.join(plan_columns)}) "
                            f"VALUES (?, ?, {plan_placeholders})",
                            [new_sermon_id, max_plan_revision]
                            + [plan_dict[c] for c in plan_columns],
                        )
                except Exception as plan_err:
                    logger.debug("Edit plan carry-over skipped: %s", plan_err)
                for table in (
                    'sermon_content', 'processing_info', 'sermon_files',
                    'upload_info', 'processing_status', 'validation_results',
                    'manual_review', 'llm_api_usage', 'edit_plans',
                ):
                    try:
                        conn.execute(
                            f"DELETE FROM {table} WHERE sermon_id = ?", (dry_run_id,)
                        )
                    except Exception as table_err:
                        logger.debug("Cleanup skipped for %s: %s", table, table_err)
                conn.execute("DELETE FROM sermons WHERE id = ?", (dry_run_id,))
                conn.commit()
        except Exception as e:
            logger.exception(f"Failed to migrate dry run sermon {dry_run_id} to {new_sermon_id}")
            result['error'] = str(e)
            return result

        # Move output directory from old ID to new ID
        output_root = Path(config.get('output_directory', 'processed_sermons'))
        if not output_root.is_absolute():
            output_root = Path(__file__).parent / output_root
        old_output_dir = find_sermon_dir(output_root, dry_run_id)
        if old_output_dir and old_output_dir.exists():
            new_output_dir = get_sermon_dir(
                output_root, speaker_name, series_title, title, new_sermon_id
            )
            if old_output_dir != new_output_dir:
                import shutil

                shutil.copytree(str(old_output_dir), str(new_output_dir), dirs_exist_ok=True)
                try:
                    from src.safe_delete import trash_local
                except ImportError:
                    from safe_delete import trash_local

                trash_local(
                    str(old_output_dir),
                    reason="dry_run_publish_superseded",
                    sermon_id=new_sermon_id,
                    stage="publish_dry_run",
                )

        if upload_success:
            console_print(f"Dry run sermon published as: {new_sermon_id}")
        else:
            console_print(f"Sermon created ({new_sermon_id}) but media upload failed")
        result['success'] = upload_success
        result['sermon_id'] = new_sermon_id
        return result

    except Exception as e:
        logger.exception(f"Failed to publish dry run sermon {dry_run_id}")
        result['error'] = str(e)
        return_result = result
        return return_result


def reupload_media_for_sermon(sermon_id: str, file_path: str) -> bool:
    """Re-upload media to an existing sermon on SermonAudio.

    Args:
        sermon_id: The existing sermon ID on SermonAudio
        file_path: Path to the media file to upload

    Returns:
        True if upload succeeded, False otherwise
    """
    upload_type = "original-video" if is_video_file(file_path) else "original-audio"
    return upload_media_file(sermon_id, file_path, upload_type)


def download_file(url: str, local_path: str):
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def _clean_llm_thinking_response(response: str) -> str:
    """Return only the description text from a raw model response.

    ``extract_final_answer`` keeps the last draft-style block, then the pure
    cleanup keeps the first real paragraph and cuts trailing self-narration
    such as character counts.
    """
    if not response:
        return response

    from src.llm_manager import extract_final_answer

    extracted = extract_final_answer(response) or response
    cleaned = clean_description(extracted)
    if cleaned and cleaned != response.strip():
        logger.debug(
            "Cleaned model description output (%d -> %d chars)",
            len(response), len(cleaned),
        )
    return cleaned


_DESCRIPTION_RETRY_INSTRUCTION = (
    "That reply was not usable as a description. Rewrite it and reply with ONLY "
    "the description: one paragraph of plain prose. Do not include reasoning, "
    "character or word counting, headings, labels, quotes, or any notes about "
    "the text or its length."
)

_DESCRIPTION_MAX_ATTEMPTS = 2


class DescriptionGenerationError(RuntimeError):
    """Raised when no usable description could be generated.

    Distinct from ``LLMTimeoutError`` and the model-availability errors: the
    provider chain answered (or exhausted itself) without producing usable
    prose. Callers must treat this as "no description": never persist the
    reason as content, leave the stored field untouched, and mark the record
    for review. The provider identity and elapsed wall-clock ride along so the
    operator can act on the real cause.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        elapsed_seconds: float | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.elapsed_seconds = elapsed_seconds
        self.attempts = attempts


def _description_provider_label() -> str:
    try:
        return _llm_target_label()
    except Exception:
        return "unknown model"


def _description_chat_with_retry(
    messages: list[dict[str, str]],
    *,
    prompt_chars: int,
) -> str:
    """Run one description chat, retrying once on a transient failure.

    ``llm_manager.chat`` already walks the configured primary then fallback
    chain inside a single call. This adds one retry for a transient error that
    chain did not absorb, logs the provider and elapsed time per attempt, and
    converts a terminal failure into a typed ``DescriptionGenerationError``
    instead of a string the caller might store.
    """
    provider = _description_provider_label()
    last_error: Exception | None = None
    started = time.time()
    for attempt in range(1, _DESCRIPTION_MAX_ATTEMPTS + 1):
        attempt_started = time.time()
        try:
            response = llm_manager.chat(messages, operation="description_generation")
        except (LLMModelNotFoundError, LLMModelNotConfiguredError):
            raise
        except Exception as exc:
            last_error = exc
            elapsed = time.time() - attempt_started
            if attempt < _DESCRIPTION_MAX_ATTEMPTS:
                logger.warning(
                    "Description generation attempt %d/%d failed after %.1fs "
                    "(provider=%s, prompt=%d chars): %s; retrying once",
                    attempt,
                    _DESCRIPTION_MAX_ATTEMPTS,
                    elapsed,
                    provider,
                    prompt_chars,
                    exc,
                )
            else:
                logger.error(
                    "Description generation failed after %d attempts "
                    "(%.1fs total, provider=%s, prompt=%d chars, "
                    "timeout=%.0fs/attempt): %s",
                    attempt,
                    time.time() - started,
                    provider,
                    prompt_chars,
                    float(getattr(llm_manager, "call_timeout_seconds", 0.0) or 0.0),
                    exc,
                )
            continue
        logger.debug(
            "Description generation attempt %d/%d returned %d chars in %.1fs "
            "(provider=%s)",
            attempt,
            _DESCRIPTION_MAX_ATTEMPTS,
            len(response or ""),
            time.time() - attempt_started,
            provider,
        )
        return response

    raise DescriptionGenerationError(
        f"description generation failed: {last_error}",
        provider=provider,
        elapsed_seconds=time.time() - started,
        attempts=_DESCRIPTION_MAX_ATTEMPTS,
    ) from last_error


def generate_summary(
    transcript: str,
    event_type: str | None = None,
    speaker_name: str | None = None,
    notes: dict | None = None,
) -> str:
    def is_class_event(et):
        class_types = [
            'Sunday School', 'Midweek Service', 'Bible Study', 'Teaching', 'Class',
            'Devotional', 'Conference', 'Camp Meeting', 'Children', 'Youth', 'Question & Answer'
        ]
        et_str = str(et or '')
        return any(c.lower() in et_str.lower() for c in class_types)

    if is_class_event(event_type):
        role_desc = 'Bible class summarization assistant'
        body_desc = 'Sunday School, Midweek, or class/lecture event'
    else:
        role_desc = 'sermon summarization assistant'
        body_desc = 'sermon'

    # Build speaker instruction
    speaker_instruction = (
        f"- The speaker is Pastor {speaker_name}. You MUST begin the description with "
        f"'Pastor {speaker_name} teaches on...' or 'Pastor {speaker_name} taught from...'.\n"
        if speaker_name
        else "- Identify the primary speaker from the transcript and refer to them as "
        "'Pastor [Name]'. You MUST begin the description with 'Pastor [Name] teaches on...'.\n"
    )

    # Long transcripts exceed LLM context windows: map-reduce via per-chunk
    # summaries so the final prompt carries a faithful condensation.
    working_text = transcript
    if len(transcript) > 24000:
        try:
            chunks = []
            start = 0
            while start < len(transcript):
                end = min(start + 12000, len(transcript))
                if end < len(transcript):
                    boundary = transcript.find('\n\n', end)
                    if boundary != -1 and boundary < end + 2000:
                        end = boundary
                chunks.append(transcript[start:end])
                start = end
            chunk_summaries = []
            for i, chunk in enumerate(chunks):
                logger.info("Summarizing chunk %d/%d (%d chars)",
                            i + 1, len(chunks), len(chunk))
                chunk_summaries.append(llm_manager.chat([{
                    'role': 'user',
                    'content': (
                        f"Summarize this section ({i + 1}/{len(chunks)}) of a "
                        f"{body_desc} transcript in 3-4 sentences, covering the "
                        f"main points, scripture, and application:\n\n{chunk}"
                    ),
                }]).strip())
            working_text = "\n\n".join(chunk_summaries)
            logger.info("Chunked summarization: %d chunks -> %d chars",
                        len(chunks), len(working_text))
        except Exception as e:
            logger.warning("Chunked summarization failed (%s); using full transcript", e)
            working_text = transcript

    tmpl = _get_prompt_template("description",
                                role_desc=role_desc, body_desc=body_desc,
                                transcript=working_text,
                                speaker_instruction=speaker_instruction)
    if tmpl:
        system_prompt, user_prompt = tmpl
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
    else:
        prompt = (
            f"You are a {role_desc}. Read the following {body_desc} transcript and write a single, "
            f"concise description of the main message and application. Focus on what "
            f"the speaker wanted the audience to understand, believe, or do. "
            f"Avoid generic statements; "
            f"emphasize unique focus.\n\nTranscript:\n{working_text}\n\nGuidelines:\n"
            f"- One paragraph of plain prose: cover the main message, the key scripture, "
            f"and the practical application\n"
            f"- Four to six sentences is usually enough; keep it under 1400 characters "
            f"so the upload is accepted\n"
            + speaker_instruction +
            "- No intro or closing words\n- No markdown or bullets\n"
            "- Do not prefix with 'Summary:' or any other label\n"
            "- If the transcript is incomplete, infer the likely main message\n"
            "- Use the actual speaker name, not placeholder text\n"
            "- Include specific scripture references, source material, and concrete "
            "examples from the transcript\n"
            "- Mention the specific doctrines, rules, or texts the speaker expounded\n"
            "- Describe the practical application the speaker gave\n"
            "- Reply with the description ONLY: no reasoning, no commentary, no "
            "character or word counting, no headings, no quotes, and no notes about "
            "the text or its length\n"
            "- Start directly with the description."
        )
        messages = [{'role': 'user', 'content': prompt}]
    prompt_chars = sum(len(m.get('content') or '') for m in messages)
    started = time.time()
    provider = _description_provider_label()
    try:
        logger.debug(
            "Generating summary using %s (prompt=%d chars, timeout=%.0fs)...",
            provider,
            prompt_chars,
            float(getattr(llm_manager, "call_timeout_seconds", 0.0) or 0.0),
        )
        response = _description_chat_with_retry(messages, prompt_chars=prompt_chars)

        response, description_needs_review = clean_description_with_retry(
            _clean_llm_thinking_response(response),
            regenerate=lambda: _clean_llm_thinking_response(
                _description_chat_with_retry(
                    [*messages, {'role': 'user', 'content': _DESCRIPTION_RETRY_INSTRUCTION}],
                    prompt_chars=prompt_chars,
                )
            ),
        )
        if notes is not None:
            notes['description_needs_review'] = description_needs_review
        if description_needs_review:
            logger.warning(
                "Description flagged needs_review after cleanup and one retry (%d chars)",
                len(response or ""),
            )

        if not (response or "").strip():
            raise DescriptionGenerationError(
                "description generation produced no usable text after cleanup",
                provider=provider,
                elapsed_seconds=time.time() - started,
                attempts=_DESCRIPTION_MAX_ATTEMPTS,
            )

        # Ensure the response doesn't exceed SermonAudio's character limit
        max_chars = 1600  # Conservative limit (API limit is 1700)
        if len(response) > max_chars:
            logger.warning("Generated summary too long (%d chars), trimming to %d",
                          len(response), max_chars)
            from src.llm_manager import trim_to_sentence

            response = trim_to_sentence(response, max_chars)

        logger.info(
            "Description generated (provider=%s, chars=%d, elapsed=%.1fs)",
            provider,
            len(response),
            time.time() - started,
        )
        return response
    except (LLMTimeoutError, LLMModelNotFoundError, LLMModelNotConfiguredError):
        raise
    except DescriptionGenerationError:
        raise
    except Exception as e:  # pragma: no cover
        logger.error(
            "Description generation failed after %.1fs (provider=%s, prompt=%d chars): %s",
            time.time() - started,
            provider,
            prompt_chars,
            e,
        )
        raise DescriptionGenerationError(
            f"description generation failed: {e}",
            provider=provider,
            elapsed_seconds=time.time() - started,
            attempts=_DESCRIPTION_MAX_ATTEMPTS,
        ) from e


def verify_hashtags(initial_hashtags: str, original_text: str) -> str:
    """
    Verify and clean hashtags through a second LLM pass.
    This ensures the output strictly follows hashtag format and removes any comments.
    """
    tmpl = _get_prompt_template("hashtag_verification",
                                initial_hashtags=initial_hashtags,
                                original_text=original_text[:200])
    if tmpl:
        system_prompt, user_prompt = tmpl
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
    else:
        verification_prompt = (
            "You are a hashtag validator. Your job is to extract ONLY valid hashtags "
            "from the input below. "
            "Rules:\n"
            "1. Output ONLY hashtags (words starting with #)\n"
            "2. Remove any comments, explanations, or non-hashtag text\n"
            "3. Keep hashtags space-separated\n"
            "4. Maximum 150 characters total\n"
            "5. If you see obvious formatting issues, fix them\n"
            "6. If no valid hashtags found, generate 3-5 relevant ones for the sermon topic\n\n"
            f"Original sermon topic context: {original_text[:200]}...\n\n"
            f"Hashtag input to verify:\n{initial_hashtags}\n\n"
            "Valid hashtags only:"
        )
        messages = [{'role': 'user', 'content': verification_prompt}]

    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Verifying hashtags using %s LLM...", primary_provider)
        response = llm_manager.chat(messages)

        # Extract only hashtags from the response
        verified_hashtags = clean_hashtags(response)

        if verified_hashtags:
            logger.debug("Verified hashtags: %s", verified_hashtags)
            return verified_hashtags
        else:
            logger.warning("No valid hashtags found in verification, using fallback")
            return "#faith #hope #worship #christian #jesus"

    except (LLMTimeoutError, LLMModelNotFoundError, LLMModelNotConfiguredError):
        raise
    except Exception as e:
        logger.error("Hashtag verification failed: %s", e)
        # Return cleaned version of original hashtags as fallback
        fallback_hashtags = clean_hashtags(initial_hashtags)
        if fallback_hashtags:
            return fallback_hashtags
        else:
            return "#faith #hope #worship #christian #jesus"


def generate_hashtags(text: str) -> str:
    tmpl = _get_prompt_template("hashtags", text=text)
    if tmpl:
        system_prompt, user_prompt = tmpl
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
    else:
        prompt = (
            "Generate 5-10 highly relevant, search-friendly hashtags (<=150 chars total) for this "
            "sermon. Combine multi-word phrases (#ChristianLiving). Avoid duplicates & generic "
            "(#sermon #church) unless uniquely relevant. Output ONLY space-delimited hashtags.\n\n"
            f"Text:\n{text}\n\nHashtags:"
        )
        messages = [{'role': 'user', 'content': prompt}]
    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating hashtags using %s LLM...", primary_provider)

        response = llm_manager.chat(messages)
        logger.debug("Initial hashtag response: %s", response)

        # Second pass: Verify and clean hashtags (if enabled in config)
        if config.get('hashtag_verification', True):
            verified_hashtags = verify_hashtags(response, text)
            logger.debug("Final verified hashtags: %s", verified_hashtags)
            return verified_hashtags
        else:
            hashtags = clean_hashtags(response)
            logger.debug("Generated hashtags (no verification): %s", hashtags)
            return hashtags

    except (LLMTimeoutError, LLMModelNotFoundError, LLMModelNotConfiguredError):
        raise
    except Exception as e:  # pragma: no cover
        logger.error("LLM hashtag generation failed: %s", e)
        return "#faith #hope #worship #christian #jesus"


def generate_validated_summary(
    transcript: str,
    event_type: str | None = None,
    speaker_name: str | None = None,
) -> tuple[str, dict]:
    """
    Generate a sermon summary with validation through smaller model.

    Returns:
        Tuple of (final_summary, validation_info)
        validation_info contains details about the validation process
    """
    validation_info = {
        'primary_attempts': 0,
        'fallback_used': False,
        'validation_attempts': [],
        'final_status': 'pending',
        'needs_review': False,
        'description_needs_review': False,
    }

    # Check if validation is enabled
    metadata_config = config.get('metadata_processing', {})
    desc_config = metadata_config.get('description', {})
    validation_config = desc_config.get('validation', {})
    validation_enabled = validation_config.get('enabled', False)
    validation_criteria = validation_config.get('criteria', [])

    if not validation_enabled:
        # If validation is disabled, use the original generation method
        gen_notes: dict = {}
        summary = generate_summary(transcript, event_type, speaker_name, notes=gen_notes)
        validation_info['description_needs_review'] = bool(
            gen_notes.get('description_needs_review')
        )
        validation_info['final_status'] = 'no_validation'
        return summary, validation_info

    def _fallback_provider():
        providers = getattr(llm_manager, 'fallback_providers', None) or []
        return providers[0] if providers else None

    def try_generate_summary(use_fallback=False):
        """Helper function to generate summary with specific provider."""
        notes: dict = {}
        if use_fallback and _fallback_provider():
            # Temporarily swap providers for fallback generation
            original_primary = llm_manager.primary_provider
            llm_manager.primary_provider = _fallback_provider()
            try:
                summary = generate_summary(transcript, event_type, speaker_name, notes=notes)
                return summary, notes
            finally:
                llm_manager.primary_provider = original_primary
        else:
            return generate_summary(transcript, event_type, speaker_name, notes=notes), notes

    # Try primary model first
    validation_info['primary_attempts'] = 1
    primary_summary, primary_notes = try_generate_summary(use_fallback=False)

    # Validate the primary summary
    is_valid, reason = llm_manager.validate_description(primary_summary, validation_criteria)
    validation_info['validation_attempts'].append({
        'provider': 'primary',
        'valid': is_valid,
        'reason': reason,
        'summary_length': len(primary_summary)
    })

    if is_valid:
        validation_info['description_needs_review'] = bool(
            primary_notes.get('description_needs_review')
        )
        validation_info['final_status'] = 'approved_primary'
        return primary_summary, validation_info

    # If primary failed validation, try fallback
    if _fallback_provider():
        logger.debug("Primary summary failed validation, trying fallback model...")
        validation_info['fallback_used'] = True
        fallback_summary, fallback_notes = try_generate_summary(use_fallback=True)

        # Validate the fallback summary
        is_valid, reason = llm_manager.validate_description(fallback_summary, validation_criteria)
        validation_info['validation_attempts'].append({
            'provider': 'fallback',
            'valid': is_valid,
            'reason': reason,
            'summary_length': len(fallback_summary)
        })

        if is_valid:
            validation_info['description_needs_review'] = bool(
                fallback_notes.get('description_needs_review')
            )
            validation_info['final_status'] = 'approved_fallback'
            return fallback_summary, validation_info

    # If both failed validation, mark for manual review
    validation_info['description_needs_review'] = bool(
        primary_notes.get('description_needs_review')
    )
    validation_info['final_status'] = 'needs_review'
    validation_info['needs_review'] = True

    # Return the primary summary but mark it as needing review
    logger.warning("Both primary and fallback summaries failed validation - needs manual review")
    return primary_summary, validation_info


def process_single_sermon(sermon_id: str, no_upload: bool = False, verbose: bool = False,
                         skip_audio: bool = False, force_description: bool = False,
                         force_hashtags: bool = False, no_metadata: bool = False,
                         output_dir: str = None, save_original_audio: bool = None,
                         save_transcript: bool = None,
                         transcription_backend: str = None,
                         audio_file: str = None,
                         series_id: int | None = None,
                         config: dict | None = None):
    if not config:
        refresh_runtime_config()
        config = globals()['config']
    logger.debug(f"Processing sermon_id={sermon_id}")
    details = Node.get_sermon(sermon_id)
    speaker_name = None
    if hasattr(details, 'speaker') and details.speaker:
        speaker_name = (
            getattr(details.speaker, 'full_name', None)
            or getattr(details.speaker, 'display_name', None)
            or getattr(details.speaker, 'displayName', None)
            or str(details.speaker)
        )
    sermon_name = (
        getattr(details, 'display_title', None)
        or getattr(details, 'displayTitle', '<No Title>')
    )
    event_type = getattr(details, 'event_type', None) or getattr(details, 'eventType', None)
    logger.info("Processing: %s (%s) event=%s", sermon_name, sermon_id, event_type)

    # Determine what processing is needed
    needs_desc_update, needs_hash_update = needs_metadata_processing(
        details, config, force_description, force_hashtags
    )
    needs_audio = needs_audio_processing(config, skip_audio)

    # Override metadata processing if disabled
    if no_metadata:
        needs_desc_update = False
        needs_hash_update = False

    # Skip entirely if nothing to do
    if not (needs_desc_update or needs_hash_update or needs_audio) and series_id is None:
        logger.info("No processing needed for sermon %s - skipping", sermon_id)
        return {"action": "skipped", "reason": "No updates needed - adequate content exists"}

    # Show what will be processed
    processing_actions = []
    if needs_desc_update:
        processing_actions.append("description")
    if needs_hash_update:
        processing_actions.append("hashtags")
    if needs_audio:
        processing_actions.append("audio")

    if processing_actions:
        logger.info("Will process: %s", ", ".join(processing_actions))

    # Determine output directory from parameter, config, or default
    if output_dir:
        output_root = output_dir
    else:
        output_root = config.get('output_directory', 'processed_sermons')

    # Make path absolute if it's relative
    if not os.path.isabs(output_root):
        base_dir = os.path.abspath(os.path.dirname(__file__))
        processed_root = os.path.join(base_dir, output_root)
    else:
        processed_root = output_root

    os.makedirs(processed_root, exist_ok=True)
    sermon_dir = get_sermon_dir(processed_root, speaker_name, None, sermon_name, sermon_id)
    os.makedirs(sermon_dir, exist_ok=True)

    # Initialize variables for metadata processing
    summary = None
    hashtags = None
    transcript = None
    validation_info = None
    description_needs_review = False
    description_error: str | None = None

    # Determine if we need transcript for metadata or saving
    needs_transcript = needs_desc_update or needs_hash_update
    if not needs_transcript:
        # Check if we need transcript for saving
        should_save_transcript = save_transcript
        if should_save_transcript is None:
            should_save_transcript = config.get('save_transcript', False)
        needs_transcript = should_save_transcript

    # Get transcript if needed
    if needs_transcript:
        if not verbose:
            print("   Retrieving transcript...")
        if audio_file and transcription_backend:
            from src.transcription import transcribe
            transcript = transcribe(audio_file, model_size="base", config=config,
                                    backend_override=transcription_backend)
        else:
            transcript = get_sermon_transcript(sermon_id)
        if not transcript:
            logger.warning("No transcript available for sermon %s", sermon_id)
        else:
            # Process metadata if needed and transcript is available
            if needs_desc_update:
                if not verbose:
                    print("   Generating description...")
                try:
                    summary, validation_info = generate_validated_summary(
                        transcript, event_type=event_type, speaker_name=speaker_name
                    )
                    description_needs_review = bool(
                        validation_info.get('description_needs_review')
                    )
                    logger.debug("Generated description (%d chars), validation: %s",
                               len(summary), validation_info['final_status'])
                except DescriptionGenerationError as e:
                    summary = None
                    description_needs_review = True
                    description_error = str(e)
                    validation_info = {
                        'final_status': 'generation_failed',
                        'needs_review': True,
                        'description_needs_review': True,
                    }
                    logger.warning(
                        "Description generation failed (provider=%s, elapsed=%s, "
                        "attempts=%s); leaving the stored description unchanged "
                        "and marking it for review: %s",
                        getattr(e, 'provider', None),
                        getattr(e, 'elapsed_seconds', None),
                        getattr(e, 'attempts', None),
                        e,
                    )

            if needs_hash_update:
                if not verbose:
                    print("   Generating hashtags...")
                hashtags = generate_hashtags(transcript)
                logger.debug("Generated hashtags: %s", hashtags)

    # Audio processing (if needed)
    output_audio = None
    if needs_audio:
        if not verbose:
            print("   Downloading audio...")
        input_audio = os.path.join(sermon_dir, FILENAMES["temp"])
        output_audio = os.path.join(sermon_dir, FILENAMES["enhanced"])

        # Gather potential audio URLs
        audio_url = None
        candidates: list[str] = []
        if hasattr(details, 'media') and details.media and hasattr(details.media, 'audio'):
            for audio_obj in details.media.audio:
                for key in ('downloadURL', 'download_url', 'streamURL', 'url'):
                    if hasattr(audio_obj, key) and getattr(audio_obj, key):
                        candidates.append(getattr(audio_obj, key))
        if hasattr(details, 'audio_url') and details.audio_url:
            candidates.append(details.audio_url)
        for c in candidates:
            logger.debug("Trying audio URL: %s", c)
            try:
                download_file(c, input_audio)
                audio_url = c
                logger.debug("Audio download succeeded")
                break
            except Exception as e:
                logger.debug("Failed: %s", e)
        if not audio_url:
            logger.warning("No audio available; skipping audio processing for sermon %s",
                          sermon_id)
            needs_audio = False
        else:
            # Determine if we should save original audio
            should_save_original = save_original_audio
            if should_save_original is None:
                should_save_original = config.get('save_original_audio', True)

            # Save original audio if requested
            if should_save_original:
                original_audio_path = os.path.join(sermon_dir, FILENAMES["original"])
                try:
                    import shutil
                    shutil.copy2(input_audio, original_audio_path)
                    logger.debug("Saved original audio to: %s", original_audio_path)
                except Exception as e:
                    logger.warning("Failed to save original audio: %s", e)

            # Process audio
            if not verbose:
                print("   Processing audio...")
            try:
                result = process_sermon_audio(
                    input_audio,
                    output_audio,
                    skip_on_error=True,
                    verbose=verbose,
                    **AUDIO_PARAMS
                )

                # Handle new return format (success, info) vs old format (success only)
                if isinstance(result, tuple):
                    processing_success = result[0]
                else:
                    processing_success = result

                if not processing_success:
                    logger.warning("Audio processing issues; continuing with original audio")

            except Exception as e:
                logger.error("Audio processing failed: %s", e)
                needs_audio = False

    # Save local copies of generated content
    if summary is not None:
        try:
            with open(
                get_file_path(sermon_dir, "description"),
                'w',
                encoding='utf-8',
            ) as fh:
                fh.write(summary)
        except Exception as e:  # pragma: no cover
            logger.error("Failed writing description file: %s", e)

    if hashtags is not None:
        try:
            with open(
                get_file_path(sermon_dir, "hashtags"),
                'w',
                encoding='utf-8',
            ) as fh:
                fh.write(hashtags)
        except Exception as e:  # pragma: no cover
            logger.error("Failed writing hashtags file: %s", e)

    # Save transcript if requested and available
    if transcript is not None:
        # Determine if we should save transcript
        should_save_transcript = save_transcript
        if should_save_transcript is None:
            should_save_transcript = config.get('save_transcript', False)

        if should_save_transcript:
            try:
                with open(
                    get_file_path(sermon_dir, "transcript"),
                    'w',
                    encoding='utf-8',
                ) as fh:
                    fh.write(transcript)
                logger.debug("Saved transcript to: %s",
                           get_file_path(sermon_dir, "transcript"))
            except Exception as e:  # pragma: no cover
                logger.error("Failed writing transcript file: %s", e)

    if DRY_RUN or no_upload:
        logger.info("Dry-run / no-upload: skipping remote updates")
        # Save to database even in dry-run so results are visible in UI
        if database_available and (summary or hashtags or transcript):
            try:
                repo = SermonRepository()
                with repo.db.get_connection() as conn:
                    if summary is not None:
                        conn.execute(
                            "UPDATE sermons SET description = ?, updated_at = ? WHERE id = ?",
                            (summary, dt.datetime.now(), sermon_id)
                        )
                    else:
                        conn.execute(
                            "UPDATE sermons SET updated_at = ? WHERE id = ?",
                            (dt.datetime.now(), sermon_id)
                        )

                    content_updates: dict[str, str] = {}
                    if transcript is not None:
                        content_updates['transcript_text'] = transcript
                    if summary is not None:
                        content_updates['description'] = summary
                    if hashtags is not None:
                        content_updates['hashtags'] = hashtags
                    if content_updates:
                        cols = list(content_updates)
                        placeholders = ", ".join(["?" for _ in cols])
                        set_expr = ", ".join(f"{c} = excluded.{c}" for c in cols)
                        conn.execute(f"""
                            INSERT INTO sermon_content
                            (sermon_id, {', '.join(cols)}, updated_at)
                            VALUES (?, {placeholders}, ?)
                            ON CONFLICT(sermon_id) DO UPDATE SET
                                {set_expr}, updated_at = excluded.updated_at
                        """, [sermon_id, *content_updates.values(), str(dt.datetime.now())])

                    if needs_desc_update:
                        conn.execute(
                            "UPDATE sermons SET description_needs_review = ? WHERE id = ?",
                            (1 if description_needs_review else 0, sermon_id),
                        )

                    merged = conn.execute(
                        "SELECT transcript_text, description, hashtags FROM sermon_content "
                        "WHERE sermon_id = ?",
                        (sermon_id,),
                    ).fetchone()
                    merged = dict(merged) if merged else {}
                    conn.execute("DELETE FROM sermon_search WHERE sermon_id = ?", (sermon_id,))
                    conn.execute("""
                        INSERT INTO sermon_search
                        (sermon_id, title, speaker, transcript_text, description, hashtags)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        sermon_id,
                        sermon_name or '',
                        speaker_name or '',
                        merged.get('transcript_text') or '',
                        merged.get('description') or '',
                        merged.get('hashtags') or '',
                    ))
                    conn.commit()
                logger.debug("Dry-run: saved generated content to database")
            except Exception as e:
                logger.warning(f"Dry-run database save failed: {e}")
        return

    # Update metadata if we generated any
    if summary is not None or hashtags is not None:
        if not verbose:
            print("   Updating metadata...")
        try:
            # Get current values to preserve what we're not updating
            current_desc = (getattr(details, 'moreInfoText', None) or
                           getattr(details, 'more_info_text', None))
            current_hash = getattr(details, 'keywords', None)

            # Use generated values or preserve existing ones
            final_desc = summary if summary is not None else current_desc
            final_hash = hashtags if hashtags is not None else current_hash

            if update_sermon_metadata(sermon_id, final_desc, final_hash):
                logger.debug("Metadata updated successfully")
            else:
                logger.error("Metadata update failed")
        except Exception as e:  # pragma: no cover
            logger.error("Metadata update error: %s", e)

    # Apply the selected series via numeric seriesID
    if series_id is not None:
        if not verbose:
            print("   Setting series...")
        set_sermon_series(sermon_id, series_id)

    # Upload audio if we processed it
    if needs_audio and output_audio and os.path.exists(output_audio):
        if not verbose:
            print("   Uploading audio...")
        try:
            if upload_audio_file(sermon_id, output_audio):
                logger.debug("Audio uploaded successfully")
            else:
                logger.error("Audio upload failed")
        except Exception as e:  # pragma: no cover
            logger.error("Audio upload error: %s", e)

    # If the sermon has video on SermonAudio, download it, mux the enhanced
    # audio into it, and re-upload so audio + video stay in sync.
    if (needs_audio and output_audio and os.path.exists(output_audio)
            and hasattr(details, 'media') and details.media
            and getattr(details.media, 'video', None)):
        if not verbose:
            print("   Updating video with enhanced audio...")
        try:
            import subprocess as mux_proc
            # Pick the highest-bitrate MP4 (h264 "high" preferred; fall back
            # to any video with a stream_url if h264 is missing)
            video_choice = None
            for v in details.media.video:
                if getattr(v, 'video_codec', None) == 'h264' and getattr(v, 'stream_url', None):
                    video_choice = v
                    break
            if video_choice is None:
                for v in details.media.video:
                    if getattr(v, 'stream_url', None):
                        video_choice = v
                        break
            if video_choice is None or not getattr(video_choice, 'stream_url', None):
                logger.info("Video entries have no stream_url; skipping video update")
            else:
                video_hls_url = video_choice.stream_url
                logger.info("Downloading sermon video from HLS: %s", video_hls_url[:120])
                downloaded_video = os.path.join(
                    sermon_dir, FILENAMES.get("temp_video", "video_source.mp4")
                )
                # ffmpeg pulls the MP4 from the HLS playlist
                dl_cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", video_hls_url,
                    "-c", "copy",
                    downloaded_video,
                ]
                mux_proc.run(dl_cmd, check=True, timeout=1800)
                logger.info("Video downloaded to %s (%d MB)",
                            downloaded_video,
                            os.path.getsize(downloaded_video) // (1024 * 1024))

                muxed_video = os.path.join(
                    sermon_dir, FILENAMES.get("enhanced_video", "video_enhanced.mp4")
                )
                mux_cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", downloaded_video,
                    "-i", output_audio,
                    "-c:v", "copy",
                    *_mux_audio_codec_args(output_audio),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    muxed_video,
                ]
                logger.info("Muxing enhanced audio into video...")
                mux_proc.run(mux_cmd, check=True, timeout=600)
                logger.info("Muxed video saved to %s", muxed_video)

                if upload_media_file(sermon_id, muxed_video, "original-video"):
                    logger.debug("Video uploaded successfully")
                    if not verbose:
                        print("   Video updated with enhanced audio")
                else:
                    logger.error("Video upload failed")

                # Cleanup downloaded source video (keep muxed for reference)
                try:
                    os.remove(downloaded_video)
                except OSError:
                    pass
        except Exception as e:  # pragma: no cover
            logger.error("Video update error: %s", e)
            if not verbose:
                print(f"   Video update failed: {e}")

    # Cleanup temp audio file
    try:
        input_audio = os.path.join(sermon_dir, FILENAMES["temp"])
        if os.path.exists(input_audio):
            os.remove(input_audio)
    except Exception:  # pragma: no cover
        pass

    logger.info("Sermon %s processing complete", sermon_id)

    # Save complete sermon record to database for UI access
    if database_available and (summary or hashtags or transcript):
        try:
            repo = SermonRepository()

            # Build comprehensive sermon record
            sermon_data = {
                'id': str(sermon_id) if sermon_id else '',
                'title': str(sermon_name) if sermon_name else '',
                'speaker': str(speaker_name) if speaker_name else '',
                'recorded_date': str(getattr(details, 'preachDate', '') or ''),
                'event_type': str(event_type) if event_type else '',
                'bible_text': str(getattr(details, 'bibleText', '') or ''),
                'duration': int(getattr(details, 'durationSeconds', 0) or 0),
                'status': 'processed' if not DRY_RUN else 'pending',
                'description_needs_review': description_needs_review,
                'description_error': description_error,
                'file_paths': {
                    'audio': (
                        output_audio if output_audio and os.path.exists(output_audio) else None
                    ),
                    'transcript': (
                        str(get_file_path(sermon_dir, "transcript")) if transcript else None
                    ),
                    'description': (
                        str(get_file_path(sermon_dir, "description")) if summary else None
                    ),
                    'hashtags': str(get_file_path(sermon_dir, "hashtags")) if hashtags else None
                },
                'processing_info': {
                    'enhancement_method': AUDIO_PARAMS.get('enhancement_method', 'unknown'),
                    'noise_reduction_applied': AUDIO_PARAMS.get('noise_reduction', False),
                    'normalization_applied': AUDIO_PARAMS.get('normalize', False),
                    'processing_duration': None,  # Could be tracked with timing
                    'quality_score': None,  # Could be calculated from processing metrics
                },
                'content': {
                    'transcript_text': transcript,
                    'description': summary,
                    'hashtags': hashtags,
                    'key_topics': [],  # Could be extracted from LLM processing
                    'summary': summary  # Using description as summary for now
                },
                'upload_info': {
                    'sermonaudio_id': str(sermon_id) if sermon_id else '',
                    'upload_date': dt.datetime.now(),
                    'upload_status': 'completed' if not DRY_RUN else 'pending',
                    'upload_message': 'Processing completed successfully'
                }
            }

            # Remove None values from file_paths
            sermon_data['file_paths'] = {k: v for k, v in sermon_data['file_paths'].items() if v}

            success = repo.save_sermon(sermon_data)
            if success:
                logger.debug("Sermon data saved to database successfully")
            else:
                logger.warning("Failed to save sermon data to database")

        except Exception as e:
            logger.warning(f"Database save failed: {e}")

    # Return summary of what was processed
    completed_actions = []
    if needs_desc_update and summary is not None:
        completed_actions.append("description")
    if needs_hash_update and hashtags is not None:
        completed_actions.append("hashtags")
    if needs_audio and output_audio and os.path.exists(output_audio):
        completed_actions.append("audio")

    return {
        "action": "processed",
        "completed": completed_actions,
        "skipped": [action for action in processing_actions if action not in completed_actions],
        "validation_info": validation_info if validation_info else None,
        "description_needs_review": description_needs_review,
        "description_error": description_error,
    }


def get_sermons_in_date_range(start_date, end_date):
    """Legacy helper. Prefer cli_main() with --date-range for new code."""
    try:
        start_dt = dt.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = dt.datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        logger.error("Invalid date format; expected YYYY-MM-DD")
        return []
    params = {
        'broadcasterID': SERMON_AUDIO_BROADCASTER_ID,
        'preachedAfterTimestamp': int(start_dt.timestamp()),
        'preachedBeforeTimestamp': int(end_dt.timestamp()),
        'pageSize': 100,
        'page': 1,
        'cache': 'true',
        'lite': 'true'
    }
    headers = get_api_headers()
    url = f"{BASE_URL}node/sermons"
    all_sermons = []
    while True:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=60)
            if r.status_code != 200:
                break
            data = r.json()
            results = data.get('results', [])
            for s in results:
                speaker_info = s.get('speaker') or {}
                all_sermons.append({
                    'sermonID': s.get('sermonID'),
                    'displayTitle': s.get('displayTitle'),
                    'preachDate': s.get('preachDate'),
                    'speakerName': speaker_info.get('displayName'),
                    'eventType': s.get('eventType')
                })
            if not data.get('next'):
                break
            params['page'] += 1
        except Exception:
            break
    all_sermons.sort(key=lambda x: x['preachDate'] or '1900-01-01')
    return all_sermons


def search_broadcaster_sermons(start_date: str, end_date: str, max_results: int = 100,
                               speaker_filter: str = None,
                               event_type_filter: str = None) -> list[dict[str, Any]]:
    """Search the broadcaster's sermons with full metadata for batch filtering.

    Returns dicts with sermon_id, title, speaker, date, event_type,
    has_description, has_hashtags, has_audio, has_transcript and duration
    (minutes) keys.
    """
    try:
        start_dt = dt.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = dt.datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        logger.error("Invalid date range; expected YYYY-MM-DD")
        return []
    params = {
        'broadcasterID': SERMON_AUDIO_BROADCASTER_ID,
        'preachedAfterTimestamp': int(start_dt.timestamp()),
        'preachedBeforeTimestamp': int(end_dt.timestamp()),
        'pageSize': 100,
        'page': 1,
        'cache': 'true',
        'lite': 'false'
    }
    headers = get_api_headers()
    url = f"{BASE_URL}node/sermons"
    sermons = []
    while len(sermons) < max_results:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=60)
            if r.status_code != 200:
                break
            data = r.json()
            results = data.get('results', [])
            if not results:
                break
            for s in results:
                speaker_info = s.get('speaker') or {}
                speaker_name = speaker_info.get('displayName') or ''
                if speaker_filter and speaker_filter.lower() not in speaker_name.lower():
                    continue
                if event_type_filter and event_type_filter != s.get('eventType'):
                    continue
                media = s.get('media') or {}
                audio = media.get('audio') or []
                duration_sec = s.get('audioDurationSeconds') or 0
                sermons.append({
                    'sermon_id': s.get('sermonID'),
                    'title': s.get('displayTitle', 'Untitled'),
                    'speaker': speaker_name or 'Unknown',
                    'date': s.get('preachDate', ''),
                    'event_type': s.get('eventType', ''),
                    'has_description': bool((s.get('moreInfoText') or '').strip()),
                    'has_hashtags': bool((s.get('keywords') or '').strip()),
                    'has_audio': bool(audio),
                    'has_transcript': bool(s.get('transcript')),
                    'duration': float(duration_sec) / 60.0,
                })
                if len(sermons) >= max_results:
                    break
            if not data.get('next') or len(sermons) >= max_results:
                break
            params['page'] += 1
        except Exception as e:
            logger.error("Error searching sermons: %s", e)
            break
    return sermons


def get_broadcaster_pastors(limit: int = 500) -> list[str]:
    """
    Retrieve a list of distinct pastors/speakers from the broadcaster's sermons.

    Args:
        limit: Maximum number of sermons to fetch for analysis (default: 500)

    Returns:
        Sorted list of unique speaker names
    """
    try:
        params = {
            'page': 1,
            'pageSize': 50,
            'lite': 'true',
            'broadcasterID': SERMON_AUDIO_BROADCASTER_ID,
            'includeDrafts': 'true',
            'includeScheduled': 'true',
        }
        headers = get_api_headers()
        url = f"{BASE_URL}node/sermons"
        speakers = set()
        fetched_count = 0

        logger.debug(f"Fetching pastors from broadcaster's sermons (limit: {limit})")

        while fetched_count < limit:
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=60)
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch sermons: {resp.status_code}")
                    break

                data = resp.json()
                results = data.get('results', [])

                if not results:
                    break

                for sermon in results:
                    speaker_info = sermon.get('speaker') or {}
                    speaker_name = speaker_info.get('displayName')
                    if speaker_name and speaker_name.strip():
                        speakers.add(speaker_name.strip())
                    fetched_count += 1

                    if fetched_count >= limit:
                        break

                if not data.get('next') or fetched_count >= limit:
                    break

                params['page'] += 1

            except Exception as e:
                logger.error(f"Error fetching sermon data: {e}")
                break

        speaker_list = sorted(speakers)
        logger.debug(f"Found {len(speaker_list)} unique pastors")
        return speaker_list

    except Exception as e:
        logger.error(f"Error retrieving pastors: {e}")
        return []


def get_broadcaster_event_types(limit: int = 500) -> list[str]:
    """
    Retrieve a list of distinct event types from the broadcaster's sermons.

    Args:
        limit: Maximum number of sermons to fetch for analysis (default: 500)

    Returns:
        Sorted list of unique event types
    """
    try:
        params = {
            'page': 1,
            'pageSize': 50,
            'lite': 'true',
            'includeDrafts': 'true',
            'includeScheduled': 'true'
        }
        headers = get_api_headers()
        url = f"{BASE_URL}node/sermons"
        event_types = set()
        fetched_count = 0

        logger.debug(f"Fetching event types from broadcaster's sermons (limit: {limit})")

        while fetched_count < limit:
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=60)
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch sermons: {resp.status_code}")
                    break

                data = resp.json()
                results = data.get('results', [])

                if not results:
                    break

                for sermon in results:
                    event_type = sermon.get('eventType')
                    if event_type and event_type.strip():
                        event_types.add(event_type.strip())
                    fetched_count += 1

                    if fetched_count >= limit:
                        break

                if not data.get('next') or fetched_count >= limit:
                    break

                params['page'] += 1

            except Exception as e:
                logger.error(f"Error fetching sermon data: {e}")
                break

        event_list = sorted(event_types)
        logger.debug(f"Found {len(event_list)} unique event types")
        return event_list

    except Exception as e:
        logger.error(f"Error retrieving event types: {e}")
        return []


_SERIES_BY_NAME: dict[str, int | None] = {}


def get_broadcaster_series(limit: int = 500) -> list[dict[str, Any]]:
    """
    Retrieve the broadcaster's series with their numeric IDs.

    Args:
        limit: Kept for caller compatibility; the series endpoint returns
            the broadcaster's full series list in one response.

    Returns:
        Sorted list of dicts with 'name' (str) and 'seriesID' (int or None) keys.
    """
    try:
        resp = requests.get(
            BASE_URL + f'node/broadcasters/{SERMON_AUDIO_BROADCASTER_ID}/series',
            headers=get_api_headers(),
            timeout=60,
        )
        if resp.status_code != 200:
            logger.warning("Failed to fetch series: %s", resp.status_code)
            return []

        series_by_name: dict[str, int | None] = {}
        for series in resp.json().get('results', []):
            name = series.get('title') or series.get('displayName') or series.get('name')
            series_id = series.get('seriesID') or series.get('id')
            if series_id is not None:
                try:
                    series_id = int(series_id)
                except (TypeError, ValueError):
                    series_id = None
            if name and str(name).strip():
                series_by_name[str(name).strip()] = series_id

        series_list = [
            {'name': name, 'seriesID': series_id}
            for name, series_id in sorted(series_by_name.items())
        ]
        _SERIES_BY_NAME.clear()
        _SERIES_BY_NAME.update(series_by_name)
        logger.debug(f"Found {len(series_list)} unique series")
        return series_list
    except Exception as e:
        logger.error(f"Error fetching series: {e}")
        return []


def _normalize_entity_name(name: str) -> str:
    """Trim and case-fold an entity name for tolerant matching."""
    return " ".join(name.split()).casefold()


def resolve_series_id(series_name: str, create_missing: bool = False) -> int | None:
    """Resolve a series name to its numeric SermonAudio seriesID.

    With create_missing=True, a name that doesn't exist yet is created on
    SermonAudio and its new ID is returned (used for non-dry-run uploads).
    """
    if not series_name:
        return None
    normalized = _normalize_entity_name(series_name)
    for name, series_id in _SERIES_BY_NAME.items():
        if _normalize_entity_name(name) == normalized:
            return series_id
    try:
        get_broadcaster_series()
    except Exception as e:
        logger.warning("Failed to refresh series list: %s", e)
    for name, series_id in _SERIES_BY_NAME.items():
        if _normalize_entity_name(name) == normalized:
            return series_id
    if create_missing:
        new_id = create_series_on_api(series_name)
        if new_id is not None:
            _SERIES_BY_NAME[series_name] = new_id
            return new_id
    logger.warning(
        "Series '%s' not found on SermonAudio; the sermon will be created "
        "without a series", series_name,
    )
    return None


def create_series_on_api(series_name: str) -> int | None:
    """Create a series on SermonAudio and return its new numeric seriesID."""
    try:
        resp = requests.post(
            BASE_URL + 'node/series',
            headers=get_api_headers(),
            json={
                'broadcasterID': SERMON_AUDIO_BROADCASTER_ID,
                'title': series_name,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            series_id = resp.json().get('seriesID')
            if series_id is not None:
                series_id = int(series_id)
                logger.info(
                    "Created series '%s' on SermonAudio (seriesID %s)",
                    series_name, series_id,
                )
                return series_id
            logger.warning(
                "Series '%s' created but response missing seriesID: %s",
                series_name, resp.text[:200],
            )
            return None
        logger.warning(
            "Failed to create series '%s': %d %s",
            series_name, resp.status_code, resp.text[:200],
        )
    except Exception as e:
        logger.warning("Error creating series '%s': %s", series_name, e)
    return None


def set_sermon_series(sermon_id: str, series_id: int) -> bool:
    """PATCH a sermon's series by numeric seriesID."""
    try:
        patch_url = BASE_URL + f'node/sermons/{sermon_id}'
        patch_headers = get_api_headers()
        patch_resp = requests.patch(patch_url, headers=patch_headers,
                                    json={'seriesID': series_id}, timeout=30)
        if patch_resp.status_code in (200, 204):
            logger.info("Series set via PATCH: %s", series_id)
            return True
        logger.warning("Failed to PATCH series: %d", patch_resp.status_code)
    except Exception as e:
        logger.warning("Error PATCHing series: %s", e)
    return False


def _join_segment_texts(segments: list[dict[str, float | str]]) -> str:
    """Join timed segment texts into a plain transcript string."""
    return " ".join(str(seg.get("text", "")) for seg in segments).strip()


def _reuse_existing_transcript(input_path: Path, speaker_name: str, series_title: str,
                               title: str, config: dict) -> str:
    """Load a saved transcript when the source file is unchanged.

    Reuses only when transcript.txt exists in the sermon output dir and the
    input's identity matches the one recorded in metadata.json. UI uploads
    carry a fresh epoch-milliseconds filename prefix on every upload, so raw
    mtime comparison would always consider the input newer; identity is
    compared on stems with that prefix stripped instead.
    """
    try:
        local_transcript = Path(input_path).parent / "transcript.txt"
        if local_transcript.exists() and local_transcript.stat().st_size > 0:
            logger.info("Reusing existing transcript next to media: %s", local_transcript)
            return local_transcript.read_text(encoding='utf-8')

        output_root = Path(config.get('output_directory', 'processed_sermons'))
        if not output_root.is_absolute():
            output_root = Path(__file__).parent / output_root
        reuse_dir = get_sermon_dir(output_root, speaker_name, series_title, title, "reuse")
        transcript_path = get_file_path(reuse_dir, "transcript")
        if not transcript_path.exists():
            logger.info("Transcript reuse miss: no file at %s", transcript_path)
            return ""

        meta = read_metadata(reuse_dir) or {}
        stored_original = meta.get('original_file') or ''
        if stored_original:
            if _normalized_file_stem(stored_original) == _normalized_file_stem(input_path):
                logger.info("Reusing existing transcript: %s", transcript_path)
                return transcript_path.read_text(encoding='utf-8')
            logger.info(
                "Transcript reuse miss: stored original %r does not match input %r",
                stored_original, str(input_path),
            )
            return ""

        # Legacy output dirs carry no original_file; keep the old mtime
        # heuristic for them
        try:
            if transcript_path.stat().st_mtime > Path(input_path).stat().st_mtime:
                logger.info("Reusing existing transcript: %s", transcript_path)
                return transcript_path.read_text(encoding='utf-8')
        except OSError:
            pass
    except Exception as e:
        logger.debug("Transcript reuse check failed: %s", e)
    return ""


def _reuse_existing_transcript_segments(input_path: Path, speaker_name: str, series_title: str,
                                        title: str, config: dict) -> list[dict[str, float | str]]:
    """Load saved transcript timestamps when the source file is unchanged.

    Mirrors the identity and mtime checks in _reuse_existing_transcript but
    reads transcript_timestamps.json instead of transcript.txt.
    """
    try:
        output_root = Path(config.get('output_directory', 'processed_sermons'))
        if not output_root.is_absolute():
            output_root = Path(__file__).parent / output_root
        reuse_dir = get_sermon_dir(output_root, speaker_name, series_title, title, "reuse")
        timestamps_path = get_file_path(reuse_dir, "transcript_timestamps")
        if not timestamps_path.exists():
            return []

        meta = read_metadata(reuse_dir) or {}
        stored_original = meta.get('original_file') or ''
        if stored_original:
            if _normalized_file_stem(stored_original) == _normalized_file_stem(input_path):
                logger.info("Reusing existing transcript timestamps: %s", timestamps_path)
                return read_transcript_timestamps(reuse_dir)
            return []

        try:
            if timestamps_path.stat().st_mtime > Path(input_path).stat().st_mtime:
                logger.info("Reusing existing transcript timestamps: %s", timestamps_path)
                return read_transcript_timestamps(reuse_dir)
        except OSError:
            pass
    except Exception as e:
        logger.debug("Transcript timestamp reuse check failed: %s", e)
    return []


@dataclass
class SermonLite:
    sermonID: str
    displayTitle: str
    preachDate: str | None
    speakerName: str | None
    eventType: str | None


SERMON_FILTER_ARG_MAP = {
    # Maps CLI flag -> (API param, type, help text)
    # type: int/str -> value passed directly; 'flag' -> 'true'; 'negflag' -> 'false'
    'page': ('page', int, 'Result page (default 1)'),
    'page_size': ('pageSize', int, 'Page size (max 100)'),
    'exact_ref_match': ('exactRefMatch', 'flag', 'Exact Bible ref match'),
    'chapter': ('chapter', int, 'First/only chapter'),
    'chapter_end': ('chapterEnd', int, 'Last chapter inclusive'),
    'verse': ('verse', int, 'First/only verse'),
    'verse_end': ('verseEnd', int, 'Last verse inclusive'),
    'featured': ('featured', 'flag', 'Featured sermons only'),
    'search_keyword': ('searchKeyword', str, 'Full-text search'),
    'include_transcripts': ('includeTranscripts', 'flag', 'Search transcripts (needs cache=true)'),
    'language_code': ('languageCode', str, 'ISO 639 language code'),
    'require_audio': ('requireAudio', 'flag', 'Require audio'),
    'require_video': ('requireVideo', 'flag', 'Require video'),
    'require_pdf': ('requirePDF', 'flag', 'Require PDF'),
    'no_media': ('noMedia', 'flag', 'Only sermons with no media'),
    'series': ('series', str, 'Filter by series (needs broadcaster)'),
    'denomination': ('denomination', str, 'Broadcaster denomination'),
    'vacant_pulpit': ('vacantPulpit', 'flag', 'Vacant pulpit'),
    'state': ('state', str, 'Broadcaster state/region'),
    'country': ('country', str, 'ISO3 country'),
    'speaker_name': ('speakerName', str, 'Speaker name'),
    'speaker_id': ('speakerID', int, 'Speaker ID'),
    'staff_pick': ('staffPick', 'flag', 'Staff pick'),
    'listener_recommended': ('listenerRecommended', 'flag', 'Listener recommended'),
    # 'year' reserved for core shortcut; expose preached-year for filtering
    'preached_year': ('year', int, 'Year preached (filter)'),
    'month': ('month', int, 'Month (1-12)'),
    'day': ('day', int, 'Day (1-31)'),
    'audio_min_duration': ('audioMinDurationSeconds', int, 'Minimum audio duration (s)'),
    'audio_max_duration': ('audioMaxDurationSeconds', int, 'Maximum audio duration (s)'),
    'lite': ('lite', 'flag', 'Lite sermons'),
    'lite_broadcaster': ('liteBroadcaster', 'flag', 'Lite broadcaster'),
    'cache': ('cache', 'flag', 'Enable API cache'),
    'preached_after': ('preachedAfterTimestamp', str, 'Preached after date (YYYY-MM-DD)'),
    'preached_before': ('preachedBeforeTimestamp', str, 'Preached before date (YYYY-MM-DD)'),
    'collection_id': ('collectionID', int, 'Collection ID'),
    'include_drafts': ('includeDrafts', 'flag', 'Include drafts'),
    'include_scheduled': ('includeScheduled', 'flag', 'Include scheduled'),
    'exclude_published': ('includePublished', 'negflag', 'Exclude published'),
    'book': ('book', str, 'OSIS book'),
    'sermon_ids': ('sermonIDs', str, 'Comma-separated sermon IDs'),
    'event_type': ('eventType', str, 'Event type description'),
    'broadcaster_id': ('broadcasterID', str, 'Override broadcaster ID'),
    'sort_by': ('sortBy', str, 'Sort field')
}


def build_sermon_query_params(args: argparse.Namespace) -> dict[str, Any]:
    """Map parsed argparse namespace -> API query parameter dict.

    Handles:
    * Boolean flags (flag / negflag) -> 'true' / 'false'
    * Date range ( --date-range ) -> preachedAfterTimestamp / preachedBeforeTimestamp
    * since-days shortcut -> preachedAfterTimestamp
    * limit does not override explicit pageSize already set
    """
    params: dict[str, Any] = {}
    for cli_name, (api_name, kind, _help) in SERMON_FILTER_ARG_MAP.items():
        if not hasattr(args, cli_name):
            continue
        value = getattr(args, cli_name)
        if value in (None, False):
            continue
        if kind == 'flag':
            params[api_name] = 'true'
        elif kind == 'negflag':
            params[api_name] = 'false'
        else:
            params[api_name] = value

    if getattr(args, 'date_range', None):
        start, end = args.date_range
        try:
            s_dt = dt.datetime.strptime(start, '%Y-%m-%d')
            e_dt = dt.datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            params['preachedAfterTimestamp'] = int(s_dt.timestamp())
            params['preachedBeforeTimestamp'] = int(e_dt.timestamp())
        except Exception as e:  # pragma: no cover
            logger.warning("Invalid --date-range: %s", e)

    if getattr(args, 'since_days', None):
        after = dt.datetime.utcnow() - dt.timedelta(days=args.since_days)
        params.setdefault('preachedAfterTimestamp', int(after.timestamp()))

    # Handle user-friendly date strings for preached_after/preached_before
    if getattr(args, 'preached_after', None):
        try:
            after_dt = dt.datetime.strptime(args.preached_after, '%Y-%m-%d')
            params['preachedAfterTimestamp'] = int(after_dt.timestamp())
        except ValueError as e:
            logger.warning("Invalid --preached-after date format (expected YYYY-MM-DD): %s", e)

    if getattr(args, 'preached_before', None):
        try:
            before_dt = dt.datetime.strptime(args.preached_before, '%Y-%m-%d')
            before_dt = before_dt.replace(hour=23, minute=59, second=59)
            params['preachedBeforeTimestamp'] = int(before_dt.timestamp())
        except ValueError as e:
            logger.warning("Invalid --preached-before date format (expected YYYY-MM-DD): %s", e)

    if getattr(args, 'limit', None):
        params.setdefault('pageSize', args.limit)
    return params


def fetch_sermons(params: dict[str, Any], max_results: int | None = None) -> list[SermonLite]:
    """Iterate paginated sermon list endpoint accumulating results.

    Stops early if max_results reached or API error encountered.
    """
    url = f"{BASE_URL}node/sermons"
    headers = get_api_headers()
    sermons: list[SermonLite] = []
    page = int(params.get('page', 1))
    params = params.copy()
    params.setdefault('page', page)
    params.setdefault('pageSize', 50)
    while True:
        params['page'] = page
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code != 200:
            logger.error("Sermons query failed (%d): %s", resp.status_code, resp.text[:160])
            break
        data = resp.json()
        results = data.get('results', [])
        for r in results:
            speaker_info = r.get('speaker') or {}
            sermons.append(
                SermonLite(
                    sermonID=r.get('sermonID'),
                    displayTitle=r.get('displayTitle'),
                    preachDate=r.get('preachDate'),
                    speakerName=speaker_info.get('displayName'),
                    eventType=r.get('eventType'),
                )
            )
            if max_results and len(sermons) >= max_results:
                return sermons
        if not data.get('next'):
            break
        page += 1
    return sermons


def cli_main(argv: Iterable[str] | None = None):  # orchestration
    """CLI entry point with subcommand support.

    Handles different subcommands:
    - new-sermon: Create new sermon from audio file
    - sermon-update: Update existing sermons with audio processing
    - metadata-update: Update only metadata for existing sermons
    - validation: Validate sermon descriptions
    - list: List sermons without processing
    """
    global config, llm_manager, DRY_RUN, DEBUG
    cli_parser = CLIParser(CONFIG_PATH)
    parser = cli_parser.build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Set up logging based on verbose flag
    setup_logging(args.verbose)

    if args.config and args.config != CONFIG_PATH:
        if not os.path.exists(args.config):
            parser.error(f"Config not found: {args.config}")
        config = load_config(args.config)
        llm_manager = LLMManager(config)
        # update dependent flags
        DRY_RUN = config.get('dry_run', DRY_RUN)
        DEBUG = config.get('debug', DEBUG)

    if args.verbose:
        DEBUG = True
    if args.dry_run:
        DRY_RUN = True

    # Check if no subcommand was provided
    if not hasattr(args, 'command') or args.command is None:
        parser.print_help()
        return

    # Dispatch to appropriate handler based on subcommand
    if args.command == 'new-sermon':
        handle_new_sermon(args)
    elif args.command == 'sermon-update' or args.command == 'process':
        handle_sermon_update(args)
    elif args.command == 'metadata-update':
        handle_metadata_update(args)
    elif args.command == 'validation' or args.command == 'validate':
        handle_validation(args)
    elif args.command == 'list':
        handle_list_sermons(args)
    else:
        parser.error(f"Unknown command: {args.command}")


def handle_new_sermon(args):
    """Handle new-sermon subcommand."""
    console_print("Creating new sermon from audio file...")

    cli_auto_edit_mode = getattr(args, 'auto_edit_mode', None)
    if cli_auto_edit_mode is None and (
        getattr(args, 'auto_edit', False) or getattr(args, 'edit_plan_file', None)
    ):
        auto_edit_cfg_cli = config.get('auto_edit', {}) if isinstance(config, dict) else {}
        cli_auto_edit_mode = auto_edit_cfg_cli.get('mode')
        if cli_auto_edit_mode is None:
            cli_auto_edit_mode = (
                'interactive' if bool(auto_edit_cfg_cli.get('require_review', False)) else 'auto'
            )

    result = process_new_sermon(
        audio_file=args.audio_file,
        speaker_name=args.speaker,
        recorded_date=args.date,
        event_type=args.event_type,
        bible_text=args.bible_text,
        title=args.title,
        subtitle=args.subtitle,
        series_title=getattr(args, 'series_title', None),
        description=args.description,
        hashtags=args.hashtags,
        dry_run=args.dry_run,
        skip_transcription=args.skip_transcription,
        skip_audio=(
            getattr(args, 'skip_audio', False) or getattr(args, 'skip_audio_processing', False)
        ),
        whisper_model=args.whisper_model,
        transcription_backend=getattr(args, 'transcription_backend', 'whisper_local'),
        use_clean_audio=getattr(args, 'use_clean_audio', False),
        clean_audio_script=getattr(
            args, 'clean_audio_script', '~/Documents/Repositories/deepfilternet/clean-audio.py'
        ),
        clean_audio_device=getattr(
            args, 'clean_audio_device', 'auto'
        ),
        auto_edit_mode=cli_auto_edit_mode,
        edit_plan_file=getattr(args, 'edit_plan_file', None),
        audio_offset=getattr(args, 'audio_offset', None),
    )

    if result.get('success'):
        sermon_id = result.get('sermon_id')
        if sermon_id:
            console_print(f"New sermon created successfully! ID: {sermon_id}")
        else:
            console_print("New sermon processed successfully (dry run)")
    else:
        error_msg = result.get('error', 'Unknown error')
        console_print(f"Failed to create new sermon: {error_msg}", "error")
        exit(1)


def handle_sermon_update(args):
    """Handle sermon-update subcommand (original functionality)."""
    # Convert args to match original structure for backward compatibility
    args.list_only = False
    args.metadata_only = False
    args.skip_audio = False
    args.force_description = False
    args.force_hashtags = False
    args.no_metadata = False

    # Call the original processing logic
    handle_original_processing(args)


def handle_metadata_update(args):
    """Handle metadata-update subcommand."""
    # Set metadata-only flags
    args.list_only = False
    args.metadata_only = True
    args.skip_audio = True
    args.no_metadata = False
    args.no_upload = False

    # Call the original processing logic
    handle_original_processing(args)


def handle_validation(args):
    """Handle validation subcommand."""
    # Initialize validator
    try:
        validator = DescriptionValidator(config)

        if not llm_manager.validator_provider:
            console_print(
                "No validator LLM configured, using primary provider for validation", "warning"
            )

        # Parse sermon IDs if provided
        validation_sermon_ids = None
        if args.validation_sermon_ids:
            validation_sermon_ids = [
                sid.strip() for sid in args.validation_sermon_ids.split(',') if sid.strip()
            ]
            console_print(f"Validating {len(validation_sermon_ids)} specific sermons")

        # Run validation
        if args.validate_and_regenerate:
            console_print("Validating descriptions and regenerating failed ones...")
            results = validate_and_regenerate_descriptions(
                validator=validator,
                sermon_ids=validation_sermon_ids,
                regenerate_failed=True,
                dry_run=args.dry_run,
                upload_to_sermonaudio=True,
            )
            # results is a dict: {'validated', 'regenerated', 'failed', ...}
            console_print(
                f"Validated {results.get('validated', 0)}, "
                f"regenerated {results.get('regenerated', 0)}, "
                f"failed {results.get('failed', 0)}"
            )
        else:
            console_print("Validating descriptions...")
            results = validator.validate_local_sermons(validation_sermon_ids)
            summary = validator.generate_summary(results)

            if args.validation_report:
                validator.print_detailed_report(results, summary)

            if args.export_validation_csv:
                validator.export_to_csv(results, args.export_validation_csv)
                console_print(f"Validation results exported to {args.export_validation_csv}")

            if args.export_validation_json:
                validator.export_to_json(results, summary, args.export_validation_json)
                console_print(
                    f"Detailed validation results exported to {args.export_validation_json}"
                )

        console_print("Validation Complete!")

    except Exception as e:
        console_print(f"Validation failed: {e}", "error")
        exit(1)


def handle_list_sermons(args):
    """Handle list subcommand."""
    args.list_only = True
    args.metadata_only = False
    args.skip_audio = False
    args.no_metadata = False
    args.no_upload = True

    # Call the original processing logic
    handle_original_processing(args)


def handle_original_processing(args):
    """Handle the original sermon processing logic for backward compatibility."""
    # Normalize arguments using the new orchestrator
    processing_options, validation_options = ArgumentsNormalizer.normalize_args(args)

    # Create orchestrator and filter instances
    orchestrator = ProcessingOrchestrator(config, console_print)
    SermonFilter(config)

    # Validate processing requirements
    issues = orchestrator.validate_processing_requirements(processing_options, validation_options)
    if issues:
        for issue in issues:
            console_print(f"{issue}", "error")
        return

    # Resolve audio and transcript save options
    save_original_audio = ArgumentsNormalizer.resolve_audio_save_option(args, config)
    save_transcript = ArgumentsNormalizer.resolve_transcript_save_option(args, config)

    if args.sermon_id:
        if not confirm(f"Process sermon {args.sermon_id}?", args.auto_yes):
            console_print("Cancelled")
            return
        console_print(f"Processing sermon {args.sermon_id}...")

        # Handle metadata-only and skip-audio flags
        skip_audio = args.metadata_only or args.skip_audio

        result = process_single_sermon(
            args.sermon_id,
            no_upload=args.no_upload or args.dry_run,
            verbose=args.verbose,
            skip_audio=skip_audio,
            force_description=getattr(args, 'force_description', False),
            force_hashtags=getattr(args, 'force_hashtags', False),
            no_metadata=getattr(args, 'no_metadata', False),
            output_dir=args.output_dir,
            save_original_audio=save_original_audio,
            save_transcript=save_transcript
        )

        # Display result summary for single sermon processing
        if result:
            if result.get("action") == "skipped":
                console_print(f"Skipped: {result.get('reason', 'No updates needed')}", "info")
            elif result.get("action") == "processed":
                completed = result.get("completed", [])
                if completed:
                    actions_text = ", ".join(completed)
                    console_print(f"Completed: Updated {actions_text}", "success")
                else:
                    console_print("Processing completed", "success")

        return

    # Year shortcut -> preached_year (pure filter) so --limit & other filters apply
    if getattr(args, 'year', None):
        if not hasattr(args, 'preached_year') or getattr(args, 'preached_year', None) in (None, 0):
            args.preached_year = args.year
        logger.debug(f"Using --year {args.year} as preached_year filter (respects --limit)")

    # Multi-year support: --years accepts comma separated and/or single range (e.g. 2020-2022)
    multi_years: list[int] = []
    if getattr(args, 'years', None):
        parts = [p.strip() for p in args.years.split(',') if p.strip()]
        for p in parts:
            if '-' in p:
                try:
                    a, b = p.split('-', 1)
                    start_y = int(a)
                    end_y = int(b)
                    if start_y > end_y:
                        start_y, end_y = end_y, start_y
                    multi_years.extend(range(start_y, end_y + 1))
                except ValueError:
                    logger.warning("Invalid year range: %s", p)
            else:
                try:
                    multi_years.append(int(p))
                except ValueError:
                    print(f"[WARN] Invalid year: {p}")
        # Deduplicate & sort
        multi_years = sorted(set(multi_years))
        if multi_years:
            logger.debug(f"Multi-year filter parsed: {multi_years}")
            # Remove single-year preached_year if present to avoid conflict
            if hasattr(args, 'preached_year'):
                args.preached_year = None

    params = build_sermon_query_params(args)
    params.setdefault('broadcasterID', SERMON_AUDIO_BROADCASTER_ID)

    # Only set default time filter if no explicit time/year filters AND not using multi-year
    filter_keys = ('preachedAfterTimestamp', 'preachedBeforeTimestamp', 'year')
    has_time_or_year_filter = any(k in params for k in filter_keys)
    if not multi_years and not has_time_or_year_filter:
        after = dt.datetime.utcnow() - dt.timedelta(days=30)
        params['preachedAfterTimestamp'] = int(after.timestamp())
        params.setdefault('cache', 'true')

    # If multi-year list requested, perform separate queries per year and merge.
    if multi_years:
        combined: list[SermonLite] = []
        for y in multi_years:
            y_params = params.copy()
            y_params['year'] = y
            logger.debug(f"Fetching year {y} with params: {y_params}")
            batch = fetch_sermons(y_params, max_results=None)
            combined.extend(batch)
            if getattr(args, 'limit', None) and len(combined) >= args.limit:
                combined = combined[:args.limit]
                break
        sermons = combined
    else:
        sermons = fetch_sermons(params, max_results=getattr(args, 'limit', None))

    if not sermons:
        print('No sermons matched filters.')
        return

    print(f"Matched {len(sermons)} sermons:")
    for s in sermons:
        print(
            f"  {s.preachDate} | {s.sermonID} | {s.displayTitle} | "
            f"{s.speakerName or '-'} | {s.eventType or '-'}"
        )

    if args.list_only:
        return

    if not confirm(f"Process {len(sermons)} sermons?", args.auto_yes):
        console_print('Cancelled')
        return

    # Handle metadata-only and skip-audio flags for batch processing
    skip_audio = getattr(args, 'metadata_only', False) or getattr(args, 'skip_audio', False)

    # Show processing summary and settings
    console_print(f"Processing {len(sermons)} sermons...")
    if args.dry_run:
        console_print("DRY RUN MODE - No changes will be made", "warning")
    if args.no_upload:
        console_print("NO UPLOAD MODE - Audio will not be uploaded", "warning")

    # Show processing settings summary
    settings_info = []
    if skip_audio:
        settings_info.append("Metadata only (no audio processing)")
    else:
        settings_info.append("Full processing (metadata + audio)")

    # LLM provider info
    provider_info = llm_manager.get_provider_info()
    if provider_info['primary']:
        primary = provider_info['primary']
        llm_text = f"LLM: {primary['type'].title()}/{primary['model']}"
        if provider_info['fallback']:
            fallback = provider_info['fallback']
            llm_text += f" (fallback: {fallback['type'].title()}/{fallback['model']})"
        settings_info.append(llm_text)

    # Output directory
    output_path = args.output_dir or config.get('output_directory', 'processed_sermons')
    settings_info.append(f"Output: {output_path}")

    # File saving options
    save_opts = []
    original_audio_enabled = (save_original_audio or
                             (save_original_audio is None and
                              config.get('save_original_audio', True)))
    if original_audio_enabled:
        save_opts.append("original audio")
    transcript_enabled = (save_transcript or
                         (save_transcript is None and
                          config.get('save_transcript', False)))
    if transcript_enabled:
        save_opts.append("transcript")
    if save_opts:
        settings_info.append(f"Saving: {', '.join(save_opts)}")

    # Display settings
    for setting in settings_info:
        console_print(f"   {setting}")
    console_print("")  # Extra line for readability

    success = 0
    errors = 0
    needs_review = []  # Track sermons that need manual review
    validation_stats = {
        'approved_primary': 0,
        'approved_fallback': 0,
        'needs_review': 0,
        'no_validation': 0
    }

    # Process each sermon with individual progress updates
    for idx, s in enumerate(sermons, 1):
        if not args.verbose:
            console_print(f"[{idx}/{len(sermons)}] Processing: {s.displayTitle}")
        try:
            result = process_single_sermon(
                s.sermonID,
                no_upload=args.no_upload or args.dry_run,
                verbose=args.verbose,
                skip_audio=skip_audio,
                force_description=getattr(args, 'force_description', False),
                force_hashtags=getattr(args, 'force_hashtags', False),
                no_metadata=getattr(args, 'no_metadata', False),
                output_dir=args.output_dir,
                save_original_audio=save_original_audio,
                save_transcript=save_transcript
            )
            success += 1

            # Track validation results for summary
            if result and result.get("validation_info"):
                val_info = result["validation_info"]
                status = val_info.get('final_status', 'unknown')
                if status in validation_stats:
                    validation_stats[status] += 1
                if val_info.get('needs_review'):
                    needs_review.append({
                        'id': s.sermonID,
                        'title': s.displayTitle,
                        'validation_attempts': val_info.get('validation_attempts', [])
                    })

            # Display meaningful completion message based on what was done
            if not args.verbose:
                if result and result.get("action") == "skipped":
                    reason = result.get('reason', 'No updates needed')
                    msg = f"[{idx}/{len(sermons)}] Skipped: {s.displayTitle} - {reason}"
                    console_print(msg, "info")
                elif result and result.get("action") == "processed":
                    completed = result.get("completed", [])
                    if completed:
                        actions_text = ", ".join(completed)
                        msg = (f"[{idx}/{len(sermons)}] Updated: {s.displayTitle} - "
                               f"{actions_text}")
                        console_print(msg, "success")
                    else:
                        msg = f"[{idx}/{len(sermons)}] Completed: {s.displayTitle}"
                        console_print(msg, "success")
                else:
                    msg = f"[{idx}/{len(sermons)}] Completed: {s.displayTitle}"
                    console_print(msg, "success")
        except Exception as e:  # pragma: no cover
            errors += 1
            error_msg = f"[{idx}/{len(sermons)}] Error: {s.displayTitle} - {e}"
            if args.verbose:
                console_print(error_msg, "error")
                traceback.print_exc()
            else:
                console_print(error_msg, "error")
        time.sleep(1)

    # Final summary
    if success > 0:
        console_print(f"Completed successfully: {success} sermons", "success")
    if errors > 0:
        console_print(f"Errors encountered: {errors} sermons", "error")
    else:
        console_print("All sermons processed without errors!", "success")

    # Validation summary
    total_validated = sum(validation_stats.values())
    if total_validated > 0:
        console_print("\nDescription Validation Summary:", "info")
        if validation_stats['approved_primary'] > 0:
            count = validation_stats['approved_primary']
            console_print(f"   Approved (Primary): {count}", "success")
        if validation_stats['approved_fallback'] > 0:
            count = validation_stats['approved_fallback']
            console_print(f"   Approved (Fallback): {count}", "success")
        if validation_stats['no_validation'] > 0:
            console_print(f"   No Validation: {validation_stats['no_validation']}", "info")
        if validation_stats['needs_review'] > 0:
            console_print(f"   Needs Review: {validation_stats['needs_review']}", "warning")

    # Manual review items
    if needs_review:
        console_print("\nSermons requiring manual review:", "warning")
        for item in needs_review:
            console_print(f"   {item['title']} (ID: {item['id']})", "warning")
            for attempt in item['validation_attempts']:
                provider = attempt['provider'].title()
                reason = attempt['reason']
                console_print(f"      {provider}: {reason}", "info")

        return


if __name__ == '__main__':  # pragma: no cover
    try:
        cli_main()
    except Exception as top_e:  # noqa: BLE001
        console_print(f"Fatal error: {top_e}", "error")
        traceback.print_exc()
        sys.exit(1)
