# Configurable Embedding Providers for RAG System

This document describes the configurable embedding system used by the
analytics RAG chat. Providers are implemented in `ui/embedding_manager.py`
(`EmbeddingManager`) and consumed by `ui/rag_system.py` (`SermonAnalyticsRAG`).

## Overview

Supported providers:

- **sentence_transformers** (alias `local`): local models (`all-MiniLM-L6-v2`, `all-mpnet-base-v2`, ...)
- **openai**: remote API (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`)
- **ollama**: local API server (`nomic-embed-text`, `mxbai-embed-large`, ...)
- **cohere**: remote API (`embed-english-v3.0`, `embed-multilingual-v3.0`, ...)
- **voyageai**: remote API (`voyage-2`, `voyage-large-2`, ...)
- **hash**: deterministic offline pseudo-vectors, no semantic signal

## Where settings live

The `embeddings` block is part of the SQLite settings store. Edit it in the
web UI Settings page, seed it with the `EMBEDDING_PROVIDER` and
`EMBEDDING_MODEL` environment variables (they override the stored primary
provider and model), or keep it in a file layer via `SA_UPDATER_CONFIG`.
There is no required config file.

## Configuration

### Basic

```yaml
embeddings:
  primary:
    provider: "sentence_transformers"
    model: "all-MiniLM-L6-v2"
  fallback:
    - provider: "ollama"
      host: "http://localhost:11434"
      model: "nomic-embed-text"
```

### Advanced

```yaml
embeddings:
  primary:
    provider: "openai"     # or sentence_transformers / local, ollama, cohere, voyageai
    model: "text-embedding-3-small"

    # Provider-specific blocks (nested values win over the outer keys)
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "text-embedding-3-small"
      base_url: "https://api.openai.com/v1"   # optional, for compatible endpoints
    sentence_transformers:
      model: "all-MiniLM-L6-v2"
    ollama:
      host: "http://localhost:11434"
      model: "nomic-embed-text"
      auto_download: false                    # ollama only: pull the model on first use
    cohere:
      api_key: "your-cohere-key"
      model: "embed-english-v3.0"
    voyageai:
      api_key: "your-voyageai-key"
      model: "voyage-2"

  # Fallback providers, tried in order
  fallback:
    - provider: "sentence_transformers"
      model: "all-MiniLM-L6-v2"
    - provider: "hash"
      dimensions: 384
```

`dimensions` (default 384) is read from the provider block; providers with a
known model table derive it from the model name, and sentence transformers
read it from the loaded model.

## Model reference

### Sentence Transformers (local)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `all-MiniLM-L6-v2` | 384 | Fast, good quality (default) |
| `all-mpnet-base-v2` | 768 | Higher quality, slower |
| `all-distilroberta-v1` | 768 | Balance of speed and quality |
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | Multilingual |

### OpenAI (remote)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `text-embedding-3-small` | 1536 | Fast, cost-effective (default) |
| `text-embedding-3-large` | 3072 | Highest quality |
| `text-embedding-ada-002` | 1536 | Legacy |

### Ollama (local API)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `nomic-embed-text` | 768 | General purpose (default) |
| `mxbai-embed-large` | 1024 | High quality |
| `snowflake-arctic-embed:s` | 384 | Small, fast |
| `snowflake-arctic-embed:m` | 768 | Medium |
| `snowflake-arctic-embed:l` | 1024 | Large, highest quality |

### Cohere (remote)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `embed-english-v3.0` | 1024 | English (default) |
| `embed-multilingual-v3.0` | 1024 | Multilingual |
| `embed-english-light-v3.0` | 384 | Faster English |
| `embed-multilingual-light-v3.0` | 384 | Faster multilingual |

### VoyageAI (remote)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `voyage-2` | 1024 | General purpose (default) |
| `voyage-large-2` | 1536 | Higher quality |
| `voyage-large-2-instruct` | 1536 | Instruction-tuned |
| `voyage-code-2` | 1536 | Code retrieval |

Requires the optional `cohere` / `voyageai` Python packages; the provider
raises with an install hint when they are missing.

### Hash (offline)

Produces deterministic pseudo-vectors from an md5 hash of the text. The
vectors carry no semantic similarity signal; retrieval degrades to
keyword-level overlap. Select it deliberately with `provider: hash` for
fully offline installs. `EmbeddingManager` also appends a hash fallback
automatically as the last resort, sized to the primary provider's dimensions
(384 when there is no primary).

## Fallback behavior

1. The primary provider handles every request while it succeeds.
2. On failure, the configured `fallback` providers are tried in order.
3. A hash provider is appended automatically as the final option.

The manager remembers which provider answered and keeps using it until it
fails again.

## Usage from Python

```python
from ui.rag_system import SermonAnalyticsRAG

embedding_config = {
    'primary': {
        'provider': 'openai',
        'openai': {'api_key': 'your-api-key', 'model': 'text-embedding-3-small'}
    },
    'fallback': [
        {'provider': 'hash', 'dimensions': 1536}
    ]
}

rag = SermonAnalyticsRAG(embedding_config=embedding_config)

provider_info = rag.get_embedding_provider_info()
print(provider_info['current_provider'])

rag.add_analytics_data(sermon_data)
result = rag.query_analytics("What are the most popular sermons?")
```

The same configuration can be changed at runtime:

```python
success = rag.switch_embedding_provider({
    'primary': {
        'provider': 'ollama',
        'host': 'http://localhost:11434',
        'model': 'nomic-embed-text'
    }
})
```

Switching to a provider with different dimensions makes the stored vectors
incompatible; `query_analytics()` detects the mismatch and the Analytics chat
clears and re-indexes the collection automatically.

## Troubleshooting

**Sentence transformer download fails.** Check connectivity to
huggingface.co, configure a proxy if needed, or run offline with the hash
provider. Pre-download models with:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

**"OpenAI API key is required".** The provider block has no `api_key` and no
`OPENAI_API_KEY` environment variable is set. Set one of the two and re-open
the Analytics page.

**"Failed to connect to Ollama".** Ensure Ollama is running and the host is
reachable, then pull the model: `ollama pull nomic-embed-text`.

**Dimension mismatch after switching models.** Expected: the stored vectors
no longer match. The chat interface resets the collection and re-indexes on
the next query, or clear it manually with `rag.clear_collection()`.

## API reference

### EmbeddingManager

```python
class EmbeddingManager:
    def __init__(self, config: dict[str, Any])
    def get_embeddings(self, texts: list[str]) -> list[list[float]]
    def get_embedding_dimension(self) -> int
    def get_current_provider_info(self) -> dict[str, Any]
```

### SermonAnalyticsRAG

```python
class SermonAnalyticsRAG:
    def __init__(self, db_path: str = "analytics_vector_db",
                 embedding_config: dict[str, Any] | None = None,
                 llm_config: dict[str, Any] | None = None)
    def get_embedding_provider_info(self) -> dict[str, Any]
    def switch_embedding_provider(self, new_config: dict[str, Any]) -> bool
```

## Best practices

1. Start with sentence transformers for offline, private operation.
2. Configure at least one real fallback before the automatic hash fallback.
3. Keep embedding dimensions consistent; rebuild the vector store after a
   dimension change.
4. Check `get_embedding_provider_info()` if retrieval quality drops; it shows
   which provider is actually serving requests.
