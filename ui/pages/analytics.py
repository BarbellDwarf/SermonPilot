"""
Analytics Page for SermonAudio Processor

Displays processing metrics, success rates, content analysis, cost tracking,
and performance charts with interactive visualizations.
"""

import streamlit as st
import pandas as pd
import datetime
import json

def show_analytics():
    """Main analytics interface"""
    st.markdown('<div class="main-header">📈 Analytics</div>', unsafe_allow_html=True)
    
    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return
    
    # Analytics tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Processing Metrics", 
        "📝 Content Analysis", 
        "💰 Cost Tracking", 
        "⚡ Performance"
    ])
    
    with tab1:
        show_processing_metrics()
    
    with tab2:
        show_content_analysis()
    
    with tab3:
        show_cost_tracking()
    
    with tab4:
        show_performance_metrics()

def show_processing_metrics():
    """Processing statistics and success rates"""
    st.markdown("### 📊 Processing Metrics")
    
    # Time range selector
    col1, col2, col3 = st.columns(3)
    
    with col1:
        time_range = st.selectbox(
            "Time Range",
            options=["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"],
            index=1
        )
    
    with col2:
        refresh_data = st.button("🔄 Refresh Data")
    
    with col3:
        auto_refresh = st.checkbox("Auto Refresh (30s)")
    
    # Generate mock data based on time range
    metrics_data = generate_mock_metrics_data(time_range)
    
    # Key metrics row
    show_key_metrics(metrics_data)
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        show_success_rate_chart(metrics_data)
        show_processing_volume_chart(metrics_data)
    
    with col2:
        show_error_types_chart(metrics_data)
        show_processing_time_trend(metrics_data)

def show_content_analysis():
    """Content and speaker analysis"""
    st.markdown("### 📝 Content Analysis")
    
    # Content metrics
    content_data = generate_mock_content_data()
    
    # Speaker activity
    st.markdown("#### 👤 Speaker Activity")
    
    speaker_stats = content_data['speaker_stats']
    df_speakers = pd.DataFrame(speaker_stats)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Mock plotly chart (would use actual plotly when installed)
        st.markdown("**Speaker Processing Volume (Last 30 Days)**")
        st.bar_chart(df_speakers.set_index('speaker')['sermons_processed'])
    
    with col2:
        st.markdown("**Top Speakers**")
        for speaker in speaker_stats[:5]:
            st.metric(
                speaker['speaker'], 
                f"{speaker['sermons_processed']} sermons",
                f"{speaker['avg_quality_score']:.1f} quality"
            )
    
    # Event type distribution
    st.markdown("#### 📅 Event Type Distribution")
    
    event_data = content_data['event_types']
    df_events = pd.DataFrame(event_data)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Event Type Breakdown**")
        # Mock pie chart
        for event in event_data:
            st.write(f"• {event['event_type']}: {event['count']} ({event['percentage']:.1f}%)")
    
    with col2:
        st.markdown("**Quality by Event Type**")
        for event in event_data:
            st.metric(
                event['event_type'],
                f"{event['avg_quality']:.1f}/10",
                f"{event['success_rate']:.1f}% success"
            )
    
    # Content quality trends
    st.markdown("#### ✅ Content Quality Trends")
    
    quality_data = content_data['quality_trends']
    df_quality = pd.DataFrame(quality_data)
    
    # Mock line chart
    st.line_chart(df_quality.set_index('date')[['description_quality', 'hashtag_quality']])

