# Analytics

## Overview

The Streamlit web UI includes an Analytics page (`ui/ui_pages/analytics.py`)
that reports on sermon processing from the local SQLite database and fetches
engagement data from the SermonAudio API. It also provides an AI-powered chat
interface that answers natural-language questions about your sermon analytics
using a ChromaDB vector store (`ui/rag_system.py`).

## Enabling Analytics

Analytics is controlled from `config.yaml` under `web_ui`:

```yaml
web_ui:
  analytics_enabled: true              # Show the Analytics page
  analytics_refresh_interval: 300      # Cache refresh interval in seconds (default 300)
```

Analytics is enabled by default. The data comes from two places:

- The local `sermons` table (processing dates, speakers, event types, titles)
- The SermonAudio API (downloads, video downloads, comment counts, and
  recent-access timestamps for your broadcaster's sermons)

## The Analytics Page

Open the Streamlit UI and navigate to the "📈 Analytics" page. It has five tabs:

| Tab | Contents |
|-----|----------|
| 📊 Processing Metrics | Sermons processed per time range, success rate, error types, processing time trend |
| 📝 Content Analysis | Speaker and event-type distribution from the local database |
| 💰 Cost Tracking | LLM API call counts, token usage, and estimated cost per month |
| ⚡ Performance | Live CPU, memory, disk, network, and GPU metrics via `ui/performance_monitor.py` |
| 🎙️ SermonAudio Analytics | Two sub-tabs: a data view of API engagement metrics and the AI chat interface |

### SermonAudio Analytics Data View

The data view lists sermons with the metrics the SermonAudio API actually
provides:

- Downloads and video downloads
- Comment count
- Audio/video duration
- Last audio/video access timestamps (used as a "recent activity" signal)

The API does not expose view or listen counts to regular accounts, so the
`views` field is reported as 0. When no API credentials are configured, or
the fetch fails, the client falls back to mock/demo data and the page shows a
warning.

## Using the Chat Interface

The "💬 Chat Interface" sub-tab (`ui/analytics_chat.py`) lets you ask
questions about your sermon analytics in plain language, for example:

- "Which speaker has the most downloads?"
- "What is the average engagement score?"
- "Show me the top sermons by engagement this year"

The chat runs the question through `SermonAnalyticsRAG`
(`ui/rag_system.py`): the question is embedded, matched against the stored
sermon analytics documents in ChromaDB, and the retrieved context is passed
to the configured LLM to produce an answer. Answers include the list of
relevant sermons and a relevance score for each.

### RAG Data Flow

```
Question → Embedding → Vector Search (ChromaDB) → Context → LLM Answer
```

Analytics records are added to the vector store with
`add_analytics_data()`, queried with `query_analytics()`, and inspected with
`get_collection_stats()`. See [RAG_SYSTEM.md](RAG_SYSTEM.md) for details.

## Configuration Options

### LLM for the Chat Interface

The chat interface reuses the main `llm` configuration block in
`config.yaml` (primary and fallback providers).

### Embeddings

Embedding providers are configured under `embeddings`:

```yaml
embeddings:
  primary:
    provider: "sentence_transformers"  # or openai, ollama, xai, anthropic
    model: "all-MiniLM-L6-v2"
```

See [EMBEDDING_PROVIDERS.md](EMBEDDING_PROVIDERS.md) for the full list of
providers and fallback behavior.

## Troubleshooting

**Analytics data not loading:** verify `web_ui.analytics_enabled: true` in
`config.yaml`, then use the "🔄 Refresh Data" button on the Processing
Metrics tab to clear the cached data.

**SermonAudio engagement metrics missing or zero:** the API does not provide
play/view counts for regular accounts, so views are always 0. Downloads,
comment counts, and access timestamps are the real signals available.

**Chat interface errors:** check the LLM provider configuration (the chat
uses the same `llm` block as metadata generation) and confirm the embedding
provider can run locally or reach its API. If the embedding model or
dimensions change, the vector store is reset automatically on the next query.

## Performance Monitoring

The ⚡ Performance tab reads system metrics from `ui/performance_monitor.py`:
CPU usage, memory usage, disk usage, network I/O, and NVIDIA GPU utilization
and memory when a GPU is present.
