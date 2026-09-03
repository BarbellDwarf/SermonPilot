# SermonPilot -- AI Agent Context

## Project Overview
Automated sermon processing tool that enhances audio (DeepFilterNet/Clear), transcribes (Whisper), generates AI metadata (title/description/hashtags via Ollama/OpenAI), and uploads to SermonAudio API. Provides a Streamlit web UI and CLI.

## Architecture

```
sermon_updater.py        -- Core CLI processing engine
streamlit_app.py         -- Streamlit UI entry point
ui/
|-- config_utils.py      -- Single config resolution path (see below)
|-- database.py          -- SQLite models: SermonDatabase, SermonRepository (also the settings store)
|-- job_queue.py         -- Background job system (serialized by default, max_workers=1)
|-- job_executors.py     -- Job execution (calls process_new_sermon)
|-- ui_processor.py      -- UI processing interface
|-- sermonaudio_api.py   -- SermonAudio API client
|-- sermon_importer.py   -- Filesystem -> DB import
`-- ui_pages/
    |-- library.py       -- Library page (reads SQLite; fetches transcript from API if missing locally)
    |-- new_sermon_enhanced.py -- Main New Sermon page
    |-- dashboard.py, batch_update.py, validation.py, jobs.py, analytics.py, ...
src/
|-- audio_processing.py       -- Audio enhancement
|-- transcription.py          -- Whisper transcription (whisper-local default; faster-whisper; cloud backends)
|-- llm_manager.py            -- LLM provider abstraction
|-- core/config.py            -- ENV_CONFIG_MAP, env override + ${VAR} expansion helpers
`-- processing/orchestrator.py -- Options dataclass
config/templates/{cuda,rocm,cpu}.yaml -- Per-Docker-variant config templates (import/export artifacts)
processed_sermons/           -- Output directory
sermon_processor.db          -- SQLite database (UI persistence + settings config_cache)
```

### Configuration resolution (no required config.yaml)

`ui/config_utils.resolve_config()` is the single resolution path. Layers,
lowest to highest: built-in defaults; optional file layer at `$SA_UPDATER_CONFIG`;
the SQLite `config_cache` row (an empty database is seeded once from env vars,
and a legacy `config.yaml` is imported once for existing installs); then
`ENV_CONFIG_MAP` env overrides (`src/core/config.py`), which always win;
then `${VAR}` / `${VAR:-default}` expansion. `config.yaml` itself is never
read for resolution: it is a UI export/import artifact only. Docker images
carry per-variant templates under `config/templates/` (selected by the
`SERMONPILOT_VARIANT` env the Dockerfile sets, surfaced at startup).

## Key Conventions

