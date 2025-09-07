"""
CLI Argument Parser Module

Extracted from sermon_updater.py to reduce complexity.
Handles command line argument parsing for the SermonAudio Processor.
"""

import argparse
from typing import Any


class CLIParser:
    """Handles command line argument parsing for SermonAudio Processor."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
    
    def build_parser(self) -> argparse.ArgumentParser:
        """Build and configure the main argument parser."""
        p = argparse.ArgumentParser(
            description=(
                "SermonAudio Processor - Process, create, and manage sermons with AI-powered enhancement. "
                "Use subcommands for different operations."
            ),
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )

        # Global options that apply to all subcommands
        self._add_global_options(p)
        
        # Create subcommands
        subparsers = p.add_subparsers(dest='command', help='Available commands')
        
        # Add individual subcommands
        self._add_new_sermon_command(subparsers)
        self._add_process_command(subparsers)
        self._add_list_command(subparsers)
        self._add_validation_command(subparsers)
        
        return p
    
    def _add_global_options(self, parser: argparse.ArgumentParser):
        """Add global options that apply to all subcommands."""
        parser.add_argument('--config', default=self.config_path, help='Alternate config file')
        parser.add_argument('-v', '--verbose', action='store_true', help='Verbose debug output')
        parser.add_argument('--dry-run', action='store_true', help='Skip remote updates')
        parser.add_argument('--auto-yes', action='store_true', help='Skip confirmation prompts')
    
    def _add_new_sermon_command(self, subparsers):
        """Add new-sermon subcommand."""
        new_sermon = subparsers.add_parser(
            'new-sermon',
            help='Create a new sermon from audio file',
            description='Process an audio file and create a new sermon with AI-generated metadata'
        )
        
        # Required arguments
        new_sermon.add_argument('audio_file', help='Path to audio file')
        new_sermon.add_argument('--speaker', required=True, help='Speaker name')
        new_sermon.add_argument('--date', required=True, help='Recording date (YYYY-MM-DD)')
        
        # Optional metadata
        new_sermon.add_argument('--event-type', default='Sunday Service', help='Event type')
        new_sermon.add_argument('--bible-text', help='Bible reference text')
        new_sermon.add_argument('--title', help='Sermon title (will be generated if not provided)')
        new_sermon.add_argument('--subtitle', help='Sermon subtitle')
        new_sermon.add_argument('--description', help='Sermon description (will be generated if not provided)')
        new_sermon.add_argument('--hashtags', help='Hashtags/keywords (will be generated if not provided)')
        
        # Processing options
        new_sermon.add_argument('--skip-transcription', action='store_true',
                               help='Skip transcription generation')
        new_sermon.add_argument('--skip-audio-processing', action='store_true',
                               help='Skip audio enhancement')
        new_sermon.add_argument('--output-dir', help='Output directory for processed files')
        new_sermon.add_argument('--save-original-audio', action='store_true',
                               help='Save original audio file')
        new_sermon.add_argument('--no-save-original-audio', action='store_true',
                               help='Do not save original audio file')
        new_sermon.add_argument('--save-transcript', action='store_true',
                               help='Save transcript file')
    
    def _add_process_command(self, subparsers):
        """Add process subcommand for processing existing sermons."""
        process_cmd = subparsers.add_parser(
            'process',
            help='Process existing sermons',
            description='Process and enhance existing sermons from SermonAudio'
        )
        
        # Filtering options
        self._add_sermon_filters(process_cmd)
        
        # Processing options
        process_cmd.add_argument('--no-upload', action='store_true',
                               help='Do not upload processed audio back to SermonAudio')
        process_cmd.add_argument('--force-description', action='store_true',
                               help='Force regeneration of description even if one exists')
        process_cmd.add_argument('--force-hashtags', action='store_true',
                               help='Force regeneration of hashtags even if they exist')
        process_cmd.add_argument('--output-dir', help='Output directory for processed files')
        process_cmd.add_argument('--save-original-audio', action='store_true',
                               help='Save original audio file')
        process_cmd.add_argument('--no-save-original-audio', action='store_true',
                               help='Do not save original audio file')
        process_cmd.add_argument('--save-transcript', action='store_true',
                               help='Save transcript file')
    
    def _add_list_command(self, subparsers):
        """Add list subcommand for listing sermons."""
        list_cmd = subparsers.add_parser(
            'list',
            help='List sermons',
            description='List sermons with filtering options'
        )
        
        # Filtering options
        self._add_sermon_filters(list_cmd)
        
        # List-specific options
        list_cmd.add_argument('--list-only', action='store_true',
                            help='Only list sermons, do not process')
    
    def _add_validation_command(self, subparsers):
        """Add validation subcommand."""
        validation_cmd = subparsers.add_parser(
            'validate',
            help='Validate sermon descriptions',
            description='Validate and optionally regenerate sermon descriptions'
        )
        
        # Validation options
        validation_cmd.add_argument('--validate-descriptions', action='store_true',
                                  help='Validate existing descriptions')
        validation_cmd.add_argument('--validate-and-regenerate', action='store_true',
                                  help='Validate and regenerate failed descriptions')
        validation_cmd.add_argument('--validation-report', action='store_true',
                                  help='Generate detailed validation report')
        validation_cmd.add_argument('--export-validation-csv',
                                  help='Export validation results to CSV file')
        validation_cmd.add_argument('--export-validation-json',
                                  help='Export validation results to JSON file')
        validation_cmd.add_argument('--validation-sermon-ids',
                                  help='Comma-separated list of sermon IDs to validate')
        
        # Filtering for validation
        self._add_sermon_filters(validation_cmd)
    
    def _add_sermon_filters(self, parser: argparse.ArgumentParser):
        """Add common sermon filtering arguments."""
        # Basic filters
        parser.add_argument('--sermon-id', help='Process specific sermon by ID')
        parser.add_argument('--since-days', type=int, help='Process sermons from last N days')
        parser.add_argument('--limit', type=int, default=10, help='Maximum number of sermons to process')
        
        # Date filters
        parser.add_argument('--year', type=int, help='Filter by specific year')
        parser.add_argument('--years', help='Filter by year range (e.g., "2022-2023,2025")')
        parser.add_argument('--date-range', nargs=2, metavar=('START', 'END'),
                          help='Date range in YYYY-MM-DD format')
        
        # Content filters
        parser.add_argument('--event-type', help='Filter by event type')
        parser.add_argument('--speaker-name', help='Filter by speaker name')
        parser.add_argument('--search-keyword', help='Search for keyword in title/description')
        parser.add_argument('--bible-text', help='Filter by Bible text reference')
        parser.add_argument('--language-code', help='Filter by language code')
        parser.add_argument('--series', help='Filter by sermon series')
        
        # Requirements
        parser.add_argument('--require-audio', action='store_true',
                          help='Only process sermons with audio')
        parser.add_argument('--require-video', action='store_true',
                          help='Only process sermons with video')
        parser.add_argument('--require-transcript', action='store_true',
                          help='Only process sermons with transcripts')
        
        # Audio quality filters
        parser.add_argument('--min-duration', type=int, help='Minimum audio duration in seconds')
        parser.add_argument('--max-duration', type=int, help='Maximum audio duration in seconds')
        
        # Sorting
        parser.add_argument('--sort-by', choices=['date', 'title', 'speaker'],
                          default='date', help='Sort results by field')
        parser.add_argument('--sort-order', choices=['asc', 'desc'],
                          default='desc', help='Sort order')


def confirm(prompt: str, auto_yes: bool) -> bool:
    """Helper function for user confirmation prompts."""
    if auto_yes:
        return True
    return input(f"{prompt} [y/N]: ").strip().lower() == 'y'


def parse_years(years_str: str) -> list[int]:
    """Parse years string into list of years.
    
    Supports formats like:
    - "2023" -> [2023]
    - "2022-2024" -> [2022, 2023, 2024]
    - "2022,2024,2025" -> [2022, 2024, 2025]
    - "2022-2023,2025" -> [2022, 2023, 2025]
    """
    years = []
    for part in years_str.split(','):
        part = part.strip()
        if '-' in part:
            start, end = map(int, part.split('-'))
            years.extend(range(start, end + 1))
        else:
            years.append(int(part))
    return years