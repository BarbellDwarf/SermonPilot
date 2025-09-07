# Test Fixtures

This directory contains test data and fixtures for the SermonAudio Processor tests.

## Directory Structure

- `sample_audio/` - Sample audio files for testing audio processing
- `mock_configs/` - Mock configuration files for testing config loading
- `test_data/` - Other test data files (JSON, text, etc.)

## Security Notice

⚠️ **IMPORTANT**: This directory contains test data only. 
- Never put real credentials or production data here
- All files in this directory are excluded from production builds
- Use environment variables for any real configuration values

## Usage

Test files should reference fixtures from this directory to ensure proper isolation from production code.

Example:
```python
# Good - proper test isolation
test_config = load_config('tests/fixtures/mock_configs/test_config.yaml')

# Bad - test data in production areas
test_config = {'api_key': 'test_key'}  # Hardcoded in test
```

## Adding New Fixtures

When adding new test fixtures:
1. Place them in the appropriate subdirectory
2. Use descriptive names that indicate they are test data
3. Include clear comments indicating test-only status
4. Avoid any real or production-like values