- **No comments in code** unless absolutely necessary (existing code has some, but don't add new ones)
- **Python 3.10+**, uses `from __future__ import annotations` style
- **Type hints** everywhere (`dict[str, Any]` not `dict`)
- **Black** formatting (line-length=100), **Ruff** linting
- **Pytest** for tests (`testpaths = ['tests']` in pyproject.toml); `tests/conftest.py` points the app at a throwaway config and database (`SA_UPDATER_CONFIG`, `DATABASE_URL`), stubs the `sermonaudio` package when missing, and skips `heavy`-marked tests unless `--run-heavy` is passed
- **ffmpeg/ffprobe** for audio duration detection and video muxing

## Database (SQLite -- `sermon_processor.db`)

Key tables: `sermons` (id TEXT PK, title, speaker, recorded_date, status TEXT DEFAULT 'pending', ...), `sermon_files`, `processing_info`, `sermon_content`, `sermon_search` (FTS5), `upload_info`.

**Status values:** `'pending'`, `'processed'` (uploaded to SermonAudio), `'draft'` (dry run -- saved locally only), `'error'`.

## Processing Pipeline (`process_new_sermon`)

1. Clean audio (optional clean-audio.py) -> 2. Enhance audio (DeepFilterNet/Clear) -> 3. Mux video (if input is video) -> 4. Transcribe (Whisper/faster-whisper) -> 5. Generate metadata (LLM: title, description, hashtags) -> 6. **Dry run check** (early return if `dry_run=True`) -> 7. Create on SermonAudio API -> 8. Upload media -> 9. Save to filesystem + database

**Dry run** currently saves to filesystem + DB with status `'draft'` for Library visibility, but skips API calls.

## Critical Code Paths

| Action | File | Line |
|--------|------|------|
| `process_new_sermon()` | `sermon_updater.py` | 1479 |
| Dry run early return (saves to DB as draft) | `sermon_updater.py` | 1916 |
| Database save (dry run block) | `sermon_updater.py` | 2033 |
| Database save (normal) | `sermon_updater.py` | 2171 |
| `publish_dry_run_sermon()` (push draft -> API) | `sermon_updater.py` | 2454 |
| `get_sermon_transcript()` (fetch from API) | `sermon_updater.py` | 311 |
| Library page data fetch | `ui/ui_pages/library.py` | 510 (calls `repo.get_all_sermons(limit=1001)`) |
| Library "Generate" button (fetches transcript from API if missing locally) | `ui/ui_pages/library.py` | 158 (`generate_ai_content`) |
| `SermonRepository.save_sermon()` | `ui/database.py` | 860 |
| `SermonRepository.get_all_sermons()` | `ui/database.py` | 1153 |
| Job executor | `ui/job_executors.py` | 371 (`execute_sermon_processing_job`) |

Line numbers verified against `release/v1.6.2` (08a324f).

## Important Patterns

- **Jobs system:** UI creates jobs via `job_queue.py`, executed by `job_executors.py`, which calls `sermon_updater.process_new_sermon()` for new sermons
- **Progress reporting:** `progress_callback(progress_pct: float, message: str)` called throughout `process_new_sermon`
- **Result dict keys:** `success`, `sermon_id`, `title`, `description`, `hashtags`, `enhanced_audio_path`, `transcript_length`, `transcript`, `error`, `output_dir`
- **Config access:** `config.get('key', default)` on the dict returned by `from ui.config_utils import resolve_config` (or `load_config_from_file()`); engine module level resolves once at import and falls back to a plain file read only if the settings DB is unavailable
- **Import pattern:** `from ui.database import SermonRepository` used inline (inside function body) in `sermon_updater.py` to avoid circular imports
- **Push dual behavior:** `push_sermon_metadata_to_api()` in `library.py:51` detects `status == 'draft'` -> calls `publish_dry_run_sermon()` to create+upload on SermonAudio; `status == 'error'` re-uploads local media; otherwise updates existing sermon metadata
- **Auto-refresh in Jobs:** the Active tab in `ui/ui_pages/jobs.py` renders inside an `@st.fragment(run_every=2.0)` (`_render_active_tab`, line 137), so running/queued job lists update without a full page rerun; the sidebar "Refresh" button calls `st.rerun()`
- **Transcript fallback:** `generate_ai_content()` in `library.py:158` tries the SermonAudio transcript first via `sermon_updater.get_sermon_transcript()`, falls back to the local transcript
- **Transcription backends:** `transcription.py` supports whisper-local (`whisper_local`, the code default), faster-whisper (`faster_whisper_local`, CTranslate2), and OpenAI / OpenRouter cloud backends; device detection (`_detect_device`) maps AMD ROCm to `cuda` for torch-based whisper but passes `allow_rocm=False` for faster-whisper because CTranslate2 has no ROCm support, so it lands on CPU

## Versioning & Release Process

### Version Scheme
- **MAJOR.MINOR.PATCH** (e.g. 1.5.1)
- Bump PATCH for bug fixes (Docker, config, small fixes)
- Bump MINOR for new features (new models, UI changes, major additions)
- Bump MAJOR for breaking changes

### General Workflow (all changes)

Direct commits to `master` are **not allowed**. Every change must go through a branch + PR:

1. **Create a feature/fix branch** -- `git checkout -b fix/description` or `feature/description`
2. **Make your changes and commit** -- `git add -A && git commit -m "description"`
3. **Push the branch** -- `git push origin fix/description`
4. **Create a PR** -- `gh pr create --base master --head fix/description --title "Title" --body "Description"`
5. **Wait for CI/approval** -- the PR must be merged by the user or via the GitHub UI
6. **Delete the branch** -- `git branch -d fix/description && git push origin --delete fix/description`

### Release Steps (in order)

1. **Update `pyproject.toml`** -- change `version = "X.Y.Z"` to the new version
2. **Create a release branch** -- `git checkout -b release/vX.Y.Z`
3. **Commit the version bump** -- `git add pyproject.toml && git commit -m "Bump version X.Y.Z -> X.Y.Z+1"`
4. **Push the branch** -- `git push origin release/vX.Y.Z`
5. **Create a PR** -- `gh pr create --base master --head release/vX.Y.Z --title "Release vX.Y.Z" --body "Version bump and changelog"`
6. **Merge the release PR** -- the release workflow (`.github/workflows/release.yml`) creates the annotated tag `vX.Y.Z` automatically after the merge when the version is not yet tagged
7. **Publish the release draft** -- the workflow drafts the GitHub Release with auto-generated notes; once the Docker build finishes, publish the draft in the GitHub UI (or `gh release edit vX.Y.Z --draft=false`)
8. **Delete the release branch** -- `git branch -d release/vX.Y.Z && git push origin --delete release/vX.Y.Z`

### Release Automation

- `.github/workflows/release.yml` covers the release flow end to end:
  - **On release PRs** (branch `release/vX.Y.Z`, touching `pyproject.toml`): fails unless the version is a valid `MAJOR.MINOR.PATCH` bump above the latest tag, the tag does not exist yet, and the branch name matches the version
  - **On merge to master**: creates the annotated tag `vX.Y.Z` when the pyproject.toml version is not yet tagged, then drafts the GitHub Release with auto-generated notes and dispatches `.github/workflows/docker-build.yml` on the tag ref (refs pushed with GITHUB_TOKEN fire no push events, so the tag push alone would trigger nothing)
  - **On tag push**: validates the tag against `pyproject.toml`, then drafts the GitHub Release with auto-generated notes unless a draft already exists; this path covers manually pushed tags
- `.github/workflows/docker-build.yml` builds and pushes the `cuda`/`rocm`/`cpu` images from any `v*` tag ref, whether pushed or dispatched on the tag: versioned tags plus the moving per-backend and `latest` tags. Plain branch dispatches produce timestamp-only tags
- The release draft is published manually after the Docker build succeeds
- The checks exist so a merged version bump can never ship untagged again

### Tag Naming
- Tags must start with `v` followed by the version: `v1.5.3`, `v1.6.0`, etc.
- The tag message should be a one-line summary of changes
- Tags trigger the release workflow to validate the version and draft the GitHub Release, and the Docker workflow to build and push images to GHCR

### Branch Naming
- Release branches: `release/vX.Y.Z`
- Feature branches: `feature/description-of-feature`
- Fix branches: `fix/description-of-fix`
