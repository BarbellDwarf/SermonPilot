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

Config: defaults to ``config.yaml`` (override with ``--config`` or SA_UPDATER_CONFIG env var).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import re
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

print("🔄 Initializing SermonPilot...")
print("   📦 Loading dependencies...")

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
)

print("   🤖 Loading AI components...")
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
    from cli.parser import CLIParser, confirm
    from core.config import ConfigManager
    from llm_manager import LLMManager
    from processing.orchestrator import (
        ArgumentsNormalizer,
        ProcessingOrchestrator,
        SermonFilter,
    )
    from transcription import TranscriptionError, transcribe
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
    print("   ⚙️  Configuring environment...")
load_dotenv()

if _is_cli:
    print("✅ Initialization complete!")
    print("📃Retrieving Sermon List....")

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
    # Legacy function - now uses ConfigManager
    config_manager = ConfigManager(path)
    return config_manager.get_raw_config()


CONFIG_PATH = os.environ.get("SA_UPDATER_CONFIG", "config.yaml")
config_manager = ConfigManager(CONFIG_PATH)

# Validate required settings
missing_settings = config_manager.validate_required_settings()
if missing_settings:
    raise RuntimeError(
        f"[FATAL] Missing required configuration settings: {', '.join(missing_settings)}. "
        f"Please check your config file: {CONFIG_PATH}"
    )

# For backward compatibility, provide config dict
config = config_manager.get_raw_config()
llm_manager = LLMManager(config)

SERMON_AUDIO_API_KEY = config_manager.get('api_key')
SERMON_AUDIO_BROADCASTER_ID = config_manager.get('broadcaster_id')
sermonaudio.set_api_key(SERMON_AUDIO_API_KEY)

DRY_RUN = config.get('dry_run', False)
DEBUG = config.get('debug', False)

AUDIO_PARAMS = {
    'noise_reduction': config.get('audio_noise_reduction', True),
    'amplify': config.get('audio_amplify', True),
    'normalize': config.get('audio_normalize', True),
    'gain_db': config.get('audio_gain_db', 1.0),
    'target_level_db': config.get('audio_target_level_db', -22.0),
    'use_audacity': config.get('use_audacity', False),
    'enhancement_method': config.get('audio_enhancement_method', 'deepfilternet'),
    'config': config  # Pass full config for Q&A normalization
}

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


