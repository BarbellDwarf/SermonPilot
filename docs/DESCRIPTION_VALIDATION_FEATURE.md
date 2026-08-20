# Description Validation Feature

## Overview

The Description Validation feature allows you to check existing sermon descriptions against predefined quality criteria and automatically regenerate those that don't meet standards. This feature integrates with the existing LLM validation system and provides comprehensive reporting and automation capabilities.

## Key Features

### 1. **Automated Quality Assessment**
- Validates descriptions against configurable criteria
- Provides detailed scoring (0.0-1.0) for each description
- Identifies specific criteria that are met or failed
- Supports bulk validation of processed sermons

### 2. **Intelligent Regeneration**
- Automatically regenerates descriptions that fail validation
- Uses the existing validated summary generation system
- Preserves original descriptions as backups
- Integrates with primary/fallback LLM providers

### 3. **Comprehensive Reporting**
- Detailed validation reports with criteria performance
- Export results to CSV or JSON for analysis
- Summary statistics and trend analysis
- Identification of sermons needing manual review

### 4. **Flexible Validation Criteria**
- Configurable validation criteria in `config.yaml`
- Default criteria focus on theological content, speaker message, professional style, substance over generic phrases, and practical application
- Easy to customize for different organizations

## Configuration

### Basic Setup

Add the validator configuration to your `config.yaml`:

```yaml
llm:
  # ... existing primary and fallback config ...
  
  # Validation LLM settings (smaller model for description validation)
  validator:
    enabled: true
    provider: "ollama"  # Options: "ollama", "openai", "anthropic", "xai", "google", "groq"
    ollama:
      host: "http://localhost:11434"
      model: "gemma2:2b"  # Smaller, faster model for validation
    openai:
      api_key: "your-api-key"
      model: "gpt-4o-mini"  # Smaller OpenAI model for validation
      base_url: "https://api.openai.com/v1"  # Optional custom endpoint

metadata_processing:
  description:
    validation:
      enabled: true  # Enable description validation
      criteria:
        - "Contains specific theological content or Bible references"
        - "Mentions the speaker's main message or key points"
        - "Is written in a professional, engaging style"
        - "Avoids generic Christian phrases without substance"
        - "Has clear application or takeaway for listeners"
```

### Advanced Configuration

```yaml
metadata_processing:
  description:
    validation:
      enabled: true
      min_length_threshold: 50      # Minimum description length
      max_length_threshold: 1600    # Maximum description length  
      regeneration_threshold: 0.6   # Score below which regeneration is suggested
      criteria:
        - "Contains specific theological content or Bible references"
        - "Mentions the speaker's main message or key points"
        - "Is written in a professional, engaging style"
        - "Avoids generic Christian phrases without substance"
        - "Has clear application or takeaway for listeners"
        - "Includes practical application for daily life"  # Custom criterion
        - "References specific Bible passages or themes"   # Custom criterion
```

## Usage

### 1. Basic Validation

Validate all existing processed sermons:

```bash
python src/description_validator.py --local-sermons
```

### 2. Detailed Validation Report

Get a comprehensive report with criteria performance:

```bash
python src/description_validator.py --local-sermons --detailed-report
```

### 3. Validate Specific Sermons

Validate only specific sermon IDs:

```bash
python src/description_validator.py --local-sermons --sermon-ids 123456789,987654321
```

### 4. Export Results for Analysis

Export validation results to CSV for spreadsheet analysis:

```bash
python src/description_validator.py --local-sermons --export-csv validation_results.csv
```

Export detailed results to JSON:

```bash
python src/description_validator.py --local-sermons --export-json detailed_results.json
```

### 5. Integrated Validation and Regeneration

Use the `validation` subcommand of the CLI to validate and automatically
regenerate failed descriptions:

```bash
# Validate all and regenerate failed descriptions
python sermon_updater.py validation --validate-and-regenerate

# Dry run to see what would be regenerated
python sermon_updater.py validation --validate-and-regenerate --dry-run

# Validate recent sermons and regenerate
python sermon_updater.py validation --validate-descriptions --validation-report --since-days 30

# Validate specific sermons
python sermon_updater.py validation --validate-and-regenerate --validation-sermon-ids 123456789,987654321
```

## Understanding Validation Results

### Validation Scores

- **0.8-1.0**: High quality, approved
- **0.6-0.79**: Acceptable quality but could be improved  
- **0.0-0.59**: Poor quality, recommended for regeneration

### Validation Status

- **✅ APPROVED**: Description meets quality standards
- **❌ REJECTED**: Description fails to meet minimum standards
- **⚠️ NEEDS_REVIEW**: Manual review recommended

### Sample Output

```
📊 DESCRIPTION VALIDATION REPORT
================================================================================

📈 SUMMARY:
   Total Sermons Validated: 150
   ✅ Valid Descriptions: 120 (80.0%)
   ❌ Invalid Descriptions: 30
   🔄 Need Regeneration: 25
   📊 Average Score: 0.75/1.0

📋 CRITERIA PERFORMANCE:
   ✅ Contains specific theological content or Bible references: 85.3%
   ✅ Mentions the speaker's main message or key points: 78.7%
   ⚠️ Is written in a professional, engaging style: 72.0%
   ❌ Avoids generic Christian phrases without substance: 55.3%
   ✅ Has clear application or takeaway for listeners: 81.3%

❌ FAILED VALIDATIONS (25 sermons):

   📝 Sermon ID: 123456789
      Score: 0.45/1.0
      Reason: Too generic, lacks specific biblical content
      Length: 89 chars
      Failed Criteria: Avoids generic phrases, Contains theological content
      Description: This sermon encourages believers to trust God and live faithfully...
```

