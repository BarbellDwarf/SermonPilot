# AI Coding Agent Instructions for SermonPilot

## Architecture Overview

SermonPilot is a sermon processing pipeline with a CLI and a Streamlit web
UI:

1. **`sermon_updater.py`** - CLI orchestrator. Downloads sermons from the
   SermonAudio API, runs enhancement, transcription, and LLM metadata
   generation, and uploads results.
2. **`src/audio_processing.py`** - Audio enhancement. Supports DeepFilterNet
   (PyTorch) and Clear (ONNX, desert-ant-labs) models, plus custom Clear
   models and no enhancement.
3. **`src/transcription.py`** - Whisper transcription with four backends:
   `whisper_local`, `faster_whisper_local`, `whisper_openai`,
   `whisper_openrouter`.
4. **`src/llm_manager.py`** - Multi-provider LLM abstraction (Ollama,
   OpenAI-compatible, Anthropic, xAI, Google, Groq, OpenRouter) with
   primary/fallback/validator providers.
5. **`streamlit_app.py`** - Streamlit web UI. Page components live in
   `ui/ui_pages/`; analytics, RAG, and job infrastructure live in `ui/`.

**Key Data Flow**: SermonAudio API → Audio Download → AI Enhancement →
Transcription → LLM Summary/Hashtags → Upload Back → Analytics & Insights

## Essential Patterns

### Configuration-Driven Everything

- `config.yaml` is the single source of truth. It supports `${VAR}` and
  `${VAR:-default}` environment substitution.
- `audio_enhancement_method` is a flat top-level key (values:
  `deepfilternet`, `clear-studio`, `clear-natural`, `custom`, `none`).
  Related keys: `clear_model_variant`, `clear_custom_repo`,
  `clear_custom_file`, `audio_noise_reduction`, `audio_normalize`,
  `audio_gain_db`, `audio_target_level_db`.
- `transcription.backend` selects the transcription backend.
- `llm.primary` / `llm.fallback` / `llm.validator` each carry a `provider`
  plus a provider-named sub-block.
- Legacy config is migrated automatically on load by
  `src/core/config.py` (`_migrate_legacy_config`); LLM-specific legacy
  formats are handled by `migrate_legacy_config()` in `src/llm_manager.py`.
- `debug: true/false` and the `--verbose` flag control logging output.

### Dual-Provider Pattern (LLM + Audio)

```python
# LLM: primary → fallback → validator
llm_manager.chat(messages)

# Audio: enhancement method → fallback to no-op
processor = AudioProcessor(enhancement_method="deepfilternet")
```

### Graceful Degradation Chain

**Audio**: chosen enhancement method → copy original file unchanged
**LLM**: Primary provider → Fallback provider → hard failure with a clear
message
**Models**: GPU (CUDA/ROCm) → CPU

### Test-First Development

- All tests live in `tests/` (`testpaths = ["tests"]` in `pyproject.toml`).
  Never put test files elsewhere.
- The default `pytest` run is an offline fast suite. Tests that need
  network, audio, or GPU resources are marked `heavy` and skipped unless
  `--run-heavy` is passed.
- `tests/conftest.py` points `SA_UPDATER_CONFIG` and `DATABASE_URL` at
  throwaway paths, so tests never read real `config.yaml` or real
  credentials.
- Documentation goes in `docs/`. Never put docs in the repo root.

## Critical Commands

### Development Setup

```bash
# UV package manager (REQUIRED - handles Python versions and dependencies)
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# Install from the lockfile and pyproject.toml
uv sync

# Or install from the requirements directory
uv pip install -r requirements/requirements.txt
```

There is no `requirements.txt` at the repo root. Requirement files live in
`requirements/`.

### Web Interface

```bash
streamlit run streamlit_app.py
# Access at http://localhost:8501
```

### Testing Workflow

```bash
# Fast, offline suite
pytest

# Include tests that need network, audio, or GPU resources
pytest --run-heavy

# A single file
pytest tests/test_pipeline.py
```

Current test files: `tests/conftest.py`, `tests/test_sermonaudio_api.py`,
`tests/test_pipeline.py`, `tests/test_cli_dispatch.py`,
`tests/test_publish_dry_run.py`, `tests/test_batch_processing.py`. There is
no `tests/sample_audio.mp3`; audio-dependent tests generate fake audio bytes
in `tmp_path` fixtures.

### CLI

```bash
# Create a new sermon from an audio file (dry run saves locally, no API calls)
python sermon_updater.py new-sermon audio.mp3 --speaker "Speaker Name" --date "2024-01-15" --dry-run

# Process existing sermons from SermonAudio
python sermon_updater.py sermon-update --since-days 30

# Update metadata only (skip audio processing)
python sermon_updater.py metadata-update --force-description

# List sermons without processing
python sermon_updater.py list --since-days 30 --list-only --limit 10

# Validate sermon descriptions
python sermon_updater.py validation --validate-descriptions

# Global flags: --dry-run, --auto-yes, --limit N, --config PATH, -v/--verbose
```

