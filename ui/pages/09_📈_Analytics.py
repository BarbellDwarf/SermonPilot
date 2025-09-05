"""
Content Analytics Dashboard - Advanced analytics for sermon processing

Provides comprehensive analytics as specified in requirements:
- Overall processing statistics with SermonAudio integration
- Q&A processing performance metrics with gain distribution
- Content themes and topic analysis
- Geographic and engagement data from SermonAudio API
- Processing quality trends and performance monitoring
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
import asyncio

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

from database import SermonRepository, get_db
from analytics_manager import get_analytics_manager
from sermon_manager import get_sermon_manager
from shared_navigation import render_shared_sidebar, initialize_session_state

# Page configuration
st.set_page_config(page_title="Analytics Dashboard", page_icon="📈", layout="wide")

# Load configuration
try:
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    config = {}

# Initialize managers
@st.cache_resource
def get_managers():
    analytics_mgr = get_analytics_manager(config)
    sermon_mgr = get_sermon_manager(config)
    return analytics_mgr, sermon_mgr

@st.cache_data
def get_sermon_count():
    """Get total count of sermons"""
    try:
        repo = SermonRepository()
        sermons = repo.get_all_sermons()
        return len(sermons)
    except Exception as e:
        st.error(f"Error getting sermon count: {e}")
        return 0

@st.cache_data
def get_qa_session_count():
    """Get count of sermons with Q&A sessions"""
    try:
        repo = SermonRepository()
        sermons = repo.get_all_sermons()
        qa_count = sum(1 for s in sermons if s.get('qa_segments'))
        return qa_count
    except Exception as e:
        st.error(f"Error getting Q&A session count: {e}")
        return 0

@st.cache_data
def get_total_duration():
    """Get total duration of all sermons in hours"""
    try:
        repo = SermonRepository()
        sermons = repo.get_all_sermons()
        total_seconds = sum(s.get('duration', 0) for s in sermons if s.get('duration'))
        return round(total_seconds / 3600, 1)  # Convert to hours
    except Exception as e:
        st.error(f"Error getting total duration: {e}")
        return 0.0


def show_content_analytics():
    """Enhanced content analytics dashboard with SermonAudio integration"""
    st.title("📈 Analytics Dashboard")
    st.markdown("Comprehensive analytics for sermon processing and engagement")
    
    # Initialize managers
    analytics_manager, sermon_manager = get_managers()
    
    # Load dashboard analytics
    with st.spinner("Loading analytics data..."):
        try:
            dashboard_data = asyncio.run(analytics_manager.get_dashboard_analytics())
        except Exception as e:
            st.error(f"Error loading analytics: {e}")
            dashboard_data = None
    
    if not dashboard_data:
        st.warning("Analytics data unavailable. Using local database statistics.")
        show_fallback_analytics()
        return
    
    # === OVERVIEW METRICS ===
    st.subheader("📊 Overview Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Sermons", 
            dashboard_data.total_sermons,
            help="Total number of sermons in the system"
        )
    
    with col2:
        st.metric(
            "Total Views", 
            f"{dashboard_data.total_views:,}",
            delta=f"+{dashboard_data.growth_metrics.get('views_growth', 0):.1f}%",
            help="Total views across all sermons"
        )
    
    with col3:
        st.metric(
            "Hours Watched", 
            f"{dashboard_data.total_hours_watched:.1f}",
            help="Total hours of content watched"
        )
    
    with col4:
        avg_engagement = dashboard_data.avg_engagement_rate * 100
        st.metric(
            "Avg Engagement", 
            f"{avg_engagement:.1f}%",
            delta=f"+{dashboard_data.growth_metrics.get('completion_growth', 0):.1f}%",
            help="Average completion rate across sermons"
        )
    
    st.divider()
    
    # === MAIN ANALYTICS SECTIONS ===
    
    # Geographic and Engagement Charts
    col1, col2 = st.columns(2)
    
    with col1:
        show_geographic_analytics(dashboard_data.geographic_summary)
    
    with col2:
        show_engagement_trends(dashboard_data.engagement_trends)
    
    st.divider()
    
    # Q&A Processing Performance
    show_qa_processing_analytics()
    
    st.divider()
    
    # Top Performing Sermons
    show_top_sermons(dashboard_data.top_sermons)
    
    st.divider()
    
    # Content Analysis
    show_content_analysis()
    
    st.divider()
    
    # Recent Activity
    show_recent_activity(dashboard_data.recent_activity)
    
    # Data Export
    st.subheader("📤 Data Export")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Export Analytics CSV"):
            csv_data = generate_analytics_csv(dashboard_data)
            st.download_button(
                "Download Analytics Data",
                csv_data,
                file_name=f"analytics_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    with col2:
        if st.button("📈 Export Charts PDF"):
            st.info("PDF export feature in development")
    
    with col3:
        if st.button("🔄 Refresh Data"):
            analytics_manager.invalidate_cache()
            st.rerun()
    
    # Last updated
    st.caption(f"Last updated: {dashboard_data.last_updated.strftime('%Y-%m-%d %H:%M:%S')}")

def show_geographic_analytics(geographic_data):
    """Show geographic distribution of listeners"""
    st.subheader("🌍 Geographic Distribution")
    
    if not geographic_data:
        st.info("Geographic data not available")
        return
    
    # Prepare data for visualization
    geo_df = pd.DataFrame([
        {
            'Location': loc.location,
            'Views': loc.views,
            'Percentage': loc.percentage
        } for loc in geographic_data
    ])
    
    # Pie chart
    fig = px.pie(
        geo_df,
        values='Views',
        names='Location',
        title="Listener Distribution by Location",
        hover_data=['Percentage']
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig, use_container_width=True)
    
    # Data table
    with st.expander("📋 Detailed Geographic Data"):
        st.dataframe(geo_df, use_container_width=True)

def show_engagement_trends(engagement_trends):
    """Show engagement trends over time"""
    st.subheader("📈 Engagement Trends")
    
    if not engagement_trends:
        st.info("Engagement data not available")
        return
    
    # Prepare timeline data
    trends_df = pd.DataFrame([
        {
            'Date': point.timestamp,
            'Views': point.value,
            'Label': point.label
        } for point in engagement_trends
    ])
    
    # Line chart
    fig = px.line(
        trends_df,
        x='Date',
        y='Views',
        title="Daily Views Over Time",
        markers=True
    )
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Views",
        hovermode='x unified'
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Summary statistics
    if len(trends_df) > 1:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            avg_views = trends_df['Views'].mean()
            st.metric("Avg Daily Views", f"{avg_views:.0f}")
        
        with col2:
            peak_views = trends_df['Views'].max()
            st.metric("Peak Day Views", f"{peak_views:.0f}")
        
        with col3:
            recent_trend = trends_df['Views'].tail(7).mean() - trends_df['Views'].head(7).mean()
            trend_indicator = "📈" if recent_trend > 0 else "📉"
            st.metric("Recent Trend", f"{trend_indicator} {recent_trend:+.0f}")

def show_qa_processing_analytics():
    """Show Q&A processing performance metrics"""
    st.subheader("🗣️ Q&A Processing Performance")
    
    repo = SermonRepository()
    
    # Get Q&A metrics from database
    qa_metrics = get_qa_processing_metrics()
    
    if not qa_metrics['segments_data']:
        st.info("No Q&A segments found in processed sermons")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Q&A Detection Chart
        st.markdown("#### Q&A Detection Over Time")
        
        if qa_metrics['monthly_trends']:
            monthly_df = pd.DataFrame(qa_metrics['monthly_trends'])
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=monthly_df['month'],
                y=monthly_df['sermons_with_qa'],
                name='Sermons with Q&A',
                marker_color='lightblue'
            ))
            fig.add_trace(go.Scatter(
                x=monthly_df['month'],
                y=monthly_df['total_segments'],
                mode='lines+markers',
                name='Total Segments',
                yaxis='y2',
                line=dict(color='red')
            ))
            
            fig.update_layout(
                title="Q&A Detection Trends",
                xaxis_title="Month",
                yaxis_title="Sermons with Q&A",
                yaxis2=dict(
                    title="Total Segments",
                    overlaying='y',
                    side='right'
                ),
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Gain Distribution Chart
        st.markdown("#### Audio Gain Distribution")
        
        if qa_metrics['gain_distribution']:
            gain_df = pd.DataFrame(qa_metrics['gain_distribution'])
            
            fig = px.histogram(
                gain_df,
                x='gain_applied',
                bins=20,
                title="Q&A Audio Gain Distribution",
                labels={'gain_applied': 'Gain Applied (dB)', 'count': 'Number of Segments'}
            )
            fig.update_layout(
                xaxis_title="Gain Applied (dB)",
                yaxis_title="Number of Segments"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Q&A Performance Summary
    st.markdown("#### Q&A Performance Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_segments = len(qa_metrics['segments_data'])
        st.metric("Total Q&A Segments", total_segments)
    
    with col2:
        avg_gain = sum(s['avg_gain'] for s in qa_metrics['segments_data']) / len(qa_metrics['segments_data']) if qa_metrics['segments_data'] else 0
        st.metric("Avg Gain Applied", f"+{avg_gain:.1f}dB")
    
    with col3:
        avg_confidence = sum(s['avg_confidence'] for s in qa_metrics['segments_data']) / len(qa_metrics['segments_data']) if qa_metrics['segments_data'] else 0
        st.metric("Avg Confidence", f"{avg_confidence:.1%}")
    
    with col4:
        sermons_with_qa = len([s for s in qa_metrics['segments_data'] if s['segment_count'] > 0])
        st.metric("Sermons with Q&A", sermons_with_qa)

def show_top_sermons(top_sermons):
    """Show top performing sermons"""
    st.subheader("🏆 Top Performing Sermons")
    
    if not top_sermons:
        st.info("No sermon performance data available")
        return
    
    # Convert to DataFrame
    top_df = pd.DataFrame(top_sermons)
    
    # Add ranking
    top_df['Rank'] = range(1, len(top_df) + 1)
    
    # Display table
    columns_to_show = ['Rank', 'title', 'speaker', 'views', 'completion_rate', 'unique_listeners']
    display_df = top_df[columns_to_show].copy()
    display_df.columns = ['Rank', 'Title', 'Speaker', 'Views', 'Completion Rate', 'Unique Listeners']
    
    # Format columns
    display_df['Completion Rate'] = display_df['Completion Rate'].apply(lambda x: f"{x:.1%}")
    display_df['Views'] = display_df['Views'].apply(lambda x: f"{x:,}")
    display_df['Unique Listeners'] = display_df['Unique Listeners'].apply(lambda x: f"{x:,}")
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        # Top sermons by views
        fig = px.bar(
            top_df.head(10),
            x='views',
            y='title',
            orientation='h',
            title="Top 10 Sermons by Views",
            labels={'views': 'Views', 'title': 'Sermon Title'}
        )
        fig.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Completion rate vs views scatter
        fig = px.scatter(
            top_df,
            x='views',
            y='completion_rate',
            size='unique_listeners',
            hover_data=['title', 'speaker'],
            title="Views vs Completion Rate",
            labels={'views': 'Views', 'completion_rate': 'Completion Rate'}
        )
        fig.update_traces(opacity=0.7)
        st.plotly_chart(fig, use_container_width=True)

def show_content_analysis():
    """Show content themes and topic analysis"""
    st.subheader("📊 Content Analysis")
    
    repo = SermonRepository()
    
    # Get content statistics
    content_stats = analyze_sermon_content()
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Speaker distribution
        st.markdown("#### Speaker Distribution")
        
        if content_stats['speaker_stats']:
            speaker_df = pd.DataFrame(content_stats['speaker_stats'])
            
            fig = px.pie(
                speaker_df,
                values='sermon_count',
                names='speaker',
                title="Sermons by Speaker"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Event type distribution
        st.markdown("#### Event Type Distribution")
        
        if content_stats['event_type_stats']:
            event_df = pd.DataFrame(content_stats['event_type_stats'])
            
            fig = px.bar(
                event_df,
                x='event_type',
                y='sermon_count',
                title="Sermons by Event Type"
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
    
    # Topic analysis (if available)
    if content_stats['topic_analysis']:
        st.markdown("#### Popular Topics")
        
        topic_df = pd.DataFrame(content_stats['topic_analysis'])
        
        fig = px.treemap(
            topic_df,
            path=['topic'],
            values='frequency',
            title="Topic Distribution"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Processing statistics
    st.markdown("#### Processing Statistics")
    
    processing_stats = content_stats['processing_stats']
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Processed Sermons", processing_stats.get('processed_count', 0))
    
    with col2:
        st.metric("With Transcripts", processing_stats.get('transcript_count', 0))
    
    with col3:
        st.metric("With Descriptions", processing_stats.get('description_count', 0))
    
    with col4:
        st.metric("With Q&A", processing_stats.get('qa_count', 0))

def show_recent_activity(recent_activity):
    """Show recent sermon activity"""
    st.subheader("🕒 Recent Activity")
    
    if not recent_activity:
        st.info("No recent activity data available")
        return
    
    # Display as expandable items
    for activity in recent_activity[:10]:  # Show last 10
        with st.expander(f"🎵 {activity.get('title', 'Unknown')} - {activity.get('speaker', 'Unknown')}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**Date:** {activity.get('date', 'Unknown')}")
                st.write(f"**Status:** {activity.get('status', 'Unknown').title()}")
            
            with col2:
                st.write(f"**Recent Views:** {activity.get('recent_views', 0)}")
                st.write(f"**Sermon ID:** {activity.get('sermon_id', 'Unknown')}")
            
            with col3:
                if st.button(f"📖 View Details", key=f"view_{activity.get('sermon_id')}"):
                    st.session_state.selected_sermon = activity.get('sermon_id')
                    st.switch_page("pages/08_📖_Viewer.py")

def show_fallback_analytics():
    """Show fallback analytics when SermonAudio API unavailable"""
    st.info("Using local database statistics (SermonAudio API unavailable)")
    
    repo = SermonRepository()
    stats = repo.get_processing_stats()
    
    # Basic metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Sermons", stats.get('total_sermons', 0))
    
    with col2:
        st.metric("Q&A Sessions", stats.get('qa_sermons', 0))
    
    with col3:
        st.metric("Total Duration", f"{stats.get('total_duration_hours', 0):.1f} hours")
    
    with col4:
        avg_quality = get_avg_quality_score()
        st.metric("Avg Quality Score", f"{avg_quality:.1f}/10")
    
    # Show local Q&A analytics
    show_qa_processing_analytics()
    
    # Show content analysis
    show_content_analysis()

# Helper functions
def get_qa_processing_metrics():
    """Get Q&A processing performance metrics from database"""
    repo = SermonRepository()
    
    with repo.db.get_connection() as conn:
        # Q&A segments by sermon
        segments_data = conn.execute("""
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
        'segments_data': [dict(row) for row in segments_data],
        'monthly_trends': [dict(row) for row in monthly_trends],
        'gain_distribution': [dict(row) for row in gain_distribution]
    }

