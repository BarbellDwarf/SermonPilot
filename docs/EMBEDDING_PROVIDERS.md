# Configurable Embedding Providers for RAG System

This document describes the new configurable embedding system that supports multiple embedding providers with automatic fallback capabilities.

## Overview

The RAG system now supports multiple embedding providers:

- **Sentence Transformers**: Local models (all-MiniLM-L6-v2, all-mpnet-base-v2, etc.)
- **OpenAI Embeddings**: Remote API-based embeddings (text-embedding-3-small, text-embedding-3-large, etc.)
- **Ollama Embeddings**: Local API server embeddings (nomic-embed-text, mxbai-embed-large, etc.)
- **Hash-based Fallback**: Deterministic offline embeddings for complete offline operation

## Configuration

### Basic Configuration

Add the following to your `config.yaml`:

```yaml
embeddings:
  primary:
    provider: "sentence_transformers"
    model: "all-MiniLM-L6-v2"
  fallback:
    - provider: "hash"
      dimensions: 384
```

### Advanced Configuration

```yaml
embeddings:
  # Primary embedding provider
  primary:
    provider: "openai"  # or "sentence_transformers", "ollama"
    
    # OpenAI configuration
    openai:
      api_key: "your-openai-key"
      model: "text-embedding-3-small"
      base_url: "https://api.openai.com/v1"  # Optional: for other providers
    
    # Sentence Transformers configuration
    sentence_transformers:
      model: "all-MiniLM-L6-v2"  # Local model name
    
    # Ollama configuration
    ollama:
      host: "http://localhost:11434"
      model: "nomic-embed-text"
  
  # Fallback providers (tried in order)
  fallback:
    - provider: "sentence_transformers"
      model: "all-MiniLM-L6-v2"
    - provider: "hash"
      dimensions: 384  # Final fallback for offline mode
```

## Supported Models

### Sentence Transformers (Local)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `all-MiniLM-L6-v2` | 384 | Fast, good quality (default) |
| `all-mpnet-base-v2` | 768 | Higher quality, slower |
| `all-distilroberta-v1` | 768 | Good balance of speed/quality |
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | Multilingual support |

### OpenAI Embeddings (Remote)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `text-embedding-3-small` | 1536 | Fast, cost-effective |
| `text-embedding-3-large` | 3072 | Highest quality |
| `text-embedding-ada-002` | 1536 | Legacy model |

### Ollama Embeddings (Local API)

| Model | Dimensions | Description |
|-------|------------|-------------|
| `nomic-embed-text` | 768 | General purpose embedding |
| `mxbai-embed-large` | 1024 | High-quality embedding |
| `snowflake-arctic-embed:s` | 384 | Small, fast model |
| `snowflake-arctic-embed:m` | 768 | Medium model |
| `snowflake-arctic-embed:l` | 1024 | Large, high-quality model |

## Usage Examples

### Programming Interface

```python
from ui.rag_system import SermonAnalyticsRAG

# Configuration for OpenAI embeddings
embedding_config = {
    'primary': {
        'provider': 'openai',
        'api_key': 'your-api-key',
        'model': 'text-embedding-3-small'
    },
    'fallback': [
        {
            'provider': 'hash',
            'dimensions': 1536
        }
    ]
}

# Initialize RAG system
rag = SermonAnalyticsRAG(embedding_config=embedding_config)

# Check current provider
provider_info = rag.get_embedding_provider_info()
print(f"Using: {provider_info['current_provider']['provider']}")

# Add data and query
rag.add_analytics_data(sermon_data)
result = rag.query_analytics("What are the most popular sermons?")
```

### Web Interface

The new embedding system is automatically integrated into the Streamlit web interface:

1. Navigate to **Analytics** → **SermonAudio Analytics**
2. Initialize the chat system
3. View embedding provider information in the sidebar
4. The system automatically uses your configured embedding provider

## Fallback Mechanism

The system implements a robust fallback chain:

1. **Primary Provider**: Configured primary embedding provider
2. **Fallback Providers**: Configured fallback providers (in order)
3. **Hash Fallback**: Automatically added as final fallback for offline mode

If the primary provider fails, the system automatically tries fallback providers until one succeeds.

## Provider Switching

You can switch embedding providers at runtime:

```python
# Switch to a different provider
new_config = {
    'primary': {
        'provider': 'ollama',
        'host': 'http://localhost:11434',
        'model': 'nomic-embed-text'
    }
}

success = rag.switch_embedding_provider(new_config)
if success:
    print("Successfully switched to Ollama embeddings")
```