def show_cost_tracking():
    """LLM API usage and cost analysis"""
    st.markdown("### 💰 Cost Tracking")
    
    # Cost summary
    cost_data = generate_mock_cost_data()
    
    # Current month summary
    st.markdown("#### 📊 Current Month Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total API Calls",
            f"{cost_data['total_calls']:,}",
            f"+{cost_data['calls_change']:,} vs last month"
        )
    
    with col2:
        st.metric(
            "Total Tokens",
            f"{cost_data['total_tokens']:,}",
            f"+{cost_data['tokens_change']:,} vs last month"
        )
    
    with col3:
        st.metric(
            "Total Cost",
            f"${cost_data['total_cost']:.2f}",
            f"+${cost_data['cost_change']:.2f} vs last month"
        )
    
    with col4:
        st.metric(
            "Avg Cost/Sermon",
            f"${cost_data['avg_cost_per_sermon']:.3f}",
            f"{cost_data['efficiency_change']:+.1f}% efficiency"
        )
    
    # Provider breakdown
    st.markdown("#### 🤖 Provider Usage Breakdown")
    
    provider_data = cost_data['provider_breakdown']
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Usage by Provider**")
        for provider in provider_data:
            st.write(f"**{provider['name']}**")
            st.write(f"• Calls: {provider['calls']:,}")
            st.write(f"• Cost: ${provider['cost']:.2f}")
            st.write(f"• Usage: {provider['percentage']:.1f}%")
            st.write("")
    
    with col2:
        st.markdown("**Cost Trends (Last 30 Days)**")
        # Mock cost trend chart
        dates = pd.date_range(start=datetime.date.today() - datetime.timedelta(days=29), 
                             end=datetime.date.today(), freq='D')
        costs = [cost_data['total_cost'] * (0.8 + 0.4 * i / len(dates)) for i in range(len(dates))]
        
        df_costs = pd.DataFrame({'date': dates, 'daily_cost': costs})
        st.line_chart(df_costs.set_index('date'))
    
    # Model usage details
    st.markdown("#### 🔧 Model Usage Details")
    
    model_data = cost_data['model_usage']
    df_models = pd.DataFrame(model_data)
    
    st.dataframe(
        df_models,
        column_config={
            "model": "Model",
            "calls": st.column_config.NumberColumn("API Calls", format="%d"),
            "tokens": st.column_config.NumberColumn("Tokens", format="%d"),
            "cost": st.column_config.NumberColumn("Cost", format="$%.3f"),
            "avg_tokens_per_call": st.column_config.NumberColumn("Avg Tokens/Call", format="%.0f")
        },
        hide_index=True,
        use_container_width=True
    )

def show_performance_metrics():
    """System performance and optimization metrics"""
    st.markdown("### ⚡ Performance Metrics")
    
    # Performance summary
    perf_data = generate_mock_performance_data()
    
    # System health
    st.markdown("#### 🔍 System Health")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Avg Processing Time",
            f"{perf_data['avg_processing_time']:.1f} min",
            f"{perf_data['processing_time_change']:+.1f} min vs last week"
        )
    
    with col2:
        st.metric(
            "Success Rate",
            f"{perf_data['success_rate']:.1f}%",
            f"{perf_data['success_rate_change']:+.1f}% vs last week"
        )
    
    with col3:
        st.metric(
            "Queue Length",
            f"{perf_data['queue_length']}",
            f"{perf_data['queue_change']:+d} vs yesterday"
        )
    
    with col4:
        st.metric(
            "Error Rate",
            f"{perf_data['error_rate']:.1f}%",
            f"{perf_data['error_rate_change']:+.1f}% vs last week"
        )
    
    # Performance charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### ⏱️ Processing Time Distribution")
        
        # Mock histogram data
        time_buckets = ["0-2 min", "2-5 min", "5-10 min", "10-20 min", "20+ min"]
        time_counts = [45, 120, 85, 30, 8]
        
        df_times = pd.DataFrame({
            'time_bucket': time_buckets,
            'count': time_counts
        })
        
        st.bar_chart(df_times.set_index('time_bucket'))
    
    with col2:
        st.markdown("#### 🔄 Processing Steps Performance")
        
        step_data = perf_data['step_performance']
        df_steps = pd.DataFrame(step_data)
        
        st.dataframe(
            df_steps,
            column_config={
                "step": "Processing Step",
                "avg_time": st.column_config.NumberColumn("Avg Time (s)", format="%.1f"),
                "success_rate": st.column_config.NumberColumn("Success Rate", format="%.1f%%"),
                "bottleneck_score": st.column_config.NumberColumn("Bottleneck Score", format="%.2f")
            },
            hide_index=True,
            use_container_width=True
        )
    
    # Resource usage
    st.markdown("#### 💻 Resource Usage")
    
    resource_data = perf_data['resource_usage']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("CPU Usage", f"{resource_data['cpu_usage']:.1f}%")
        st.metric("Memory Usage", f"{resource_data['memory_usage']:.1f}%")
    
    with col2:
        st.metric("Disk Usage", f"{resource_data['disk_usage']:.1f}%")
        st.metric("Network I/O", f"{resource_data['network_io']:.1f} MB/s")
    
    with col3:
        st.metric("GPU Usage", f"{resource_data['gpu_usage']:.1f}%")
        st.metric("GPU Memory", f"{resource_data['gpu_memory']:.1f}%")
    
    # Optimization recommendations
    st.markdown("#### 💡 Optimization Recommendations")
    
    recommendations = perf_data['recommendations']
    
    for rec in recommendations:
        priority_color = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
        icon = priority_color.get(rec['priority'], "🔵")
        
        with st.expander(f"{icon} {rec['title']} ({rec['priority']} Priority)"):
            st.write(rec['description'])
            st.write(f"**Impact:** {rec['impact']}")
            st.write(f"**Effort:** {rec['effort']}")