## Integration with Existing Workflow

### 1. During Processing

The validation system integrates with the existing `generate_validated_summary()` function:

```python
# This already happens during sermon processing
description, validation_info = generate_validated_summary(transcript, event_type, speaker_name)

if validation_info['final_status'] == 'needs_review':
    print("⚠️ Description may need manual review")
```

`final_status` is one of `no_validation` (validation disabled),
`approved_primary`, `approved_fallback`, or `needs_review`.

### 2. Post-Processing Audit

Run periodic audits of your sermon descriptions:

```bash
# Weekly audit
python src/description_validator.py --local-sermons --since-days 7 --detailed-report

# Monthly comprehensive check
python src/description_validator.py --local-sermons --export-csv monthly_audit.csv
```

### 3. Quality Improvement Workflow

1. **Identify Issues**: Run validation to find problematic descriptions
2. **Analyze Patterns**: Review criteria performance to understand common issues
3. **Adjust Criteria**: Modify validation criteria based on your standards
4. **Regenerate Failed**: Use automated regeneration for descriptions below threshold
5. **Manual Review**: Address descriptions that still fail after regeneration

## Troubleshooting

### Common Issues

**"Validator LLM not configured"**
- Ensure the `llm.validator` section is properly configured in `config.yaml`
- Verify the validator model is available (run `ollama list` for Ollama models)

**"No sermons found to validate"**
- Check that processed sermons exist in the `output_directory`
- Verify description files exist in each sermon directory (e.g., `description.txt`)

**"Validation always returns approved"**
- Check that validation criteria are specific enough
- Lower the `regeneration_threshold` for stricter validation
- Review the validator model's performance

**Poor validation quality**
- Try a different validator model (larger models often perform better)
- Adjust validation criteria to be more specific
- Ensure the validator prompt is clear and unambiguous

### Performance Optimization

**For Large Numbers of Sermons:**
- Use the `--sermon-ids` parameter to validate in batches
- Consider using a faster validator model for bulk operations
- Export results to files rather than printing detailed reports

**For Regular Monitoring:**
- Set up automated scripts to run validation on recent sermons
- Use CSV exports for tracking trends over time
- Integrate with existing reporting systems

## API Integration (Future Enhancement)

The validator is designed to support direct integration with the SermonAudio
API. The CLI exposes an `--api-sermons` flag for this purpose:

```bash
python src/description_validator.py --api-sermons --sermon-ids 123456789,987654321
```

API validation is not yet implemented; the flag currently falls back to
validating the local copies of the requested sermons.

## Best Practices

### 1. **Regular Validation**
- Run weekly validation on recent sermons
- Perform monthly comprehensive audits
- Set up alerts for dropping validation rates

### 2. **Criteria Customization**
- Tailor validation criteria to your organization's style
- Update criteria based on feedback and performance
- Consider different criteria for different sermon types

### 3. **Quality Monitoring**
- Track validation rates over time
- Monitor criteria performance trends
- Identify areas for improvement in description generation

### 4. **Workflow Integration**
- Include validation in your standard processing workflow
- Use automation for bulk regeneration of failed descriptions
- Maintain manual review process for edge cases

## Examples

### Example 1: Weekly Quality Check

```bash
#!/bin/bash
# weekly_validation.sh

echo "Running weekly description validation..."

# Validate recent sermons
python src/description_validator.py --local-sermons --since-days 7 --detailed-report

# Export results for tracking
python src/description_validator.py --local-sermons --export-csv "reports/validation_$(date +%Y%m%d).csv"

echo "Validation complete!"
```

### Example 2: Bulk Improvement Project

```bash
# 1. First, see what needs work
python src/description_validator.py --local-sermons --detailed-report

# 2. Export for analysis
python src/description_validator.py --local-sermons --export-csv all_descriptions.csv

# 3. Regenerate failed descriptions (dry run first)
python sermon_updater.py validation --validate-and-regenerate --dry-run

# 4. Actually regenerate
python sermon_updater.py validation --validate-and-regenerate

# 5. Verify improvements
python src/description_validator.py --local-sermons --detailed-report
```

### Example 3: Custom Criteria Testing

```yaml
# config.yaml - test different criteria
metadata_processing:
  description:
    validation:
      enabled: true
      criteria:
        - "References specific Bible verses or passages"
        - "Identifies the main theological theme"
        - "Includes practical application"
        - "Mentions the speaker by name"
        - "Avoids repetitive or filler phrases"
        - "Appropriate length (100-400 words)"
```

```bash
# Test the new criteria
python src/description_validator.py --local-sermons --detailed-report
```

This comprehensive validation system helps ensure that your sermon descriptions consistently meet quality standards and provide value to your audience.