**Note**: Switching providers with different dimensions may make existing embeddings incompatible.

## Performance Characteristics

### Sentence Transformers
- ✅ **Offline**: Works completely offline after initial download
- ✅ **Privacy**: Data never leaves your machine
- ⚠️ **Speed**: Moderate (depends on model size)
- ⚠️ **Setup**: Requires model download (100MB+)

### OpenAI Embeddings
- ✅ **Quality**: High-quality embeddings
- ✅ **Speed**: Fast API responses
- ❌ **Offline**: Requires internet connection
- ❌ **Privacy**: Data sent to OpenAI
- ❌ **Cost**: API usage costs

### Ollama Embeddings
- ✅ **Offline**: Works offline after model download
- ✅ **Privacy**: Data stays local
- ✅ **Quality**: Good quality embeddings
- ⚠️ **Setup**: Requires Ollama server setup

### Hash Fallback
- ✅ **Offline**: Always works
- ✅ **Fast**: Instant generation
- ✅ **Deterministic**: Same input = same output
- ❌ **Quality**: Lower semantic quality

## Migration Guide

### From Legacy RAG System

Old RAG system (hardcoded sentence-transformers):
```python
rag = SermonAnalyticsRAG()
```

New configurable system:
```python
embedding_config = {
    'primary': {
        'provider': 'sentence_transformers',
        'model': 'all-MiniLM-L6-v2'
    }
}
rag = SermonAnalyticsRAG(embedding_config=embedding_config)
```

### Existing Vector Database

The new system is compatible with existing vector databases as long as you use the same embedding dimensions. If switching to a provider with different dimensions, clear and rebuild the vector database:

```python
rag.clear_collection()  # Clear existing data
rag.add_analytics_data(analytics_data)  # Re-add with new embeddings
```

## Troubleshooting

### Model Download Issues

**Problem**: Sentence transformer models fail to download
```
Failed to connect to 'https://huggingface.co'
```

**Solution**: 
1. Check internet connection
2. Configure proxy if needed
3. Use hash fallback for offline mode

### OpenAI API Issues

**Problem**: OpenAI embeddings fail
```
OpenAI API key is required
```

**Solution**:
1. Check API key configuration
2. Verify API key permissions
3. Check rate limits
4. Ensure fallback provider is configured

### Ollama Connection Issues

**Problem**: Ollama embeddings fail
```
Failed to connect to Ollama
```

**Solution**:
1. Ensure Ollama is installed and running
2. Check host configuration
3. Verify model is downloaded: `ollama pull nomic-embed-text`

### Dimension Mismatch

**Problem**: Existing embeddings incompatible with new provider
```
Dimension mismatch: old=384, new=1536
```

**Solution**:
1. Use same dimension provider
2. Or clear and rebuild vector database
3. Consider using `dimensions` parameter to match

## API Reference

### EmbeddingManager

```python
class EmbeddingManager:
    def __init__(self, config: Dict[str, Any])
    def get_embeddings(self, texts: List[str]) -> List[List[float]]
    def get_embedding_dimension(self) -> int
    def get_current_provider_info(self) -> Dict[str, Any]
```

### SermonAnalyticsRAG

```python
class SermonAnalyticsRAG:
    def __init__(self, db_path: str = "analytics_vector_db", 
                 embedding_config: Optional[Dict[str, Any]] = None)
    def get_embedding_provider_info(self) -> Dict[str, Any]
    def switch_embedding_provider(self, new_config: Dict[str, Any]) -> bool
```

## Best Practices

1. **Start Simple**: Begin with sentence-transformers for offline operation
2. **Configure Fallbacks**: Always configure hash fallback for reliability
3. **Match Dimensions**: Keep consistent embedding dimensions for compatibility
4. **Monitor Performance**: Check provider info to ensure optimal provider is used
5. **Test Offline**: Verify system works without internet connectivity
6. **Consider Costs**: Be aware of API costs when using remote providers

## Integration with Existing Codebase

The new embedding system is designed to be backward compatible:

- **No Breaking Changes**: Existing code continues to work
- **Default Behavior**: Falls back to hash embeddings if no config provided
- **Graceful Degradation**: Automatically handles provider failures
- **Configuration Driven**: All behavior controlled via config.yaml

The embedding system enhances the RAG capabilities while maintaining the existing robust, offline-first design philosophy of the sermon processor.