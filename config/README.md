# Configuration Directory

This directory holds configuration templates that ship with the Docker images,
plus YAML examples kept for reference. No file here is read at run time.

## Files

### `templates/{cuda,rocm,cpu}.yaml`
Per-Docker-variant templates. The Dockerfile sets `SERMONPILOT_VARIANT`, and the
matching template is imported into the settings database once, on a fresh
database only. After that the database is authoritative.

### `config.example.yaml`
A reference config showing every supported path. It is not copied to
`config.yaml` for normal use. A pre-database install that still has a
`config.yaml` (or a file named by `SA_UPDATER_CONFIG`) has its contents imported
into the database once, when the database has no configuration row yet.

### `llm_examples.yaml`
LLM provider configuration examples for different services:

- xAI Grok configuration
- Anthropic Claude configuration
- OpenAI configuration
- Ollama configuration
- Provider fallback examples

## How settings resolve

Settings come from, lowest to highest priority:

1. Built-in defaults
2. The per-variant template (fresh database only)
3. The SQLite `config_cache.app_config` row
4. Environment variables mapped in `src/core/config.py::ENV_CONFIG_MAP`

Environment variables always win while they are set. Config-like variables are
seeded into the database once on startup, when no value is saved for their path
yet. Deploy-time secrets (API keys) stay in the environment and are never copied
into the database.

Edit settings in the web console Settings page or the Streamlit settings page,
not in a file.
