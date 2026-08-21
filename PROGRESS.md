# TKT-154 progress: CI supply chain and caching

Branch: fix/ci-supply-chain (base = master 1aff3c5)

## Done

- Read docker-build.yml: five floating refs found (checkout@v4, setup-buildx@v3,
  login-action@v3 x2 jobs, build-push@v6).
- Collected repo's pinned-SHA convention from ci.yml / release.yml / security-check.yml:
  - actions/checkout @ 11bd71901bbe5b1630ceea73d27597364c9af683 (v4.2.2)
  - actions/setup-python @ 42375524e23c412d93fb67b49958b491fce71c38 (v5.4.0)
  - actions/upload-artifact @ b4b15b8c7c6ac21ea08fcf65892d2ee8f75cf882 (v4.4.3)
- Docker actions absent elsewhere in repo, so verified latest tags via GitHub API
  (all resolved objects are type=commit):
  - docker/setup-buildx-action v3.12.0 -> 8d2750c68a42422c14e847fe6c8ac0403b4cbd6f
  - docker/login-action v3.7.0 -> c94ce9fb468520275223c153574b00df6fe4bcc9
  - docker/build-push-action v6.19.2 -> 10e90e3645eae34f1e60eeb005ba3a3d33f178e8

## AUDIT-014 analysis (minimal dep set)

Module-level import trace for the fast suite:
- sermon_updater.py top level: stdlib + requests + dotenv(load_dotenv) +
  sermonaudio (stubbed by conftest) + src.sermon_paths (stdlib) + lazy
  cli.parser/core.config/llm_manager/processing.orchestrator/transcription ->
  core.config needs yaml; llm_manager+transcription need requests;
  audio_processing import is try/except guarded (no torch needed).
- ui.database, ui.sermonaudio_analytics: stdlib + requests.
- ui.sermon_metadata: needs streamlit (unguarded module-level import).
- Minimal set: pytest, ruff, requests, python-dotenv, PyYAML, streamlit.

Proof: clean venv (/tmp/opencode/ci-min-venv) with only those packages ->
ruff check . passes; pytest -m "not heavy" -> 30 passed, 0.28s.
No manifest files touched.

## Changes

- [x] docker-build.yml: pin all five refs, add ci.yml-style pinning comment.
- [x] ci.yml: setup-python cache: 'pip' keyed on requirements/requirements.txt;
      fast job installs the verified minimal set instead of full requirements.
- [x] Validate both files parse (python yaml.safe_load).
- [x] Prove CI sequence in clean venv: minimal install -> pip install -e .
      --no-deps (hatchling, build isolation) -> ruff check . -> 30 passed.
- [ ] Commit.

## Final pins in docker-build.yml

| Action | SHA | Tag |
|---|---|---|
| actions/checkout | 11bd71901bbe5b1630ceea73d27597364c9af683 | v4.2.2 (repo convention) |
| docker/setup-buildx-action | 8d2750c68a42422c14e847fe6c8ac0403b4cbd6f | v3.12.0 (latest v3) |
| docker/login-action | c94ce9fb468520275223c153574b00df6fe4bcc9 | v3.7.0 (latest v3, both jobs) |
| docker/build-push-action | 10e90e3645eae34f1e60eeb005ba3a3d33f178e8 | v6.19.2 (latest v6) |

## Cache key config (ci.yml)

```yaml
cache: 'pip'
cache-dependency-path: requirements/requirements.txt
```

Fast job installs: ruff pytest requests python-dotenv PyYAML streamlit,
plus `pip install -e . --no-deps`.

