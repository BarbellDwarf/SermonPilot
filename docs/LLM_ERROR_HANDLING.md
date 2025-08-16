# LLM Error Handling Enhancement

## Overview

Enhanced the `llm_manager.py` to provide robust error handling for LLM model selection and endpoint connectivity issues. The system now distinguishes between "invalid model" errors and general endpoint/connectivity problems, providing appropriate user feedback and fallback behavior.

## Key Features

### 1. Model Validation with Listing

- **Invalid Model Detection**: Automatically detects when a specified model doesn't exist
- **Available Models Listing**: Lists all available models when an invalid model is detected
- **Graceful Exit**: Exits with error code 1 when invalid model is found, preventing unnecessary processing

### 2. Fallback vs. Exit Logic

- **Invalid Model**: Lists available models and exits (no fallback attempt)
- **Endpoint Down**: Attempts fallback to secondary provider
- **Connection Issues**: Tries fallback before failing completely

### 3. Enhanced Provider Support

#### OllamaProvider
- `list_models()`: Retrieves available models via Ollama API (`/api/tags`)
- Detects model errors in both Ollama library and HTTP responses
- Handles 404 errors specifically for model validation

#### OpenAIProvider
- `list_models()`: Retrieves available models via OpenAI API (`/v1/models`)
- Catches `openai.NotFoundError` for model-specific errors
- Handles connection timeouts and API errors separately

## Error Handling Flow

```
┌─────────────────┐
│ LLM Request     │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    Model Error     ┌─────────────────┐
│ Primary Provider│ ──────────────────▶│ List Models &   │
│ (e.g., Ollama)  │                    │ Exit(1)         │
└─────────┬───────┘                    └─────────────────┘
          │
          │ Endpoint Error
          ▼
┌─────────────────┐    Model Error     ┌─────────────────┐
│ Fallback Provider│ ──────────────────▶│ List Models &   │
│ (e.g., OpenAI)  │                    │ Exit(1)         │
└─────────┬───────┘                    └─────────────────┘
          │
          │ Endpoint Error
          ▼
┌─────────────────┐
│ Final Exception │
│ "All providers  │
│ failed"         │
└─────────────────┘
```

## Configuration Examples

### With Invalid Model (will exit with model list)
```yaml
llm:
  primary:
    provider: ollama
    ollama:
      host: "http://localhost:11434"
      model: "nonexistent-model"  # ← Will trigger model listing & exit
  fallback:
    enabled: true
    provider: openai
    openai:
      api_key: "your-key"
      model: "gpt-3.5-turbo"
```

### With Invalid Endpoint (will use fallback)
```yaml
llm:
  primary:
    provider: ollama
    ollama:
      host: "http://localhost:99999"  # ← Invalid port, will fallback
      model: "llama3.1:8b"
  fallback:
    enabled: true
    provider: ollama
    ollama:
      host: "http://localhost:11434"  # ← Valid endpoint
      model: "llama3.1:8b"
```

## User Experience Examples

### Invalid Model Error
```
Error: Model 'nonexistent-model-12345' not found in Ollama.
Available models: llama3.1:8b, gemma3:latest, mistral:latest, qwen3:8b

Command exited with code 1
```

### Endpoint Down (with successful fallback)
```
Primary provider failed: Connection refused to localhost:99999
Fallback provider succeeded: OpenAIProvider
Response: [LLM response content]
```

### Both Providers Failed
```
Primary provider failed: Model 'invalid-model' not found
Fallback provider failed: Connection timeout
Error: All LLM providers failed. Please check your configuration and network connectivity.
```

## Implementation Details

### Model Detection Logic

**Ollama**: 
- Checks for "model" + ("not found" OR "does not exist") in error messages
- Uses `/api/tags` endpoint to list available models
- Handles both Ollama library exceptions and HTTP 404 responses

**OpenAI**:
- Catches `openai.NotFoundError` specifically for model errors
- Uses `/v1/models` endpoint to list available models
- Distinguishes between model errors and connection/timeout errors

### Error Recovery Strategy

1. **Primary Provider Fails**:
   - If model error: List models and exit (no recovery possible)
   - If endpoint error: Try fallback provider

2. **Fallback Provider Fails**:
   - If model error: List models and exit 
   - If endpoint error: Raise final exception

3. **Both Providers Fail**: Raise comprehensive error message

## Benefits

- **Faster Debugging**: Immediately shows available models when wrong model is specified
- **Robust Operation**: Continues working when primary endpoint is down
- **Clear Error Messages**: Distinguishes between configuration errors and connectivity issues
- **Zero Downtime**: Fallback ensures processing continues when possible
- **Developer Friendly**: Prevents wasted processing time on invalid configurations

## Testing

The error handling has been tested with:
- ✅ Invalid model names (both Ollama and OpenAI)
- ✅ Invalid endpoints (wrong ports/hosts)
- ✅ Successful fallback scenarios
- ✅ Model listing functionality
- ✅ Integration with existing sermon processing pipeline

## Backward Compatibility

All existing configurations continue to work without changes. The enhanced error handling is transparent to users with valid configurations, only activating when errors occur.
