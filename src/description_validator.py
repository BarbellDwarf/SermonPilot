"""
Description Validation Tool for SermonPilot

This tool validates existing sermon descriptions against predefined criteria to ensure
they meet quality standards. It can be used to audit existing descriptions and
identify those that may need manual review or regeneration.

The DescriptionValidator implementation lives in sermon_updater.py (single
canonical copy); this script provides a standalone CLI over it.

Features:
- Validate descriptions in processed sermon directories
- Batch validation with filtering options
- Detailed reporting with validation scores and reasons
- Export validation results for review

Usage:
    python description_validator.py --help
    python description_validator.py --local-sermons
    python description_validator.py --sermon-ids 123456789,987654321
    python description_validator.py --since-days 30 --export-csv results.csv
    python description_validator.py --local-sermons --detailed-report
"""

import argparse
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


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


def main() -> int:
    """Main entry point for the description validator."""
    parser = build_arg_parser()
    args = parser.parse_args()

    # Set up logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        project_root = Path(__file__).resolve().parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from sermon_updater import DescriptionValidator, load_config

        if not Path(args.config).exists():
            logger.error("Config file not found: %s", args.config)
            return 1

        config = load_config(args.config)
        validator = DescriptionValidator(config)

        if not validator.llm_manager.validator_provider:
            logger.warning("No validator LLM configured, using primary provider for validation")

        # Parse sermon IDs if provided
        sermon_ids = None
        if args.sermon_ids:
            sermon_ids = [sid.strip() for sid in args.sermon_ids.split(',') if sid.strip()]
            logger.info("Filtering to %d specific sermon IDs", len(sermon_ids))

        # Validate sermons
        if args.local_sermons:
            results = validator.validate_local_sermons(sermon_ids)
        elif args.api_sermons:
            if not sermon_ids:
                logger.error("--api-sermons requires --sermon-ids to be specified")
                return 1
            logger.warning("API validation not implemented; validating local copies instead")
            results = validator.validate_local_sermons(sermon_ids)
        else:
            logger.error("Must specify either --local-sermons or --api-sermons")
            return 1

        if not results:
            logger.warning("No sermons found to validate")
            return 0

        # Generate summary
        summary = validator.generate_summary(results)

        # Print basic summary
        print("\n✅ Validation Complete!")
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
        logger.error("Validation failed: %s", e)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
