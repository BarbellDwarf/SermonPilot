# Test Files

## Fast suite (default)

The default `pytest` run is a fast, offline suite.  It never touches the
network, real credentials, audio files, or GPUs.

```bash
pytest
```

Tests that need network, audio, or GPU resources are marked `heavy` and
are skipped by default.  Run them explicitly with:

```bash
pytest --run-heavy
```

## Test files

- `conftest.py` - Shared fixtures: points the app at a throwaway config and
  database, stubs optional third-party modules, and skips `heavy` tests.
- `test_sermonaudio_api.py` - Mocked tests for the SermonAudio analytics
  client (no network, no real credentials).
- `test_pipeline.py` - `process_new_sermon` with `dry_run=True` (no network,
  transcription, or LLM calls).
- `test_cli_dispatch.py` - `cli_main` subcommand dispatch.
- `test_publish_dry_run.py` - `publish_dry_run_sermon` with a mocked API.
- `test_batch_processing.py` - Regression: batch processing invokes
  per-sermon processing exactly once per sermon.

## Notes

- Tests never read `config.yaml` or real credentials; `conftest.py` points
  `SA_UPDATER_CONFIG` at a throwaway config and `DATABASE_URL` at a
  throwaway database.
- Audio files are excluded from git via `.gitignore`.
