# RAG (Retrieval-Augmented Generation) System

## Overview

The SermonAudio Processor implements a sophisticated RAG system that enables natural language queries over sermon analytics data. The system combines ChromaDB for vector storage, sentence transformers for embeddings, and LLM integration for generating responses.

## Architecture

### Components

1. **Vector Database**: ChromaDB for storing sermon analytics embeddings
2. **Embedding Model**: sentence-transformers/all-MiniLM-L6-v2 for text embeddings
3. **LLM Integration**: Uses existing LLMManager for response generation
4. **Query Processor**: Converts natural language to vector queries
5. **Response Generator**: Combines retrieved data with LLM responses

### Data Flow

```
User Query → Embedding → Vector Search → Context Retrieval → LLM Response → User
```

## Implementation Details

### Vector Database Setup

The RAG system uses ChromaDB as a persistent vector database:

```python
from chromadb.config import Settings
import chromadb

client = chromadb.PersistentClient(
    path="analytics_vector_db",
    settings=Settings(anonymized_telemetry=False)
)

collection = client.get_or_create_collection(
    name="sermon_analytics",
    metadata={"description": "SermonAudio analytics data for RAG queries"}
)
```

### Embedding Pipeline

Documents are converted to embeddings using sentence-transformers:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(documents)
```

### Document Processing

Analytics data is converted to searchable text documents:

```python
def create_document_text(sermon_data):
    """Convert sermon analytics to searchable text"""
    return f"""
    Sermon: {sermon_data['title']}
    Speaker: {sermon_data['speaker']}
    Views: {sermon_data['views']}
    Engagement: {sermon_data['engagement_score']}
    Date: {sermon_data['date_preached']}
    """
```

### Query Processing

Natural language queries are processed and matched against stored embeddings:

```python
def query_sermons(query_text, n_results=5):
    """Find relevant sermons for a query"""
    query_embedding = embedding_model.encode([query_text])
    
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        include=['documents', 'metadatas', 'distances']
    )
    
    return results
```

## Configuration

### Basic Configuration

```yaml
rag_system:
  enabled: true
  embedding_model: "all-MiniLM-L6-v2"
  vector_db_path: "analytics_vector_db"
  similarity_threshold: 0.7
  max_results: 10
```

### Advanced Configuration

```yaml
rag_system:
  enabled: true
  
  # Embedding settings
  embedding_model: "all-MiniLM-L6-v2"
  embedding_batch_size: 32
  normalize_embeddings: true
  
  # Vector database settings
  vector_db_path: "analytics_vector_db"
  collection_name: "sermon_analytics"
  persistence_directory: "./chroma_db"
  
  # Query settings
  similarity_threshold: 0.7
  max_results: 10
  min_similarity_score: 0.5
  
  # Response generation
  context_window_size: 4000
  response_max_tokens: 500
  temperature: 0.7
```

## Usage Examples

### Basic Setup

```python
from ui.rag_system import SermonAnalyticsRAG

# Initialize RAG system
rag = SermonAnalyticsRAG()

# Add sermon data
sermon_data = {
    "sermon_id": "123456",
    "title": "The Power of Prayer",
    "speaker": "John Doe",
    "views": 1250,
    "engagement_score": 8.5
}

rag.add_sermon_data([sermon_data])

# Query the system
results = rag.query("sermons about prayer with high engagement")
```

### Advanced Queries

```python
# Statistical queries
results = rag.query("What's the average engagement score for John Doe's sermons?")

# Trend analysis
results = rag.query("How has sermon engagement changed over the last 6 months?")

# Comparative analysis
results = rag.query("Compare engagement between Sunday morning and evening services")

# Content discovery
results = rag.query("Find sermons about forgiveness with more than 1000 views")
```

## Data Models

### Sermon Analytics Document

```python
{
    "sermon_id": str,           # Unique identifier
    "title": str,               # Sermon title
    "speaker": str,             # Speaker name
    "series": str,              # Sermon series
    "date_preached": str,       # Preaching date
    "event_type": str,          # Service type
    "bible_text": str,          # Scripture reference
    "views": int,               # View count
    "listens": int,             # Listen count
    "downloads": int,           # Download count
    "avg_watch_percentage": float,  # Completion rate
    "engagement_score": float,  # Calculated engagement
    "keywords": List[str],      # Content keywords
    "metadata": dict           # Additional metadata
}
```

### Query Result Format

```python
{
    "query": str,              # Original query
    "results": [
        {
            "document": str,    # Document text
            "metadata": dict,   # Sermon metadata
            "similarity": float # Similarity score
        }
    ],
    "response": str,           # Generated response
    "context_used": str        # Context provided to LLM
}
```

## Performance Optimization

### Embedding Caching

```python
# Cache embeddings to avoid recomputation
EMBEDDING_CACHE = {}

