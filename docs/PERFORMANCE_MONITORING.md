# Performance Monitoring System

## Overview

The SermonPilot includes a comprehensive performance monitoring system that provides real-time insights into system resource usage, processing performance, and optimization opportunities. The monitoring system helps identify bottlenecks, optimize resource allocation, and ensure optimal processing performance.

## Features

### System Resource Monitoring

#### CPU Metrics
- **Usage Percentage**: Real-time CPU utilization across all cores
- **Core Count**: Number of physical and logical CPU cores
- **Frequency**: Current and maximum CPU frequencies
- **Load Average**: System load over 1, 5, and 15-minute intervals
- **Process CPU Usage**: CPU usage by individual processes

#### Memory Metrics
- **Physical Memory**: Total, used, available, and percentage
- **Virtual Memory**: Swap usage and availability
- **Memory by Process**: Memory consumption by individual processes
- **Cache Usage**: System cache and buffer usage
- **Memory Trends**: Historical memory usage patterns

#### Disk Metrics
- **Disk Usage**: Total, used, and available space
- **I/O Statistics**: Read/write operations and throughput
- **Disk Performance**: Average response times and queue lengths
- **Storage Health**: Drive health and temperature (where available)

#### Network Metrics
- **Network I/O**: Bytes sent/received and packet counts
- **Connection Statistics**: Active connections and connection states
- **Bandwidth Usage**: Current and peak bandwidth utilization
- **API Performance**: Response times for external API calls

#### GPU Metrics (NVIDIA)
- **GPU Utilization**: GPU core and memory utilization
- **Memory Usage**: GPU memory allocation and availability
- **Temperature**: GPU temperature monitoring
- **Power Usage**: GPU power consumption
- **Process Information**: GPU usage by process

### Processing Performance Tracking

#### Audio Processing Metrics
- **Enhancement Times**: Time spent on AI audio enhancement
- **Model Load Times**: Time to initialize audio processing models
- **Processing Throughput**: Sermons processed per hour/day
- **Quality Metrics**: Audio enhancement quality scores
- **Error Rates**: Processing failure rates and error types

#### LLM Performance Metrics
- **API Response Times**: Response times for different LLM providers
- **Token Usage**: Input/output token consumption
- **Cost Tracking**: API costs per request and per sermon
- **Success Rates**: API call success and failure rates
- **Provider Comparison**: Performance comparison between providers

#### Overall Processing Metrics
- **End-to-End Times**: Total time from start to completion
- **Stage Breakdown**: Time spent in each processing stage
- **Batch Processing**: Performance metrics for batch operations
- **Queue Metrics**: Job queue length and processing rates

## Configuration

### Basic Configuration

```yaml
performance_monitoring:
  enabled: true
  collection_interval_seconds: 30
  retention_days: 30
  database_path: "performance_metrics.db"
```

### Advanced Configuration

```yaml
performance_monitoring:
  enabled: true
  
  # Collection settings
  collection_interval_seconds: 30
  detailed_collection_interval_seconds: 300
  retention_days: 30
  
  # Storage settings
  database_path: "performance_metrics.db"
  backup_enabled: true
  backup_interval_hours: 24
  
  # Alert thresholds
  cpu_alert_threshold: 80.0
  memory_alert_threshold: 85.0
  disk_alert_threshold: 90.0
  
  # GPU monitoring (if available)
  gpu_monitoring_enabled: true
  gpu_alert_threshold: 85.0
  
  # Network monitoring
  network_monitoring_enabled: true
  api_timeout_threshold_seconds: 30
  
  # Processing monitoring
  processing_alert_enabled: true
  max_processing_time_minutes: 30
  error_rate_threshold: 0.1
```

## Usage

### Real-time Monitoring

```python
from ui.performance_monitor import PerformanceMonitor

# Initialize monitor
monitor = PerformanceMonitor()

# Get current system metrics
metrics = monitor.get_system_metrics()
print(f"CPU Usage: {metrics['cpu']['usage_percent']}%")
print(f"Memory Usage: {metrics['memory']['usage_percent']}%")
print(f"GPU Usage: {metrics['gpu']['utilization_percent']}%")

# Get processing performance
processing_metrics = monitor.get_processing_metrics()
print(f"Average processing time: {processing_metrics['avg_processing_time']}s")
print(f"Success rate: {processing_metrics['success_rate']}%")
```

### Historical Analysis

```python
# Get historical performance data
history = monitor.get_historical_metrics(days=7)

# Analyze trends
cpu_trend = monitor.analyze_cpu_trend(history)
memory_trend = monitor.analyze_memory_trend(history)

# Generate optimization recommendations
recommendations = monitor.get_optimization_recommendations()
```

