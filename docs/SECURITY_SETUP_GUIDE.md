# Security Setup Guide

## Overview

This guide helps you configure SermonPilot securely: environment variables,
credential management, optional UI password protection, and the pre-commit
credential scanner.

## Quick Setup

### 1. Environment Configuration

Copy the environment template and configure your credentials:

```bash
# Copy the environment template
cp .env.example .env

# Edit with your actual values
nano .env  # or your preferred editor
```

### 2. Required Environment Variables

At minimum, you need:

```bash
# SermonAudio API (Required)
SERMONAUDIO_API_KEY=your-actual-api-key-here
SERMONAUDIO_BROADCASTER_ID=your-actual-broadcaster-id

# At least one LLM provider (choose one or more)
OPENAI_API_KEY=sk-your-openai-key-here
# OR
XAI_API_KEY=xai-your-xai-key-here
# OR configure Ollama (see Ollama Setup below)
```

### 3. Configuration

No configuration file is required. Settings live in the SQLite settings
database: on first launch the environment variables above are seeded into it
automatically, and the web UI Settings page maintains them from then on.

Optional extras:

- `SA_UPDATER_CONFIG` points at a YAML file loaded as an extra layer between
  defaults and the database. `${VAR}` placeholders in that file are expanded
  from the environment.
- `config/config.example.yaml` is a reference listing every recognized key.
- The Settings page's Import/Export tab produces a masked YAML backup and
  restores from an uploaded YAML file.

### 4. Security Validation

Validate your setup:

```bash
# Check configuration security and environment setup
python src/secure_config.py
```

This prints the status of your `.env` file, required variables, and
`config.yaml` (validating `config/config.example.yaml` instead when no
`config.yaml` exists), then loads the configuration through the secure loader
(`src/secure_config.py`), which fails on hardcoded credentials.

## Detailed Setup Instructions

### Environment Variable Reference

See `.env.example` for the complete list of available environment variables. Key sections:

#### Required Variables
- `SERMONAUDIO_API_KEY` - Your SermonAudio API key
- `SERMONAUDIO_BROADCASTER_ID` - Your broadcaster ID

#### LLM Providers (Configure at least one)
- `OPENAI_API_KEY` - OpenAI GPT models (also backs `transcription.whisper_openai`)
- `XAI_API_KEY` - xAI Grok models
- `GROQ_API_KEY` - Groq fast inference
- `OPENROUTER_API_KEY` - OpenRouter models (also backs `transcription.whisper_openrouter`)
- `ANTHROPIC_API_KEY` - Anthropic Claude models
- `GOOGLE_API_KEY` - Google Gemini models
- `AUTO_EDIT_LLM_API_KEY` / `AUTO_EDIT_LLM_BASE_URL` - dedicated auto-edit endpoint (`llm.operations.auto_edit`)

#### Model Pins (optional, override config without editing files)
- `LLM_PROVIDER`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `XAI_MODEL`, `GOOGLE_MODEL`, `GROQ_MODEL`, `OPENROUTER_MODEL`
- `OLLAMA_MODEL`, `WHISPER_MODEL`, `TRANSCRIPTION_BACKEND`

#### Audio / Output / Behavior (optional overrides)
- `AUDIO_ENHANCEMENT_METHOD`, `AUDIO_NOISE_REDUCTION`, `AUDIO_NORMALIZE`, `AUDIO_TARGET_LEVEL`, `AUDIO_GAIN_DB`
- `OUTPUT_DIRECTORY`, `SAVE_TRANSCRIPT`, `SAVE_ORIGINAL_AUDIO`
- `DRY_RUN`, `DEBUG`, `VERBOSE`, `HASHTAG_VERIFICATION`, `QA_NORMALIZATION_ENABLED`

#### Config Plumbing
- `SA_UPDATER_CONFIG` - file for the one-time legacy import into an empty settings database (absolute preferred)
- `DATABASE_URL` - SQLite database path / URL

