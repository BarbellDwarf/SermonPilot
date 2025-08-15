# LLM Configuration Guide

## Overview

The SermonAudio Updater now supports flexible LLM configuration with both primary and fallback providers. You can easily switch between OpenAI, Ollama, xAI, Anthropic, and other OpenAI-compatible providers by configuring different endpoints, models, and API keys.

## New Configuration Structure

### Current config.yaml
```yaml
# LLM Configuration
llm:
  # Primary LLM settings
  primary:
    provider: "ollama"  # Options: "ollama", "openai"
    ollama:
      host: "http://192.168.75.12:11434"
      model: "llama3.1:8b"
    openai:
      api_key: "your-openai-key"
      model: "gpt-4o"
      # base_url: "https://api.openai.com/v1"  # Optional for custom endpoints
  
  # Fallback LLM settings (used if primary fails)
  fallback:
    enabled: true
    provider: "openai"  # Options: "ollama", "openai"
    ollama:
      host: "http://192.168.75.12:11434"
      model: "llama2"
    openai:
      api_key: "your-openai-key"
      model: "gpt-3.5-turbo"
      # base_url: "https://api.openai.com/v1"  # Optional for custom endpoints
```

## Provider Examples

### OpenAI (Default)
```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "sk-..."
      model: "gpt-4o"
      # base_url is optional for OpenAI
```

### xAI (Grok)
```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "xai-..."
      model: "grok-beta"
      base_url: "https://api.x.ai/v1"
```

### Anthropic (Claude)
```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "sk-ant-..."
      model: "claude-3-5-sonnet-20241022"
      base_url: "https://api.anthropic.com/v1"
```

### Local/Self-hosted OpenAI API
```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "local-key"
      model: "llama-3.1-8b"
      base_url: "http://localhost:8000/v1"
```

### Groq
```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "gsk_..."
      model: "llama-3.1-70b-versatile"
      base_url: "https://api.groq.com/openai/v1"
```

## How to Switch Providers

### To use xAI as primary with OpenAI fallback

```yaml
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "xai-your-api-key"
      model: "grok-beta"
      base_url: "https://api.x.ai/v1"
  fallback:
    enabled: true
    provider: "openai"
    openai:
      api_key: "sk-your-openai-key"
      model: "gpt-4o"
```

### To use only Ollama (no fallback)

```yaml
llm:
  primary:
    provider: "ollama"
    ollama:
      host: "http://your-ollama-server:11434"
      model: "llama3.1:8b"
  fallback:
    enabled: false
```

### To use different Ollama servers for primary and fallback

```yaml
llm:
  primary:
    provider: "ollama"
    ollama:
      host: "http://192.168.1.100:11434"  # Main server
      model: "llama3.1:8b"
  fallback:
    enabled: true
    provider: "ollama"
    ollama:
      host: "http://192.168.1.200:11434"  # Backup server
      model: "llama2"
```

## Features Implemented

✅ **Flexible Provider Configuration**: Switch between OpenAI and Ollama easily

✅ **Custom Endpoints**: Configure different server hosts for any OpenAI-compatible API

✅ **Multi-Provider Support**: OpenAI, xAI, Anthropic, Groq, local APIs, and more

✅ **Model Selection**: Choose different models for each provider

✅ **Automatic Fallback**: If primary provider fails, automatically use fallback

✅ **Legacy Support**: Old configuration format is automatically migrated

✅ **Detailed Logging**: See which provider is being used and why fallbacks occur

✅ **Error Handling**: Clear error messages when both providers fail

✅ **Debug Mode**: Enable verbose debugging output for troubleshooting

## Debug Mode

The SermonAudio Updater includes a debug mode to help with troubleshooting. Set `debug: true` in your `config.yaml` to enable verbose output that shows:

- Detailed sermon processing steps
- File paths and directory operations
- Audio processing parameters
- API response details
- Provider initialization details

**To enable debug mode:**
```yaml
# Processing Options
debug: true    # Set to true to enable verbose debug output
```

**To disable debug mode (default):**
```yaml
# Processing Options
debug: false   # Set to false for normal operation
```

When debug is disabled, the script will only show essential progress messages and errors.

## Testing

Run `python tests/test_llm_manager.py` to test your configuration:

- Verifies both providers are configured correctly
- Tests the fallback mechanism
- Shows which provider will be used
- Tests custom endpoint configuration

## Usage

When you run the sermon updater, you'll see output like:

```
INFO:llm_manager:Primary LLM provider initialized: ollama
INFO:llm_manager:Fallback LLM provider initialized: openai
Generating summary using ollama LLM...
```

If the primary provider fails:

```
WARNING:llm_manager:Primary provider failed: connection error
INFO:llm_manager:Fallback provider succeeded: OpenAIProvider
```

For custom endpoints, you'll see the base URL in the provider info:

```
INFO:llm_manager:Primary LLM provider initialized: openai
Primary provider: OpenAIProvider(model=grok-beta, base_url=https://api.x.ai/v1)
```

## Migration from Old Format

The system automatically migrates old configuration formats:

- `llm_provider: "ollama"` → new structured format
- `ollama_host`, `ollama_model` → `llm.primary.ollama.*`
- `openai_api_key`, `openai_model` → `llm.primary.openai.*`

Your existing config will work without changes!
