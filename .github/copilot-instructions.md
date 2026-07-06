# AI Coding Agent Instructions for SermonAudio Processor

## Architecture Overview

This is a **comprehensive sermon processing pipeline** with multiple interfaces:

1. **`sermon_updater.py`** - CLI orchestrator that fetches sermons from SermonAudio API, coordinates processing, and uploads results
2. **`audio_processing.py`** - Audio enhancement engine with multiple AI models (DeepFilterNet, Resemble Enhance, SpeechBrain) and fallback mechanisms  
3. **`llm_manager.py`** - Multi-provider LLM abstraction (OpenAI-compatible APIs, Ollama) with primary/fallback pattern
4. **`streamlit_app.py`** - Modern web interface for intuitive interaction and analytics
5. **Analytics & RAG System** - AI-powered insights and natural language queries over sermon data

**Key Data Flow**: SermonAudio API → Audio Download → AI Enhancement → LLM Summary/Hashtags → Upload Back → Analytics & Insights

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
# Web Interface
streamlit run streamlit_app.py           # Launch web interface
# Access at http://localhost:8501

# Test setup first
python tests/test_setup.py

# Test individual components  
python tests/test_llm_manager.py        # LLM provider switching
python tests/test_audio_upscaling.py    # Audio pipeline
python tests/test_real_sermon_deepfilternet.py  # End-to-end with real data
python test_implementation.py          # Test all new UI components

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

### Web Interface & Analytics

- **Streamlit UI**: Modern web interface accessible via `streamlit run streamlit_app.py`
- **Analytics Dashboard**: Real-time performance monitoring, processing metrics, and SermonAudio insights
- **RAG System**: ChromaDB + sentence-transformers for natural language queries over sermon data
- **Chat Interface**: AI-powered conversational analytics ("What sermons have highest engagement?")
- **Performance Monitoring**: Real-time system resource tracking (CPU, memory, GPU, network)
- **Cost Tracking**: LLM API usage monitoring and optimization recommendations

### Audio Processing Integration Points

- **Enhancement methods**: `"clear"`, `"deepfilternet"`, `"none"`
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
- **`ui/`** - Streamlit web interface and analytics components
- **`ui/ui_pages/`** - Individual page components for web interface
- **`tests/sample_audio.mp3`** - Required for audio-dependent tests (gitignored)
- **`.venv/`** - Virtual environment (ALWAYS use UV: `uv venv --python 3.11`)
- **`pyproject.toml`** - Primary dependency management (UV-compatible)
- **`analytics_vector_db/`** - ChromaDB vector database for RAG system

### Performance Considerations

- **Large audio files**: Automatic chunking based on available memory
- **Model initialization**: Cached after first load, device-aware placement
- **API rate limits**: Built-in throttling for SermonAudio calls
- **Memory management**: Monitor usage with `psutil`, clean up models between runs

## Key Files for Understanding Context

- `config.yaml` - All runtime configuration
- `streamlit_app.py` - Main web interface entry point
- `ui/analytics_chat.py` - AI-powered analytics chat interface
- `ui/rag_system.py` - Vector database and retrieval system
- `ui/performance_monitor.py` - Real-time system monitoring
- `ui/sermonaudio_analytics.py` - SermonAudio data provider
- `tests/ENHANCEMENT_MODEL_TESTING_RESULTS.md` - Model performance benchmarks
- `docs/LLM_Configuration_Guide.md` - Provider setup examples
- `docs/ANALYTICS.md` - Analytics features documentation
- `docs/RAG_SYSTEM.md` - RAG technical documentation
- `docs/PERFORMANCE_MONITORING.md` - Performance monitoring guide
- `pyproject.toml` - Dependencies and tooling config (UV primary)
- `requirements.txt` - Runtime dependencies (sync with pyproject.toml)
- `ui/requirements-ui.txt` - Additional web interface dependencies
- `uv.lock` - UV lockfile for reproducible builds

## Common Gotchas

- **Import order matters**: Audio ML libraries can conflict - use context managers to suppress warnings
- **Windows path handling**: Use `Path` objects, test both forward/backslashes  
- **Model downloads**: First run downloads GBs of data - warn users and cache properly
- **Config migration**: Always call `migrate_legacy_config()` when loading config
- **Test isolation**: Audio tests must not require external resources - skip gracefully
