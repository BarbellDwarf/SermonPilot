"""
Description Validation Tool for SermonAudio Processor

This tool validates existing sermon descriptions against predefined criteria to ensure
they meet quality standards. It can be used to audit existing descriptions and 
identify those that may need manual review or regeneration.

Features:
- Validate descriptions in processed sermon directories
- Validate descriptions directly from SermonAudio API
- Batch validation with filtering options
- Detailed reporting with validation scores and reasons
- Export validation results for review
- Integration with existing LLM validation system

Usage:
    python description_validator.py --help
    python description_validator.py --local-sermons
    python description_validator.py --sermon-ids 123456789,987654321
    python description_validator.py --since-days 30 --export-csv results.csv
    python description_validator.py --local-sermons --detailed-report
"""

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from llm_manager import LLMManager, migrate_legacy_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


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
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the validator with configuration."""
        self.config_path = config_path
        self.config = self._load_config()
        self.llm_manager = LLMManager(self.config)
        self.validation_criteria = self._get_validation_criteria()
        self.output_dir = self.config.get('output_directory', 'processed_sermons')
        
        # Validation thresholds
        self.min_length = 50
        self.max_length = 1600
        self.regeneration_threshold = 0.6  # Below this score suggests regeneration
        
    def _load_config(self) -> dict[str, Any]:
        """Load and migrate configuration."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
            
        return migrate_legacy_config(config)
    
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
    
    def validate_description(self, description: str, context: dict[str, Any] = None) -> tuple[bool, str, float, list[str], list[str]]:
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
            response = self.llm_manager.validator_provider.chat([
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
    
    def validate_local_sermons(self, sermon_ids: list[str] | None = None) -> list[ValidationResult]:
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
            
            # Look for hashtags file to get title/speaker info
            hashtags_file = sermon_dir / f"{sermon_id}_hashtags.txt"
            if hashtags_file.exists():
                hashtags = hashtags_file.read_text(encoding='utf-8').strip()
                # Hashtags sometimes contain title info, but let's keep it simple for now
                
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
                validated_at=datetime.now().isoformat(),
                source="local"
            )
            
        except Exception as e:
            logger.error(f"Error reading description for sermon {sermon_id}: {e}")
            return None
    
    def validate_api_sermons(self, sermon_ids: list[str]) -> list[ValidationResult]:
        """Validate descriptions directly from SermonAudio API."""
        # This would require implementing SermonAudio API integration
        # For now, return empty list with a note
        logger.warning("API validation not yet implemented. Use --local-sermons for now.")
        return []
    
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
        print(f"\n📈 SUMMARY:")
        print(f"   Total Sermons Validated: {summary.total_sermons}")
        print(f"   ✅ Valid Descriptions: {summary.valid_descriptions} ({summary.validation_rate:.1f}%)")
        print(f"   ❌ Invalid Descriptions: {summary.invalid_descriptions}")
        print(f"   🔄 Need Regeneration: {summary.needs_regeneration}")
        print(f"   📊 Average Score: {summary.average_score:.2f}/1.0")
        
        # Criteria performance
        print(f"\n📋 CRITERIA PERFORMANCE:")
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
        export_data = {
            'summary': asdict(summary),
            'validation_criteria': self.validation_criteria,
            'results': [asdict(result) for result in results],
            'exported_at': datetime.now().isoformat(),
            'validator_config': {
                'min_length': self.min_length,
                'max_length': self.max_length,
                'regeneration_threshold': self.regeneration_threshold
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Detailed results exported to {filename}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate sermon descriptions against quality criteria",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate all local processed sermons
  python description_validator.py --local-sermons
  
  # Validate specific sermons by ID
  python description_validator.py --local-sermons --sermon-ids 123456789,987654321
  
  # Validate and export detailed report
  python description_validator.py --local-sermons --detailed-report --export-json results.json
  
  # Validate and export CSV for spreadsheet analysis
  python description_validator.py --local-sermons --export-csv validation_results.csv
  
  # Use different config file
  python description_validator.py --config my_config.yaml --local-sermons
        """
    )
    
    # Data sources
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        '--local-sermons',
        action='store_true',
        help='Validate descriptions from local processed sermon directories'
    )
    source_group.add_argument(
        '--api-sermons',
        action='store_true',
        help='Validate descriptions directly from SermonAudio API (not yet implemented)'
    )
    
    # Filtering options
    parser.add_argument(
        '--sermon-ids',
        type=str,
        help='Comma-separated list of specific sermon IDs to validate'
    )
    
    parser.add_argument(
        '--since-days',
        type=int,
        help='Only validate sermons processed in the last N days'
    )
    
    # Output options
    parser.add_argument(
        '--detailed-report',
        action='store_true',
        help='Print detailed validation report to console'
    )
    
    parser.add_argument(
        '--export-csv',
        type=str,
        metavar='FILENAME',
        help='Export validation results to CSV file'
    )
    
    parser.add_argument(
        '--export-json',
        type=str,
        metavar='FILENAME',
        help='Export detailed validation results to JSON file'
    )
    
    # Configuration
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser


def main():
    """Main entry point for the description validator."""
    parser = build_arg_parser()
    args = parser.parse_args()
    
    # Set up logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize validator
        validator = DescriptionValidator(args.config)
        
        # Check if validator is properly configured
        if not validator.llm_manager.validator_provider:
            logger.error("Validator LLM not configured. Please check your config.yaml file.")
            logger.info("Add a 'validator' section under 'llm' in your config file.")
            return 1
        
        # Parse sermon IDs if provided
        sermon_ids = None
        if args.sermon_ids:
            sermon_ids = [id.strip() for id in args.sermon_ids.split(',') if id.strip()]
            logger.info(f"Filtering to {len(sermon_ids)} specific sermon IDs")
        
        # Validate sermons
        if args.local_sermons:
            results = validator.validate_local_sermons(sermon_ids)
        elif args.api_sermons:
            if not sermon_ids:
                logger.error("--api-sermons requires --sermon-ids to be specified")
                return 1
            results = validator.validate_api_sermons(sermon_ids)
        else:
            logger.error("Must specify either --local-sermons or --api-sermons")
            return 1
        
        if not results:
            logger.warning("No sermons found to validate")
            return 0
        
        # Generate summary
        summary = validator.generate_summary(results)
        
        # Print basic summary
        print(f"\n✅ Validation Complete!")
        print(f"   Validated {summary.total_sermons} sermons")
        print(f"   {summary.valid_descriptions} valid ({summary.validation_rate:.1f}%)")
        print(f"   {summary.invalid_descriptions} invalid")
        print(f"   {summary.needs_regeneration} need regeneration")
        print(f"   Average score: {summary.average_score:.2f}/1.0")
        
        # Print detailed report if requested
        if args.detailed_report:
            validator.print_detailed_report(results, summary)
        
        # Export results if requested
        if args.export_csv:
            validator.export_to_csv(results, args.export_csv)
        
        if args.export_json:
            validator.export_to_json(results, summary, args.export_json)
        
        # Return non-zero exit code if validation issues found
        return 1 if summary.invalid_descriptions > 0 else 0
        
    except KeyboardInterrupt:
        logger.info("Validation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
