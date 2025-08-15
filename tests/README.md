# Test Organization

This directory contains all tests for the SermonAudio AI Audio Processor, organized into logical categories:

## Directory Structure

- **`unit/`** - Unit tests for individual components and basic functionality
- **`integration/`** - Integration tests that test end-to-end workflows with real data
- **`audio/`** - Audio processing tests including AI enhancement models (DeepFilterNet, Resemble)
- **`llm/`** - LLM-related tests including provider switching, hashtag generation, and OpenAI/Ollama
- **`api/`** - SermonAudio API tests and transcript processing
- **`cli/`** - Command-line interface tests and argument validation
- **`utils/`** - Utility scripts and helper functions for testing

## Running Tests

```bash
# Run all tests
pytest tests/

# Run specific categories
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests only
pytest tests/audio/          # Audio processing tests
pytest tests/llm/            # LLM tests
pytest tests/api/            # API tests
pytest tests/cli/            # CLI tests

# Skip live API tests
pytest -v -m "not live"

# Run tests with specific markers
pytest -v -m "network"       # Network-dependent tests
pytest -v -m "live"          # Live API tests
```

## Test Categories

### Unit Tests (`unit/`)
- Basic setup and configuration validation
- Component isolation tests
- Debug functionality tests

### Integration Tests (`integration/`)
- End-to-end pipeline tests with real sermon data
- GPU processing workflows
- Full system integration validation

### Audio Tests (`audio/`)
- AI enhancement model testing (DeepFilterNet, Resemble Enhance)
- Audio quality optimization tests
- Windows-specific audio processing fixes
- Quick model performance tests

### LLM Tests (`llm/`)
- LLM provider switching (OpenAI, Ollama)
- Hashtag generation and verification
- Provider fallback mechanisms
- Connection and routing tests

### API Tests (`api/`)
- SermonAudio API integration
- Transcript fetching and parsing
- Raw API endpoint testing
- Web endpoint validation

### CLI Tests (`cli/`)
- Command-line argument validation
- Filter integration testing
- Live API integration via CLI

### Utilities (`utils/`)
- Import validation helpers
- Memory usage testing
- Node method enumeration
- Pipe testing utilities

## Notes

- Tests requiring external resources (audio files, API keys) should gracefully skip when resources are unavailable
- Live API tests are marked with `@pytest.mark.live` and can be skipped with `-m "not live"`
- GPU tests automatically fall back to CPU when CUDA is unavailable
- All documentation has been moved to the root `docs/` directory
