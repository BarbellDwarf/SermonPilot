# LLM Configuration Guide

## Overview

SermonPilot generates sermon metadata (title, description, hashtags) and
validates descriptions through an LLM. Providers are configured with a
primary and an optional fallback, plus a separate smaller validator model.

The provider implementations live in `src/llm_manager.py`. Five provider
types are supported:

| Provider | Class | Default model | Default endpoint | API key env var |
|----------|-------|---------------|------------------|-----------------|
| `ollama` | `OllamaProvider` | `llama3` | `http://localhost:11434` | n/a (local) |
| `openai` | `OpenAIProvider` | `gpt-3.5-turbo` | OpenAI default | `OPENAI_API_KEY` |
| `xai` | `XAIProvider` | `grok-beta` | `https://api.x.ai/v1` | `XAI_API_KEY` |
| `groq` | `GroqProvider` | `llama-3.1-70b-versatile` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| `openrouter` | `OpenRouterProvider` | `openai/gpt-4o-mini` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |

`openai`, `xai`, `groq`, and `openrouter` share one OpenAI-compatible client
class, so any of them accepts a custom `base_url`.

Anthropic and Google are not implemented. `ANTHROPIC_API_KEY`,
`GOOGLE_API_KEY`, `ANTHROPIC_MODEL`, and `GOOGLE_MODEL` exist in the
environment variable map and their values are stored with the rest of your
settings, but the provider factory has no class for `provider: "anthropic"`
or `provider: "google"`; selecting one logs a failed initialization and the
manager runs without a primary. Use one of the five supported providers, or
an OpenAI-compatible endpoint.

## Where settings live

Settings are stored in the SQLite settings database and resolved as:
built-in defaults, an optional file layer (`SA_UPDATER_CONFIG`), the stored
settings, then environment variables (env wins for the running process).
There is no required config file. Practical consequences:

- Set `OPENAI_API_KEY` or `LLM_PROVIDER` etc. in `.env` and the first launch
  seeds them into the database; they survive restarts.
- Change providers any time in the web UI Settings page.
- The Settings page's Import/Export tab writes the current settings to YAML
  and restores from an uploaded YAML file. A pre-existing `config.yaml` from
  an older install is imported into the database once, automatically.

## Configuration structure

```yaml
llm:
  primary:
    provider: "ollama"        # ollama, openai, xai, groq, openrouter
    ollama:
      host: "http://localhost:11434"
      model: "llama3"
    openai:
      api_key: "${OPENAI_API_KEY}"   # or set OPENAI_API_KEY in the environment
      model: "gpt-4o"
      # base_url: "https://api.openai.com/v1"  # optional, for compatible endpoints
    xai:
      api_key: "${XAI_API_KEY}"
      model: "grok-beta"
    groq:
      api_key: "${GROQ_API_KEY}"
      model: "llama-3.1-70b-versatile"
    openrouter:
      api_key: "${OPENROUTER_API_KEY}"
      model: "openai/gpt-4o-mini"

  fallback:
    enabled: true
    provider: "openai"        # single fallback provider
    # providers: ["openai", "groq"]  # optional: try several, in order
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-3.5-turbo"

  validator:
    enabled: true             # smaller model for description validation
    provider: "ollama"
    ollama:
      host: "http://localhost:11434"
      model: "gemma2:2b"
```

Only the fields for the provider you actually select are required; the rest
are ignored. `${VAR}` placeholders are expanded from the environment when a
file layer or stored value references them.

## Environment variables

| Variable | Sets |
|----------|------|
| `LLM_PROVIDER` | `llm.primary.provider` |
| `OLLAMA_HOST` | `llm.primary.ollama.host` and `llm.fallback.ollama.host` |
| `OLLAMA_MODEL` | `llm.primary.ollama.model` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | `llm.primary.openai.api_key` / `.model` |
| `XAI_API_KEY` / `XAI_MODEL` | `llm.primary.xai.api_key` / `.model` |
| `GROQ_API_KEY` / `GROQ_MODEL` | `llm.primary.groq.api_key` / `.model` |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | `llm.primary.openrouter.api_key` / `.model` |
| `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | stored, but no provider implementation exists (see above) |

## Provider examples

### Local Ollama (default)

```yaml
llm:
  primary:
    provider: "ollama"
    ollama:
      host: "http://localhost:11434"
      model: "llama3.1:8b"
  fallback:
    enabled: false
