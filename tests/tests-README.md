# Test Files

## Fast suite (default)

The default `pytest` run is a fast, offline suite. It never touches the
network, real credentials, audio files, or GPUs.

```bash
pytest
```

`testpaths = ["tests"]` in `pyproject.toml` makes `tests/` the default
discovery root.

Tests that need network, audio, or GPU resources are marked `heavy` and are
skipped by default. Run them explicitly with:

```bash
pytest --run-heavy
```

## Test files

- `conftest.py` - Shared fixtures. Points the app at a throwaway config and
  database via `SA_UPDATER_CONFIG` and `DATABASE_URL`, stubs the
  `sermonaudio` package when it is not installed, and registers the
  `--run-heavy` option.
- `test_sermonaudio_api.py` - Mocked tests for the SermonAudio analytics
  client (`ui/sermonaudio_analytics.py`). No network, no real credentials.
  The client reports mock mode when no credentials are configured.
- `test_pipeline.py` - `process_new_sermon` with `dry_run=True`: saves the
  draft locally, skips API and transcription calls, and reports a missing
  input file as an error.
- `test_cli_dispatch.py` - `cli_main` subcommand dispatch: `new-sermon`,
  `process`/`sermon-update`, `metadata-update`, `validate`/`validation`,
  and `list`. Handlers are patched, so nothing runs for real.
- `test_publish_dry_run.py` - `publish_dry_run_sermon` with a fake
  repository and mocked API calls.
- `test_batch_processing.py` - Regression: batch processing invokes
  per-sermon processing exactly once per sermon, and the list-only path
  does not process.

There are no other test files. In particular, there is no
`tests/sample_audio.mp3` and no audio fixture checked into git.

## Notes

- Tests never read the real `config.yaml` or real credentials.
  `conftest.py` sets `SA_UPDATER_CONFIG` to a throwaway config and
  `DATABASE_URL` to a throwaway database inside a temp directory.
- Audio files (`*.mp3`, `*.wav`, `*.flac`, ...) are excluded from git via
  `.gitignore`. Tests that need audio generate fake bytes in `tmp_path`
  fixtures.
- `tests/` is excluded from the Docker image via `.dockerignore`, so tests
  run from a local checkout, not inside a container.