def console_print(message: str, level: str = "info"):
    """Print messages to console with appropriate formatting.

    Args:
        message: Message to print
        level: Message level (info, warning, error, success)
    """
    if level == "error":
        print(f"❌ {message}")
    elif level == "warning":
        print(f"⚠️  {message}")
    elif level == "success":
        print(f"✅ {message}")
    else:
        print(f"ℹ️  {message}")


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
            "SermonAudio API key is not configured. Set 'api_key' in config.yaml "
            "or the SERMONAUDIO_API_KEY environment variable."
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
                response = llm_manager.validator_provider.chat([
                    {'role': 'user', 'content': validation_prompt}
                ])

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
        print("📊 DESCRIPTION VALIDATION REPORT")
        print("="*80)

        # Summary section
        print("\n📈 SUMMARY:")
        print(f"   Total Sermons Validated: {summary.total_sermons}")
        print(
            f"   ✅ Valid Descriptions: {summary.valid_descriptions} "
            f"({summary.validation_rate:.1f}%)"
        )
        print(f"   ❌ Invalid Descriptions: {summary.invalid_descriptions}")
        print(f"   🔄 Need Regeneration: {summary.needs_regeneration}")
        print(f"   📊 Average Score: {summary.average_score:.2f}/1.0")

        # Criteria performance
        print("\n📋 CRITERIA PERFORMANCE:")
        for criterion, performance in summary.criteria_performance.items():
            status_icon = "✅" if performance >= 80 else "⚠️" if performance >= 60 else "❌"
            print(f"   {status_icon} {criterion}: {performance:.1f}%")

        # Individual results (failed validations)
        failed_results = [r for r in results if not r.is_valid]
        if failed_results:
            print(f"\n❌ FAILED VALIDATIONS ({len(failed_results)} sermons):")
            for result in failed_results[:10]:  # Show first 10
                print(f"\n   📝 Sermon ID: {result.sermon_id}")
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
            print(f"\n⚠️  PASSED BUT LOW SCORING ({len(low_score_passed)} sermons):")
            for result in low_score_passed[:5]:  # Show first 5
                print(
                    f"   📝 {result.sermon_id}: {result.validation_score:.2f}/1.0 "
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
    console_print("🔍 Starting description validation and regeneration process...")

    # Validate existing descriptions
    console_print("📋 Validating existing descriptions...")
    results = validator.validate_local_sermons(sermon_ids)

    if not results:
        console_print("❌ No sermons found to validate", "error")
        return {'validated': 0, 'regenerated': 0, 'failed': 0}

    # Generate summary
    summary = validator.generate_summary(results)

    # Print validation summary
    console_print("📊 Validation Results:")
    console_print(f"   Total validated: {summary.total_sermons}")
    console_print(f"   ✅ Valid: {summary.valid_descriptions} ({summary.validation_rate:.1f}%)")
    console_print(f"   ❌ Invalid: {summary.invalid_descriptions}")
    console_print(f"   🔄 Need regeneration: {summary.needs_regeneration}")

    regenerated_count = 0
    failed_regeneration = 0
    regenerated_sermons = []  # Track successfully regenerated sermons
    validation_failures = []  # Track double-validation failures

    if regenerate_failed and summary.invalid_descriptions > 0:
        console_print(f"🔄 Regenerating {summary.invalid_descriptions} failed descriptions...")

        failed_results = [r for r in results if not r.is_valid]

        for i, result in enumerate(failed_results, 1):
            sermon_id = result.sermon_id
            console_print(f"   [{i}/{len(failed_results)}] Processing sermon {sermon_id}...")

            try:
                if dry_run:
                    console_print(f"      🔍 DRY RUN: Would regenerate description for {sermon_id}")
                    regenerated_count += 1
                    continue

                # Get sermon transcript for regeneration
                transcript = get_sermon_transcript(sermon_id)
                if not transcript:
                    console_print(f"      ❌ Could not get transcript for {sermon_id}", "error")
                    failed_regeneration += 1
                    continue

                # Generate new description with validation
                console_print("      🤖 Generating new description...")
                new_description, validation_info = generate_validated_summary(
                    transcript,
                    event_type=None,  # Could enhance this with API data
                    speaker_name=None
                )

                # Double-validate the newly generated description
                console_print("      🔍 Double-validating new description...")
                is_valid, reason, score, criteria_met, criteria_failed = (
                    validator.validate_description(
                        new_description,
                        {'sermon_id': sermon_id}
                    )
                )

                # Check if the new description actually passes validation
                if not is_valid:
                    console_print(
                        "      ⚠️  WARNING: New description still fails validation!", "warning"
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
                    status_icon = "✅"
                elif validation_info.get('final_status') == 'approved_fallback':
                    status_icon = "⚠️"
                else:
                    status_icon = "❌"

                console_print(f"      {status_icon} Generated new description "
                      f"({len(new_description)} chars, score: {score:.2f})")

                # Save the new description locally
                sermon_dir = find_sermon_dir(validator.output_dir, sermon_id)
                if not sermon_dir:
                    console_print(
                        f"      ❌ Could not find sermon directory for {sermon_id}", "error"
                    )
                    failed_regeneration += 1
                    continue
                description_file = get_file_path(sermon_dir, "description")

                if description_file.exists():
                    # Backup old description
                    backup_file = sermon_dir / f"{sermon_id}_description_backup.txt"
                    description_file.rename(backup_file)
                    console_print(f"      💾 Backed up original to {backup_file.name}")

                description_file.write_text(new_description, encoding='utf-8')

                # Update SermonAudio if not in dry run mode and upload is enabled
                upload_success = False
                if upload_to_sermonaudio and not dry_run:
                    console_print("      📤 Uploading to SermonAudio...")
                    try:
                        upload_success = update_sermon_metadata(sermon_id, new_description, None)
                        if upload_success:
                            console_print("      ✅ Updated SermonAudio successfully", "success")
                        else:
                            console_print("      ⚠️  SermonAudio update failed", "warning")
                    except Exception as e:
                        console_print(f"      ❌ SermonAudio upload error: {e}", "error")

                regenerated_count += 1
                console_print(f"      ✅ Updated description for sermon {sermon_id}", "success")

            except Exception as e:
                console_print(
                    f"      ❌ Failed to regenerate description for {sermon_id}: {e}", "error"
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
    elif isinstance(hashtags, (list, tuple)):
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
        title = response.strip().strip('"').strip("'")

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
        short_title = response.strip().strip('"').strip("'")
        if len(short_title) > 30:
            short_title = short_title[:27] + "..."
        if short_title:
            logger.debug(
                "Generated short display title (%d chars): %s", len(short_title), short_title
            )
            return short_title
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


def _transcode_media(src: Path, dst: Path) -> bool:
    """Transcode an audio file into the container implied by dst's extension.

    Returns True when the converted file exists. Falls back to ffmpeg's
    default encoder for the container, then gives up (caller keeps src).
    """
    import subprocess
    codec_args = _TRANSCODE_CODEC_ARGS.get(dst.suffix.lower(), [])
    attempts: list[list[str]] = []
    if codec_args:
        attempts.append(["ffmpeg", "-y", "-i", str(src), *codec_args, str(dst)])
    attempts.append(["ffmpeg", "-y", "-i", str(src), str(dst)])
    last_err: Exception | None = None
    for cmd in attempts:
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=True)
            if dst.exists() and dst.stat().st_size > 0:
                return True
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
                SELECT id FROM sermons
                WHERE title = ? AND speaker = ? AND recorded_date = ?
                  AND status = 'processed'
                  AND id NOT LIKE 'draft\\_%' ESCAPE '\\'
                ORDER BY updated_at DESC
                LIMIT 1
            """, (title, speaker_name, recorded_date or '')).fetchone()
            if row:
                return row['id']
    except Exception as e:
        logger.debug("Existing processed sermon lookup failed: %s", e)
    return None


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

    Returns:
        Created sermon ID if successful, None if failed
    """
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
                      transcription_backend: str = "whisper_local",
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
                      cancel_check: Callable[[], None] | None = None) -> dict:
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

    Returns:
        Dict with keys: success, sermon_id, title, description, hashtags,
                        enhanced_audio_path, transcript_length, error
    """
    def _report(progress, msg):
        if progress_callback is not None:
            try:
                progress_callback(progress, msg)
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
        'output_dir': None,
        'error': None,
    }

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

    # Preprocessing: optional clean-audio.py step (runs before enhancement)
    if use_clean_audio:
        console_print("🧹 Running external clean-audio.py preprocessing...")
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
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
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
            console_print(f"✅ clean-audio.py done: {clean_output.name}")
            _report(7, "clean-audio.py complete")
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
    import subprocess as _subprocess
    import tempfile as _tempfile
    try:
        # Step 1: Process the audio (or skip if requested)
        if skip_audio:
            console_print("⏭️  Skipping audio enhancement (--skip-audio enabled)")
            logger.info("Skipping audio enhancement per user request")
            _report(20, "Skipping audio enhancement (using file as-is)")
            enhanced_audio_path = audio_path
        else:
            console_print("🎵 Processing audio...")
            _report(10, "Initializing audio processor...")
            if audio_processor_available:
                # Create temporary output directory (absolute path).
                # processing_temp_dir config key overrides the TMPDIR-backed
                # default so long jobs don't fill a small RAM disk.
                temp_root = config.get('processing_temp_dir') or _tempfile.gettempdir()
                temp_dir = Path(temp_root) / "sermon_processing"
                temp_dir.mkdir(parents=True, exist_ok=True)

                # For video inputs, extract audio to WAV first
                process_input = audio_path
                if input_is_video:
                    _report(12, "Extracting audio from video...")
                    extracted_wav = temp_dir / "extracted_audio.wav"
                    try:
                        _subprocess.run(
                            ["ffmpeg", "-y", "-i", str(audio_path),
                             "-vn", "-acodec", "pcm_s16le", "-ar", "48000",
                             "-ac", "1", str(extracted_wav)],
                            capture_output=True, text=True, timeout=300, check=True
                        )
                        process_input = extracted_wav
                        _report(14, "Audio extracted from video")
                    except Exception as e:
                        logger.warning("Failed to extract audio from video: %s", e)
                        _report(14, "Audio extraction failed, using original file")

                processor = AudioProcessor(
                    enhancement_method=(
                        enhancement_method
                        or config.get('audio_enhancement_method', 'deepfilternet')
                    )
                )
                if enhancement_method == "custom" and custom_repo and custom_file:
                    processor.config['clear_custom_repo'] = custom_repo
                    processor.config['clear_custom_file'] = custom_file
                enhanced_audio_path = temp_dir / "enhanced_audio.wav"
                _report(15, f"Running audio enhancement ({processor.enhancement_method})...")
                success, proc_result = processor.process_sermon_audio(
                    str(process_input),
                    str(enhanced_audio_path)
                )
                if not success or not enhanced_audio_path.exists():
                    logger.warning("Audio processing failed, using original file")
                    _report(20, "Audio processing failed, falling back to original")
                    enhanced_audio_path = audio_path
                else:
                    _report(30, "Audio enhancement complete")
            else:
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
                if _transcode_media(Path(enhanced_audio_path), converted_path):
                    console_print(
                        f"🎧 Converted enhanced audio to {target_ext.lstrip('.').upper()}"
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
                    import subprocess as mux_proc
                    final_video = original_input_path.with_name(
                        f"{original_input_path.stem}_enhanced{original_input_path.suffix}"
                    )
                    mux_cmd = [
                        "ffmpeg", "-y",
                        "-i", str(original_input_path),
                        "-i", str(enhanced_audio_path),
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-map", "0:v:0",
                        "-map", "1:a:0",
                        "-shortest",
                        str(final_video),
                    ]
                    logger.info("Muxing enhanced audio into video: %s", " ".join(mux_cmd))
                    mux_proc.run(mux_cmd, capture_output=True, text=True, timeout=600, check=True)
                    final_upload_path = final_video
                    upload_type = "original-video"
                    console_print(f"🎬 Muxed enhanced audio into video: {final_video.name}")
                except Exception as e:
                    logger.warning("Video muxing failed, falling back to audio upload: %s", e)
                    console_print("⚠️  Video mux failed, uploading audio only")
            else:
                console_print("🎬 Uploading original video (no audio enhancement)")
                final_upload_path = original_input_path
                upload_type = "original-video"

        # Step 2: Transcribe audio for metadata generation
        transcript = ""
        if (not title or not description or not hashtags) and not skip_transcription:
            transcript = _reuse_existing_transcript(
                original_input_path, speaker_name, series_title, title, config
            )
            if transcript:
                console_print(f"♻️ Reusing existing transcript ({len(transcript)} characters)")
                _report(55, f"Reusing existing transcript ({len(transcript)} characters)")
            else:
                _report(35, f"Starting transcription ({whisper_model} model)...")
                try:
                    transcript = transcribe(
                        str(enhanced_audio_path),
                        model_size=whisper_model,
                        config=config,
                        backend_override=transcription_backend,
                        progress_callback=_report,
                    )
                    if not transcript:
                        _report(
                            45,
                            "First transcription attempt produced no result, "
                            "retrying with original audio...",
                        )
                        transcript = transcribe(
                            str(audio_path),
                            model_size=whisper_model,
                            config=config,
                            backend_override=transcription_backend,
                            progress_callback=_report,
                        )
                except TranscriptionError as e:
                    logger.error("Transcription failed: %s", e)
                    raise RuntimeError(f"Transcription failed: {e}") from e
                except Exception as e:
                    logger.warning("Transcription attempt produced no result: %s", e)
                    transcript = ""
                _report(55, f"Transcription complete: {len(transcript)} characters")
        elif skip_transcription:
            console_print("⏭️  Skipping transcription (--skip-transcription enabled)")
            _report(55, "Skipped transcription")

        result['transcript'] = transcript
        result['transcript_length'] = len(transcript) if transcript else 0

        # Step 3: Generate metadata using transcript or fallback
        if transcript and not skip_ai_generation:
            console_print("🤖 Generating metadata from transcript...")

            if not title:
                try:
                    _report(60, "Generating title...")
                    title = generate_title(
                        transcript=transcript,
                        speaker_name=speaker_name,
                        event_type=event_type,
                        bible_text=bible_text
                    )
                except Exception as e:
                    logger.warning("LLM title generation failed: %s", e)

            if not description:
                try:
                    _report(70, "Generating description...")
                    if force_validation and transcript:
                        _report(70, "Generating description with validation...")
                        validator = DescriptionValidator(config)
                        description, validation_info = generate_validated_summary(
                            transcript,
                            event_type=event_type,
                            speaker_name=speaker_name
                        )
                        is_valid, reason, score, _, _ = validator.validate_description(
                            description, {'sermon_id': None}
                        )
                        if not is_valid:
                            logger.warning(
                                "Generated description failed validation (%s); "
                                "regenerating without validation as fallback", reason,
                            )
                            description = generate_summary(
                                transcript,
                                event_type=event_type,
                                speaker_name=speaker_name
                            )
                    else:
                        description = generate_summary(
                            transcript,
                            event_type=event_type,
                            speaker_name=speaker_name
                        )
                except Exception as e:
                    logger.warning("LLM description generation failed: %s", e)
                    description = None

            if not hashtags:
                try:
                    _report(80, "Generating hashtags...")
                    hashtags = generate_hashtags(transcript)
                except Exception as e:
                    logger.warning("LLM hashtag generation failed: %s", e)
                    hashtags = None
        elif skip_ai_generation:
            console_print("⏭️  Skipping AI metadata generation")
        else:
            console_print("⚠️  No transcript available, using basic metadata...")

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

            if not description:
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

        # Generate short display title if requested
        short_display_title = None
        if generate_short_title and title:
            try:
                short_display_title = generate_short_display_title(title)
                console_print(f"📝 Short display title: {short_display_title}")
            except Exception as e:
                logger.warning("Short title generation failed: %s", e)

        console_print(f"📝 Generated title: {title}")
        console_print(f"📝 Generated description: {description[:100]}...")
        if hashtags:
            console_print(f"🏷️  Generated hashtags: {hashtags}")

        if dry_run:
            console_print("🔍 DRY RUN - Would create sermon with:")
            console_print(f"  Title: {title}")
            console_print(f"  Speaker: {speaker_name}")
            console_print(f"  Date: {recorded_date}")
            console_print(f"  Event: {event_type}")
            console_print(f"  Bible Text: {bible_text}")
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
            import re
            import uuid
            safe_title = re.sub(r'[^a-zA-Z0-9]+', '_', (title or 'Untitled').strip().lower())[:40]
            safe_speaker = re.sub(
                r'[^a-zA-Z0-9]+', '_', (speaker_name or 'Unknown').strip().lower()
            )[:20]
            safe_date = (recorded_date or 'nodate').replace('-', '')
            sermon_id = f"draft_{safe_speaker}_{safe_date}_{safe_title}_{uuid.uuid4().hex[:8]}"
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
                'original_file': str(audio_path),
                'processed_file': str(final_output_path),
                'is_video': input_is_video,
                'upload_type': upload_type,
                'transcript_length': len(transcript) if transcript else 0,
                'has_transcript': bool(transcript),
                'dry_run': True,
            }
            import json
            with open(get_file_path(output_dir, "metadata"), 'w') as f:
                json.dump(metadata, f, indent=2)

            if transcript:
                with open(get_file_path(output_dir, "transcript"), 'w', encoding='utf-8') as f:
                    f.write(transcript)

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
                console_print("💾 Dry run sermon saved to local database (status: draft)")
            except Exception as e:
                logger.warning(f"Failed to save dry run sermon to local database: {e}")

            console_print(f"📁 Dry run files saved to: {output_dir}")
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
        if reusable_sermon_id:
            sermon_id = reusable_sermon_id
            console_print(
                f"♻️  Existing processed sermon {sermon_id} matches "
                f"'{title}' by {speaker_name} ({recorded_date}); reusing it"
            )
            _report(88, f"Reusing existing sermon: {sermon_id}")
        else:
            # Persist everything generated so far as a local draft BEFORE the
            # API create so a failed create loses no work.
            try:
                import json as _json
                import re as _re
                import shutil as _shutil
                import uuid as _uuid

                from src.sermon_paths import build_output_filename

                safe_title = _re.sub(
                    r'[^a-zA-Z0-9]+', '_', (title or 'Untitled').strip().lower()
                )[:40]
                safe_speaker = _re.sub(
                    r'[^a-zA-Z0-9]+', '_', (speaker_name or 'Unknown').strip().lower()
                )[:20]
                safe_date = (recorded_date or 'nodate').replace('-', '')
                recovery_draft_id = (
                    f"draft_{safe_speaker}_{safe_date}_{safe_title}_"
                    f"{_uuid.uuid4().hex[:8]}"
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
                    console_print(f"💾 Draft saved locally before upload: {recovery_draft_id}")
                except Exception as db_err:
                    logger.warning("Failed to save pre-upload draft to database: %s", db_err)
            except Exception as draft_err:
                logger.warning("Failed to persist pre-upload draft: %s", draft_err)
                recovery_draft_id = None

            _report(83, "Resolving speaker...")
            console_print("👤 Resolving speaker...")
            speaker_id = resolve_speaker_id(speaker_name)
            if speaker_id:
                console_print(f"✅ Resolved speaker '{speaker_name}' to ID {speaker_id}")
            else:
                console_print(f"ℹ️  Using speaker name '{speaker_name}' as-is (no numeric ID found)")

            _report(85, "Creating sermon on SermonAudio...")
            console_print("📤 Creating sermon on SermonAudio...")
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
                        f"💾 Create failed - progress saved as draft {recovery_draft_id}"
                    )
                return result

        result['sermon_id'] = sermon_id
        _report(90, f"Created sermon: {sermon_id}")

        # Single application path for series: the API ignores it during
        # creation, so always PATCH it onto the sermon afterwards
        if series_id is not None:
            if set_sermon_series(sermon_id, series_id):
                console_print(f"📚 Series set: {series_title} (ID {series_id})")
            else:
                console_print(
                    f"⚠️ Failed to set series '{series_title}' on sermon {sermon_id}"
                )
                logger.error(
                    "set_sermon_series failed: sermon %s, seriesID %s (%s)",
                    sermon_id, series_id, series_title,
                )

        # Step 5: Upload the media (audio or video)
        media_label = "video" if upload_type == "original-video" else "audio"
        console_print(f"📤 Uploading {media_label} for sermon {sermon_id}...")
        _report(92, f"Uploading {media_label} to SermonAudio...")
        upload_success = upload_media_file(sermon_id, str(final_upload_path), upload_type)

        if upload_success:
            console_print(
                f"✅ Successfully created and uploaded {media_label} for sermon {sermon_id}"
            )
            _report(95, f"{media_label.capitalize()} uploaded successfully")

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
                'original_file': str(audio_path),
                'processed_file': str(final_output_path),
                'is_video': input_is_video,
                'upload_type': upload_type,
                'transcript_length': len(transcript) if transcript else 0,
                'has_transcript': bool(transcript)
            }

            import json
            with open(get_file_path(output_dir, "metadata"), 'w') as f:
                json.dump(metadata, f, indent=2)

            # Save transcript if available
            if transcript:
                with open(get_file_path(output_dir, "transcript"), 'w', encoding='utf-8') as f:
                    f.write(transcript)
                console_print(f"📝 Transcript saved ({len(transcript)} characters)")

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

                console_print("💾 Sermon saved to local database")
            except Exception as e:
                logger.warning(f"Failed to save sermon to local database: {e}")

            console_print(f"📁 Sermon files saved to: {output_dir}")
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
            return result

    except ProcessingCancelledError:
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


def publish_dry_run_sermon(dry_run_id: str) -> dict[str, Any]:
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

        console_print(f"📤 Publishing dry run sermon: {title}")
        console_print(f"   Speaker: {speaker_name}, Date: {recorded_date}")

        speaker_id = resolve_speaker_id(speaker_name)
        if speaker_id:
            console_print(f"✅ Resolved speaker '{speaker_name}' to ID {speaker_id}")

        # If a previous publish attempt already created the remote sermon
        # (e.g. it died mid-upload), reuse that ID instead of creating a
        # duplicate.
        existing_publication_id = (sermon_data.get('upload_info') or {}).get(
            'sermonaudio_id'
        )
        if existing_publication_id:
            new_sermon_id = str(existing_publication_id)
            console_print(
                f"♻️  Draft was already created on SermonAudio as {new_sermon_id}; "
                "skipping creation"
            )
        else:
            console_print("📤 Creating sermon on SermonAudio...")
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

            console_print(f"✅ Sermon created with ID: {new_sermon_id}")

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
        console_print(f"📤 Uploading {media_label}...")
        upload_success = upload_media_file(new_sermon_id, str(upload_path), upload_type)

        if upload_success:
            console_print(f"✅ {media_label.capitalize()} uploaded successfully")
        else:
            console_print(f"⚠️  Sermon created but {media_label} upload failed")

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
                for table in (
                    'qa_segments', 'sermon_content', 'processing_info', 'sermon_files',
                    'upload_info', 'processing_status', 'validation_results',
                    'manual_review', 'llm_api_usage',
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
                shutil.rmtree(str(old_output_dir))

        if upload_success:
            console_print(f"✅ Dry run sermon published as: {new_sermon_id}")
        else:
            console_print(f"⚠️  Sermon created ({new_sermon_id}) but media upload failed")
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
    """
    Clean up LLM responses that include thinking/reasoning before the final answer.
    Uses a two-step approach: detection + LLM cleanup if needed.
    """
    if not response:
        return response

    # Common patterns that indicate thinking/reasoning sections
    thinking_indicators = [
        "Okay, let me",
        "Let me think",
        "Let me start by",
        "First, I need to",
        "Now, the guidelines:",
        "I need to identify",
        "Let me piece",
        "Check the character count",
        "Avoid any markdown",
        "Make sure it's",
        "Let me",
        "First,",
        "Now,",
        "I should",
        "I'll",
        "Looking at this",
        "The speaker",
        "The sermon is",
        "The main points",
        "based on",
        "seem to be",
        "carefully.",
        "The transcript",
        "reading through",
    ]

    # Check if response contains thinking patterns
    has_thinking = any(indicator.lower() in response.lower() for indicator in thinking_indicators)

    if has_thinking:
        logger.debug(
            "Detected thinking patterns in LLM response, attempting cleanup with second LLM call"
        )

        # Try to use LLM to extract just the description
        cleanup_prompt = (
            "The following text contains both reasoning/thinking and a sermon description. "
            "Extract ONLY the final sermon description paragraph. Do not include any "
            "reasoning, analysis, or commentary. Return only the description itself.\n\n"
            f"Text: {response}\n\n"
            "Instructions:\n"
            "- Return ONLY the sermon description\n"
            "- Start directly with the description content\n"
            "- Maximum 1600 characters\n"
            "- One paragraph format\n"
            "- No reasoning or explanation"
        )

        try:
            cleaned_response = llm_manager.chat([{'role': 'user', 'content': cleanup_prompt}])

            # Verify the cleaned response is shorter and doesn't have thinking patterns
            if len(cleaned_response) < len(response):
                # Check if cleaned response still has thinking patterns
                still_has_thinking = any(indicator.lower() in cleaned_response.lower()
                                       for indicator in thinking_indicators)

                if not still_has_thinking:
                    logger.debug("LLM cleanup successful (original: %d chars, cleaned: %d chars)",
                                len(response), len(cleaned_response))
                    return cleaned_response
                else:
                    logger.debug(
                        "LLM cleanup still contains thinking patterns, "
                        "falling back to regex cleanup"
                    )
            else:
                logger.debug("LLM cleanup didn't reduce length, falling back to regex cleanup")

        except Exception as e:
            logger.warning("LLM cleanup failed: %s, falling back to regex cleanup", e)

    # Fallback to original regex-based cleanup if LLM cleanup failed or wasn't needed
    return _regex_cleanup_thinking(response)


def _regex_cleanup_thinking(response: str) -> str:
    """
    Fallback regex-based cleanup for LLM thinking patterns.
    """
    # Try to find transition phrases and extract content after them
    transition_phrases = [
        " The speaker emphasizes",
        " The speaker stresses",
        " The speaker teaches",
        " The speaker explains",
        " The pastor emphasizes",
        " This sermon",
    ]

    for phrase in transition_phrases:
        if phrase in response:
            # Find where this phrase starts and take everything from there
            start_idx = response.find(phrase)
            if start_idx > 0:  # Make sure it's not at the very beginning
                result = response[start_idx:].strip()
                if len(result) > 100:  # Make sure we have substantial content
                    logger.debug(
                        "Found transition phrase, cleaned response "
                        "(original: %d chars, cleaned: %d chars)",
                        len(response), len(result),
                    )
                    return result

    # Try splitting by sentences and look for the actual content
    sentences = [s.strip() for s in response.split('.') if s.strip()]

    thinking_indicators = [
        "Okay, let me", "Let me start by", "First, I need to", "Now, the guidelines:",
        "I need to identify", "The sermon is", "The main points", "based on",
        "seem to be", "carefully.", "The transcript", "reading through"
    ]

    # Look for the transition from thinking to actual content
    for i, sentence in enumerate(sentences):
        # Check if this sentence contains thinking indicators
        has_thinking = any(
            indicator.lower() in sentence.lower() for indicator in thinking_indicators
        )

        # If we find a sentence that doesn't have thinking and is substantial
        if not has_thinking and len(sentence) > 30:
            # Check if it starts with speaker name or substantive content
            if any(word in sentence for word in ["emphasizes", "stresses", "teaches", "explains"]):
                remaining_sentences = sentences[i:]
                result = '. '.join(remaining_sentences)
                if not result.endswith('.'):
                    result += '.'

                logger.debug("Regex cleanup found content (original: %d chars, cleaned: %d chars)",
                            len(response), len(result))
                return result

    # If all else fails, look for the last substantial paragraph
    paragraphs = [p.strip() for p in response.split('\n\n') if p.strip()]
    if len(paragraphs) > 1:
        last_para = paragraphs[-1]
        if len(last_para) > 100:  # Substantial content
            logger.debug("Using last paragraph as summary (original: %d chars, cleaned: %d chars)",
                        len(response), len(last_para))
            return last_para

    # Return original if no cleanup was possible
    return response


def generate_summary(
    transcript: str,
    event_type: str | None = None,
    speaker_name: str | None = None,
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
            f"- Maximum 1600 characters (STRICT LIMIT - API will reject longer text)\n"
            f"- One paragraph format\n"
            + speaker_instruction +
            "- No intro/closing words\n- No markdown or bullets\n"
            "- Do not prefix with 'Summary:'\n- If incomplete, infer likely main message\n"
            "- Keep under 1600 characters or the upload will fail\n"
            "- Use the actual speaker name, not placeholder text\n"
            "- Include specific scripture references, source material, and concrete "
            "examples from the transcript\n"
            "- Mention the specific doctrines, rules, or texts the speaker expounded\n"
            "- Describe the practical application the speaker gave\n"
            "- IMPORTANT: Return ONLY the final summary paragraph. Do not include any reasoning, "
            "thinking process, explanations, or commentary. "
            "Start directly with the summary content."
        )
        messages = [{'role': 'user', 'content': prompt}]
    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating summary using %s LLM...", primary_provider)
        response = llm_manager.chat(messages)

        # Clean up responses that include thinking/reasoning (common with some models)
        response = _clean_llm_thinking_response(response)

        # Ensure the response doesn't exceed SermonAudio's character limit
        max_chars = 1600  # Conservative limit (API limit is 1700)
        if len(response) > max_chars:
            logger.warning("Generated summary too long (%d chars), truncating to %d",
                          len(response), max_chars)
            # Truncate at word boundary to avoid cutting words in half
            truncated = response[:max_chars]
            last_space = truncated.rfind(' ')
            if last_space > max_chars - 100:  # If we can find a reasonable word boundary
                response = truncated[:last_space] + "..."
            else:
                response = truncated[:-3] + "..."

        logger.debug("Summary generated (%d chars)", len(response))
        return response
    except Exception as e:  # pragma: no cover
        logger.error("LLM summary generation failed: %s", e)
        return "Summary generation failed"


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
        import re
        hashtag_pattern = r'#\w+'
        hashtags = re.findall(hashtag_pattern, response)

        if hashtags:
            verified_hashtags = ' '.join(hashtags)
            # Ensure length limit
            if len(verified_hashtags) > 150:
                # Truncate at word boundary
                truncated = verified_hashtags[:150]
                last_space = truncated.rfind(' ')
                if last_space > 0:
                    verified_hashtags = truncated[:last_space]
                else:
                    verified_hashtags = truncated

            logger.debug("Verified hashtags: %s", verified_hashtags)
            return verified_hashtags
        else:
            logger.warning("No valid hashtags found in verification, using fallback")
            return "#faith #hope #worship #christian #jesus"

    except Exception as e:
        logger.error("Hashtag verification failed: %s", e)
        # Return cleaned version of original hashtags as fallback
        import re
        hashtag_pattern = r'#\w+'
        fallback_hashtags = re.findall(hashtag_pattern, initial_hashtags)
        if fallback_hashtags:
            return ' '.join(fallback_hashtags)[:150]
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
            # Original processing method for backward compatibility
            hashtags = ' '.join(response.replace(',', ' ').split())
            if len(hashtags) > 150:
                hashtags = hashtags[:150]
            logger.debug("Generated hashtags (no verification): %s", hashtags)
            return hashtags

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
        'needs_review': False
    }

    # Check if validation is enabled
    metadata_config = config.get('metadata_processing', {})
    desc_config = metadata_config.get('description', {})
    validation_config = desc_config.get('validation', {})
    validation_enabled = validation_config.get('enabled', False)
    validation_criteria = validation_config.get('criteria', [])

    if not validation_enabled:
        # If validation is disabled, use the original generation method
        summary = generate_summary(transcript, event_type, speaker_name)
        validation_info['final_status'] = 'no_validation'
        return summary, validation_info

    def try_generate_summary(use_fallback=False):
        """Helper function to generate summary with specific provider."""
        if use_fallback and llm_manager.fallback_provider:
            # Temporarily swap providers for fallback generation
            original_primary = llm_manager.primary_provider
            llm_manager.primary_provider = llm_manager.fallback_provider
            try:
                summary = generate_summary(transcript, event_type, speaker_name)
                return summary
            finally:
                llm_manager.primary_provider = original_primary
        else:
            return generate_summary(transcript, event_type, speaker_name)

    # Try primary model first
    validation_info['primary_attempts'] = 1
    primary_summary = try_generate_summary(use_fallback=False)

    # Validate the primary summary
    is_valid, reason = llm_manager.validate_description(primary_summary, validation_criteria)
    validation_info['validation_attempts'].append({
        'provider': 'primary',
        'valid': is_valid,
        'reason': reason,
        'summary_length': len(primary_summary)
    })

    if is_valid:
        validation_info['final_status'] = 'approved_primary'
        return primary_summary, validation_info

    # If primary failed validation, try fallback
    if llm_manager.fallback_provider:
        logger.debug("Primary summary failed validation, trying fallback model...")
        validation_info['fallback_used'] = True
        fallback_summary = try_generate_summary(use_fallback=True)

        # Validate the fallback summary
        is_valid, reason = llm_manager.validate_description(fallback_summary, validation_criteria)
        validation_info['validation_attempts'].append({
            'provider': 'fallback',
            'valid': is_valid,
            'reason': reason,
            'summary_length': len(fallback_summary)
        })

        if is_valid:
            validation_info['final_status'] = 'approved_fallback'
            return fallback_summary, validation_info

    # If both failed validation, mark for manual review
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
    if config is None:
        config = globals().get('config') or {}
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
            print("   📄 Retrieving transcript...")
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
                    print("   ✨ Generating description...")
                summary, validation_info = generate_validated_summary(
                    transcript, event_type=event_type, speaker_name=speaker_name
                )
                logger.debug("Generated description (%d chars), validation: %s",
                           len(summary), validation_info['final_status'])

            if needs_hash_update:
                if not verbose:
                    print("   🏷️  Generating hashtags...")
                hashtags = generate_hashtags(transcript)
                logger.debug("Generated hashtags: %s", hashtags)

    # Audio processing (if needed)
    output_audio = None
    qa_processing_info = None
    if needs_audio:
        if not verbose:
            print("   🎵 Downloading audio...")
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
                print("   🔧 Processing audio...")
            try:
                result = process_sermon_audio(
                    input_audio,
                    output_audio,
                    skip_on_error=True,
                    verbose=verbose,
                    **AUDIO_PARAMS
                )

                # Handle new return format (success, qa_info) vs old format (success only)
                if isinstance(result, tuple):
                    processing_success, qa_processing_info = result
                else:
                    processing_success = result

                if not processing_success:
                    logger.warning("Audio processing issues; continuing with original audio")
                elif qa_processing_info:
                    logger.info(
                        f"Q&A processing: "
                        f"{qa_processing_info.get('total_segments', 0)} segments detected"
                    )

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
                    conn.execute(
                        "UPDATE sermons SET description = ?, updated_at = ? WHERE id = ?",
                        (summary, dt.datetime.now(), sermon_id)
                    )
                    conn.execute("""
                        INSERT OR REPLACE INTO sermon_content
                        (sermon_id, transcript_text, description, hashtags, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        sermon_id, transcript or '', summary or '', hashtags or '',
                        str(dt.datetime.now())
                    ))
                    conn.execute("DELETE FROM sermon_search WHERE sermon_id = ?", (sermon_id,))
                    conn.execute("""
                        INSERT INTO sermon_search
                        (sermon_id, title, speaker, transcript_text, description, hashtags)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        sermon_id,
                        sermon_name or '',
                        speaker_name or '',
                        transcript or '',
                        summary or '',
                        hashtags or '',
                    ))
                    conn.commit()
                logger.debug("Dry-run: saved generated content to database")
            except Exception as e:
                logger.warning(f"Dry-run database save failed: {e}")
        return

    # Update metadata if we generated any
    if summary is not None or hashtags is not None:
        if not verbose:
            print("   📤 Updating metadata...")
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
            print("   📚 Setting series...")
        set_sermon_series(sermon_id, series_id)

    # Upload audio if we processed it
    if needs_audio and output_audio and os.path.exists(output_audio):
        if not verbose:
            print("   📤 Uploading audio...")
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
            print("   🎬 Updating video with enhanced audio...")
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
                    "-c:a", "aac",
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
                        print("   ✅ Video updated with enhanced audio")
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
                print(f"   ⚠️  Video update failed: {e}")

    # Cleanup temp audio file
    try:
        input_audio = os.path.join(sermon_dir, FILENAMES["temp"])
        if os.path.exists(input_audio):
            os.remove(input_audio)
    except Exception:  # pragma: no cover
        pass

    logger.info("Sermon %s processing complete", sermon_id)

    # Save complete sermon record to database for UI access
    if database_available and (qa_processing_info or summary or hashtags or transcript):
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
                    'qa_normalization_applied': qa_processing_info is not None,
                    'qa_segments_count': (
                        qa_processing_info.get('total_segments', 0) if qa_processing_info else 0
                    ),
                    'qa_segments': (
                        qa_processing_info.get('qa_segments', []) if qa_processing_info else []
                    ),
                    'processing_duration': None,  # Could be tracked with timing
                    'quality_score': None,  # Could be calculated from processing metrics
                    'processing_logs': qa_processing_info if qa_processing_info else {}
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
                if qa_processing_info and qa_processing_info.get('total_segments', 0) > 0:
                    logger.info(
                        f"💾 Saved Q&A processing info: "
                        f"{qa_processing_info['total_segments']} segments"
                    )
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
        "validation_info": validation_info if validation_info else None
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
            'lite': 'true'
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

    except Exception as e:
        logger.error(f"Error retrieving series: {e}")
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
        output_root = Path(config.get('output_directory', 'processed_sermons'))
        if not output_root.is_absolute():
            output_root = Path(__file__).parent / output_root
        reuse_dir = get_sermon_dir(output_root, speaker_name, series_title, title, "reuse")
        transcript_path = get_file_path(reuse_dir, "transcript")
        if not transcript_path.exists():
            return ""

        meta = read_metadata(reuse_dir) or {}
        stored_original = meta.get('original_file') or ''
        if stored_original:
            if _normalized_file_stem(stored_original) == _normalized_file_stem(input_path):
                logger.info("Reusing existing transcript: %s", transcript_path)
                return transcript_path.read_text(encoding='utf-8')
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
    global config, llm_manager, DRY_RUN, DEBUG, config_manager
    cli_parser = CLIParser(CONFIG_PATH)
    parser = cli_parser.build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Set up logging based on verbose flag
    setup_logging(args.verbose)

    if args.config and args.config != CONFIG_PATH:
        if not os.path.exists(args.config):
            parser.error(f"Config not found: {args.config}")
        config_manager = ConfigManager(args.config)
        config = config_manager.get_raw_config()
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
    console_print("🎵 Creating new sermon from audio file...")

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
        clean_audio_device=getattr(args, 'clean_audio_device', 'auto'),
    )

    if result.get('success'):
        sermon_id = result.get('sermon_id')
        if sermon_id:
            console_print(f"✅ New sermon created successfully! ID: {sermon_id}")
        else:
            console_print("✅ New sermon processed successfully (dry run)")
    else:
        error_msg = result.get('error', 'Unknown error')
        console_print(f"❌ Failed to create new sermon: {error_msg}", "error")
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
                "⚠️  No validator LLM configured, using primary provider for validation", "warning"
            )

        # Parse sermon IDs if provided
        validation_sermon_ids = None
        if args.validation_sermon_ids:
            validation_sermon_ids = [
                sid.strip() for sid in args.validation_sermon_ids.split(',') if sid.strip()
            ]
            console_print(f"🎯 Validating {len(validation_sermon_ids)} specific sermons")

        # Run validation
        if args.validate_and_regenerate:
            console_print("🔍 Validating descriptions and regenerating failed ones...")
            results = validate_and_regenerate_descriptions(
                validator=validator,
                sermon_ids=validation_sermon_ids,
                regenerate_failed=True,
                dry_run=args.dry_run,
                upload_to_sermonaudio=True,
            )
            # results is a dict: {'validated', 'regenerated', 'failed', ...}
            console_print(
                f"📊 Validated {results.get('validated', 0)}, "
                f"regenerated {results.get('regenerated', 0)}, "
                f"failed {results.get('failed', 0)}"
            )
        else:
            console_print("🔍 Validating descriptions...")
            results = validator.validate_local_sermons(validation_sermon_ids)
            summary = validator.generate_summary(results)

            if args.validation_report:
                validator.print_detailed_report(results, summary)

            if args.export_validation_csv:
                validator.export_to_csv(results, args.export_validation_csv)
                console_print(f"📊 Validation results exported to {args.export_validation_csv}")

            if args.export_validation_json:
                validator.export_to_json(results, summary, args.export_validation_json)
                console_print(
                    f"📊 Detailed validation results exported to {args.export_validation_json}"
                )

        console_print("✅ Validation Complete!")

    except Exception as e:
        console_print(f"❌ Validation failed: {e}", "error")
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
            console_print(f"❌ {issue}", "error")
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
                console_print(f"⏭️  Skipped: {result.get('reason', 'No updates needed')}", "info")
            elif result.get("action") == "processed":
                completed = result.get("completed", [])
                if completed:
                    actions_text = ", ".join(completed)
                    console_print(f"✅ Completed: Updated {actions_text}", "success")
                else:
                    console_print("✅ Processing completed", "success")

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
    console_print(f"🎯 Processing {len(sermons)} sermons...")
    if args.dry_run:
        console_print("🔍 DRY RUN MODE - No changes will be made", "warning")
    if args.no_upload:
        console_print("📁 NO UPLOAD MODE - Audio will not be uploaded", "warning")

    # Show processing settings summary
    settings_info = []
    if skip_audio:
        settings_info.append("⚙️ Metadata only (no audio processing)")
    else:
        settings_info.append("⚙️ Full processing (metadata + audio)")

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
                    msg = f"[{idx}/{len(sermons)}] ⏭️  Skipped: {s.displayTitle} - {reason}"
                    console_print(msg, "info")
                elif result and result.get("action") == "processed":
                    completed = result.get("completed", [])
                    if completed:
                        actions_text = ", ".join(completed)
                        msg = (f"[{idx}/{len(sermons)}] ✅ Updated: {s.displayTitle} - "
                               f"{actions_text}")
                        console_print(msg, "success")
                    else:
                        msg = f"[{idx}/{len(sermons)}] ✅ Completed: {s.displayTitle}"
                        console_print(msg, "success")
                else:
                    msg = f"[{idx}/{len(sermons)}] ✅ Completed: {s.displayTitle}"
                    console_print(msg, "success")
        except Exception as e:  # pragma: no cover
            errors += 1
            error_msg = f"[{idx}/{len(sermons)}] ❌ Error: {s.displayTitle} - {e}"
            if args.verbose:
                console_print(error_msg, "error")
                traceback.print_exc()
            else:
                console_print(error_msg, "error")
        time.sleep(1)

    # Final summary
    if success > 0:
        console_print(f"✅ Completed successfully: {success} sermons", "success")
    if errors > 0:
        console_print(f"❌ Errors encountered: {errors} sermons", "error")
    else:
        console_print("🎉 All sermons processed without errors!", "success")

    # Validation summary
    total_validated = sum(validation_stats.values())
    if total_validated > 0:
        console_print("\n📋 Description Validation Summary:", "info")
        if validation_stats['approved_primary'] > 0:
            count = validation_stats['approved_primary']
            console_print(f"   ✅ Approved (Primary): {count}", "success")
        if validation_stats['approved_fallback'] > 0:
            count = validation_stats['approved_fallback']
            console_print(f"   ✅ Approved (Fallback): {count}", "success")
        if validation_stats['no_validation'] > 0:
            console_print(f"   ℹ️  No Validation: {validation_stats['no_validation']}", "info")
        if validation_stats['needs_review'] > 0:
            console_print(f"   ⚠️  Needs Review: {validation_stats['needs_review']}", "warning")

    # Manual review items
    if needs_review:
        console_print("\n⚠️  Sermons requiring manual review:", "warning")
        for item in needs_review:
            console_print(f"   📝 {item['title']} (ID: {item['id']})", "warning")
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
