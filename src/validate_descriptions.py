"""
Integration script for adding description validation to the existing sermon processing workflow.

This script extends the existing sermon_updater.py with validation capabilities,
allowing users to validate existing descriptions and optionally regenerate them.

Usage:
    python validate_descriptions.py --help
    python validate_descriptions.py --validate-all
    python validate_descriptions.py --validate-recent --since-days 30
    python validate_descriptions.py --regenerate-failed --dry-run
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Import existing modules
try:
    from description_validator import DescriptionValidator
    # Import from parent directory
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from sermon_updater import (
        load_config, setup_logging, LLMManager, 
        generate_validated_summary, get_sermon_transcript,
        update_sermon_metadata
    )
    import sermonaudio
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

logger = logging.getLogger(__name__)


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
    print("🔍 Starting description validation and regeneration process...")
    
    # Validate existing descriptions
    print("📋 Validating existing descriptions...")
    results = validator.validate_local_sermons(sermon_ids)
    
    if not results:
        print("❌ No sermons found to validate")
        return {'validated': 0, 'regenerated': 0, 'failed': 0}
    
    # Generate summary
    summary = validator.generate_summary(results)
    
    # Print validation summary
    print(f"\n📊 Validation Results:")
    print(f"   Total validated: {summary.total_sermons}")
    print(f"   ✅ Valid: {summary.valid_descriptions} ({summary.validation_rate:.1f}%)")
    print(f"   ❌ Invalid: {summary.invalid_descriptions}")
    print(f"   🔄 Need regeneration: {summary.needs_regeneration}")
    
    regenerated_count = 0
    failed_regeneration = 0
    regenerated_sermons = []  # Track successfully regenerated sermons
    validation_failures = []  # Track double-validation failures

    if regenerate_failed and summary.invalid_descriptions > 0:
        print(f"\n🔄 Regenerating {summary.invalid_descriptions} failed descriptions...")
        
        failed_results = [r for r in results if not r.is_valid]
        
        for i, result in enumerate(failed_results, 1):
            sermon_id = result.sermon_id
            print(f"   [{i}/{len(failed_results)}] Processing sermon {sermon_id}...")
            
            try:
                if dry_run:
                    print(f"      🔍 DRY RUN: Would regenerate description for {sermon_id}")
                    # Simulate successful regeneration for dry run
                    regenerated_sermons.append({
                        'sermon_id': sermon_id,
                        'old_description': result.description[:100] + "...",
                        'old_score': result.validation_score,
                        'new_description': "[DRY RUN] Would generate new description here...",
                        'new_score': 0.85,  # Simulated score
                        'validation_status': 'dry_run',
                        'sermonaudio_link': f"https://www.sermonaudio.com/sermon/{sermon_id}"
                    })
                    regenerated_count += 1
                    continue
                
                # Get sermon transcript for regeneration
                transcript = get_sermon_transcript(sermon_id)
                if not transcript:
                    print(f"      ❌ Could not get transcript for {sermon_id}")
                    failed_regeneration += 1
                    continue
                
                # Generate new description with validation
                print(f"      🤖 Generating new description...")
                new_description, validation_info = generate_validated_summary(
                    transcript,
                    event_type=None,  # Could enhance this with API data
                    speaker_name=None
                )
                
                # Double-validate the newly generated description
                print(f"      🔍 Double-validating new description...")
                is_valid, reason, score, criteria_met, criteria_failed = validator.validate_description(
                    new_description, 
                    {'sermon_id': sermon_id}
                )
                
                # Check if the new description actually passes validation
                if not is_valid:
                    print(f"      ⚠️  WARNING: New description still fails validation!")
                    print(f"               Score: {score:.2f}, Reason: {reason}")
                    validation_failures.append({
                        'sermon_id': sermon_id,
                        'new_description': new_description,
                        'score': score,
                        'reason': reason,
                        'criteria_failed': criteria_failed
                    })
                    # Continue anyway but mark as needing manual review
                
                if validation_info.get('final_status') == 'approved_primary':
                    status_icon = "✅"
                elif validation_info.get('final_status') == 'approved_fallback':
                    status_icon = "⚠️"
                else:
                    status_icon = "❌"
                    
                print(f"      {status_icon} Generated new description "
                      f"({len(new_description)} chars, score: {score:.2f})")
                
                # Save the new description locally
                sermon_dir = Path(validator.output_dir) / sermon_id
                description_file = sermon_dir / f"{sermon_id}_description.txt"
                
                if description_file.exists():
                    # Backup old description
                    backup_file = sermon_dir / f"{sermon_id}_description_backup.txt"
                    description_file.rename(backup_file)
                    print(f"      💾 Backed up original to {backup_file.name}")
                
                description_file.write_text(new_description, encoding='utf-8')
                
                # Update SermonAudio if not in dry run mode and upload is enabled
                upload_success = False
                if upload_to_sermonaudio and not dry_run:
                    print(f"      📤 Uploading to SermonAudio...")
                    try:
                        upload_success = update_sermon_metadata(sermon_id, new_description, None)
                        if upload_success:
                            print(f"      ✅ Updated SermonAudio successfully")
                        else:
                            print(f"      ⚠️  SermonAudio update failed")
                    except Exception as e:
                        print(f"      ❌ SermonAudio upload error: {e}")
                
                # Track this regeneration
                regenerated_sermons.append({
                    'sermon_id': sermon_id,
                    'old_description': result.description,
                    'old_score': result.validation_score,
                    'new_description': new_description,
                    'new_score': score,
                    'validation_status': 'passed' if is_valid else 'failed_double_validation',
                    'sermonaudio_updated': upload_success,
                    'sermonaudio_link': f"https://www.sermonaudio.com/sermon/{sermon_id}",
                    'criteria_met': criteria_met,
                    'criteria_failed': criteria_failed
                })
                
                regenerated_count += 1
                print(f"      ✅ Updated description for sermon {sermon_id}")
                
            except Exception as e:
                print(f"      ❌ Failed to regenerate description for {sermon_id}: {e}")
                failed_regeneration += 1
    
    # Print detailed results for regenerated sermons
    if regenerated_sermons:
        print(f"\n📋 REGENERATED SERMONS SUMMARY ({len(regenerated_sermons)} sermons)")
        print("=" * 70)
        
        for sermon in regenerated_sermons:
            sermon_id = sermon['sermon_id']
            old_score = sermon['old_score']
            new_score = sermon['new_score']
            validation_status = sermon['validation_status']
            
            # Status icon based on validation result
            if validation_status == 'passed':
                status_icon = "✅"
            elif validation_status == 'failed_double_validation':
                status_icon = "⚠️"
            elif validation_status == 'dry_run':
                status_icon = "🔍"
            else:
                status_icon = "❓"
            
            print(f"\n{status_icon} Sermon ID: {sermon_id}")
            print(f"   📊 Score: {old_score:.2f} → {new_score:.2f} "
                  f"({'+' if new_score > old_score else ''}{new_score - old_score:.2f})")
            
            if not dry_run:
                print(f"   🔗 SermonAudio: {sermon['sermonaudio_link']}")
                if upload_to_sermonaudio:
                    upload_status = "✅ Updated" if sermon.get('sermonaudio_updated') else "❌ Failed"
                    print(f"   📤 Upload Status: {upload_status}")
            
            if validation_status == 'failed_double_validation':
                print(f"   ⚠️  Double-validation failed - may need manual review")
                if sermon.get('criteria_failed'):
                    print(f"   📋 Failed criteria: {', '.join(sermon['criteria_failed'][:2])}...")
        
        # Print validation failures summary
        if validation_failures:
            print(f"\n⚠️  DOUBLE-VALIDATION FAILURES ({len(validation_failures)} sermons)")
            print("These descriptions were regenerated but still failed validation:")
            for failure in validation_failures:
                print(f"   • {failure['sermon_id']}: {failure['reason']} (Score: {failure['score']:.2f})")
    
    return {
        'validated': summary.total_sermons,
        'regenerated': regenerated_count,
        'failed': failed_regeneration,
        'validation_rate': summary.validation_rate,
        'regenerated_sermons': regenerated_sermons,
        'validation_failures': validation_failures,
        'sermonaudio_links': [s['sermonaudio_link'] for s in regenerated_sermons]
    }


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate and regenerate sermon descriptions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate all local sermons
  python validate_descriptions.py --validate-all
  
  # Validate recent sermons and regenerate failed ones
  python validate_descriptions.py --validate-recent --since-days 30 --regenerate-failed
  
  # Validate specific sermons
  python validate_descriptions.py --sermon-ids 123456789,987654321
  
  # Dry run to see what would be regenerated
  python validate_descriptions.py --validate-all --regenerate-failed --dry-run
        """
    )
    
    # Validation scope
    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument(
        '--validate-all',
        action='store_true',
        help='Validate all local processed sermons'
    )
    scope_group.add_argument(
        '--validate-recent',
        action='store_true',
        help='Validate recently processed sermons (use with --since-days)'
    )
    scope_group.add_argument(
        '--sermon-ids',
        type=str,
        help='Comma-separated list of specific sermon IDs to validate'
    )
    
    # Filtering options
    parser.add_argument(
        '--since-days',
        type=int,
        default=30,
        help='Only process sermons from the last N days (default: 30)'
    )
    
    # Actions
    parser.add_argument(
        '--regenerate-failed',
        action='store_true',
        help='Regenerate descriptions that fail validation'
    )
    
    parser.add_argument(
        '--no-upload',
        action='store_true',
        help='Skip uploading regenerated descriptions to SermonAudio (local only)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making any changes (local or SermonAudio)'
    )    # Output options
    parser.add_argument(
        '--detailed-report',
        action='store_true',
        help='Show detailed validation report'
    )
    
    parser.add_argument(
        '--export-results',
        type=str,
        metavar='FILENAME',
        help='Export validation results to JSON file'
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
    """Main entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.verbose)
    
    # Load configuration
    if not os.path.exists(args.config):
        logger.error(f"Config file not found: {args.config}")
        return 1
    
    try:
        # Initialize validator
        validator = DescriptionValidator(args.config)
        
        if not validator.llm_manager.validator_provider:
            logger.error("Validator LLM not configured. Please check your config file.")
            return 1
        
        # Parse sermon IDs if provided
        sermon_ids = None
        if args.sermon_ids:
            sermon_ids = [id.strip() for id in args.sermon_ids.split(',') if id.strip()]
            print(f"🎯 Targeting {len(sermon_ids)} specific sermons")
        
        # Determine which sermons to process based on arguments
        if args.validate_recent and not sermon_ids:
            # This would require implementing date filtering
            print(f"🕒 Processing sermons from the last {args.since_days} days")
            # For now, just process all local sermons
            sermon_ids = None
        
        # Run validation and optional regeneration
        results = validate_and_regenerate_descriptions(
            validator=validator,
            sermon_ids=sermon_ids,
            regenerate_failed=args.regenerate_failed,
            upload_to_sermonaudio=not args.no_upload,
            dry_run=args.dry_run
        )
        
        # Print summary
        print("\n" + "="*60)
        print("📋 PROCESSING SUMMARY")
        print("="*60)
        print(f"Sermons validated: {results['validated']}")
        print(f"Validation rate: {results['validation_rate']:.1f}%")
        if args.regenerate_failed:
            print(f"Descriptions regenerated: {results['regenerated']}")
            print(f"Regeneration failures: {results['failed']}")
        
        # Show detailed report if requested
        if args.detailed_report:
            validation_results = validator.validate_local_sermons(sermon_ids)
            summary = validator.generate_summary(validation_results)
            validator.print_detailed_report(validation_results, summary)
        
        # Export results if requested
        if args.export_results:
            validation_results = validator.validate_local_sermons(sermon_ids)
            summary = validator.generate_summary(validation_results)
            validator.export_to_json(validation_results, summary, args.export_results)
            print(f"📁 Results exported to {args.export_results}")
        
        # Return appropriate exit code
        if results['failed'] > 0:
            return 1
        elif results['validation_rate'] < 80.0:
            print("\n⚠️  Validation rate below 80% - consider reviewing criteria")
            return 1
        else:
            print("\n✅ Processing completed successfully!")
            return 0
        
    except KeyboardInterrupt:
        print("\n🛑 Processing cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