The full override table lives in code at `src/core/config.py`
(`ConfigManager._override_from_env`); direct `os.getenv` readers are
`src/transcription.py` (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`),
`src/llm_manager.py` (provider `ENV_KEY`s plus `${VAR}` placeholder
resolution), `sermon_updater.get_api_headers` (`SERMONAUDIO_API_KEY`),
and `ui/ui_pages/new_sermon_enhanced.py`
(`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_BASE_URL`).

### API-Key Storage Contract

- Keys may live in **environment variables** (preferred) or the **DB
  `config_cache`** (UI-saved settings). They must **never** be literals
  in a file.
- `config/config.example.yaml` holds `${VAR}` placeholders; the loader
  substitutes them and env overrides win over the DB. The Settings UI keeps
  user-typed keys in the DB, and any YAML export replaces them with
  `${VAR}` placeholders. Precedence is environment > DB > built-in default.
- Empty, whitespace-only, unresolved `${VAR}`, or obviously-invalid short
  values (for example a stray few-character string in
  `transcription.whisper_openai.api_key`) are treated as unset and are
  never sent to an endpoint; cloud transcription raises a clear
  "API key missing" error instead.

#### Local LLM (Alternative to API providers)
- `OLLAMA_HOST` - Ollama server URL (default: http://localhost:11434)

#### UI Security (Optional)
- `APP_PASSWORD` - require a password before the UI loads (leave empty for
  local-only use without authentication)
- `HOST_BIND` - bind address for the published port (default: 127.0.0.1;
  use 0.0.0.0 only when `APP_PASSWORD` is set)

### Ollama Setup (Local LLM Alternative)

If you prefer to run models locally:

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve

# Pull recommended models
ollama pull llama3.1:8b      # Primary model
ollama pull gemma2:2b        # Fast validator model

# Configure environment
export OLLAMA_HOST=http://localhost:11434
```

Set the model names with the `OLLAMA_MODEL` environment variable or in the
Settings page under `llm.primary.ollama.model` and `llm.validator.ollama.model`.

### Security Best Practices

#### 1. Credential Management
- **Never** commit `.env` files to version control
- Use different API keys for development/production
- Regularly rotate API keys
- Prefer the environment over stored values; when a key must live in stored
  settings or a file layer, keep it as a `${VAR}` placeholder

#### 2. Development vs Production
```bash
# Development
DEBUG=true
DRY_RUN=true

# Production
DEBUG=false
DRY_RUN=false
```

#### 3. Pre-commit Security Hooks
Install the pre-commit hook to prevent credential commits:

```bash
# Install the security pre-commit hook
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Test the hook
git add .
git commit -m "test commit"  # Will scan for credentials
```

### Configuration Validation

Configuration resolution does **not** run a credential scan at startup. The
active path, `ui/config_utils.resolve_config()`, layers built-in defaults, an
optional file, the DB `config_cache`, and `ENV_CONFIG_MAP` environment
overrides (environment wins), then expands `${VAR}` and `${VAR:-default}`
placeholders. Unresolved or obviously-invalid short values are treated as
unset and never sent to an endpoint.

A standalone scanner ships in `src/secure_config.py`. It reads a YAML file,
flags hardcoded credential shapes, and checks required variables; it is a
manual utility and is not wired into application startup.

Run it manually:

```bash
# Scan a YAML config file for hardcoded credentials
python src/secure_config.py
```

With no `config.yaml` present it validates `config/config.example.yaml`.

### Troubleshooting

#### Common Issues

**"Missing required environment variables"**
```bash
# Check which variables are missing
python src/secure_config.py

# Set missing variables in .env file
echo "SERMONAUDIO_API_KEY=your-key-here" >> .env
```

**"Hardcoded credentials detected"**
```bash
# Replace hardcoded values with environment variables
# Example: api_key: "sk-abc123" -> api_key: "${OPENAI_API_KEY}"
```

**"Configuration file not found"**
```bash
# Nothing to fix: no config file is required. Settings come from the
# environment and the settings database. To validate the example file:
python src/secure_config.py
```

#### Environment Variable Not Loading
1. Check `.env` file exists and has correct format
2. Ensure no quotes around variable names in `.env`:
   ```bash
   # Correct
   OPENAI_API_KEY=sk-abc123
   
   # Incorrect  
   "OPENAI_API_KEY"="sk-abc123"
   ```

3. Verify the variable is referenced correctly in config:
   ```yaml
   # Correct
   api_key: "${OPENAI_API_KEY}"
   
   # Incorrect
   api_key: "$OPENAI_API_KEY"
   ```

## Verification Checklist

After setup, verify:

- [ ] `.env` file exists with your credentials
- [ ] Secrets stay in the environment (or as `${VAR_NAME}` placeholders), never committed
- [ ] Security validation passes: `python src/secure_config.py`
- [ ] Pre-commit hook installed and working
- [ ] LLM provider connectivity verified
- [ ] SermonAudio API connectivity verified: `python sermon_updater.py list --since-days 30`

## Next Steps

Once security is configured:

1. **Test the system**: Run `python sermon_updater.py list --since-days 30` to test API connectivity
2. **Configure audio processing**: Set up audio enhancement models
3. **Set up web interface**: Run `streamlit run streamlit_app.py`
4. **Process sermons**: Begin processing with proper security in place

## Support

For security-related issues:
- Check configuration validation: `python src/secure_config.py`
- Review the project README and `docs/` for setup guidance

For general setup issues, see the main README.md and documentation in the `docs/` directory.
