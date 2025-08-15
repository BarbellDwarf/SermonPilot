# AI Coding Agent Instructions for SermonAudio Processor

## Architecture Overview

This is a **three-component pipeline** for automated sermon processing:

1. **`sermon_updater.py`** - CLI orchestrator that fetches sermons from SermonAudio API, coordinates processing, and uploads results
2. **`audio_processing.py`** - Audio enhancement engine with multiple AI models (DeepFilterNet, Resemble Enhance, SpeechBrain) and fallback mechanisms  
3. **`llm_manager.py`** - Multi-provider LLM abstraction (OpenAI-compatible APIs, Ollama) with primary/fallback pattern

**Key Data Flow**: SermonAudio API → Audio Download → AI Enhancement → LLM Summary/Hashtags → Upload Back

## Essential Patterns

### Configuration-Driven Everything

- `config.yaml` is the single source of truth for all components
- **Legacy migration**: `migrate_legacy_config()` in `llm_manager.py` handles backward compatibility
- **Debug mode**: `debug: true/false` controls all verbose output across components
- **Provider switching**: LLM providers configured via nested `llm.primary/fallback` structure

### Dual-Provider Pattern (LLM + Audio)

```python
# LLM: primary → fallback → exception
llm_manager.chat(messages)  # Auto-handles provider switching

# Audio: method → CLI fallback → traditional processing  
processor = AudioProcessor(enhancement_method="deepfilternet")
```

### Graceful Degradation Chain

**Audio**: AI enhancement → CLI fallback → basic pydub processing  
**LLM**: Primary provider → Fallback provider → Hard failure  
**Models**: GPU → CPU → Skip processing

### Test-First Development

- **All tests in `tests/` directory** - never put test files elsewhere
- **Documentation in `docs/` directory** - never put docs in root or other locations
- **Audio tests require `tests/sample_audio.mp3`** - gracefully skip if missing
- **Live API tests** marked with `@pytest.mark.network @pytest.mark.live`
- **Integration tests** validate end-to-end pipelines with real sermon data

## Critical Commands

### Development Setup

```bash
# UV package manager (REQUIRED - handles Python versions and dependencies)
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

uv pip install -r requirements.txt

# For new packages, always use UV
uv add package-name        # Add to pyproject.toml
uv pip install package     # Install directly
```

### Testing Workflow

```bash
# Test setup first
python tests/test_setup.py

# Test individual components  
python tests/test_llm_manager.py        # LLM provider switching
python tests/test_audio_upscaling.py    # Audio pipeline
python tests/test_real_sermon_deepfilternet.py  # End-to-end with real data

# Run specific test categories
pytest -v -m "not live"    # Skip live API tests
pytest tests/test_*.py     # All unit tests
```

### Model Management

```bash
# DeepFilterNet (auto-downloads on first use)
# Ollama models
ollama pull llama3.1:8b
ollama list

# Check model availability
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

## Project-Specific Conventions

### Audio Processing Integration Points

- **Enhancement methods**: `"deepfilternet"`, `"resemble_enhance"`, `"none"`
- **Device detection**: Auto GPU/CPU selection in `AudioProcessor.__init__()`
- **Chunking strategy**: Dynamic based on available memory and audio duration
- **Upscaling pipeline**: AI enhancement → traditional resampling → fallback

### LLM Provider Configuration

```yaml
llm:
  primary:
    provider: "openai"  # or "ollama"
    openai:
      base_url: "https://api.x.ai/v1"  # xAI, Anthropic, etc.
      api_key: "..."
      model: "grok-beta"
  fallback:
    enabled: true
    provider: "ollama"
    ollama:
      host: "http://localhost:11434"
      model: "llama3.1:8b"
```

### CLI Argument Mapping

- **All SermonAudio API parameters exposed as CLI flags** (see `sermon_updater.py` docstring)
- **Filtering strategy**: Use `--list-only` first, then process with same filters
- **Safety**: `--dry-run` for testing, `--auto-yes` for automation, `--limit N` to prevent runaway

### Error Handling Patterns

```python
# Audio: Try AI → Fallback to CLI → Copy original file
# LLM: Try primary → Try fallback → Hard fail with clear message
# Uploads: Validate locally → Upload → Verify remotely
```

## Integration & Dependencies

### External Service Dependencies

- **SermonAudio API**: Requires broadcaster credentials, handles rate limiting
- **Ollama**: Local inference server, must be running (`ollama serve`)
- **CUDA/PyTorch**: Auto-detected, gracefully degrades to CPU
- **Audacity**: Optional integration via mod-script-pipe for advanced processing

### File Structure Conventions

- **`processed_sermons/[ID]/`** - Per-sermon output directory with audio + metadata
- **`tests/`** - All test files (NEVER put tests elsewhere)
- **`docs/`** - All documentation files (NEVER put docs in root)
- **`tests/sample_audio.mp3`** - Required for audio-dependent tests (gitignored)
- **`.venv/`** - Virtual environment (ALWAYS use UV: `uv venv --python 3.11`)
- **`pyproject.toml`** - Primary dependency management (UV-compatible)

### Performance Considerations

- **Large audio files**: Automatic chunking based on available memory
- **Model initialization**: Cached after first load, device-aware placement
- **API rate limits**: Built-in throttling for SermonAudio calls
- **Memory management**: Monitor usage with `psutil`, clean up models between runs

## Key Files for Understanding Context

- `config.yaml` - All runtime configuration
- `tests/ENHANCEMENT_MODEL_TESTING_RESULTS.md` - Model performance benchmarks
- `tests/LLM_Configuration_Guide.md` - Provider setup examples
- `pyproject.toml` - Dependencies and tooling config (UV primary)
- `requirements.txt` - Runtime dependencies (sync with pyproject.toml)
- `uv.lock` - UV lockfile for reproducible builds

## Common Gotchas

- **Import order matters**: Audio ML libraries can conflict - use context managers to suppress warnings
- **Windows path handling**: Use `Path` objects, test both forward/backslashes  
- **Model downloads**: First run downloads GBs of data - warn users and cache properly
- **Config migration**: Always call `migrate_legacy_config()` when loading config
- **Test isolation**: Audio tests must not require external resources - skip gracefully
