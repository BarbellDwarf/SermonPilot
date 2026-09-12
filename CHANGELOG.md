# Changelog

All notable changes to SermonPilot are documented here.

## v1.6.10 (2026-09-12)

Audio quality: no more low-bitrate re-encode on video mux.

### Fixed

- Enhanced audio muxed into video is stream-copied when already AAC (mp4/m4a/aac), instead of being re-encoded by ffmpeg's default AAC bitrate (~70k mono, measured on the deployed output). Other formats are encoded once at 192k. The previous chain was WAV -> AAC 192k -> AAC ~70k, a second lossy pass that audibly degraded speech and was introduced with the v1.4.0 video remux

## v1.6.9 (2026-09-12)

Trailing self-talk removed from generated text.

### Fixed

- extract_final_answer now drops planning paragraphs from both edges of the candidate, not just the start. Model self-talk like "Paragraph: I'll estimate. Let me count words: roughly 220 words." no longer ends a stored description
- Planning signals extended with "the task:", "i'll estimate", "count words", and "paragraph:"

## v1.6.8 (2026-09-12)

Sentence-safe description trimming.

### Fixed

- Long descriptions are trimmed at sentence boundaries instead of mid-word: whole sentences are kept while they fit, and a single oversized sentence is cut at a word boundary and closed with a period. Applies to the Library generation flow and the processing engine's summary cap
- Planning detection also catches "The task:" style preambles from models that restate instructions

## v1.6.7 (2026-09-11)

Resource-aware queueing and clean output from planning-style models.

### Fixed

- Descriptions no longer store the model's planning text: when a model emits "The user wants...", key points, and a "Draft:" section as visible content, the final draft is extracted before saving (library and processing paths)
- The job queue now waits for resources instead of starting jobs into an overloaded host: a queued job only starts when free RAM clears job_queue.min_free_ram_gb (default 3 GB) and free GPU VRAM clears min_free_vram_gb (default 1.5 GB); jobs stay Queued, with a rate-limited log line explaining the wait
- MemoryError during a job now records a clear failure message instead of a raw traceback, and does not poison subsequent jobs

### Documentation

- job_queue thresholds documented in the example config and all three variant templates

## v1.6.6 (2026-09-11)

Description generation completeness on reasoning models.

### Fixed

- Ollama requests now disable hidden reasoning by default (llm.primary.ollama.think, default false). Thinking models like glm-5.3-flash:cloud were spending the entire output token budget on invisible reasoning, so descriptions ended mid-sentence with no ellipsis and Ollama reported done_reason=length. Direct answers are complete and faster; set think: true per provider when reasoning is wanted
- Responses truncated at the token limit now log a warning naming max_tokens and the think setting, instead of failing silently
- The Library Generate path's description prompt targets 900-1200 characters like the processing engine (it still carried the old 1600-ceiling wording)
- Template and example configs document the think option

## v1.6.5 (2026-09-11)

Status truth and prompt template visibility.

### Fixed

- System status panel no longer reports false errors on Docker installs: it reads the resolved settings-database configuration instead of a config.yaml that intentionally does not exist
- The per-variant config template now acts as a defaults layer for existing installs, so settings like audio_enhancement_method resolve even when a database predates the template seeding
- Settings > Templates is populated out of the box: built-in prompt templates (title, short title, description, hashtags, hashtag verification) ship as defaults; enable or edit them per install

## v1.6.4 (2026-09-11)

Login persistence, version visibility, and the config-cleanup follow-through.

### Added

- Persistent sign-in: a signed cookie keeps sessions alive across browser refreshes and restarts for 30 days; changing APP_PASSWORD revokes every session. Sign out button in the sidebar
- Version indicator in the sidebar and on the login screen, resolved from pyproject.toml

### Fixed

- Engine file-config vestiges removed: the settings database is the only runtime source; a database outage is a clear error, never a silent file read
- Library AI generation validates the sermon still exists before saving (stale selections get guidance instead of a FOREIGN KEY traceback)
- Description prompts target 900-1200 characters instead of treating the 1600 API ceiling as a goal, so responses stop being chopped with ellipses