def analyze_sermon_content():
    """Analyze sermon content for topics and statistics"""
    repo = SermonRepository()
    
    with repo.db.get_connection() as conn:
        # Speaker statistics
        speaker_stats = conn.execute("""
            SELECT speaker, COUNT(*) as sermon_count
            FROM sermons
            WHERE speaker IS NOT NULL
            GROUP BY speaker
            ORDER BY sermon_count DESC
        """).fetchall()
        
        # Event type statistics
        event_type_stats = conn.execute("""
            SELECT event_type, COUNT(*) as sermon_count
            FROM sermons
            WHERE event_type IS NOT NULL
            GROUP BY event_type
            ORDER BY sermon_count DESC
        """).fetchall()
        
        # Processing statistics
        processing_stats = conn.execute("""
            SELECT 
                COUNT(*) as total_count,
                COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed_count,
                COUNT(CASE WHEN transcript IS NOT NULL AND transcript != '' THEN 1 END) as transcript_count,
                COUNT(CASE WHEN description IS NOT NULL AND description != '' THEN 1 END) as description_count
            FROM sermons
        """).fetchone()
        
        # Q&A count
        qa_count = conn.execute("""
            SELECT COUNT(DISTINCT sermon_id) as qa_count
            FROM qa_segments
        """).fetchone()
    
    # Basic topic analysis (could be enhanced with NLP)
    topic_analysis = []  # Placeholder for future topic extraction
    
    return {
        'speaker_stats': [dict(row) for row in speaker_stats],
        'event_type_stats': [dict(row) for row in event_type_stats],
        'processing_stats': dict(processing_stats) if processing_stats else {},
        'qa_count': qa_count['qa_count'] if qa_count else 0,
        'topic_analysis': topic_analysis
    }

