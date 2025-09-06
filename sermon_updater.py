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
import sys
import time
import traceback
import warnings
from collections.abc import Iterable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

print("🔄 Initializing SermonAudio Processor...")
print("   📦 Loading dependencies...")

import requests
import sermonaudio
import yaml
from dotenv import load_dotenv
from sermonaudio.node.requests import Node

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
    from audio_processing import process_sermon_audio
    from llm_manager import LLMManager, migrate_legacy_config

    # Import database for Q&A processing tracking
    try:
        sys.path.insert(0, str(Path(__file__).parent / "ui"))
        from database import SermonRepository
        database_available = True
    except ImportError:
        database_available = False
        SermonRepository = None

    # Import enhanced audio processor
    try:
        from enhanced_audio_processor import EnhancedAudioProcessor
        enhanced_processor_available = True
    except ImportError:
        enhanced_processor_available = False
        EnhancedAudioProcessor = None

print("   ⚙️  Configuring environment...")
load_dotenv()

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
            'resemble_enhance', 'deepfilternet', 'DeepFilterNet'
        ]:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

        # Specifically suppress DF logger which is very verbose
        df_logger = logging.getLogger("df")
        df_logger.setLevel(logging.CRITICAL)
        df_logger.disabled = True
def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return migrate_legacy_config(cfg)


CONFIG_PATH = os.environ.get("SA_UPDATER_CONFIG", "config.yaml")
if not os.path.exists(CONFIG_PATH):
    print(f"[FATAL] Config file not found: {CONFIG_PATH}")
    sys.exit(1)

config = load_config(CONFIG_PATH)
llm_manager = LLMManager(config)

SERMON_AUDIO_API_KEY = config['api_key']
SERMON_AUDIO_BROADCASTER_ID = config['broadcaster_id']
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
    'enhancement_method': config.get('audio_enhancement_method', 'resemble_enhance'),
    'config': config  # Pass full config for Q&A normalization
}

BASE_URL = 'https://api.sermonaudio.com/v2/'


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
            logger.warning(f"Failed to get sermon details for {sermon_id}: HTTP {resp.status_code}")
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
    return {'X-Api-Key': SERMON_AUDIO_API_KEY, 'Content-Type': 'application/json'}


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

    def validate_description(self, description: str, context: dict = None) -> tuple[bool, str, float, list[str], list[str]]:
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

        criteria_text = "\n".join([f"{i+1}. {criterion}" for i, criterion in enumerate(self.validation_criteria)])

        validation_prompt = f"""You are a sermon description quality validator. Evaluate the following description against specific criteria and provide a detailed assessment.

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
            score, is_valid, reason, criteria_met, criteria_failed = self._parse_validation_response(response)

            return is_valid, reason, score, criteria_met, criteria_failed

        except Exception as e:
            logger.warning(f"Validation failed: {e}")
            return True, f"Validation error: {e}", 0.5, [], []

    def _parse_validation_response(self, response: str) -> tuple[float, bool, str, list[str], list[str]]:
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
                        met_indices = [int(x.strip()) - 1 for x in met_text.split(',') if x.strip().isdigit()]
                        criteria_met = [self.validation_criteria[i] for i in met_indices
                                      if 0 <= i < len(self.validation_criteria)]
                    except (ValueError, IndexError):
                        pass

            elif line.startswith('CRITERIA_FAILED:'):
                failed_text = line.split(':', 1)[1].strip()
                if failed_text and failed_text != 'None':
                    try:
                        failed_indices = [int(x.strip()) - 1 for x in failed_text.split(',') if x.strip().isdigit()]
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
        processed_dir = Path(self.output_dir)

        if not processed_dir.exists():
            logger.warning(f"Processed sermons directory not found: {processed_dir}")
            return results

        sermon_dirs = [d for d in processed_dir.iterdir() if d.is_dir()]

        if sermon_ids:
            sermon_dirs = [d for d in sermon_dirs if d.name in sermon_ids]

        logger.info(f"Validating {len(sermon_dirs)} local sermons...")

        for sermon_dir in sermon_dirs:
            try:
                result = self._validate_local_sermon(sermon_dir)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Error validating sermon {sermon_dir.name}: {e}")

        return results

    def _validate_local_sermon(self, sermon_dir: Path) -> ValidationResult | None:
        """Validate a single local sermon directory."""
        sermon_id = sermon_dir.name
        description_file = sermon_dir / f"{sermon_id}_description.txt"

        if not description_file.exists():
            logger.debug(f"No description file found for sermon {sermon_id}")
            return None

        try:
            description = description_file.read_text(encoding='utf-8').strip()

            # Try to get additional context from API or files
            context = {'sermon_id': sermon_id}

            is_valid, reason, score, criteria_met, criteria_failed = self.validate_description(description, context)

            return ValidationResult(
                sermon_id=sermon_id,
                title=f"Sermon {sermon_id}",  # Could enhance this with API call
                speaker="Unknown",  # Could enhance this with API call
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
        
        Args:
            sermon_id: Sermon ID to validate
            
        Returns:
            ValidationResult object or None if sermon not found
        """
        try:
            # First try to validate from local files
            processed_dir = Path(self.output_dir)
            sermon_dir = processed_dir / sermon_id

            if sermon_dir.exists():
                return self._validate_local_sermon(sermon_dir)

            # If not found locally, we could implement API validation here
            # For now, return None
            logger.warning(f"Sermon {sermon_id} not found in local processed directory")
            return None

        except Exception as e:
            logger.error(f"Error validating sermon {sermon_id}: {e}")
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
        print(f"   ✅ Valid Descriptions: {summary.valid_descriptions} ({summary.validation_rate:.1f}%)")
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
                print(f"   📝 {result.sermon_id}: {result.validation_score:.2f}/1.0 - {result.validation_reason}")

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

    def export_to_json(self, results: list[ValidationResult], summary: ValidationSummary, filename: str):
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
                is_valid, reason, score, criteria_met, criteria_failed = validator.validate_description(
                    new_description,
                    {'sermon_id': sermon_id}
                )

                # Check if the new description actually passes validation
                if not is_valid:
                    console_print("      ⚠️  WARNING: New description still fails validation!", "warning")
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
                sermon_dir = Path(validator.output_dir) / sermon_id
                description_file = sermon_dir / f"{sermon_id}_description.txt"

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
                console_print(f"      ❌ Failed to regenerate description for {sermon_id}: {e}", "error")
                failed_regeneration += 1

    return {
        'validated': summary.total_sermons,
        'regenerated': regenerated_count,
        'failed': failed_regeneration,
        'validation_rate': summary.validation_rate,
        'regenerated_sermons': regenerated_sermons,
        'validation_failures': validation_failures
    }


