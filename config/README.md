# Configuration Directory

This directory contains configuration templates and examples for the SermonAudio Processor.

## Files

### `config.example.yaml`
Main configuration template. Copy this to `config.yaml` in the repository root and update with your settings:

```bash
cp config/config.example.yaml config.yaml
```

Contains:
- SermonAudio API credentials
- LLM provider settings  
- Processing options
- Audio enhancement settings
- Default search criteria

### `llm_examples.yaml`
LLM provider configuration examples for different services:

- xAI Grok configuration
- Anthropic Claude configuration
- OpenAI configuration
- Ollama configuration
- Provider fallback examples

## Usage

1. Copy the main template:
   ```bash
   cp config/config.example.yaml config.yaml
   ```

2. Edit `config.yaml` with your credentials and preferences

3. Reference `llm_examples.yaml` for LLM provider-specific configurations

4. The `config.yaml` file is automatically ignored by git to protect your credentials