def get_cached_embedding(text):
    if text not in EMBEDDING_CACHE:
        EMBEDDING_CACHE[text] = model.encode([text])
    return EMBEDDING_CACHE[text]
```

### Batch Processing

```python
# Process multiple documents efficiently
def add_batch_data(sermon_batch):
    texts = [create_document_text(s) for s in sermon_batch]
    embeddings = model.encode(texts, batch_size=32)
    
    collection.add(
        documents=texts,
        embeddings=embeddings,
        metadatas=[s['metadata'] for s in sermon_batch],
        ids=[s['sermon_id'] for s in sermon_batch]
    )
```

### Query Optimization

```python
# Use appropriate similarity thresholds
def optimized_query(query_text, threshold=0.7):
    results = collection.query(
        query_embeddings=model.encode([query_text]),
        n_results=20,  # Get more candidates
        include=['documents', 'metadatas', 'distances']
    )
    
    # Filter by similarity threshold
    filtered_results = [
        r for r in results if r['distance'] >= threshold
    ]
    
    return filtered_results[:10]  # Return top 10
```

## Troubleshooting

### Common Issues

**Model Download Failures:**
```bash
# Pre-download models
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

**ChromaDB Persistence Issues:**
```python
# Check database permissions
import os
db_path = "analytics_vector_db"
if not os.path.exists(db_path):
    os.makedirs(db_path, exist_ok=True)
```

**Memory Issues with Large Datasets:**
```python
# Process in smaller batches
BATCH_SIZE = 100
for i in range(0, len(sermon_data), BATCH_SIZE):
    batch = sermon_data[i:i+BATCH_SIZE]
    rag.add_sermon_data(batch)
```

### Performance Monitoring

```python
import time
import logging

def monitor_query_performance(query):
    start_time = time.time()
    results = rag.query(query)
    end_time = time.time()
    
    logging.info(f"Query '{query}' took {end_time - start_time:.2f}s")
    logging.info(f"Returned {len(results)} results")
    
    return results
```

## API Reference

### SermonAnalyticsRAG Class

```python
class SermonAnalyticsRAG:
    def __init__(self, db_path: str = "analytics_vector_db"):
        """Initialize RAG system"""
        
    def add_sermon_data(self, sermon_list: List[dict]):
        """Add sermon analytics data to vector database"""
        
    def query(self, query_text: str, n_results: int = 5) -> dict:
        """Query sermon data using natural language"""
        
    def clear_database(self):
        """Clear all data from vector database"""
        
    def get_collection_info(self) -> dict:
        """Get information about stored data"""
```

### Helper Functions

```python
def initialize_rag_system_with_data(sermon_data: List[dict]) -> SermonAnalyticsRAG:
    """Initialize RAG system and populate with data"""
    
def create_document_text(sermon: dict) -> str:
    """Convert sermon data to searchable text"""
    
def extract_query_intent(query: str) -> dict:
    """Analyze query to determine intent and parameters"""
```

## Security Considerations

### Data Privacy
- Sermon data is stored locally in ChromaDB
- No external services receive sensitive data
- Embeddings are anonymized representations

### API Security
- LLM providers receive only aggregated, anonymized data
- No personal information is included in queries
- Rate limiting prevents abuse

### Access Control
- Database files are protected by file system permissions
- Web interface requires authentication (if configured)
- Audit logging for all queries

## Deployment

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . .

# Initialize RAG system
RUN python -c "from ui.rag_system import SermonAnalyticsRAG; rag = SermonAnalyticsRAG()"

EXPOSE 8501

CMD ["streamlit", "run", "streamlit_app.py"]
```

### Production Configuration

```yaml
rag_system:
  enabled: true
  
  # Production settings
  vector_db_path: "/data/analytics_vector_db"
  embedding_model: "all-MiniLM-L6-v2"
  
  # Performance settings
  embedding_batch_size: 64
  max_concurrent_queries: 10
  query_timeout_seconds: 30
  
  # Monitoring
  enable_metrics: true
  log_level: "INFO"
  metrics_export_path: "/data/metrics"
```

## Future Enhancements

- **Multi-modal embeddings**: Support for audio and video content
- **Custom models**: Fine-tuned embeddings for sermon content
- **Distributed deployment**: Scale across multiple servers
- **Real-time updates**: Stream new sermon data automatically
- **Advanced analytics**: Trend prediction and anomaly detection