def update_sermon_metadata(sermon_id: str, description: str, hashtags: str | list[str]) -> bool:
    url = BASE_URL + f'node/sermons/{sermon_id}'
    headers = get_api_headers()
    keywords = hashtags if isinstance(hashtags, str) else ','.join(hashtags)
    payload = {'moreInfoText': description, 'keywords': keywords}
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
    url = BASE_URL + 'media'
    headers = get_api_headers()
    payload = {'uploadType': 'original-audio', 'sermonID': sermon_id}
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    logger.debug("Audio upload initiation status: %d", resp.status_code)
    if resp.status_code != 201:
        logger.error("Failed to initiate audio upload: %s", resp.text[:200])
        return False
    data = resp.json()
    upload_url = data.get('uploadURL')
    if not upload_url:
        logger.error("No upload URL returned.")
        return False
    try:
        with open(audio_path, 'rb') as fh:
            up = requests.post(
                upload_url,
                data=fh,
                headers={'Content-Type': 'audio/mpeg'},
                timeout=600,
            )
        logger.debug("Direct upload status: %d", up.status_code)
        return up.status_code in (200, 201, 204)
    except Exception as e:  # pragma: no cover
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

    prompt = f"""You are a sermon title generator. Create a compelling, descriptive title for this sermon.

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
{transcript[:1000]}...

Generate a compelling sermon title:"""

    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating title using %s LLM...", primary_provider)

        response = llm_manager.chat([{'role': 'user', 'content': prompt}])

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


def transcribe_audio(audio_path: str, model_size: str = "base") -> str:
    """Transcribe audio file using OpenAI Whisper.
    
    Args:
        audio_path: Path to audio file
        model_size: Whisper model size ("tiny", "base", "small", "medium", "large")
        
    Returns:
        Transcribed text if successful, empty string if failed
    """
    try:
        import warnings

        import whisper

        logger.info("Starting audio transcription with Whisper...")
        console_print("🎙️  Transcribing audio...")

        # Suppress warnings during model loading
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                model = whisper.load_model(model_size)
            except Exception as e:
                if "connection" in str(e).lower() or "network" in str(e).lower():
                    logger.warning("Network error loading Whisper model, trying smaller model")
                    console_print("⚠️  Network issues with model download, trying 'tiny' model...")
                    model = whisper.load_model("tiny")
                else:
                    raise e

        # Transcribe the audio
        result = model.transcribe(audio_path)
        transcript = result["text"].strip()

        logger.info("Transcription completed (%d characters)", len(transcript))
        console_print(f"✅ Transcription completed ({len(transcript)} characters)")

        return transcript

    except ImportError:
        logger.warning("Whisper not available for transcription")
        console_print("⚠️  Whisper not available - skipping transcription")
        return ""
    except Exception as e:
        if "connection" in str(e).lower() or "network" in str(e).lower() or "address" in str(e).lower():
            logger.warning("Network error during transcription, skipping: %s", e)
            console_print("⚠️  Network error - skipping transcription")
        else:
            logger.error("Transcription failed: %s", e)
            console_print(f"❌ Transcription failed: {e}")
        return ""