def show_key_metrics(metrics_data):
    """Display key processing metrics"""
    st.markdown("#### 📊 Key Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Processed",
            f"{metrics_data['total_processed']:,}",
            f"+{metrics_data['processed_change']:,} vs previous period"
        )
    
    with col2:
        st.metric(
            "Success Rate",
            f"{metrics_data['success_rate']:.1f}%",
            f"{metrics_data['success_rate_change']:+.1f}% vs previous period"
        )
    
    with col3:
        st.metric(
            "Avg Processing Time",
            f"{metrics_data['avg_time']:.1f} min",
            f"{metrics_data['time_change']:+.1f} min vs previous period"
        )
    
    with col4:
        st.metric(
            "Total Errors",
            f"{metrics_data['total_errors']:,}",
            f"{metrics_data['error_change']:+d} vs previous period"
        )

def show_success_rate_chart(metrics_data):
    """Show success rate over time"""
    st.markdown("#### ✅ Success Rate Trend")
    
    # Mock time series data
    dates = pd.date_range(start=datetime.date.today() - datetime.timedelta(days=29), 
                         end=datetime.date.today(), freq='D')
    success_rates = [85 + 10 * (i % 7) / 7 + (i % 3) for i in range(len(dates))]
    
    df_success = pd.DataFrame({'date': dates, 'success_rate': success_rates})
    st.line_chart(df_success.set_index('date'))

def show_processing_volume_chart(metrics_data):
    """Show processing volume over time"""
    st.markdown("#### 📈 Processing Volume")
    
    # Mock volume data
    dates = pd.date_range(start=datetime.date.today() - datetime.timedelta(days=29), 
                         end=datetime.date.today(), freq='D')
    volumes = [20 + 15 * (i % 5) / 5 for i in range(len(dates))]
    
    df_volume = pd.DataFrame({'date': dates, 'volume': volumes})
    st.area_chart(df_volume.set_index('date'))

def show_error_types_chart(metrics_data):
    """Show error type distribution"""
    st.markdown("#### ❌ Error Types")
    
    error_types = ["LLM Timeout", "Audio Processing", "API Error", "Network Error", "Other"]
    error_counts = [12, 8, 5, 3, 2]
    
    df_errors = pd.DataFrame({'error_type': error_types, 'count': error_counts})
    st.bar_chart(df_errors.set_index('error_type'))

def show_processing_time_trend(metrics_data):
    """Show processing time trend"""
    st.markdown("#### ⏱️ Processing Time Trend")
    
    dates = pd.date_range(start=datetime.date.today() - datetime.timedelta(days=29), 
                         end=datetime.date.today(), freq='D')
    times = [5.2 + 2 * (i % 4) / 4 for i in range(len(dates))]
    
    df_times = pd.DataFrame({'date': dates, 'avg_time': times})
    st.line_chart(df_times.set_index('date'))

def generate_mock_metrics_data(time_range):
    """Generate mock metrics data"""
    return {
        'total_processed': 1247,
        'processed_change': 156,
        'success_rate': 89.3,
        'success_rate_change': 2.1,
        'avg_time': 4.7,
        'time_change': -0.3,
        'total_errors': 133,
        'error_change': -12
    }