## v1.6.3 (2026-09-11)

Single config source and first-boot correctness round, driven by field logs from the deployed GPU host.

### Fixed

- Settings saved in the UI now reach the processing engine without a restart: the engine rebuilds its runtime constants from the settings database on every sermon run
- Jobs re-resolve config at execution time; a queue-time snapshot (or an empty one) can no longer wipe good values (the reported settings-not-applied loop)
- No config file is ever written; the settings database is the only persistent store. The SermonAudio API client resolves keys through the settings DB instead of warning about a missing config.yaml
- Fresh containers open configured out of the box: the one-time database seed merges the built-in variant template (enhancement, transcription, output settings) under the env-mapped keys
- Audacity integration removed end to end (processor, settings toggle, templates, migration key)
- Security-scan validates config.example.yaml (config.yaml is untracked by design); dependency-security audits the resolvable base lockfile

## v1.6.2 (2026-09-10)

Docker hardening round: per-variant config templates, config resolution (DB, env, then defaults), output hygiene, and CUDA GPU enablement.

### Fixed

- Docker: /data volume ownership repaired or guarded at startup; per-variant config templates; variant printed at startup; uv index strategy so GPU requirement sets install CUDA torch (cu124 index shadowed PyPI packages)
- Docker: cuda image actually uses its GPU now. ONNX Runtime pinned below 1.27 (CUDA 12 wheels) on a cuDNN-bearing base (12.4.1-cudnn-runtime); faster-whisper GPU unblocked by the same cuDNN
- Docker: GPU override file (docker-compose.gpu.yml) attaches NVIDIA devices without editing compose; startup report prints torch CUDA state, ORT providers, and CUDA library loadability
- Config: single-source resolution, env seeding, embeddings auto_download default True; dead config keys purged from example and templates
- Jobs: queue serialized by default (max_workers=1); disk-backed temp/upload dirs with per-job cleanup
- Output: plain-ASCII runtime logs everywhere (emoji banners removed)
- App: settings page lists only constructible providers (ollama, openai, xai, groq, openrouter); stale direct config.yaml reads replaced with the resolution path

## v1.6.1 (2026-08-21)

Post-release security and quality audit remediation: 109 findings addressed across UI, backend, database, jobs, pipeline, providers, and infrastructure.

### Fixed

- Security: auth gate enforced per request (was bypassed after first session); MD5 hardened; sermon paths sanitized against traversal
- Crashes: regenerated descriptions upload again; status-update SQL rewritten (raised on every second write); DeepFilterNet retry sample rate; sys.exit calls in LLM providers replaced with exceptions
- Data loss: transcript fetch preserves AI content; dry-run publish preserves created_at and cleans child tables; API-create failure persists recovery draft; failed uploads keep media
- Jobs: cancellation checkpoints before remote create/save; duplicate-sermon guard on retry; per-job temp dirs; transcripts stripped from persisted results; retention for terminal jobs and LLM usage rows; thread-safe singleton; WAL mode
- Pipeline: WAV output transcoded to input container; single series application; configured language code; uploaded copies cleaned; transcript reuse fixed
- Providers: broken Anthropic/Google removed; env-key fallbacks; sampling options + num_ctx; full fallback chain; no global env mutation; honest unknown-model cost handling
- Context/validation: chunked summarization for long transcripts; titles sampled beginning/middle/end; validation checkbox wired end-to-end; fail-closed validation errors
- Transcription: typed failures replace silent empty strings; tiny-model downgrade removed; cloud model picker honored; language/compute wiring; OpenRouter timeout + progress parity
- Entities: custom pastors/series/event types persisted; normalized resolution; missing-series warning
- RAG/chat: answers routed through the app's LLM stack; fabricated embedding providers removed; refresh uses upserts

### Changed

