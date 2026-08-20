# RAG (Retrieval-Augmented Generation) System

## Overview

The SermonPilot web UI includes a RAG system that answers natural-language
questions about sermon analytics data. It combines ChromaDB for vector
storage, configurable embedding providers, and the existing LLM
configuration for response generation. The implementation lives in
`ui/rag_system.py` (`SermonAnalyticsRAG`) and is used by the Analytics chat
interface (`ui/analytics_chat.py`).

## Architecture

### Components

1. **Vector Database**: ChromaDB (persistent client) for storing sermon
   analytics embeddings
2. **Configurable Embedding Providers** (`ui/embedding_manager.py`):
   - **Sentence Transformers**: local models (`all-MiniLM-L6-v2`, `all-mpnet-base-v2`, ...)
   - **OpenAI**: remote API (`text-embedding-3-small`, `text-embedding-3-large`, ...)
   - **Ollama**: local API server (`nomic-embed-text`, `mxbai-embed-large`, ...)
   - **xAI / Anthropic**: remote API (OpenAI-compatible or deterministic fallback)
   - **Hash-based fallback**: deterministic offline embeddings (the default when
     no configuration is provided)
3. **LLM Integration**: response generation reuses the `llm` block from
   `config.yaml`
4. **Automatic Fallback**: if the primary embedding provider fails, the
   configured fallbacks are tried in order

### Data Flow

```
Question → Embedding → Vector Search (ChromaDB) → Context → LLM Answer
```

## Vector Database Setup

The RAG system uses a ChromaDB persistent client stored at
`analytics_vector_db` (or the path configured under
`rag_system.vector_db_path`):

```python
from ui.rag_system import SermonAnalyticsRAG

rag = SermonAnalyticsRAG()  # db_path="analytics_vector_db" by default
```

The collection is named `sermon_analytics`.

## Configuration

### Embeddings

Embedding providers are configured under `embeddings` in `config.yaml`:

```yaml
embeddings:
  primary:
    provider: "ollama"                # sentence_transformers, openai, ollama, xai, anthropic
    ollama:
      host: "http://localhost:11434"
      model: "mxbai-embed-large:latest"
  fallback:
    - provider: "sentence_transformers"
      model: "all-MiniLM-L6-v2"
    - provider: "openai"
      openai:
        api_key: "${OPENAI_API_KEY}"
        model: "text-embedding-3-small"
```

The only RAG-specific key is `rag_system.vector_db_path`, which overrides the
default `analytics_vector_db` storage location:

```yaml
rag_system:
  vector_db_path: "/data/analytics_vector_db"
```

See [EMBEDDING_PROVIDERS.md](EMBEDDING_PROVIDERS.md) for the full provider
list and fallback behavior.

## Usage

### Adding analytics data

```python
from ui.rag_system import SermonAnalyticsRAG

rag = SermonAnalyticsRAG()

analytics_data = [
    {
        "sermon_id": "123456",
        "title": "The Power of Prayer",
        "speaker": "John Doe",
        "series": "Foundations",
        "event_type": "Sunday - AM",
        "date_preached": "2025-01-15",
        "views": 1250,
        "listens": 800,
        "downloads": 150,
        "duration_minutes": 38,
        "engagement_score": 8.5,
        "watch_time_avg": 0.75,
        "keywords": ["prayer", "faith"],
    }
]

rag.add_analytics_data(analytics_data)
```

### Querying

```python
results = rag.query_analytics("sermons about prayer with high engagement")
print(results["answer"])
for sermon in results["relevant_sermons"]:
    print(sermon["title"], sermon["relevance_score"])
```

### Collection management

```python
stats = rag.get_collection_stats()   # document count, provider, model, dimensions
rag.clear_collection()               # wipe all stored documents
rag.get_embedding_provider_info()    # current provider and available fallbacks
rag.switch_embedding_provider(new_config)  # change provider at runtime
```

### Creating from configuration

```python
from ui.rag_system import create_rag_with_config

rag = create_rag_with_config(config)  # reads embeddings + rag_system.vector_db_path
```

## Data Models

### Analytics document

Each analytics record added to the store carries these fields:

```python
{
    "sermon_id": str,             # Unique identifier
    "title": str,                 # Sermon title
    "speaker": str,               # Speaker name
    "series": str,                # Sermon series
    "event_type": str,            # Service type
    "date_preached": str,         # Preaching date
    "date_uploaded": str,         # Upload date
    "views": int,                 # View count (0 when the API does not provide it)
    "listens": int,               # Listen count
    "downloads": int,             # Download count
    "duration_minutes": int,      # Audio duration
    "engagement_score": float,    # Calculated engagement
    "watch_time_avg": float,      # Average completion rate
    "keywords": list[str],        # Content keywords
}
```

String fields are stored as ChromaDB metadata strings, numeric fields as
floats, and keywords as a comma-joined string.

### Query result format

`query_analytics()` returns:

```python
{
    "question": str,              # Original question
    "answer": str,                # LLM-generated answer
    "relevant_sermons": [         # Retrieved sermons, best match first
        {
            "title": str,
            "speaker": str,
            "views": int,
            "listens": int,
            "relevance_score": float,  # 1 - distance
        }
    ],
    "data_source": str,           # "rag_system", "dimension_mismatch_error", or "error"
    "timestamp": str,             # ISO timestamp (successful queries only)
}
```

When no relevant documents are found, `relevant_sermons` is empty and
`answer` explains that nothing matched. A dimension mismatch (for example,
after switching embedding models) triggers an automatic reset message.

## Troubleshooting

### Model download failures

Pre-download sentence-transformers models so first use is offline:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### Dimension mismatch after changing the embedding model

ChromaDB rejects queries whose embedding dimensions differ from the stored
vectors. `query_analytics()` detects this and returns a reset message; the
Analytics chat interface clears the collection and re-indexes on the next
query.

### ChromaDB persistence issues

The vector store is a local directory. Ensure the process can write to it:

```bash
ls -ld analytics_vector_db
```

Delete the directory to start from scratch; it will be recreated on the next
indexing pass.

## Security Considerations

- Analytics data is stored locally in the ChromaDB directory; nothing is
  sent to external services except the question and retrieved context, which
  go to the configured LLM provider
- API keys are read from environment variables via `config.yaml` substitution
- The web UI can require a password before any page renders (set
  `APP_PASSWORD` in `.env`); see [SECURITY_SETUP_GUIDE.md](SECURITY_SETUP_GUIDE.md)