def generate_mock_content_data():
    """Generate mock content analysis data"""
    return {
        'speaker_stats': [
            {'speaker': 'Pastor John Smith', 'sermons_processed': 45, 'avg_quality_score': 8.7},
            {'speaker': 'Dr. Sarah Johnson', 'sermons_processed': 32, 'avg_quality_score': 9.1},
            {'speaker': 'Rev. Michael Brown', 'sermons_processed': 28, 'avg_quality_score': 8.3},
            {'speaker': 'Pastor Mary Wilson', 'sermons_processed': 23, 'avg_quality_score': 8.9},
            {'speaker': 'Elder David Lee', 'sermons_processed': 19, 'avg_quality_score': 8.1}
        ],
        'event_types': [
            {'event_type': 'Sunday - AM', 'count': 89, 'percentage': 45.2, 'avg_quality': 8.6, 'success_rate': 91.0},
            {'event_type': 'Sunday - PM', 'count': 56, 'percentage': 28.4, 'avg_quality': 8.3, 'success_rate': 88.5},
            {'event_type': 'Wednesday Service', 'count': 34, 'percentage': 17.3, 'avg_quality': 8.1, 'success_rate': 85.3},
            {'event_type': 'Bible Study', 'count': 18, 'percentage': 9.1, 'avg_quality': 7.9, 'success_rate': 83.3}
        ],
        'quality_trends': [
            {'date': '2024-01-01', 'description_quality': 8.2, 'hashtag_quality': 7.8},
            {'date': '2024-01-08', 'description_quality': 8.4, 'hashtag_quality': 8.1},
            {'date': '2024-01-15', 'description_quality': 8.6, 'hashtag_quality': 8.3},
            {'date': '2024-01-22', 'description_quality': 8.5, 'hashtag_quality': 8.5},
            {'date': '2024-01-29', 'description_quality': 8.7, 'hashtag_quality': 8.4}
        ]
    }

def generate_mock_cost_data():
    """Generate mock cost tracking data"""
    return {
        'total_calls': 2847,
        'calls_change': 284,
        'total_tokens': 1245890,
        'tokens_change': 156780,
        'total_cost': 47.23,
        'cost_change': 5.67,
        'avg_cost_per_sermon': 0.038,
        'efficiency_change': -12.3,
        'provider_breakdown': [
            {'name': 'OpenAI GPT-4', 'calls': 1523, 'cost': 28.45, 'percentage': 60.2},
            {'name': 'Ollama Llama3', 'calls': 987, 'cost': 0.00, 'percentage': 34.7},
            {'name': 'OpenAI GPT-3.5', 'calls': 337, 'cost': 18.78, 'percentage': 11.8}
        ],
        'model_usage': [
            {'model': 'gpt-4', 'calls': 1523, 'tokens': 789456, 'cost': 28.45, 'avg_tokens_per_call': 518},
            {'model': 'gpt-3.5-turbo', 'calls': 337, 'tokens': 234567, 'cost': 18.78, 'avg_tokens_per_call': 696},
            {'model': 'llama3:8b', 'calls': 987, 'tokens': 221867, 'cost': 0.00, 'avg_tokens_per_call': 225}
        ]
    }

def generate_mock_performance_data():
    """Generate mock performance data"""
    return {
        'avg_processing_time': 4.7,
        'processing_time_change': -0.3,
        'success_rate': 89.3,
        'success_rate_change': 2.1,
        'queue_length': 3,
        'queue_change': -2,
        'error_rate': 10.7,
        'error_rate_change': -2.1,
        'step_performance': [
            {'step': 'Audio Enhancement', 'avg_time': 145.3, 'success_rate': 94.2, 'bottleneck_score': 0.85},
            {'step': 'Transcription', 'avg_time': 67.8, 'success_rate': 96.7, 'bottleneck_score': 0.45},
            {'step': 'Description Generation', 'avg_time': 23.4, 'success_rate': 91.3, 'bottleneck_score': 0.32},
            {'step': 'Hashtag Generation', 'avg_time': 12.1, 'success_rate': 93.8, 'bottleneck_score': 0.18},
            {'step': 'Validation', 'avg_time': 8.7, 'success_rate': 97.1, 'bottleneck_score': 0.12}
        ],
        'resource_usage': {
            'cpu_usage': 45.3,
            'memory_usage': 62.7,
            'disk_usage': 34.2,
            'network_io': 12.8,
            'gpu_usage': 78.9,
            'gpu_memory': 84.3
        },
        'recommendations': [
            {
                'title': 'Optimize Audio Enhancement Pipeline',
                'priority': 'High',
                'description': 'Audio enhancement is the primary bottleneck. Consider GPU acceleration or model optimization.',
                'impact': 'Could reduce processing time by 40%',
                'effort': 'Medium - requires model configuration changes'
            },
            {
                'title': 'Implement Batch Processing for Transcription',
                'priority': 'Medium',
                'description': 'Group smaller audio files for batch transcription to improve GPU utilization.',
                'impact': 'Could increase throughput by 25%',
                'effort': 'Low - configuration change only'
            }
        ]
    }

if __name__ == "__main__":
    show_analytics()