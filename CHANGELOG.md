# Changelog

All notable changes to SermonPilot are documented here.

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