def create_new_sermon_api(title: str, speaker_name: str, recorded_date: str,
                         event_type: str = "Sunday Service", bible_text: str = None,
                         subtitle: str = None, description: str = None,
                         hashtags: str = None) -> str:
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
        'languageCode': 'eng'  # Default to English
    }

    # Add optional fields
    if bible_text:
        payload['bibleText'] = bible_text
    if subtitle:
        payload['subtitle'] = subtitle[:30]  # Ensure limit
    if description:
        payload['moreInfoText'] = description
    if hashtags:
        payload['keywords'] = hashtags

    # Generate display title from full title
    display_title = title[:30] if len(title) <= 30 else title[:27] + "..."
    payload['displayTitle'] = display_title

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
                      description: str = None, hashtags: str = None,
                      dry_run: bool = False, skip_transcription: bool = False,
                      whisper_model: str = "base") -> bool:
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
        whisper_model: Whisper model size for transcription
        
    Returns:
        True if successful, False if failed
    """
    from pathlib import Path

    from src.audio_processing import AudioProcessor

    audio_path = Path(audio_file)
    if not audio_path.exists():
        logger.error("Audio file not found: %s", audio_file)
        return False

    logger.info("Processing new sermon from audio file: %s", audio_file)

    try:
        # Step 1: Process the audio
        console_print("🎵 Processing audio...")
        processor = AudioProcessor()

        # Create temporary output directory
        temp_dir = Path("temp_sermon_processing")
        temp_dir.mkdir(exist_ok=True)

        # Process audio with enhancement
        enhanced_audio_path = temp_dir / f"enhanced_{audio_path.name}"
        success = processor.process_sermon_audio(
            str(audio_path),
            str(enhanced_audio_path)
        )

        if not success:
            logger.warning("Audio processing failed, using original file")
            enhanced_audio_path = audio_path

        # Step 2: Transcribe audio for metadata generation
        transcript = ""
        if (not title or not description or not hashtags) and not skip_transcription:
            # Try to get transcript from processed audio
            try:
                transcript = transcribe_audio(str(enhanced_audio_path), model_size=whisper_model)
                if not transcript:
                    # If transcription failed, try original audio
                    transcript = transcribe_audio(str(audio_path), model_size=whisper_model)
            except Exception as e:
                logger.warning("Transcription failed: %s", e)
                transcript = ""
        elif skip_transcription:
            console_print("⏭️  Skipping transcription (--skip-transcription enabled)")

        # Step 3: Generate metadata using transcript or fallback
        if transcript:
            console_print("🤖 Generating metadata from transcript...")

            if not title:
                try:
                    title = generate_title(
                        transcript=transcript,
                        speaker_name=speaker_name,
                        event_type=event_type,
                        bible_text=bible_text
                    )
                except Exception as e:
                    logger.warning("LLM title generation failed: %s", e)
                    title = None

            if not description:
                try:
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
                    hashtags = generate_hashtags(transcript)
                except Exception as e:
                    logger.warning("LLM hashtag generation failed: %s", e)
                    hashtags = None
        else:
            console_print("⚠️  No transcript available, using basic metadata...")

        # Fallback metadata generation for any missing fields
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
            base_tags = ["#sermon", f"#{speaker_name.replace(' ', '')}", f"#{event_type.replace(' ', '').replace('-', '')}"]
            if bible_text:
                # Extract book name for hashtag
                book = bible_text.split()[0] if bible_text else ""
                if book:
                    base_tags.append(f"#{book}")
            hashtags = " ".join(base_tags[:5])  # Limit to 5 tags

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
            console_print(f"  Transcript: {len(transcript)} characters" if transcript else "  Transcript: None")
            return True

        # Step 4: Create sermon via API
        console_print("📤 Creating sermon on SermonAudio...")
        sermon_id = create_new_sermon_api(
            title=title,
            speaker_name=speaker_name,
            recorded_date=recorded_date,
            event_type=event_type,
            bible_text=bible_text,
            subtitle=subtitle,
            description=description,
            hashtags=hashtags
        )

        if not sermon_id:
            logger.error("Failed to create sermon")
            return False

        # Step 5: Upload the audio
        console_print(f"📤 Uploading audio for sermon {sermon_id}...")
        upload_success = upload_audio_file(sermon_id, str(enhanced_audio_path))

        if upload_success:
            console_print(f"✅ Successfully created and uploaded sermon {sermon_id}")

            # Create local output directory
            output_dir = Path("processed_sermons") / sermon_id
            output_dir.mkdir(parents=True, exist_ok=True)

            # Copy audio to output directory
            final_audio_path = output_dir / f"sermon_{sermon_id}.mp3"
            if enhanced_audio_path != audio_path:
                import shutil
                shutil.copy2(enhanced_audio_path, final_audio_path)
            else:
                import shutil
                shutil.copy2(audio_path, final_audio_path)

            # Save metadata
            metadata = {
                'sermonID': sermon_id,
                'title': title,
                'speaker': speaker_name,
                'recorded_date': recorded_date,
                'event_type': event_type,
                'bible_text': bible_text,
                'subtitle': subtitle,
                'description': description,
                'hashtags': hashtags,
                'original_audio': str(audio_path),
                'processed_audio': str(final_audio_path),
                'transcript_length': len(transcript) if transcript else 0,
                'has_transcript': bool(transcript)
            }

            import json
            with open(output_dir / "metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)

            # Save transcript if available
            if transcript:
                with open(output_dir / f"{sermon_id}_transcript.txt", 'w', encoding='utf-8') as f:
                    f.write(transcript)
                console_print(f"📝 Transcript saved ({len(transcript)} characters)")

            console_print(f"📁 Sermon files saved to: {output_dir}")
            return True
        else:
            logger.error("Failed to upload audio")
            return False

    except Exception as e:
        logger.error("Error processing new sermon: %s", e)
        return False
    finally:
        # Clean up temporary files
        if 'temp_dir' in locals() and temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass  # Ignore cleanup errors


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
        logger.debug("Detected thinking patterns in LLM response, attempting cleanup with second LLM call")

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
                    logger.debug("LLM cleanup still contains thinking patterns, falling back to regex cleanup")
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
        " Mark Hogan emphasizes",
        " Mark Hogan stresses",
        " Mark Hogan teaches",
        " Mark Hogan explains",
        " The speaker emphasizes",
        " This sermon",
        " Hogan emphasizes",
        " Hogan stresses",
    ]

    for phrase in transition_phrases:
        if phrase in response:
            # Find where this phrase starts and take everything from there
            start_idx = response.find(phrase)
            if start_idx > 0:  # Make sure it's not at the very beginning
                result = response[start_idx:].strip()
                if len(result) > 100:  # Make sure we have substantial content
                    logger.debug("Found transition phrase, cleaned response (original: %d chars, cleaned: %d chars)",
                                len(response), len(result))
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
        has_thinking = any(indicator.lower() in sentence.lower() for indicator in thinking_indicators)

        # If we find a sentence that doesn't have thinking and is substantial
        if not has_thinking and len(sentence) > 30:
            # Check if it starts with speaker name or substantive content
            if any(word in sentence for word in ["Mark Hogan", "emphasizes", "stresses", "teaches", "explains"]):
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
        f"- The speaker's name is {speaker_name}\n"
        if speaker_name
        else "- Identify the primary speaker from the transcript\n"
    )

    prompt = (
        f"You are a {role_desc}. Read the following {body_desc} transcript and write a single, "
        f"concise description of the main message and application. Focus on what "
        f"the speaker wanted the audience to understand, believe, or do. Avoid generic statements; "
        f"emphasize unique focus.\n\nTranscript:\n{transcript}\n\nGuidelines:\n"
        f"- Maximum 1600 characters (STRICT LIMIT - API will reject longer text)\n"
        f"- One paragraph format\n"
        + speaker_instruction +
        "- No intro/closing words\n- No markdown or bullets\n"
        "- Do not prefix with 'Summary:'\n- If incomplete, infer likely main message\n"
        "- Keep under 1600 characters or the upload will fail\n"
        "- Use the actual speaker name, not placeholder text\n"
        "- IMPORTANT: Return ONLY the final summary paragraph. Do not include any reasoning, "
        "thinking process, explanations, or commentary. Start directly with the summary content."
    )
    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating summary using %s LLM...", primary_provider)
        response = llm_manager.chat([{'role': 'user', 'content': prompt}])

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
    verification_prompt = (
        "You are a hashtag validator. Your job is to extract ONLY valid hashtags from the input below. "
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

    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Verifying hashtags using %s LLM...", primary_provider)
        response = llm_manager.chat([{'role': 'user', 'content': verification_prompt}])

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
    prompt = (
        "Generate 5-10 highly relevant, search-friendly hashtags (<=150 chars total) for this "
        "sermon. Combine multi-word phrases (#ChristianLiving). Avoid duplicates & generic "
        "(#sermon #church) unless uniquely relevant. Output ONLY space-delimited hashtags.\n\n"
        f"Text:\n{text}\n\nHashtags:"
    )
    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating hashtags using %s LLM...", primary_provider)

        # First pass: Generate hashtags
        response = llm_manager.chat([{'role': 'user', 'content': prompt}])
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
                         save_transcript: bool = None):
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
    if not (needs_desc_update or needs_hash_update or needs_audio):
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
    sermon_dir = os.path.join(processed_root, sermon_id)
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
    if needs_audio:
        if not verbose:
            print("   🎵 Downloading audio...")
        input_audio = os.path.join(sermon_dir, f"temp_{sermon_id}.mp3")
        output_audio = os.path.join(sermon_dir, f"processed_{sermon_id}.mp3")

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
                original_audio_path = os.path.join(sermon_dir, f"original_{sermon_id}.mp3")
                try:
                    import shutil
                    shutil.copy2(input_audio, original_audio_path)
                    logger.debug("Saved original audio to: %s", original_audio_path)
                except Exception as e:
                    logger.warning("Failed to save original audio: %s", e)

            # Process audio
            qa_processing_info = None
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
                    logger.info(f"Q&A processing: {qa_processing_info.get('total_segments', 0)} segments detected")

            except Exception as e:
                logger.error("Audio processing failed: %s", e)
                needs_audio = False

    # Save local copies of generated content
    if summary is not None:
        try:
            with open(
                os.path.join(sermon_dir, f"{sermon_id}_description.txt"),
                'w',
                encoding='utf-8',
            ) as fh:
                fh.write(summary)
        except Exception as e:  # pragma: no cover
            logger.error("Failed writing description file: %s", e)

    if hashtags is not None:
        try:
            with open(
                os.path.join(sermon_dir, f"{sermon_id}_hashtags.txt"),
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
                    os.path.join(sermon_dir, f"{sermon_id}_transcript.txt"),
                    'w',
                    encoding='utf-8',
                ) as fh:
                    fh.write(transcript)
                logger.debug("Saved transcript to: %s",
                           os.path.join(sermon_dir, f"{sermon_id}_transcript.txt"))
            except Exception as e:  # pragma: no cover
                logger.error("Failed writing transcript file: %s", e)

    if DRY_RUN or no_upload:
        logger.info("Dry-run / no-upload: skipping remote updates")
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

    # Cleanup temp audio file
    try:
        input_audio = os.path.join(sermon_dir, f"temp_{sermon_id}.mp3")
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
                'id': sermon_id,
                'title': sermon_name,
                'speaker': speaker_name,
                'recorded_date': getattr(details, 'preachDate', ''),
                'event_type': event_type,
                'bible_text': getattr(details, 'bibleText', ''),
                'duration': getattr(details, 'durationSeconds', 0),
                'status': 'processed' if not DRY_RUN else 'pending',
                'file_paths': {
                    'processed_audio': output_audio if os.path.exists(output_audio) else None,
                    'original_audio': original_audio_path if 'original_audio_path' in locals() and os.path.exists(original_audio_path) else None,
                    'transcript': os.path.join(sermon_dir, f"{sermon_id}_transcript.txt") if transcript else None,
                    'description': os.path.join(sermon_dir, f"{sermon_id}_description.txt") if summary else None,
                    'hashtags': os.path.join(sermon_dir, f"{sermon_id}_hashtags.txt") if hashtags else None
                },
                'processing_info': {
                    'enhancement_method': AUDIO_PARAMS.get('enhancement_method', 'unknown'),
                    'noise_reduction_applied': AUDIO_PARAMS.get('noise_reduction', False),
                    'normalization_applied': AUDIO_PARAMS.get('normalize', False),
                    'qa_normalization_applied': qa_processing_info is not None,
                    'qa_segments_count': qa_processing_info.get('total_segments', 0) if qa_processing_info else 0,
                    'qa_segments': qa_processing_info.get('qa_segments', []) if qa_processing_info else [],
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
                    'sermonaudio_id': sermon_id,
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
                    logger.info(f"💾 Saved Q&A processing info: {qa_processing_info['total_segments']} segments")
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


def get_sermons_in_year(year):
    return get_sermons_in_date_range(f"{year}-01-01", f"{year}-12-31")


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
            'lite': 'true'
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

        speaker_list = sorted(list(speakers))
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

        event_list = sorted(list(event_types))
        logger.debug(f"Found {len(event_list)} unique event types")
        return event_list

    except Exception as e:
        logger.error(f"Error retrieving event types: {e}")
        return []


def get_broadcaster_series(limit: int = 500) -> list[str]:
    """
    Retrieve a list of distinct series from the broadcaster's sermons.
    
    Args:
        limit: Maximum number of sermons to fetch for analysis (default: 500)
        
    Returns:
        Sorted list of unique series names
    """
    try:
        params = {
            'page': 1,
            'pageSize': 50,
            'lite': 'false'  # Need full data to get series info
        }
        headers = get_api_headers()
        url = f"{BASE_URL}node/sermons"
        series_names = set()
        fetched_count = 0

        logger.debug(f"Fetching series from broadcaster's sermons (limit: {limit})")

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
                    # Check for series information in various possible fields
                    series_info = sermon.get('series')
                    if series_info:
                        if isinstance(series_info, dict):
                            series_name = series_info.get('displayName') or series_info.get('name')
                        else:
                            series_name = str(series_info)

                        if series_name and series_name.strip():
                            series_names.add(series_name.strip())

                    # Also check subtitle field which sometimes contains series info
                    subtitle = sermon.get('subtitle')
                    if subtitle and subtitle.strip() and len(subtitle.strip()) > 3:
                        # Only include if it looks like a series name (not too short)
                        series_names.add(subtitle.strip())

                    fetched_count += 1

                    if fetched_count >= limit:
                        break

                if not data.get('next') or fetched_count >= limit:
                    break

                params['page'] += 1

            except Exception as e:
                logger.error(f"Error fetching sermon data: {e}")
                break

        series_list = sorted(list(series_names))
        logger.debug(f"Found {len(series_list)} unique series")
        return series_list

    except Exception as e:
        logger.error(f"Error retrieving series: {e}")
        return []


def process_year(year, no_upload=False):
    """Legacy bulk processor. Prefer cli_main() with --year for new code."""
    sermons = get_sermons_in_year(year)
    if not sermons:
        logger.warning("No sermons found for year")
        return
    if input(f"Process all {len(sermons)} sermons from {year}? (y/N): ").lower() != 'y':
        return
    for s in sermons:
        process_single_sermon(s['sermonID'], no_upload=no_upload, output_dir=None,
                             save_original_audio=None, save_transcript=None)


def process_date_range(start_date, end_date, no_upload=False):
    sermons = get_sermons_in_date_range(start_date, end_date)
    if not sermons:
        logger.warning("No sermons found in date range")
        return
    if input(f"Process all {len(sermons)} sermons? (y/N): ").lower() != 'y':
        return
    for s in sermons:
        process_single_sermon(s['sermonID'], no_upload=no_upload, output_dir=None,
                             save_original_audio=None, save_transcript=None)


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


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "SermonAudio Processor - Process, create, and manage sermons with AI-powered enhancement. "
            "Use subcommands for different operations."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Global options that apply to all subcommands
    p.add_argument('--config', default=CONFIG_PATH, help='Alternate config file')
    p.add_argument('-v', '--verbose', action='store_true', help='Verbose debug output')
    p.add_argument('--dry-run', action='store_true', help='Skip remote updates')
    p.add_argument('--auto-yes', action='store_true', help='Skip confirmation prompts')

    # Create subcommands
    subparsers = p.add_subparsers(dest='command', help='Available commands')

    # NEW SERMON subcommand
    new_sermon = subparsers.add_parser(
        'new-sermon',
        help='Create a new sermon from audio file',
        description='Process an audio file and create a new sermon with AI-generated metadata'
    )
    new_sermon.add_argument('audio_file', help='Path to audio file')
    new_sermon.add_argument('--speaker', required=True, help='Speaker name')
    new_sermon.add_argument('--date', required=True, help='Recording date (YYYY-MM-DD)')
    new_sermon.add_argument('--event-type', default='Sunday Service', help='Event type')
    new_sermon.add_argument('--bible-text', help='Bible reference text')
    new_sermon.add_argument('--title', help='Sermon title (will be generated if not provided)')
    new_sermon.add_argument('--subtitle', help='Sermon subtitle')
    new_sermon.add_argument('--description', help='Sermon description (will be generated if not provided)')
    new_sermon.add_argument('--hashtags', help='Hashtags/keywords (will be generated if not provided)')
    new_sermon.add_argument('--skip-transcription', action='store_true',
                          help='Skip audio transcription (faster but less accurate metadata)')
    new_sermon.add_argument('--whisper-model', default='base',
                          choices=['tiny', 'base', 'small', 'medium', 'large'],
                          help='Whisper model size for transcription (default: base)')

    # SERMON UPDATE subcommand
    update_sermon = subparsers.add_parser(
        'sermon-update',
        help='Update existing sermons',
        description='Process existing sermons with audio enhancement and metadata updates'
    )
    update_sermon.add_argument('--sermon-id', help='Process a single sermon ID')
    update_sermon.add_argument('--limit', type=int, help='Max sermons to process')
    update_sermon.add_argument('--since-days', type=int, help='Preached after N days ago')
    update_sermon.add_argument('--date-range', nargs=2, metavar=('START', 'END'),
                              help='Date range YYYY-MM-DD YYYY-MM-DD')
    update_sermon.add_argument('--year', type=int, help='Process entire year')
    update_sermon.add_argument('--years', help='Multiple years: 2021,2023 or 2020-2022')
    update_sermon.add_argument('--no-upload', action='store_true', help='Skip upload')
    update_sermon.add_argument('--output-dir', help='Directory to store processed files')
    update_sermon.add_argument('--save-original-audio', action='store_true',
                              help='Save original audio')
    update_sermon.add_argument('--no-save-original-audio', action='store_true',
                              help='Skip saving original audio')
    update_sermon.add_argument('--save-transcript', action='store_true',
                              help='Save transcript as text file')
    update_sermon.add_argument('--no-save-transcript', action='store_true',
                              help='Skip saving transcript')

    # Add filter arguments to sermon-update
    filt = update_sermon.add_argument_group('Sermon Filters')
    for cli_name, (_api, kind, help_txt) in SERMON_FILTER_ARG_MAP.items():
        arg = f"--{cli_name.replace('_', '-')}"
        if kind in ('flag', 'negflag'):
            filt.add_argument(arg, action='store_true', help=help_txt)
        else:
            numeric_names = {
                'page','page_size','chapter','chapter_end','verse','verse_end','year','month','day',
                'speaker_id','collection_id','audio_min_duration','audio_max_duration'
            }
            typ = (
                int if (kind is int or 'duration' in cli_name or cli_name in numeric_names)
                else str
            )
            filt.add_argument(arg, type=typ, help=help_txt)

    # METADATA UPDATE subcommand
    metadata_update = subparsers.add_parser(
        'metadata-update',
        help='Update only metadata for existing sermons',
        description='Update descriptions and hashtags with AI validation, skip audio processing'
    )
    metadata_update.add_argument('--sermon-id', help='Process a single sermon ID')
    metadata_update.add_argument('--limit', type=int, help='Max sermons to process')
    metadata_update.add_argument('--since-days', type=int, help='Preached after N days ago')
    metadata_update.add_argument('--date-range', nargs=2, metavar=('START', 'END'),
                                help='Date range YYYY-MM-DD YYYY-MM-DD')
    metadata_update.add_argument('--year', type=int, help='Process entire year')
    metadata_update.add_argument('--years', help='Multiple years: 2021,2023 or 2020-2022')
    metadata_update.add_argument('--force-description', action='store_true',
                                help='Force update description even if exists')
    metadata_update.add_argument('--force-hashtags', action='store_true',
                                help='Force update hashtags even if exists')

    # Add filter arguments to metadata-update
    meta_filt = metadata_update.add_argument_group('Sermon Filters')
    for cli_name, (_api, kind, help_txt) in SERMON_FILTER_ARG_MAP.items():
        arg = f"--{cli_name.replace('_', '-')}"
        if kind in ('flag', 'negflag'):
            meta_filt.add_argument(arg, action='store_true', help=help_txt)
        else:
            numeric_names = {
                'page','page_size','chapter','chapter_end','verse','verse_end','year','month','day',
                'speaker_id','collection_id','audio_min_duration','audio_max_duration'
            }
            typ = (
                int if (kind is int or 'duration' in cli_name or cli_name in numeric_names)
                else str
            )
            meta_filt.add_argument(arg, type=typ, help=help_txt)

    # VALIDATION subcommand
    validation = subparsers.add_parser(
        'validation',
        help='Validate sermon descriptions',
        description='Validate existing descriptions and optionally regenerate poor quality ones'
    )
    validation.add_argument('--validate-descriptions', action='store_true',
                           help='Validate existing descriptions without processing sermons')
    validation.add_argument('--validate-and-regenerate', action='store_true',
                           help='Validate descriptions and regenerate those that fail')
    validation.add_argument('--validation-report', action='store_true',
                           help='Generate detailed validation report')
    validation.add_argument('--export-validation-csv', type=str, metavar='FILENAME',
                           help='Export validation results to CSV file')
    validation.add_argument('--export-validation-json', type=str, metavar='FILENAME',
                           help='Export detailed validation results to JSON file')
    validation.add_argument('--validation-sermon-ids', type=str,
                           help='Comma-separated sermon IDs for validation')
    validation.add_argument('--limit', type=int, help='Max sermons to validate')

    # LIST subcommand
    list_sermons = subparsers.add_parser(
        'list',
        help='List sermons without processing',
        description='Search and list sermons based on filters'
    )
    list_sermons.add_argument('--limit', type=int, help='Max sermons to list')
    list_sermons.add_argument('--since-days', type=int, help='Preached after N days ago')
    list_sermons.add_argument('--date-range', nargs=2, metavar=('START', 'END'),
                             help='Date range YYYY-MM-DD YYYY-MM-DD')
    list_sermons.add_argument('--year', type=int, help='List entire year')
    list_sermons.add_argument('--years', help='Multiple years: 2021,2023 or 2020-2022')

    # Add filter arguments to list
    list_filt = list_sermons.add_argument_group('Sermon Filters')
    for cli_name, (_api, kind, help_txt) in SERMON_FILTER_ARG_MAP.items():
        arg = f"--{cli_name.replace('_', '-')}"
        if kind in ('flag', 'negflag'):
            list_filt.add_argument(arg, action='store_true', help=help_txt)
        else:
            numeric_names = {
                'page','page_size','chapter','chapter_end','verse','verse_end','year','month','day',
                'speaker_id','collection_id','audio_min_duration','audio_max_duration'
            }
            typ = (
                int if (kind is int or 'duration' in cli_name or cli_name in numeric_names)
                else str
            )
            list_filt.add_argument(arg, type=typ, help=help_txt)

    return p


def confirm(prompt: str, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    return input(f"{prompt} [y/N]: ").strip().lower() == 'y'


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
    parser = build_arg_parser()
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
    elif args.command == 'sermon-update':
        handle_sermon_update(args)
    elif args.command == 'metadata-update':
        handle_metadata_update(args)
    elif args.command == 'validation':
        handle_validation(args)
    elif args.command == 'list':
        handle_list_sermons(args)
    else:
        parser.error(f"Unknown command: {args.command}")


def handle_new_sermon(args):
    """Handle new-sermon subcommand."""
    console_print("🎵 Creating new sermon from audio file...")

    success = process_new_sermon(
        audio_file=args.audio_file,
        speaker_name=args.speaker,
        recorded_date=args.date,
        event_type=args.event_type,
        bible_text=args.bible_text,
        title=args.title,
        subtitle=args.subtitle,
        description=args.description,
        hashtags=args.hashtags,
        dry_run=args.dry_run,
        skip_transcription=args.skip_transcription,
        whisper_model=args.whisper_model
    )

    if success:
        console_print("✅ New sermon created successfully!")
    else:
        console_print("❌ Failed to create new sermon", "error")
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
            console_print("⚠️  No validator LLM configured, using primary provider for validation", "warning")

        # Parse sermon IDs if provided
        validation_sermon_ids = None
        if args.validation_sermon_ids:
            validation_sermon_ids = [id.strip() for id in args.validation_sermon_ids.split(',') if id.strip()]
            console_print(f"🎯 Validating {len(validation_sermon_ids)} specific sermons")

        # Run validation
        if args.validate_and_regenerate:
            console_print("🔍 Validating descriptions and regenerating failed ones...")
            results = validator.validate_and_regenerate_descriptions(
                sermon_ids=validation_sermon_ids,
                limit=getattr(args, 'limit', None)
            )
        else:
            console_print("🔍 Validating descriptions...")
            results = validator.validate_descriptions(
                sermon_ids=validation_sermon_ids,
                limit=getattr(args, 'limit', None)
            )

        # Export results if requested
        if args.export_validation_csv:
            validator.export_results_csv(results, args.export_validation_csv)
            console_print(f"📊 Validation results exported to {args.export_validation_csv}")

        if args.export_validation_json:
            validator.export_results_json(results, args.export_validation_json)
            console_print(f"📊 Detailed validation results exported to {args.export_validation_json}")

        if args.validation_report:
            validator.print_validation_report(results)

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
    # Set defaults for missing attributes that might not exist in subcommand args
    if not hasattr(args, 'validate_descriptions'):
        args.validate_descriptions = False
    if not hasattr(args, 'validate_and_regenerate'):
        args.validate_and_regenerate = False
    if not hasattr(args, 'validation_report'):
        args.validation_report = False
    if not hasattr(args, 'export_validation_csv'):
        args.export_validation_csv = None
    if not hasattr(args, 'export_validation_json'):
        args.export_validation_json = None
    if not hasattr(args, 'validation_sermon_ids'):
        args.validation_sermon_ids = None
    if not hasattr(args, 'no_upload'):
        args.no_upload = False
    if not hasattr(args, 'output_dir'):
        args.output_dir = None
    if not hasattr(args, 'save_original_audio'):
        args.save_original_audio = False
    if not hasattr(args, 'no_save_original_audio'):
        args.no_save_original_audio = False
    if not hasattr(args, 'save_transcript'):
        args.save_transcript = False
    if not hasattr(args, 'no_save_transcript'):
        args.no_save_transcript = False

    if args.sermon_id:
        if not confirm(f"Process sermon {args.sermon_id}?", args.auto_yes):
            console_print("Cancelled")
            return
        console_print(f"Processing sermon {args.sermon_id}...")

        # Handle metadata-only and skip-audio flags
        skip_audio = args.metadata_only or args.skip_audio

        # Determine save_original_audio setting
        if args.no_save_original_audio:
            save_original_audio = False
        elif args.save_original_audio:
            save_original_audio = True
        else:
            save_original_audio = None  # Use config default

        # Determine save_transcript setting
        if args.no_save_transcript:
            save_transcript = False
        elif args.save_transcript:
            save_transcript = True
        else:
            save_transcript = None  # Use config default

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
    if args.year:
        if not hasattr(args, 'preached_year') or args.preached_year in (None, 0):
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
            if args.limit and len(combined) >= args.limit:
                combined = combined[:args.limit]
                break
        sermons = combined
    else:
        sermons = fetch_sermons(params, max_results=args.limit)
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
    skip_audio = args.metadata_only or args.skip_audio

    # Determine save_original_audio setting
    if args.no_save_original_audio:
        save_original_audio = False
    elif args.save_original_audio:
        save_original_audio = True
    else:
        save_original_audio = None  # Use config default

    # Determine save_transcript setting
    if args.no_save_transcript:
        save_transcript = False
    elif args.save_transcript:
        save_transcript = True
    else:
        save_transcript = None  # Use config default

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
                force_description=args.force_description,
                force_hashtags=args.force_hashtags,
                no_metadata=args.no_metadata,
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


if __name__ == '__main__':  # pragma: no cover
    try:
        cli_main()
    except Exception as top_e:  # noqa: BLE001
        console_print(f"Fatal error: {top_e}", "error")
        traceback.print_exc()
        sys.exit(1)
