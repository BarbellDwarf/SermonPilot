# Test Fixtures

There is no `tests/fixtures/` directory in this repository. Test fixtures
are defined programmatically in `tests/conftest.py`:

- `SA_UPDATER_CONFIG` points the app at a throwaway config written into a
  temp directory, and `DATABASE_URL` points at a throwaway SQLite database
  in the same temp directory, so tests never read the real `config.yaml` or
  the real `sermon_processor.db`
- The `sermonaudio` package is stubbed with a fake module when it is not
  installed, so the fast suite runs offline
- Tests that need network, audio, or GPU resources are marked `heavy` and
  skipped unless `--run-heavy` is passed

Audio bytes are generated in `tmp_path` fixtures inside the tests
themselves; no audio files are checked into git.

The historical `tests/fixtures/` layout (`sample_audio/`, `mock_configs/`,
`test_data/`) was removed along with the old test suite. See
`tests/tests-README.md` for the current test layout and commands.
