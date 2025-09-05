"""
Content Analytics Dashboard - Advanced analytics for sermon processing

Provides comprehensive analytics as specified in requirements:
- Overall processing statistics
- Q&A processing performance metrics
- Content themes and topic analysis
- Processing quality trends
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sys
from pathlib import Path
import json

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

from database import SermonRepository, get_db

# Page configuration
st.set_page_config(page_title="Analytics Dashboard", page_icon="📈", layout="wide")


def get_sermon_count():
    """Get total number of sermons"""
    repo = SermonRepository()
    stats = repo.get_processing_stats()
    return stats['total_sermons']


def get_qa_session_count():
    """Get number of sermons with Q&A sessions"""
    repo = SermonRepository()
    stats = repo.get_processing_stats()
    return stats['qa_sermons']


def get_total_duration():
    """Get total duration in hours"""
    repo = SermonRepository()
    stats = repo.get_processing_stats()
    return stats['total_duration_hours']


def get_avg_quality_score():
    """Get average quality score"""
    repo = SermonRepository()
    with repo.db.get_connection() as conn:
        result = conn.execute("""
            SELECT AVG(quality_score) as avg_score 
            FROM processing_info 
            WHERE quality_score IS NOT NULL
        """).fetchone()
        return result['avg_score'] if result['avg_score'] else 0.0


def get_qa_processing_metrics():
    """Get Q&A processing performance metrics"""
    repo = SermonRepository()
    
    with repo.db.get_connection() as conn:
        # Q&A segments by sermon
        qa_segments = conn.execute("""
            SELECT s.id, s.title, s.speaker, s.recorded_date,
                   COUNT(qa.id) as segment_count,
                   AVG(qa.gain_applied) as avg_gain,
                   AVG(qa.confidence) as avg_confidence
            FROM sermons s
            LEFT JOIN qa_segments qa ON s.id = qa.sermon_id
            WHERE qa.id IS NOT NULL
            GROUP BY s.id
            ORDER BY s.recorded_date DESC
        """).fetchall()
        
        # Monthly Q&A trends
        monthly_trends = conn.execute("""
            SELECT substr(s.recorded_date, 1, 7) as month,
                   COUNT(DISTINCT s.id) as sermons_with_qa,
                   COUNT(qa.id) as total_segments,
                   AVG(qa.gain_applied) as avg_gain
            FROM sermons s
            JOIN qa_segments qa ON s.id = qa.sermon_id
            WHERE s.recorded_date IS NOT NULL
            GROUP BY substr(s.recorded_date, 1, 7)
            ORDER BY month
        """).fetchall()
        
        # Gain distribution
        gain_distribution = conn.execute("""
            SELECT qa.gain_applied,
                   COUNT(*) as count
            FROM qa_segments qa
            GROUP BY ROUND(qa.gain_applied, 1)
            ORDER BY qa.gain_applied
        """).fetchall()
        
        return {
            'qa_segments': [dict(row) for row in qa_segments],
            'monthly_trends': [dict(row) for row in monthly_trends],
            'gain_distribution': [dict(row) for row in gain_distribution]
        }


def create_qa_detection_chart(qa_metrics):
    """Create Q&A detection performance chart"""
    if not qa_metrics['monthly_trends']:
        return go.Figure().add_annotation(text="No Q&A data available", showarrow=False)
    
    df = pd.DataFrame(qa_metrics['monthly_trends'])
    
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('Q&A Sessions Over Time', 'Average Gain Applied'),
        vertical_spacing=0.15
    )
    
    # Q&A sessions trend
    fig.add_trace(
        go.Scatter(
            x=df['month'],
            y=df['sermons_with_qa'],
            mode='lines+markers',
            name='Sermons with Q&A',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=8)
        ),
        row=1, col=1
    )
    
    # Average gain trend
    fig.add_trace(
        go.Scatter(
            x=df['month'],
            y=df['avg_gain'],
            mode='lines+markers',
            name='Avg Gain Applied',
            line=dict(color='#ff7f0e', width=3),
            marker=dict(size=8)
        ),
        row=2, col=1
    )
    
    fig.update_layout(
        title="Q&A Processing Performance",
        height=500,
        showlegend=False
    )
    
    fig.update_xaxes(title_text="Month", row=2, col=1)
    fig.update_yaxes(title_text="Sessions", row=1, col=1)
    fig.update_yaxes(title_text="Gain (dB)", row=2, col=1)
    
    return fig


def create_audio_improvement_chart(qa_metrics):
    """Create audio improvement metrics chart"""
    if not qa_metrics['gain_distribution']:
        return go.Figure().add_annotation(text="No gain data available", showarrow=False)
    
    df = pd.DataFrame(qa_metrics['gain_distribution'])
    
    fig = px.bar(
        df,
        x='gain_applied',
        y='count',
        title='Gain Applied Distribution',
        labels={'gain_applied': 'Gain Applied (dB)', 'count': 'Number of Segments'},
        color='count',
        color_continuous_scale='Blues'
    )
    
    fig.update_layout(
        height=400,
        xaxis_title="Gain Applied (dB)",
        yaxis_title="Number of Segments"
    )
    
    return fig


def analyze_sermon_topics():
    """Analyze sermon topics and themes"""
    repo = SermonRepository()
    
    with repo.db.get_connection() as conn:
        # Speaker distribution
        speakers = conn.execute("""
            SELECT speaker, COUNT(*) as sermon_count
            FROM sermons 
            WHERE speaker IS NOT NULL
            GROUP BY speaker
            ORDER BY sermon_count DESC
            LIMIT 10
        """).fetchall()
        
        # Event type distribution
        events = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM sermons 
            WHERE event_type IS NOT NULL
            GROUP BY event_type
            ORDER BY count DESC
        """).fetchall()
        
        # Monthly sermon counts
        monthly = conn.execute("""
            SELECT substr(recorded_date, 1, 7) as month,
                   COUNT(*) as sermon_count
            FROM sermons 
            WHERE recorded_date IS NOT NULL
            GROUP BY substr(recorded_date, 1, 7)
            ORDER BY month
        """).fetchall()
        
        return {
            'speakers': [dict(row) for row in speakers],
            'events': [dict(row) for row in events],
            'monthly': [dict(row) for row in monthly]
        }