### Performance Alerts

```python
# Set up performance alerts
alerts = monitor.check_performance_alerts()

for alert in alerts:
    print(f"Alert: {alert['type']} - {alert['message']}")
    print(f"Severity: {alert['severity']}")
    print(f"Recommendation: {alert['recommendation']}")
```

## Metrics Data Models

### System Metrics

```python
{
    "timestamp": "2024-01-15T10:30:00Z",
    "cpu": {
        "usage_percent": 45.2,
        "count": 8,
        "frequency_current": 2400.0,
        "frequency_max": 3200.0,
        "load_average": [1.2, 1.5, 1.8]
    },
    "memory": {
        "total_gb": 16.0,
        "used_gb": 8.5,
        "available_gb": 7.5,
        "usage_percent": 53.1,
        "swap_total_gb": 4.0,
        "swap_used_gb": 0.2
    },
    "disk": {
        "total_gb": 500.0,
        "used_gb": 275.0,
        "free_gb": 225.0,
        "usage_percent": 55.0,
        "read_speed_mbps": 120.5,
        "write_speed_mbps": 89.3
    },
    "network": {
        "bytes_sent": 1024000,
        "bytes_received": 2048000,
        "packets_sent": 1500,
        "packets_received": 2000
    },
    "gpu": {
        "available": true,
        "name": "NVIDIA RTX 4090",
        "utilization_percent": 25.0,
        "memory_total_gb": 24.0,
        "memory_used_gb": 6.0,
        "temperature_celsius": 65
    }
}
```

### Processing Metrics

```python
{
    "timestamp": "2024-01-15T10:30:00Z",
    "audio_processing": {
        "enhancement_time_seconds": 180.5,
        "model_load_time_seconds": 45.2,
        "throughput_sermons_per_hour": 20,
        "error_rate": 0.05
    },
    "llm_processing": {
        "avg_response_time_seconds": 2.5,
        "total_tokens_used": 15000,
        "cost_usd": 0.75,
        "success_rate": 0.98
    },
    "overall": {
        "total_processing_time_seconds": 245.0,
        "sermons_processed": 12,
        "success_rate": 0.92,
        "avg_sermon_size_mb": 15.5
    }
}
```

## Optimization Recommendations

### Dynamic Recommendations

The system provides context-aware optimization suggestions:

#### High CPU Usage
```
Recommendation: CPU usage is at 85%
- Consider reducing audio enhancement quality settings
- Enable batch processing to improve efficiency
- Schedule processing during off-peak hours
```

#### High Memory Usage
```
Recommendation: Memory usage is at 90%
- Reduce audio chunk size for processing
- Clear model cache between batches
- Consider processing fewer sermons simultaneously
```

#### GPU Underutilization
```
Recommendation: GPU usage is only 15%
- Enable GPU acceleration for audio enhancement
- Increase batch size for better GPU utilization
- Consider using more GPU-intensive models
```

#### Slow API Responses
```
Recommendation: LLM API responses are slow (>10s average)
- Switch to faster LLM provider for primary use
- Reduce context window size
- Enable request caching
```

### Performance Tuning

```python
def get_optimization_recommendations(metrics):
    recommendations = []
    
    # CPU optimization
    if metrics['cpu']['usage_percent'] > 80:
        recommendations.append({
            'category': 'cpu',
            'severity': 'high',
            'message': 'High CPU usage detected',
            'suggestions': [
                'Reduce audio processing quality',
                'Enable batch processing',
                'Schedule during off-peak hours'
            ]
        })
    
    # Memory optimization
    if metrics['memory']['usage_percent'] > 85:
        recommendations.append({
            'category': 'memory',
            'severity': 'high',
            'message': 'High memory usage detected',
            'suggestions': [
                'Reduce chunk size',
                'Clear model cache',
                'Process fewer sermons concurrently'
            ]
        })
    
    return recommendations
```

## Monitoring Dashboard

### Web Interface

The Streamlit interface provides real-time monitoring:

```python
def show_performance_dashboard():
    # Real-time metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("CPU Usage", f"{cpu_usage}%", delta=cpu_delta)
    
    with col2:
        st.metric("Memory Usage", f"{memory_usage}%", delta=memory_delta)
    
    with col3:
        st.metric("GPU Usage", f"{gpu_usage}%", delta=gpu_delta)
    
    with col4:
        st.metric("Processing Rate", f"{processing_rate}/hr", delta=rate_delta)
    
    # Performance charts
    st.subheader("Performance Trends")
    
    # CPU usage over time
    st.line_chart(cpu_history)
    
    # Memory usage over time
    st.line_chart(memory_history)
    
    # Processing performance
    st.bar_chart(processing_performance)
```

