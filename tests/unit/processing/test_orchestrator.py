"""
Test Processing Orchestrator Module

Tests for the extracted processing orchestration functionality.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from processing.orchestrator import (
    ProcessingOptions,
    ValidationOptions,
    ArgumentsNormalizer,
    ProcessingOrchestrator,
    SermonFilter,
)


class TestProcessingOptions:
    """Test the ProcessingOptions dataclass."""
    
    def test_default_values(self):
        """Test default values for ProcessingOptions."""
        options = ProcessingOptions()
        assert options.no_upload is False
        assert options.output_dir is None
        assert options.save_original_audio is None
        assert options.verbose is False
        assert options.dry_run is False
    
    def test_custom_values(self):
        """Test custom values for ProcessingOptions."""
        options = ProcessingOptions(
            no_upload=True,
            output_dir="/custom/path",
            save_original_audio=True,
            verbose=True,
            dry_run=True
        )
        assert options.no_upload is True
        assert options.output_dir == "/custom/path"
        assert options.save_original_audio is True
        assert options.verbose is True
        assert options.dry_run is True


class TestValidationOptions:
    """Test the ValidationOptions dataclass."""
    
    def test_default_values(self):
        """Test default values for ValidationOptions."""
        options = ValidationOptions()
        assert options.validate_descriptions is False
        assert options.validate_and_regenerate is False
        assert options.validation_report is False
        assert options.export_validation_csv is None
    
    def test_custom_values(self):
        """Test custom values for ValidationOptions."""
        options = ValidationOptions(
            validate_descriptions=True,
            validation_report=True,
            export_validation_csv="report.csv"
        )
        assert options.validate_descriptions is True
        assert options.validation_report is True
        assert options.export_validation_csv == "report.csv"


class TestArgumentsNormalizer:
    """Test the ArgumentsNormalizer functionality."""
    
    def test_normalize_args_with_minimal_args(self):
        """Test normalizing args with minimal attributes."""
        # Create a mock args object with minimal attributes
        args = Mock()
        args.verbose = True
        args.dry_run = False
        args.auto_yes = True
        
        processing_options, validation_options = ArgumentsNormalizer.normalize_args(args)
        
        # Check that missing attributes were added with defaults
        assert hasattr(args, 'validate_descriptions')
        assert args.validate_descriptions is False
        assert hasattr(args, 'no_upload')
        assert args.no_upload is False
        
        # Check that options objects were created correctly
        assert processing_options.verbose is True
        assert processing_options.dry_run is False
        assert processing_options.auto_yes is True
        assert validation_options.validate_descriptions is False
    
    def test_normalize_args_with_full_args(self):
        """Test normalizing args with all attributes present."""
        args = Mock()
        # Set all possible attributes
        args.verbose = True
        args.dry_run = True
        args.auto_yes = False
        args.no_upload = True
        args.output_dir = "/custom"
        args.save_original_audio = True
        args.validate_descriptions = True
        args.validate_and_regenerate = False
        args.validation_report = True
        args.export_validation_csv = "test.csv"
        args.export_validation_json = None
        args.validation_sermon_ids = "123,456"
        
        processing_options, validation_options = ArgumentsNormalizer.normalize_args(args)
        
        # Check processing options
        assert processing_options.verbose is True
        assert processing_options.dry_run is True
        assert processing_options.auto_yes is False
        assert processing_options.no_upload is True
        assert processing_options.output_dir == "/custom"
        
        # Check validation options
        assert validation_options.validate_descriptions is True
        assert validation_options.validate_and_regenerate is False
        assert validation_options.validation_report is True
        assert validation_options.export_validation_csv == "test.csv"
        assert validation_options.validation_sermon_ids == "123,456"
    
    def test_resolve_audio_save_option(self):
        """Test resolving audio save option from args and config."""
        config = {'save_original_audio': True}
        
        # Test with no_save_original_audio = True
        args = Mock()
        args.no_save_original_audio = True
        result = ArgumentsNormalizer.resolve_audio_save_option(args, config)
        assert result is False
        
        # Test with save_original_audio = True
        args = Mock()
        args.save_original_audio = True
        result = ArgumentsNormalizer.resolve_audio_save_option(args, config)
        assert result is True
        
        # Test with neither - should use config default
        args = Mock()
        result = ArgumentsNormalizer.resolve_audio_save_option(args, config)
        assert result is True
    
    def test_resolve_transcript_save_option(self):
        """Test resolving transcript save option from args and config."""
        config = {'save_transcript': False}
        
        # Test with no_save_transcript = True
        args = Mock()
        args.no_save_transcript = True
        result = ArgumentsNormalizer.resolve_transcript_save_option(args, config)
        assert result is False
        
        # Test with save_transcript = True
        args = Mock()
        args.save_transcript = True
        result = ArgumentsNormalizer.resolve_transcript_save_option(args, config)
        assert result is True
        
        # Test with neither - should use config default
        args = Mock()
        result = ArgumentsNormalizer.resolve_transcript_save_option(args, config)
        assert result is False


class TestProcessingOrchestrator:
    """Test the ProcessingOrchestrator functionality."""
    
    def test_orchestrator_creation(self):
        """Test creating a ProcessingOrchestrator."""
        config = {'api_key': 'test', 'broadcaster_id': 'test'}
        orchestrator = ProcessingOrchestrator(config)
        assert orchestrator.config == config
    
    def test_format_processing_result(self):
        """Test formatting processing results."""
        config = {}
        orchestrator = ProcessingOrchestrator(config)
        
        # Test skipped result
        result = {"action": "skipped", "reason": "No audio"}
        message = orchestrator.format_processing_result(result, "Test Sermon", 1, 5)
        assert "⏭️ Skipped" in message
        assert "No audio" in message
        assert "[1/5]" in message
        
        # Test processed result with completed actions
        result = {"action": "processed", "completed": ["audio", "description"]}
        message = orchestrator.format_processing_result(result, "Test Sermon", 2, 5)
        assert "✅ Updated" in message
        assert "audio, description" in message
        assert "[2/5]" in message
        
        # Test simple completed result
        result = None
        message = orchestrator.format_processing_result(result, "Test Sermon", 3, 5)
        assert "✅ Completed" in message
        assert "[3/5]" in message
    
    def test_validate_processing_requirements(self):
        """Test validation of processing requirements."""
        # Test with missing config
        config = {}
        orchestrator = ProcessingOrchestrator(config)
        processing_options = ProcessingOptions()
        validation_options = ValidationOptions()
        
        issues = orchestrator.validate_processing_requirements(processing_options, validation_options)
        assert len(issues) >= 2  # Should have API key and broadcaster ID issues
        assert any("API key" in issue for issue in issues)
        assert any("broadcaster ID" in issue for issue in issues)
        
        # Test with valid config
        config = {
            'api_key': 'test_key',
            'broadcaster_id': 'test_broadcaster',
            'llm': {'primary': {'provider': 'ollama'}}
        }
        orchestrator = ProcessingOrchestrator(config)
        
        issues = orchestrator.validate_processing_requirements(processing_options, validation_options)
        assert len(issues) == 0  # Should have no issues


class TestSermonFilter:
    """Test the SermonFilter functionality."""
    
    def test_filter_creation(self):
        """Test creating a SermonFilter."""
        config = {}
        filter_obj = SermonFilter(config)
        assert filter_obj.config == config
    
    def test_build_query_filters(self):
        """Test building query filters from args."""
        config = {}
        filter_obj = SermonFilter(config)
        
        # Create mock args with various filters
        args = Mock()
        args.since_days = 7
        args.event_type = "Sunday Service"
        args.speaker_name = "John Doe"
        args.search_keyword = "grace"
        args.limit = 10
        args.require_audio = True
        
        filters = filter_obj.build_query_filters(args)
        
        assert filters['since_days'] == 7
        assert filters['event_type'] == "Sunday Service"
        assert filters['speaker_name'] == "John Doe"
        assert filters['search_keyword'] == "grace"
        assert filters['limit'] == 10
        assert filters['require_audio'] is True
    
    def test_build_query_filters_minimal(self):
        """Test building query filters with minimal args."""
        config = {}
        filter_obj = SermonFilter(config)
        
        # Create mock args with no filter attributes
        args = Mock()
        
        filters = filter_obj.build_query_filters(args)
        
        # Should return empty dict when no filters are present
        assert filters == {}


if __name__ == "__main__":
    # Run basic tests
    print("Testing Processing Orchestrator...")
    
    # Test basic creation
    config = {'api_key': 'test', 'broadcaster_id': 'test'}
    orchestrator = ProcessingOrchestrator(config)
    print("✅ ProcessingOrchestrator creation works")
    
    # Test options creation
    processing_options = ProcessingOptions(verbose=True)
    validation_options = ValidationOptions(validate_descriptions=True)
    assert processing_options.verbose is True
    assert validation_options.validate_descriptions is True
    print("✅ Options dataclasses work")
    
    # Test arguments normalizer
    args = Mock()
    args.verbose = True
    args.dry_run = False
    args.auto_yes = True
    
    proc_opts, val_opts = ArgumentsNormalizer.normalize_args(args)
    assert proc_opts.verbose is True
    assert hasattr(args, 'validate_descriptions')
    print("✅ ArgumentsNormalizer works")
    
    # Test sermon filter
    filter_obj = SermonFilter(config)
    args.since_days = 7
    filters = filter_obj.build_query_filters(args)
    assert filters['since_days'] == 7
    print("✅ SermonFilter works")
    
    print("All processing orchestrator tests passed!")