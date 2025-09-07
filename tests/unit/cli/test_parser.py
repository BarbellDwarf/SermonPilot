"""
Test CLI Parser Module

Tests for the extracted CLI parser functionality.
"""

import pytest
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cli.parser import CLIParser, confirm, parse_years


class TestCLIParser:
    """Test the CLI parser functionality."""
    
    def test_parser_creation(self):
        """Test that parser can be created."""
        parser = CLIParser()
        arg_parser = parser.build_parser()
        assert arg_parser is not None
    
    def test_global_options(self):
        """Test global options parsing."""
        parser = CLIParser()
        arg_parser = parser.build_parser()
        
        # Test with global options
        args = arg_parser.parse_args(['--verbose', '--dry-run', '--auto-yes', 'list'])
        assert args.verbose is True
        assert args.dry_run is True
        assert args.auto_yes is True
        assert args.command == 'list'
    
    def test_new_sermon_command(self):
        """Test new-sermon subcommand."""
        parser = CLIParser()
        arg_parser = parser.build_parser()
        
        args = arg_parser.parse_args([
            'new-sermon',
            'test.mp3',
            '--speaker', 'John Doe',
            '--date', '2024-01-01',
            '--title', 'Test Sermon'
        ])
        
        assert args.command == 'new-sermon'
        assert args.audio_file == 'test.mp3'
        assert args.speaker == 'John Doe'
        assert args.date == '2024-01-01'
        assert args.title == 'Test Sermon'
    
    def test_process_command(self):
        """Test process subcommand."""
        parser = CLIParser()
        arg_parser = parser.build_parser()
        
        args = arg_parser.parse_args([
            'process',
            '--sermon-id', '123456',
            '--no-upload',
            '--force-description'
        ])
        
        assert args.command == 'process'
        assert args.sermon_id == '123456'
        assert args.no_upload is True
        assert args.force_description is True
    
    def test_list_command(self):
        """Test list subcommand."""
        parser = CLIParser()
        arg_parser = parser.build_parser()
        
        args = arg_parser.parse_args([
            'list',
            '--since-days', '7',
            '--event-type', 'Sunday Service',
            '--limit', '20'
        ])
        
        assert args.command == 'list'
        assert args.since_days == 7
        assert args.event_type == 'Sunday Service'
        assert args.limit == 20
    
    def test_validation_command(self):
        """Test validation subcommand."""
        parser = CLIParser()
        arg_parser = parser.build_parser()
        
        args = arg_parser.parse_args([
            'validate',
            '--validate-descriptions',
            '--validation-report',
            '--export-validation-csv', 'report.csv'
        ])
        
        assert args.command == 'validate'
        assert args.validate_descriptions is True
        assert args.validation_report is True
        assert args.export_validation_csv == 'report.csv'


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_confirm_auto_yes(self):
        """Test confirm function with auto_yes=True."""
        result = confirm("Test prompt", auto_yes=True)
        assert result is True
    
    def test_parse_years_single(self):
        """Test parsing single year."""
        years = parse_years("2023")
        assert years == [2023]
    
    def test_parse_years_range(self):
        """Test parsing year range."""
        years = parse_years("2022-2024")
        assert years == [2022, 2023, 2024]
    
    def test_parse_years_list(self):
        """Test parsing year list."""
        years = parse_years("2022,2024,2025")
        assert years == [2022, 2024, 2025]
    
    def test_parse_years_mixed(self):
        """Test parsing mixed year formats."""
        years = parse_years("2022-2023,2025")
        assert years == [2022, 2023, 2025]


if __name__ == "__main__":
    # Run basic tests
    print("Testing CLI Parser...")
    
    # Test parser creation
    parser = CLIParser()
    arg_parser = parser.build_parser()
    print("✅ Parser creation works")
    
    # Test basic parsing
    args = arg_parser.parse_args(['--verbose', 'list', '--limit', '5'])
    assert args.verbose is True
    assert args.command == 'list'
    assert args.limit == 5
    print("✅ Basic argument parsing works")
    
    # Test helper functions
    assert confirm("test", auto_yes=True) is True
    assert parse_years("2022-2024") == [2022, 2023, 2024]
    print("✅ Helper functions work")
    
    print("All CLI parser tests passed!")