- UI: emoji-free prose, library toolbar + card rows, dark/light theme tokens, sidebar dividers, auth gate, top-gap fix across every page
- CI: action SHAs pinned in docker-build; pip caching; minimal fast-job dependencies
- Streamlit minimum raised to 1.36.0

### Known Issues

- chromadb CVE-2026-45829: fix blocked on upstream 1.6.0 (embedded usage not exposed)
- torch advisories: accepted risk pending ROCm regression gate (see docs/GPU_INSTALLATION.md)


## v1.6.0 (2026-08-20)

A full application review: persistence, series upload, audio processing, CI, security, UI, docs, and release automation.

### Added

- Series upload end-to-end: `seriesID` payloads on sermon creation, batch series selector, processing fixes
- Optional password auth, localhost bind, and secrets warnings for the web UI
- Status checks: DeepFilterNet compatibility shim before import, correct API probe endpoint
- Database migration script (`scripts/migrate_db.py`): rebuilds FTS, dedupes rows, removes orphans
- Release automation (`.github/workflows/release.yml`): version checks on release PRs, auto-tagging on merge, drafted GitHub Releases
- Dependency review action on PRs; osv-scanner dependency scanning without auth
- Container smoke test in the Docker build before push
- Gentle de-esser high-shelf after audio enhancement

### Fixed

- Metadata persistence: startup refresh, Docker DB path, duplicate-render issues
- Audio enhancement: destructive noise gate disabled, NaN guard, output sanity check, RMS computed from a float64 copy
- Database layer: fresh databases get a working FTS table, `update_sermon` rebuilds FTS, re-save no longer duplicates FTS rows or resets `created_at`, search snippets highlight the matched column, `delete_sermon` cleans all related tables, foreign keys enforced
- Job queue: cancelling a running job sticks (all executors), API keys stripped from persisted job parameters, standalone imports fixed
- Pipeline save paths: one canonical `file_paths` key set; dry-run publish is a single transaction
- Library page: feedback survives reruns, date/sort crashes guarded, duration formatted as MM:SS, list rendered as card units with clear entry separation
- Settings page: session-state widget conflicts resolved, validation toggle persists, device/compute_type fallbacks, secrets masked in config dumps
- New Sermon page: custom speaker/event names submit correctly, Reset All clears real keys, primary action visible at 1440x900
- Batch Update: selection persists, tabs isolated, Cancel/Reset semantics fixed, exports implemented
- Validation/Analytics/Jobs pages: dead code removed, filters wired, honest zero-data states, empty states as invitations
- Navigation: direct `/dashboard` URLs work, promo banner hidden, dead session keys removed
- Dark mode: theme tokens for both modes, WCAG 2.2 AA contrast verified, headers/cards/status colors adapt
- Docker build: dispatch builds get timestamp-only tags, CUDA image installs GPU torch, compose works on Linux, cache volume writable by the app user
- Security: MD5 uses `usedforsecurity=False`, sermon paths sanitized against traversal, workflow permissions tightened

### Changed

- Whole-repo lint pass: 2,275 ruff errors to zero; ruff now gates CI
- Dependency manifest consolidated: 60 to 28 runtime deps, single torch/onnxruntime/chromadb pins, wheel packages `src/` and `ui/` correctly, dev tools moved to extras
- App-wide emoji removal from UI text; library header condensed to a toolbar row
- Streamlit minimum raised to 1.36.0 (`st.container(key=...)`)
- Documentation rewritten or patched across 18 files; line references verified against master

### Removed

- Unused runtime dependencies (noisereduce, matplotlib, gradio, transformers, speechbrain, torchcodec, and 20+ more)
- Orphaned requirements files (`requirements-gpu-minimal.txt`, `requirements-gpu-full.txt`)
- Dead code: config management page, validation batch stubs, jobs test-job helper, `wait_for_services.py`

### Known Issues

- The dependency-security scan reports torch advisories (GHSA-rrmf-rvhw-rf47, GHSA-vgrw-7cvw-pwgx). No patched build is compatible with the verified ROCm setup; documented in `docs/GPU_INSTALLATION.md`.
