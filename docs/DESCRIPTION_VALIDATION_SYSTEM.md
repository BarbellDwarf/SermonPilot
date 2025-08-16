# Description Validation System Implementation Summary

## Overview

I've implemented a two-stage LLM validation system for sermon descriptions with comprehensive summary reporting. Here's what was added:

## New Features

### 1. Validator LLM Configuration
- **New config section**: `llm.validator` for smaller, faster validation model
- **Configurable criteria**: List of validation criteria in `metadata_processing.description.validation`
- **Default validator model**: `gemma2:2b` (smaller, faster than primary models)

### 2. Description Validation Flow
1. **Primary Generation**: Uses main LLM to generate description
2. **Validation Check**: Smaller validator model reviews against criteria
3. **Fallback Generation**: If validation fails, tries fallback LLM
4. **Final Validation**: Validates fallback attempt
5. **Manual Review Flag**: If both fail validation, marks for manual review

### 3. Validation Criteria (Configurable)
- Contains specific theological content or Bible references
- Mentions the speaker's main message or key points
- Is written in a professional, engaging style
- Avoids generic Christian phrases without substance
- Has clear application or takeaway for listeners

### 4. Enhanced Summary Reporting
- **Validation Statistics**: Counts of approved primary, approved fallback, needs review
- **Manual Review List**: Detailed list of sermons requiring attention
- **Validation Reasons**: Shows why descriptions were rejected

## Configuration Example

```yaml
llm:
  validator:
    enabled: true
    provider: "ollama"
    ollama:
      host: "http://localhost:11434"
      model: "gemma2:2b"  # Smaller, faster model

metadata_processing:
  description:
    validation:
      enabled: true
      criteria:
        - "Contains specific theological content or Bible references"
        - "Mentions the speaker's main message or key points"
        - "Is written in a professional, engaging style"
        - "Avoids generic Christian phrases without substance"
        - "Has clear application or takeaway for listeners"
```

## Sample Output

```
📋 Description Validation Summary:
   ✅ Approved (Primary): 8
   ✅ Approved (Fallback): 2
   ⚠️  Needs Review: 1

⚠️  Sermons requiring manual review:
   📝 The Power of Prayer (ID: 123456789)
      Primary: Too generic, lacks specific biblical content
      Fallback: Missing clear application for listeners
```

## Files Modified

1. **`config.yaml`** - Added validator LLM and validation criteria
2. **`config.example.yaml`** - Added example validator configuration
3. **`llm_manager.py`** - Added validator provider and `validate_description()` method
4. **`sermon_updater.py`** - Added `generate_validated_summary()` and summary reporting

## Benefits

- **Quality Control**: Ensures descriptions meet minimum quality standards
- **Automated Review**: Reduces manual review burden
- **Fallback System**: Multiple attempts before giving up
- **Clear Reporting**: Shows exactly what needs attention and why
- **Configurable**: Can adjust criteria and enable/disable validation

## Testing

Created `test_validation.py` to verify the validation system works with sample good/poor descriptions.

The system gracefully handles:
- Validator model unavailable (defaults to approved)
- Validation disabled (uses original generation method)
- Network/API errors (logs warning, defaults to approved)
