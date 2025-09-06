# SermonAudio Analytics Features

## Overview

The SermonAudio Processor includes comprehensive analytics capabilities that provide insights into sermon processing performance, content analysis, and SermonAudio engagement metrics. The analytics system includes both traditional dashboard views and an AI-powered chat interface for natural language queries.

## Features

### 📊 Processing Metrics
- **Success Rates**: Track processing success/failure rates over time
- **Processing Volume**: Monitor daily/weekly/monthly processing volumes
- **Performance Trends**: Analyze processing time improvements and bottlenecks
- **Error Analysis**: Detailed breakdown of error types and patterns

### 📝 Content Analysis
- **Speaker Activity**: Track sermon processing by speaker
- **Event Type Distribution**: Analyze different sermon event types
- **Quality Scores**: Monitor content quality metrics over time
- **Topic Trends**: Identify trending topics and themes

### 💰 Cost Tracking
- **LLM API Usage**: Monitor OpenAI, Anthropic, and other LLM costs
- **Processing Costs**: Calculate cost per sermon and cost trends
- **Budget Monitoring**: Track spending against budgets
- **Cost Optimization**: Identify opportunities to reduce costs

### ⚡ Performance Monitoring
- **System Resources**: Real-time CPU, memory, disk, and network usage
- **GPU Metrics**: NVIDIA GPU utilization and memory usage
- **Processing Times**: Detailed timing analysis for each processing stage
- **Optimization Recommendations**: Dynamic suggestions for performance improvements

### 🎙️ SermonAudio Analytics (AI-Powered)
- **Natural Language Queries**: Ask questions about your sermon data
- **Engagement Metrics**: Views, listens, downloads, and watch time
- **Trend Analysis**: Identify popular sermons and engagement patterns
- **RAG-Powered Insights**: AI-generated insights from your sermon data

## Getting Started

### Configuration

Enable analytics in your `config.yaml`:

```yaml
analytics:
  enabled: true
  data_retention_days: 90  # How long to keep analytics data
  
sermonaudio_analytics:
  enabled: true
  api_key: "your-sermonaudio-api-key"
  broadcaster_id: "your-broadcaster-id"
```

### Accessing Analytics

1. Open the Streamlit web interface
2. Navigate to the "📈 Analytics" tab
3. Choose from the following sub-tabs:
   - **📊 Processing Metrics**: General processing statistics
   - **📝 Content Analysis**: Content and speaker insights
   - **💰 Cost Tracking**: Financial analysis
   - **⚡ Performance**: System performance monitoring
   - **🎙️ SermonAudio Analytics**: AI-powered analytics chat

## Using the Analytics Chat Interface

The SermonAudio Analytics tab provides a ChatGPT-like interface for querying your sermon data:

### Example Queries

**Engagement Analysis:**
- "What sermons had the highest engagement last month?"
- "Show me average watch time by speaker"
- "Which series performed best in terms of views?"

**Performance Analysis:**
- "How has sermon engagement changed over time?"
- "What are the most popular topics this year?"
- "Compare engagement between different event types"

**Content Discovery:**
- "Find sermons about prayer with high engagement"
- "Show me trending topics in the last quarter"
- "Which speakers have the most consistent engagement?"

### Query Types Supported

1. **Statistical Queries**: Numbers, averages, totals
2. **Trend Analysis**: Changes over time
3. **Comparisons**: Between speakers, series, or time periods
4. **Rankings**: Top/bottom performers
5. **Filtering**: By date, speaker, topic, engagement level

## Performance Monitoring

### System Metrics

The performance monitor tracks:

- **CPU Usage**: Real-time processor utilization
- **Memory Usage**: RAM consumption and availability
- **Disk Usage**: Storage utilization and I/O rates
- **Network Activity**: Upload/download rates
- **GPU Metrics**: CUDA GPU utilization (if available)

### Processing Performance

- **Audio Enhancement Times**: Time spent on AI audio processing
- **LLM Response Times**: API response times for different providers
- **Transcription Performance**: Speed of audio-to-text conversion
- **Upload/Download Speeds**: SermonAudio API performance

### Optimization Recommendations

The system provides dynamic recommendations based on current metrics:

- **Memory Optimization**: Suggestions when memory usage is high
- **CPU Optimization**: Recommendations for CPU-intensive tasks
- **GPU Utilization**: Advice for better GPU usage
- **Network Optimization**: Tips for improving API performance

## Data Sources

### Internal Data
- Processing logs and metrics from `sermon_updater.py`
- System performance data from `performance_monitor.py`
- Configuration and settings data
- Error logs and success rates

### SermonAudio API Data
- Sermon view counts and engagement metrics
- Download statistics
- Listener engagement patterns
- Sermon metadata and categorization

### LLM Provider Data
- API usage statistics
- Cost information
- Response times and success rates
- Token usage patterns

## Troubleshooting

### Common Issues

**Analytics Data Not Loading:**
1. Check that analytics is enabled in `config.yaml`
2. Verify database permissions and disk space
3. Review logs for processing errors

**SermonAudio Analytics Not Working:**
1. Verify SermonAudio API credentials
2. Check internet connectivity
3. Ensure sufficient API rate limits

**Performance Metrics Missing:**
1. Install required system monitoring packages
2. Check permissions for system resource access
3. Verify GPU drivers (for GPU metrics)

**Chat Interface Errors:**
1. Check LLM provider configuration
2. Verify internet access for embedding models
3. Review RAG system initialization logs

### Log Locations

- Analytics logs: `logs/analytics.log`
- Performance logs: `logs/performance.log`
- RAG system logs: `logs/rag_system.log`
- Chat interface logs: `logs/chat_interface.log`

## API Reference

### Analytics Data Models

```python
# Processing Metrics
{
    "date": "2024-01-15",
    "sermons_processed": 25,
    "success_rate": 0.96,
    "avg_processing_time": 180.5,
    "errors": ["timeout", "api_error"]
}

# SermonAudio Analytics
{
    "sermon_id": "123456",
    "title": "The Power of Prayer",
    "speaker": "John Doe",
    "views": 1250,
    "listens": 800,
    "downloads": 150,
    "avg_watch_percentage": 0.75,
    "engagement_score": 8.5
}
```

### Configuration Options

```yaml
analytics:
  enabled: true
  data_retention_days: 90
  performance_monitoring: true
  cost_tracking: true
  
sermonaudio_analytics:
  enabled: true
  api_key: "your-api-key"
  broadcaster_id: "your-id"
  sync_interval_hours: 24
  
rag_system:
  embedding_model: "all-MiniLM-L6-v2"
  vector_db_path: "analytics_vector_db"
  similarity_threshold: 0.7
```

## Future Enhancements

- **Predictive Analytics**: Forecast sermon engagement
- **A/B Testing**: Compare different processing approaches
- **Custom Dashboards**: User-configurable analytics views
- **Export Capabilities**: PDF and CSV report generation
- **Real-time Alerts**: Notifications for unusual patterns
- **Integration APIs**: Connect with external analytics tools