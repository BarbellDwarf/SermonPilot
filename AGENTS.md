# SermonPilot — AI Agent Context

## Project Overview
Automated sermon processing tool that enhances audio (DeepFilterNet/Resemble), transcribes (Whisper), generates AI metadata (title/description/hashtags via Ollama/OpenAI), and uploads to SermonAudio API. Provides a Streamlit web UI and CLI.

## Architecture

```
sermon_updater.py        — Core CLI processing engine (3871 lines)
streamlit_app.py         — Streamlit UI entry point
ui/
├── database.py          — SQLite models: SermonDatabase, SermonRepository
├── job_queue.py         — Background job system
├── job_executors.py     — Job execution (calls process_new_sermon)
├── ui_processor.py      — UI processing interface
├── sermonaudio_api.py   — SermonAudio API client
├── sermon_importer.py   — Filesystem → DB import
└── ui_pages/
    ├── library.py       — Library page (reads SQLite; fetches transcript from API if missing locally)
    ├── new_sermon_enhanced.py — Main New Sermon page
    ├── dashboard.py, batch_update.py, validation.py, jobs.py, analytics.py, ...
src/
├── audio_processing.py       — Audio enhancement
├── transcription.py          — Whisper transcription (now includes faster-whisper backend)
├── llm_manager.py            — LLM provider abstraction
└── processing/orchestrator.py — Options dataclass
config.yaml                  — Main config
processed_sermons/           — Output directory
sermon_processor.db          — SQLite database (UI persistence)
```

## Key Conventions

- **No comments in code** unless absolutely necessary (existing code has some, but don't add new ones)
- **Python 3.10+**, uses `from __future__ import annotations` style
- **Type hints** everywhere (`dict[str, Any]` not `dict`)
- **Black** formatting (line-length=100), **Ruff** linting
- **Pytest** for tests; conftest.py skips heavy tests by default
- **ffmpeg/ffprobe** for audio duration detection and video muxing

## Database (SQLite — `sermon_processor.db`)

Key tables: `sermons` (id TEXT PK, title, speaker, recorded_date, status TEXT DEFAULT 'pending', ...), `sermon_files`, `processing_info`, `sermon_content`, `sermon_search` (FTS5), `upload_info`.

**Status values:** `'pending'`, `'processed'` (uploaded to SermonAudio), `'draft'` (dry run — saved locally only), `'error'`.

## Processing Pipeline (`process_new_sermon`)

1. Clean audio (optional clean-audio.py) → 2. Enhance audio (DeepFilterNet/Resemble) → 3. Mux video (if input is video) → 4. Transcribe (Whisper/faster-whisper) → 5. Generate metadata (LLM: title, description, hashtags) → 6. **Dry run check** (early return if `dry_run=True`) → 7. Create on SermonAudio API → 8. Upload media → 9. Save to filesystem + database

**Dry run** currently saves to filesystem + DB with status `'draft'` for Library visibility, but skips API calls.

## Critical Code Paths

| Action | File | Line |
|--------|------|------|
| `process_new_sermon()` | `sermon_updater.py` | 1276 |
| Dry run early return (now saves to DB) | `sermon_updater.py` | ~1593 |
| Database save (normal) | `sermon_updater.py` | ~1704 |
| Database save (dry run) | `sermon_updater.py` | ~1593 (in dry run block) |
| `publish_dry_run_sermon()` (push draft → API) | `sermon_updater.py` | ~1858 |
| `get_sermon_transcript()` (fetch from API) | `sermon_updater.py` | 283 |
| Library page data fetch | `ui/ui_pages/library.py` | 347 (calls `repo.get_all_sermons()`) |
| Library "Generate" button (fetches transcript from API if missing locally) | `ui/ui_pages/library.py` | 87 (`generate_ai_content`) |
| `SermonRepository.save_sermon()` | `ui/database.py` | 561 |
| `SermonRepository.get_all_sermons()` | `ui/database.py` | 839 |
| Job executor | `ui/job_executors.py` | 340 (`execute_sermon_processing_job`) |

## Important Patterns

- **Jobs system:** UI creates jobs via `job_queue.py`, executed by `job_executors.py`, which calls `sermon_updater.process_new_sermon()` for new sermons
- **Progress reporting:** `progress_callback(progress_pct: float, message: str)` called throughout `process_new_sermon`
- **Result dict keys:** `success`, `sermon_id`, `title`, `description`, `hashtags`, `enhanced_audio_path`, `transcript_length`, `transcript`, `error`, `output_dir`
- **Config access:** `config.get('key', default)` — YAML config loaded at module level
- **Import pattern:** `from ui.database import SermonRepository` used inline (inside function body) in `sermon_updater.py` to avoid circular imports
- **Push dual behavior:** `push_sermon_metadata_to_api()` in `library.py:26` detects `status == 'draft'` → calls `publish_dry_run_sermon()` to create+upload on SermonAudio; otherwise updates existing sermon metadata
- **Auto-refresh in Jobs:** `ui/ui_pages/jobs.py:72` uses `time.sleep(2)` + `st.rerun()` when running/queued jobs exist (replaced broken `components.html` JS that only reloaded an iframe)
- **Transcript fallback:** `generate_ai_content()` in `library.py:87` tries local transcript first, falls back to `sermon_updater.get_sermon_transcript()` (fetches from SermonAudio API via `transcript.downloadURL`)
- **Transcription backends:** `transcription.py` now includes faster-whisper (CTranslate2) backend as default with fallback to standard whisper; supports both AMD ROCm and NVIDIA CUDA via device detection