def create_topic_distribution_chart(topic_data):
    """Create topic distribution visualization"""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Top Speakers', 'Event Types', 'Monthly Activity', 'Processing Status'),
        specs=[[{"type": "xy"}, {"type": "domain"}],
               [{"type": "xy"}, {"type": "domain"}]]
    )
    
    # Top speakers
    if topic_data['speakers']:
        speakers_df = pd.DataFrame(topic_data['speakers'])
        fig.add_trace(
            go.Bar(
                x=speakers_df['sermon_count'],
                y=speakers_df['speaker'],
                orientation='h',
                name='Speakers',
                marker_color='lightblue'
            ),
            row=1, col=1
        )
    
    # Event types pie chart
    if topic_data['events']:
        events_df = pd.DataFrame(topic_data['events'])
        fig.add_trace(
            go.Pie(
                labels=events_df['event_type'],
                values=events_df['count'],
                name="Event Types"
            ),
            row=1, col=2
        )
    
    # Monthly activity
    if topic_data['monthly']:
        monthly_df = pd.DataFrame(topic_data['monthly'])
        fig.add_trace(
            go.Scatter(
                x=monthly_df['month'],
                y=monthly_df['sermon_count'],
                mode='lines+markers',
                name='Monthly Count',
                line=dict(color='green', width=3)
            ),
            row=2, col=1
        )
    
    # Processing status (placeholder)
    fig.add_trace(
        go.Pie(
            labels=['Processed', 'Pending', 'Failed'],
            values=[85, 10, 5],  # Example values
            name="Processing Status"
        ),
        row=2, col=2
    )
    
    fig.update_layout(
        title="Content Analysis Dashboard",
        height=800,
        showlegend=False
    )
    
    return fig


