#!/usr/bin/env python3
"""
Quick test script to validate CLI argument parsing for sermon metadata processing.
"""

import argparse
import sys
from pathlib import Path

# Add the main directory to path so we can import
sys.path.insert(0, str(Path(__file__).parent))

def setup_parser():
    """Extract just the argument parser setup from sermon_updater.py"""
    parser = argparse.ArgumentParser(description='SermonAudio.com automated audio processor')
    
    # Core arguments
    parser.add_argument('--sermon-id', type=str, help='Process a single sermon by ID')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    
    # New metadata processing arguments
    parser.add_argument('--metadata-only', action='store_true', 
                       help='Only process metadata (description/hashtags), skip audio processing entirely')
    parser.add_argument('--skip-audio', action='store_true', 
                       help='Skip audio processing, but still allow other operations')
    parser.add_argument('--force-description', action='store_true', 
                       help='Force update description even if one exists')
    parser.add_argument('--force-hashtags', action='store_true', 
                       help='Force update hashtags even if they exist')
    parser.add_argument('--no-metadata', action='store_true', 
                       help='Skip all metadata processing (description and hashtags)')
    
    return parser

def test_cli_combinations():
    """Test various CLI argument combinations"""
    parser = setup_parser()
    
    test_cases = [
        # Basic functionality
        ['--sermon-id', '12345'],
        ['--sermon-id', '12345', '--dry-run'],
        ['--sermon-id', '12345', '--verbose'],
        
        # Metadata-only processing
        ['--sermon-id', '12345', '--metadata-only'],
        ['--sermon-id', '12345', '--metadata-only', '--dry-run'],
        
        # Skip audio but allow other processing
        ['--sermon-id', '12345', '--skip-audio'],
        
        # Force metadata updates
        ['--sermon-id', '12345', '--force-description'],
        ['--sermon-id', '12345', '--force-hashtags'],
        ['--sermon-id', '12345', '--force-description', '--force-hashtags'],
        
        # Skip metadata entirely
        ['--sermon-id', '12345', '--no-metadata'],
        
        # Combinations
        ['--sermon-id', '12345', '--skip-audio', '--force-description'],
        ['--sermon-id', '12345', '--metadata-only', '--force-hashtags', '--verbose'],
    ]
    
    print("Testing CLI argument combinations:\n")
    
    for i, args in enumerate(test_cases, 1):
        try:
            parsed = parser.parse_args(args)
            
            # Determine skip_audio logic
            skip_audio = parsed.metadata_only or parsed.skip_audio
            
            print(f"Test {i:2d}: {' '.join(args)}")
            print(f"         Parsed: sermon_id={parsed.sermon_id}, dry_run={parsed.dry_run}, verbose={parsed.verbose}")
            print(f"         Metadata: metadata_only={parsed.metadata_only}, skip_audio={skip_audio}, force_description={parsed.force_description}")
            print(f"         Hashtags: force_hashtags={parsed.force_hashtags}, no_metadata={parsed.no_metadata}")
            print()
            
        except Exception as e:
            print(f"Test {i:2d}: FAILED - {e}")
            print()

if __name__ == "__main__":
    test_cli_combinations()