def generate_analytics_csv(dashboard_data):
    """Generate CSV export of analytics data"""
    # Create summary data
    summary_data = {
        'Metric': [
            'Total Sermons',
            'Total Views', 
            'Total Hours Watched',
            'Average Engagement Rate',
            'Views Growth',
            'Completion Growth'
        ],
        'Value': [
            dashboard_data.total_sermons,
            dashboard_data.total_views,
            dashboard_data.total_hours_watched,
            dashboard_data.avg_engagement_rate,
            dashboard_data.growth_metrics.get('views_growth', 0),
            dashboard_data.growth_metrics.get('completion_growth', 0)
        ]
    }
    
    df = pd.DataFrame(summary_data)
    return df.to_csv(index=False)

def get_avg_quality_score():
    """Get average quality score"""
    repo = SermonRepository()
    with repo.db.get_connection() as conn:
        result = conn.execute("""
            SELECT AVG(quality_score) as avg_score 
            FROM processing_info 
            WHERE quality_score IS NOT NULL
        """).fetchone()
        return result['avg_score'] if result and result['avg_score'] else 0.0

def get_qa_processing_metrics():
    """Get Q&A processing performance metrics"""
    repo = SermonRepository()
    with repo.db.get_connection() as conn:
        # Get Q&A segments data
        qa_segments = conn.execute("""
            SELECT ROUND(gain_applied, 1) as gain_applied,
                   COUNT(*) as count
            FROM qa_segments qa
            GROUP BY ROUND(qa.gain_applied, 1)
            ORDER BY qa.gain_applied
        """).fetchall()
        
        # Get monthly trends (mock data for demo)
        monthly_trends = []
        gain_distribution = [dict(row) for row in qa_segments]
        
        return {
            'qa_segments': [dict(row) for row in qa_segments],
            'monthly_trends': monthly_trends,
            'gain_distribution': gain_distribution
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
    # Initialize session state and render navigation
    initialize_session_state()
    render_shared_sidebar()
    show_content_analytics()
else:
    # When imported as a page
    initialize_session_state()
    render_shared_sidebar()
    show_content_analytics()