```

`OllamaProvider` also reads `temperature` (default 0.7), `max_tokens`
(default 2048), and `num_ctx` (default 8192) from the provider block.

### OpenAI

```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o"
```

Any OpenAI-compatible server works through the same provider:

```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "local-key"
      model: "llama-3.1-8b"
      base_url: "http://localhost:8000/v1"
```

### xAI (Grok)

```yaml
llm:
  primary:
    provider: "xai"
    xai:
      api_key: "${XAI_API_KEY}"
      model: "grok-beta"      # default; base_url defaults to https://api.x.ai/v1
```

### Groq

```yaml
llm:
  primary:
    provider: "groq"
    groq:
      api_key: "${GROQ_API_KEY}"
      model: "llama-3.1-70b-versatile"  # default; base_url defaults to https://api.groq.com/openai/v1
```

### OpenRouter

```yaml
llm:
  primary:
    provider: "openrouter"
    openrouter:
      api_key: "${OPENROUTER_API_KEY}"
      model: "openai/gpt-4o-mini"       # default; base_url defaults to https://openrouter.ai/api/v1
```

## Switching providers

```yaml
llm:
  primary:
    provider: "groq"
    groq:
      api_key: "${GROQ_API_KEY}"
      model: "llama-3.1-70b-versatile"
  fallback:
    enabled: true
    provider: "openai"
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-3.5-turbo"
```

Set `LLM_PROVIDER=groq` (plus the key) in `.env` to the same effect through
the environment; the env override wins over stored settings.

Fallbacks are tried in order when the primary request fails (connection
errors, timeouts, provider errors). When a chat succeeds with a fallback,
the manager logs which provider answered.

## Model suggestions

### Sermon processing (primary)
- **Best value**: `groq` with `llama-3.1-70b-versatile`: fast and cheap
- **Reliable**: `openai` with `gpt-4o`
- **Privacy/local**: `ollama` with `llama3.1:8b`: no data leaves your network

### Fallback providers
- `openai` with `gpt-3.5-turbo`
- `groq` with `llama-3.1-8b-instant`
- `ollama` with a smaller model such as `gemma2:2b`

### Validation (smaller models)
The validator only runs when `llm.validator.enabled` is true:
- Local: `ollama` with `gemma2:2b` or `phi3:mini`
- Fast: `groq` with `llama-3.1-8b-instant`

## Debug mode

Set `debug: true` (Settings page, file layer, or the `DEBUG` environment
variable) for verbose output: processing steps, file paths, audio parameters,
API response details, and provider initialization details.

## Verifying your setup

```bash
python -c "
from ui.config_utils import resolve_config
from src.llm_manager import LLMManager
manager = LLMManager(resolve_config())
print('Primary:', manager.primary_provider)
print('Fallbacks:', manager.fallback_providers)
print('Validator:', manager.validator_provider)
"
```

This resolves the effective settings the same way the app does and shows
which providers initialized. During processing you will see log lines like:

```
INFO:llm_manager:Primary LLM provider initialized: ollama
INFO:llm_manager:Fallback LLM provider initialized: openai
```

If the primary fails:

```
WARNING:llm_manager:Primary provider failed: connection error
INFO:llm_manager:Fallback provider succeeded: OpenAIProvider
```

For custom endpoints, the provider info shows the base URL, e.g.
`OpenAIProvider(model=grok-beta, base_url=https://api.x.ai/v1)`.

## Migrating old configuration

- Flat legacy keys (`llm_provider`, `ollama_host`, `ollama_model`,
  `openai_api_key`, `openai_model`) are converted to the structured `llm`
  block when they appear in a loaded file.
- An existing `config.yaml` from a pre-database install is imported into the
  settings database once, automatically, on first resolution.