Subcommands and aliases: `new-sermon`, `process`/`sermon-update`,
`metadata-update`, `validate`/`validation`, `list`. Run
`python sermon_updater.py -h` for the full flag list. Argument parsing
lives in `src/cli/parser.py` (`CLIParser`).

### Model Management

```bash
# Ollama models (local inference)
ollama pull llama3.1:8b
ollama list

# Check GPU availability
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
nvidia-smi
```

## Project-Specific Conventions

### Audio Enhancement

- **Enhancement methods**: `deepfilternet` (PyTorch DFN3), `clear-studio`
  and `clear-natural` (Clear ONNX models, no PyTorch dependency),
  `custom` (Clear with a custom repo/file from `clear_custom_repo` /
  `clear_custom_file`), `none` (no enhancement).
- Unknown method values fall back to `deepfilternet` with a warning.
- DeepFilterNet is imported as `df` (`from df import enhance, init_df`).
- Device selection: `cuda` if `torch.cuda.is_available()`, with ROCm
  detection via `torch.version.hip`, otherwise `cpu`.
- Clear ONNX inference can run on CUDA, ROCm, or CPU through ONNX Runtime.

### LLM Providers

Supported `provider` values: `ollama`, `openai`, `anthropic`, `xai`,
`google`, `groq`, `openrouter`. See `docs/LLM_Configuration_Guide.md` for
setup examples.

### Transcription Backends

`transcription.backend` values: `whisper_local` (OpenAI Whisper package),
`faster_whisper_local` (faster-whisper, CTranslate2), `whisper_openai`
(OpenAI API), `whisper_openrouter` (OpenRouter API). Local backends accept
`model`, `device`, `compute_type`, and `language` sub-keys.

### File Structure Conventions

- `processed_sermons/{speaker}/{series}/{title}/` - per-sermon output with
  audio, transcript, and metadata files
- `tests/` - all test files (never put tests elsewhere)
- `docs/` - all documentation files (never put docs in the repo root)
- `ui/` - Streamlit UI and analytics components
- `ui/ui_pages/` - individual page components
- `src/` - processing, LLM, transcription, and CLI parser modules
- `requirements/` - requirement files (CPU, GPU, ROCm, dev, models)
- `pyproject.toml` - primary dependency manifest (UV-compatible)
- `sermon_processor.db` - SQLite database for UI persistence

### Removed or Optional Features

- **Resemble Enhance**: not present. Do not reference it.
- **SpeechBrain / VoiceFixer / Demucs**: not part of the enhancement chain.
  They appear only as commented-out optional dependencies in
  `pyproject.toml` and `requirements/`.
- Audio files (`*.mp3`, `*.wav`, etc.) are gitignored. Tests never depend
  on checked-in audio.

## Key Files for Understanding Context

- `config.yaml` - all runtime configuration (gitignored; see
  `config/config.example.yaml`)
- `streamlit_app.py` - web UI entry point
- `sermon_updater.py` - CLI engine (`process_new_sermon` at line 1348)
- `src/cli/parser.py` - CLI argument definitions
- `src/audio_processing.py` - audio enhancement
- `src/transcription.py` - transcription backends
- `src/llm_manager.py` - LLM provider abstraction
- `ui/database.py` - `SermonDatabase`, `SermonRepository`
- `ui/job_queue.py`, `ui/job_executors.py` - background job system
- `ui/performance_monitor.py` - system and processing metrics
- `ui/ui_pages/` - Streamlit pages (library, dashboard, jobs, analytics, ...)
- `docs/LLM_Configuration_Guide.md`, `docs/PERFORMANCE_MONITORING.md`,
  `docs/GPU_INSTALLATION.md`, `docs/UV_SETUP.md`

## Common Gotchas

- **Import order matters**: audio ML libraries can conflict; suppress
  warnings with context managers where needed.
- **Windows paths**: use `Path` objects, never hard-coded separators.
- **Model downloads**: the first run downloads model weights. Cache them in
  the standard cache directories (`~/.cache`, mounted as a volume in
  Docker).
- **Config migration** runs automatically in `src/core/config.py`; no
  manual call needed.
- **Test isolation**: tests must not require network, audio, GPU, or real
  credentials. The fast suite runs fully offline.
- **Docker image contents**: `.dockerignore` excludes `tests/` and `docs/`
  from the image, so there is no pytest or test suite inside the container.
- **Config keys are flat for audio**: `audio_enhancement_method`, not a
  nested `audio_enhancement.method` block.
