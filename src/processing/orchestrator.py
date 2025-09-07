"""
Processing Orchestrator Module

Extracted from sermon_updater.py to reduce complexity.
Handles the main sermon processing orchestration logic.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessingOptions:
    """Configuration for sermon processing operations."""
    no_upload: bool = False
    output_dir: Optional[str] = None
    save_original_audio: Optional[bool] = None
    save_transcript: Optional[bool] = None
    force_description: bool = False
    force_hashtags: bool = False
    metadata_only: bool = False
    skip_audio: bool = False
    no_metadata: bool = False
    verbose: bool = False
    dry_run: bool = False
    auto_yes: bool = False


@dataclass
class ValidationOptions:
    """Configuration for description validation operations."""
    validate_descriptions: bool = False
    validate_and_regenerate: bool = False
    validation_report: bool = False
    export_validation_csv: Optional[str] = None
    export_validation_json: Optional[str] = None
    validation_sermon_ids: Optional[str] = None


class ArgumentsNormalizer:
    """Normalizes and validates command line arguments."""
    
    @staticmethod
    def normalize_args(args) -> tuple[ProcessingOptions, ValidationOptions]:
        """Normalize arguments and extract processing/validation options."""
        # Set defaults for missing attributes that might not exist in subcommand args
        validation_attrs = {
            'validate_descriptions': False,
            'validate_and_regenerate': False,
            'validation_report': False,
            'export_validation_csv': None,
            'export_validation_json': None,
            'validation_sermon_ids': None,
        }
        
        processing_attrs = {
            'no_upload': False,
            'output_dir': None,
            'save_original_audio': False,
            'no_save_original_audio': False,
            'save_transcript': False,
            'no_save_transcript': False,
            'force_description': False,
            'force_hashtags': False,
            'metadata_only': False,
            'skip_audio': False,
            'no_metadata': False,
            'verbose': False,
            'dry_run': False,
            'auto_yes': False,
        }
        
        # Set missing attributes with defaults
        for attr, default in validation_attrs.items():
            if not hasattr(args, attr):
                setattr(args, attr, default)
        
        for attr, default in processing_attrs.items():
            if not hasattr(args, attr):
                setattr(args, attr, default)
        
        # Create options objects
        processing_options = ProcessingOptions(
            no_upload=args.no_upload,
            output_dir=args.output_dir,
            save_original_audio=args.save_original_audio if hasattr(args, 'save_original_audio') else None,
            save_transcript=args.save_transcript if hasattr(args, 'save_transcript') else None,
            force_description=getattr(args, 'force_description', False),
            force_hashtags=getattr(args, 'force_hashtags', False),
            metadata_only=getattr(args, 'metadata_only', False),
            skip_audio=getattr(args, 'skip_audio', False),
            no_metadata=getattr(args, 'no_metadata', False),
            verbose=args.verbose,
            dry_run=args.dry_run,
            auto_yes=args.auto_yes,
        )
        
        validation_options = ValidationOptions(
            validate_descriptions=args.validate_descriptions,
            validate_and_regenerate=args.validate_and_regenerate,
            validation_report=args.validation_report,
            export_validation_csv=args.export_validation_csv,
            export_validation_json=args.export_validation_json,
            validation_sermon_ids=args.validation_sermon_ids,
        )
        
        return processing_options, validation_options
    
    @staticmethod
    def resolve_audio_save_option(args, config: Dict[str, Any]) -> bool:
        """Resolve the save_original_audio setting from args and config."""
        if hasattr(args, 'no_save_original_audio') and args.no_save_original_audio:
            return False
        elif hasattr(args, 'save_original_audio') and args.save_original_audio:
            return True
        else:
            return config.get('save_original_audio', True)
    
    @staticmethod
    def resolve_transcript_save_option(args, config: Dict[str, Any]) -> bool:
        """Resolve the save_transcript setting from args and config."""
        if hasattr(args, 'no_save_transcript') and args.no_save_transcript:
            return False
        elif hasattr(args, 'save_transcript') and args.save_transcript:
            return True
        else:
            return config.get('save_transcript', False)


class ProcessingOrchestrator:
    """Orchestrates sermon processing operations."""
    
    def __init__(self, config: Dict[str, Any], console_print_func=None):
        self.config = config
        self.console_print = console_print_func or print
    
    def display_processing_settings(self, processing_options: ProcessingOptions, 
                                  validation_options: ValidationOptions,
                                  audio_save: bool, transcript_save: bool):
        """Display current processing settings."""
        settings_info = []
        
        # Processing mode
        if processing_options.metadata_only:
            settings_info.append("Mode: Metadata only")
        elif processing_options.skip_audio:
            settings_info.append("Mode: Skip audio processing")
        else:
            settings_info.append("Mode: Full processing")
        
        # Upload setting
        if processing_options.no_upload:
            settings_info.append("Upload: Disabled")
        else:
            settings_info.append("Upload: Enabled")
        
        # LLM info
        llm_config = self.config.get('llm', {})
        primary = llm_config.get('primary', {})
        if primary:
            provider = primary.get('provider', 'unknown')
            model = primary.get(provider, {}).get('model', 'default')
            llm_text = f"LLM: {provider.title()}/{model}"
            
            fallback = llm_config.get('fallback', {})
            if fallback.get('enabled'):
                fallback_provider = fallback.get('provider', 'unknown')
                fallback_model = fallback.get(fallback_provider, {}).get('model', 'default')
                llm_text += f" (fallback: {fallback_provider.title()}/{fallback_model})"
            
            settings_info.append(llm_text)
        
        # Output directory
        output_path = processing_options.output_dir or self.config.get('output_directory', 'processed_sermons')
        settings_info.append(f"Output: {output_path}")
        
        # File saving options
        save_opts = []
        if audio_save:
            save_opts.append("original audio")
        if transcript_save:
            save_opts.append("transcript")
        if save_opts:
            settings_info.append(f"Saving: {', '.join(save_opts)}")
        
        # Display settings
        for setting in settings_info:
            self.console_print(f"   {setting}")
    
    def format_processing_result(self, result: Dict[str, Any], sermon_title: str, 
                               index: int, total: int) -> str:
        """Format processing result message."""
        if not result:
            return f"[{index}/{total}] ✅ Completed: {sermon_title}"
        
        if result.get("action") == "skipped":
            reason = result.get("reason", "Unknown reason")
            return f"[{index}/{total}] ⏭️ Skipped: {sermon_title} - {reason}"
        elif result.get("action") == "processed":
            completed = result.get("completed", [])
            if completed:
                actions_text = ", ".join(completed)
                return f"[{index}/{total}] ✅ Updated: {sermon_title} - {actions_text}"
            else:
                return f"[{index}/{total}] ✅ Completed: {sermon_title}"
        else:
            return f"[{index}/{total}] ✅ Completed: {sermon_title}"
    
    def should_process_sermon(self, sermon, processing_options: ProcessingOptions) -> tuple[bool, str]:
        """Determine if a sermon should be processed and why."""
        # Add logic for determining if sermon should be processed
        # This would include checks for existing content, requirements, etc.
        
        # For now, return True - this logic would be extracted from the main function
        return True, ""
    
    def validate_processing_requirements(self, processing_options: ProcessingOptions,
                                       validation_options: ValidationOptions) -> List[str]:
        """Validate that all requirements for processing are met."""
        issues = []
        
        # Check for required configuration
        if not self.config.get('api_key'):
            issues.append("SermonAudio API key not configured")
        
        if not self.config.get('broadcaster_id'):
            issues.append("SermonAudio broadcaster ID not configured")
        
        # Check LLM configuration if content generation is needed
        if not processing_options.no_metadata:
            llm_config = self.config.get('llm', {})
            if not llm_config:
                issues.append("LLM configuration required for content generation")
        
        return issues


class SermonFilter:
    """Handles sermon filtering and querying logic."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def build_query_filters(self, args) -> Dict[str, Any]:
        """Build query filters from command line arguments."""
        filters = {}
        
        # Basic filters
        if hasattr(args, 'since_days') and args.since_days:
            filters['since_days'] = args.since_days
        
        if hasattr(args, 'event_type') and args.event_type:
            filters['event_type'] = args.event_type
        
        if hasattr(args, 'speaker_name') and args.speaker_name:
            filters['speaker_name'] = args.speaker_name
        
        if hasattr(args, 'search_keyword') and args.search_keyword:
            filters['search_keyword'] = args.search_keyword
        
        if hasattr(args, 'bible_text') and args.bible_text:
            filters['bible_text'] = args.bible_text
        
        if hasattr(args, 'language_code') and args.language_code:
            filters['language_code'] = args.language_code
        
        if hasattr(args, 'series') and args.series:
            filters['series'] = args.series
        
        # Date filters
        if hasattr(args, 'year') and args.year:
            filters['year'] = args.year
        
        if hasattr(args, 'years') and args.years:
            filters['years'] = args.years
        
        if hasattr(args, 'date_range') and args.date_range:
            filters['date_range'] = args.date_range
        
        # Requirements
        if hasattr(args, 'require_audio') and args.require_audio:
            filters['require_audio'] = True
        
        if hasattr(args, 'require_video') and args.require_video:
            filters['require_video'] = True
        
        if hasattr(args, 'require_transcript') and args.require_transcript:
            filters['require_transcript'] = True
        
        # Duration filters
        if hasattr(args, 'min_duration') and args.min_duration:
            filters['min_duration'] = args.min_duration
        
        if hasattr(args, 'max_duration') and args.max_duration:
            filters['max_duration'] = args.max_duration
        
        # Sorting
        if hasattr(args, 'sort_by') and args.sort_by:
            filters['sort_by'] = args.sort_by
        
        if hasattr(args, 'sort_order') and args.sort_order:
            filters['sort_order'] = args.sort_order
        
        # Limit
        if hasattr(args, 'limit') and args.limit:
            filters['limit'] = args.limit
        
        return filters