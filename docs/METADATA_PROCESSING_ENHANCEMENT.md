# Metadata Processing Enhancement Summary

## Overview
Successfully implemented conditional metadata processing for sermon descriptions and hashtags, allowing users to:
- Skip audio processing while still updating metadata
- Only update missing or minimal content
- Force updates when needed
- Skip metadata processing entirely if desired

## New Configuration (config.yaml)

Added `metadata_processing` section with granular controls:

```yaml
metadata_processing:
  enabled: true                    # Enable metadata processing 
  process_audio: true             # Whether to process audio (CLI overridable)
  description:
    update_if_missing: true       # Update only if null/empty
    update_if_minimal: true       # Update if less than threshold
    force_update: false          # Update even if substantial content exists
    min_length_threshold: 50     # Characters considered "minimal"
  hashtags:
    update_if_missing: true      # Update only if null/empty  
    update_if_minimal: true      # Update if less than threshold
    force_update: false         # Update even if substantial content exists
    min_length_threshold: 10    # Characters considered "minimal"
```

## New CLI Arguments

- `--metadata-only`: Process only metadata, skip audio entirely
- `--skip-audio`: Skip audio processing but allow other operations  
- `--force-description`: Force description update even if content exists
- `--force-hashtags`: Force hashtag update even if content exists
- `--no-metadata`: Skip all metadata processing

## Example Usage

```bash
# Update metadata for sermons missing descriptions/hashtags, skip audio
python sermon_updater.py --speaker-name "John Smith" --metadata-only

# Force update all descriptions regardless of existing content
python sermon_updater.py --speaker-name "John Smith" --force-description --skip-audio

# Process normally but skip hashtags entirely  
python sermon_updater.py --speaker-name "John Smith" --no-metadata

# Dry run to see what would be updated
python sermon_updater.py --speaker-name "John Smith" --metadata-only --dry-run
```

## Implementation Details

### Helper Functions Added:
- `is_content_missing_or_minimal()` - Determines if content needs updating
- `should_update_description()` - Config + CLI logic for descriptions
- `should_update_hashtags()` - Config + CLI logic for hashtags  
- `needs_metadata_processing()` - Overall metadata processing decision
- `needs_audio_processing()` - Overall audio processing decision

### Key Features:
1. **Conditional Logic**: Both single sermon and batch processing respect new flags
2. **Config + CLI Override**: CLI arguments override config file defaults
3. **Graceful Degradation**: System works with missing config sections
4. **Content Assessment**: Smart detection of missing/minimal content
5. **Batch Processing**: All new flags work in batch mode too

## Files Modified:
- `config.yaml` - Added metadata_processing configuration section
- `sermon_updater.py` - Added helper functions, CLI args, and conditional logic

## Testing:
- CLI argument parsing validated
- All argument combinations tested
- Conditional logic flow verified
- Ready for integration testing with real sermons