### Alerts and Notifications

```python
def check_and_send_alerts():
    alerts = monitor.check_performance_alerts()
    
    for alert in alerts:
        if alert['severity'] == 'critical':
            send_email_alert(alert)
        elif alert['severity'] == 'warning':
            log_warning(alert)
        
        # Update dashboard
        st.warning(f"{alert['message']}: {alert['recommendation']}")
```

## Database Schema

### Performance Metrics Table

```sql
CREATE TABLE performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    metric_type TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    metadata TEXT
);

CREATE INDEX idx_timestamp ON performance_metrics(timestamp);
CREATE INDEX idx_metric_type ON performance_metrics(metric_type);
```

### Processing Metrics Table

```sql
CREATE TABLE processing_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    sermon_id TEXT,
    processing_stage TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    metadata TEXT
);
```

## API Reference

### PerformanceMonitor Class

```python
class PerformanceMonitor:
    def __init__(self, db_path: str = "performance_metrics.db"):
        """Initialize performance monitor"""
    
    def get_system_metrics(self) -> dict:
        """Get current system resource metrics"""
    
    def get_processing_metrics(self) -> dict:
        """Get processing performance metrics"""
    
    def get_historical_metrics(self, days: int = 7) -> list:
        """Get historical performance data"""
    
    def check_performance_alerts(self) -> list:
        """Check for performance alerts"""
    
    def get_optimization_recommendations(self) -> list:
        """Get performance optimization recommendations"""
    
    def start_monitoring(self, interval_seconds: int = 30):
        """Start continuous monitoring"""
    
    def stop_monitoring(self):
        """Stop continuous monitoring"""
```

### Utility Functions

```python
def format_bytes(bytes_value: int) -> str:
    """Format bytes to human readable format"""

def calculate_percentage(used: float, total: float) -> float:
    """Calculate percentage with safe division"""

def get_gpu_info() -> dict:
    """Get GPU information (NVIDIA only)"""

def analyze_performance_trend(metrics: list) -> dict:
    """Analyze performance trends from historical data"""
```

## Troubleshooting

### Common Issues

**GPU Metrics Not Available:**
```bash
# Install NVIDIA monitoring tools
pip install nvidia-ml-py3

# Check GPU availability
nvidia-smi
```

**Permission Issues:**
```bash
# On Linux, may need elevated permissions for some metrics
sudo chmod +r /proc/*/stat
```

**Database Errors:**
```python
# Check database permissions
import os
import sqlite3

db_path = "performance_metrics.db"
if not os.path.exists(db_path):
    # Create database with proper permissions
    conn = sqlite3.connect(db_path)
    conn.close()
    os.chmod(db_path, 0o666)
```

### Performance Impact

The monitoring system is designed to have minimal impact:

- **CPU Overhead**: < 1% additional CPU usage
- **Memory Overhead**: < 50MB additional memory
- **Disk Usage**: ~1MB per day of metrics data
- **Network Impact**: No external network calls

## Integration

### With Existing Systems

```python
# Integration with sermon processing
def process_sermon_with_monitoring(sermon_id):
    monitor = PerformanceMonitor()
    
    start_time = time.time()
    try:
        result = process_sermon(sermon_id)
        
        # Record success metrics
        monitor.record_processing_metric(
            sermon_id=sermon_id,
            stage="complete",
            duration=time.time() - start_time,
            success=True
        )
        
        return result
        
    except Exception as e:
        # Record failure metrics
        monitor.record_processing_metric(
            sermon_id=sermon_id,
            stage="error",
            duration=time.time() - start_time,
            success=False,
            error_message=str(e)
        )
        raise
```

### Export and Reporting

```python
def export_performance_report(start_date, end_date):
    """Export performance report to CSV"""
    
    monitor = PerformanceMonitor()
    metrics = monitor.get_historical_metrics_range(start_date, end_date)
    
    df = pd.DataFrame(metrics)
    df.to_csv(f"performance_report_{start_date}_{end_date}.csv")
    
    return df
```

## Future Enhancements

- **Machine Learning**: Predictive performance analytics
- **Anomaly Detection**: Automatic detection of unusual patterns
- **Custom Dashboards**: User-configurable monitoring views
- **External Integrations**: Prometheus, Grafana, DataDog support
- **Mobile Alerts**: Push notifications for critical alerts
- **Performance Baselines**: Automatic baseline establishment and comparison