def show_content_analytics():
    """Main content analytics dashboard"""
    st.title("📈 Content Analytics")
    st.markdown("Comprehensive analytics for sermon processing and Q&A performance")
    
    # Overall statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_count = get_sermon_count()
        st.metric("Total Sermons", total_count)
    
    with col2:
        qa_count = get_qa_session_count()
        st.metric("Q&A Sessions", qa_count)
    
    with col3:
        total_hours = get_total_duration()
        st.metric("Total Duration", f"{total_hours:.1f} hours")
    
    with col4:
        avg_quality = get_avg_quality_score()
        st.metric("Avg Quality Score", f"{avg_quality:.1f}/10")
    
    # Q&A Processing Analytics
    st.subheader("🗣️ Q&A Processing Performance")
    
    try:
        qa_metrics = get_qa_processing_metrics()
        
        if qa_metrics['qa_segments']:
            col1, col2 = st.columns(2)
            
            with col1:
                qa_chart = create_qa_detection_chart(qa_metrics)
                st.plotly_chart(qa_chart, use_container_width=True)
            
            with col2:
                improvement_chart = create_audio_improvement_chart(qa_metrics)
                st.plotly_chart(improvement_chart, use_container_width=True)
            
            # Q&A Performance Summary
            st.subheader("📊 Q&A Performance Summary")
            
            # Calculate summary statistics
            total_segments = sum(1 for _ in qa_metrics['qa_segments'])
            if total_segments > 0:
                avg_segments_per_sermon = total_segments / len(qa_metrics['qa_segments'])
                total_gain_applied = sum(seg.get('avg_gain', 0) for seg in qa_metrics['qa_segments'])
                avg_gain = total_gain_applied / len(qa_metrics['qa_segments'])
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Avg Segments/Sermon", f"{avg_segments_per_sermon:.1f}")
                with col2:
                    st.metric("Avg Gain Applied", f"+{avg_gain:.1f}dB")
                with col3:
                    detection_rate = len(qa_metrics['qa_segments']) / total_count * 100 if total_count > 0 else 0
                    st.metric("Q&A Detection Rate", f"{detection_rate:.1f}%")
        else:
            st.info("No Q&A processing data available yet")
    
    except Exception as e:
        st.error(f"Error loading Q&A analytics: {e}")
    
    # Content themes and topics
    st.subheader("📊 Content Analysis")
    
    try:
        topic_data = analyze_sermon_topics()
        topic_chart = create_topic_distribution_chart(topic_data)
        st.plotly_chart(topic_chart, use_container_width=True)
        
        # Detailed tables
        col1, col2 = st.columns(2)
        
        with col1:
            if topic_data['speakers']:
                st.subheader("Top Speakers")
                speakers_df = pd.DataFrame(topic_data['speakers'])
                st.dataframe(speakers_df, use_container_width=True)
        
        with col2:
            if topic_data['events']:
                st.subheader("Event Types")
                events_df = pd.DataFrame(topic_data['events'])
                st.dataframe(events_df, use_container_width=True)
    
    except Exception as e:
        st.error(f"Error loading content analytics: {e}")
    
    # Processing Performance
    st.subheader("⚡ Processing Performance")
    
    try:
        repo = SermonRepository()
        with repo.db.get_connection() as conn:
            # Processing time trends
            processing_times = conn.execute("""
                SELECT pi.processing_duration,
                       pi.enhancement_method,
                       s.recorded_date
                FROM processing_info pi
                JOIN sermons s ON pi.sermon_id = s.id
                WHERE pi.processing_duration IS NOT NULL
                ORDER BY s.recorded_date DESC
                LIMIT 50
            """).fetchall()
            
            if processing_times:
                times_df = pd.DataFrame([dict(row) for row in processing_times])
                
                # Processing time by method
                if 'enhancement_method' in times_df.columns:
                    method_chart = px.box(
                        times_df,
                        x='enhancement_method',
                        y='processing_duration',
                        title='Processing Time by Enhancement Method',
                        labels={'processing_duration': 'Processing Time (seconds)', 'enhancement_method': 'Method'}
                    )
                    st.plotly_chart(method_chart, use_container_width=True)
                
                # Recent processing times
                recent_chart = px.line(
                    times_df.head(20),
                    x='recorded_date',
                    y='processing_duration',
                    title='Recent Processing Times',
                    labels={'processing_duration': 'Processing Time (seconds)', 'recorded_date': 'Date'}
                )
                st.plotly_chart(recent_chart, use_container_width=True)
            else:
                st.info("No processing time data available")
    
    except Exception as e:
        st.error(f"Error loading processing performance: {e}")
    
    # Export Options
    st.subheader("📤 Export Options")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Export Analytics Report"):
            # Generate comprehensive analytics report
            report_data = {
                'generated_at': datetime.now().isoformat(),
                'summary': {
                    'total_sermons': get_sermon_count(),
                    'qa_sessions': get_qa_session_count(),
                    'total_duration_hours': get_total_duration(),
                    'avg_quality_score': get_avg_quality_score()
                },
                'qa_metrics': qa_metrics if 'qa_metrics' in locals() else {},
                'topic_analysis': topic_data if 'topic_data' in locals() else {}
            }
            
            report_json = json.dumps(report_data, indent=2)
            st.download_button(
                "📥 Download Analytics Report (JSON)",
                report_json,
                file_name=f"sermon_analytics_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
    
    with col2:
        if st.button("📈 Export Processing Stats"):
            try:
                repo = SermonRepository()
                stats = repo.get_processing_stats()
                stats_json = json.dumps(stats, indent=2)
                st.download_button(
                    "📥 Download Stats (JSON)",
                    stats_json,
                    file_name=f"processing_stats_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )
            except Exception as e:
                st.error(f"Export failed: {e}")
    
    with col3:
        if st.button("🔄 Refresh Analytics"):
            st.cache_data.clear()
            st.rerun()


if __name__ == "__main__":
    show_content_analytics()
else:
    # When imported as a page
    show_content_analytics()