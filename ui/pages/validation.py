"""
Validation Page for SermonAudio Processor

Handles description validation, quality metrics, failed descriptions management,
and batch validation with detailed reporting.
"""

import streamlit as st
import pandas as pd
import datetime

def show_validation():
    """Main validation interface"""
    st.markdown('<div class="main-header">✅ Validation</div>', unsafe_allow_html=True)
    
    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return
    
    # Validation tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Quality Metrics", 
        "❌ Failed Descriptions", 
        "🔄 Batch Validation", 
        "📈 Trends"
    ])
    
    with tab1:
        show_quality_metrics()
    
    with tab2:
        show_failed_descriptions()
    
    with tab3:
        show_batch_validation()
    
    with tab4:
        show_validation_trends()

def show_quality_metrics():
    """Display validation metrics and quality scores"""
    st.markdown("### 📊 Quality Metrics Overview")
    
    # Generate mock validation data
    validation_data = generate_mock_validation_data()
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Overall Quality Score",
            f"{validation_data['overall_score']:.1f}/10",
            f"{validation_data['score_change']:+.1f} vs last week"
        )
    
    with col2:
        st.metric(
            "Validation Rate",
            f"{validation_data['validation_rate']:.1f}%",
            f"{validation_data['validation_change']:+.1f}% vs last week"
        )
    
    with col3:
        st.metric(
            "Auto-Pass Rate",
            f"{validation_data['auto_pass_rate']:.1f}%",
            f"{validation_data['auto_pass_change']:+.1f}% vs last week"
        )
    
    with col4:
        st.metric(
            "Avg Validation Time",
            f"{validation_data['avg_validation_time']:.1f}s",
            f"{validation_data['time_change']:+.1f}s vs last week"
        )
    
    # Quality criteria breakdown
    st.markdown("#### 🎯 Quality Criteria Performance")
    
    criteria_data = validation_data['criteria_performance']
    df_criteria = pd.DataFrame(criteria_data)
    
    # Display criteria performance
    for idx, criterion in df_criteria.iterrows():
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            st.write(f"**{criterion['criterion']}**")
        
        with col2:
            score_color = "🟢" if criterion['score'] >= 8 else "🟡" if criterion['score'] >= 6 else "🔴"
            st.write(f"{score_color} {criterion['score']:.1f}/10")
        
        with col3:
            st.write(f"{criterion['pass_rate']:.1f}% pass")
    
    # Recent validation results
    st.markdown("#### 📋 Recent Validation Results")
    
    recent_results = validation_data['recent_results']
    df_results = pd.DataFrame(recent_results)
    
    # Add status styling
    df_results['Status'] = df_results.apply(
        lambda row: f"✅ Pass ({row['score']:.1f}/10)" if row['passed'] 
                   else f"❌ Fail ({row['score']:.1f}/10)", axis=1
    )
    
    st.dataframe(
        df_results[['sermon_id', 'title', 'speaker', 'Status', 'validation_time']].rename(columns={
            'sermon_id': 'Sermon ID',
            'title': 'Title',
            'speaker': 'Speaker',
            'validation_time': 'Validation Time'
        }),
        width='stretch',
        hide_index=True
    )

def show_failed_descriptions():
    """Show descriptions that failed validation"""
    st.markdown("### ❌ Failed Descriptions")
    
    # Failed descriptions data
    failed_data = generate_mock_failed_data()
    
    # Summary stats
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Failed", len(failed_data))
    
    with col2:
        priority_count = sum(1 for item in failed_data if item['priority'] == 'High')
        st.metric("High Priority", priority_count)
    
    with col3:
        regenerated = sum(1 for item in failed_data if item.get('regenerated', False))
        st.metric("Regenerated", regenerated)
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        priority_filter = st.selectbox(
            "Filter by Priority",
            options=["All", "High", "Medium", "Low"]
        )
    
    with col2:
        speaker_filter = st.selectbox(
            "Filter by Speaker",
            options=["All"] + list(set(item['speaker'] for item in failed_data))
        )
    
    with col3:
        status_filter = st.selectbox(
            "Filter by Status",
            options=["All", "Pending", "Regenerated", "Manual Review"]
        )
    
    # Apply filters
    filtered_data = failed_data.copy()
    if priority_filter != "All":
        filtered_data = [item for item in filtered_data if item['priority'] == priority_filter]
    if speaker_filter != "All":
        filtered_data = [item for item in filtered_data if item['speaker'] == speaker_filter]
    if status_filter != "All":
        filtered_data = [item for item in filtered_data if item.get('status', 'Pending') == status_filter]
    
    # Display failed descriptions
    st.markdown("#### 📋 Failed Descriptions List")
    
    for item in filtered_data[:10]:  # Show first 10 items
        with st.expander(f"🔴 {item['title']} - {item['speaker']} (Score: {item['score']:.1f}/10)"):
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown("**Original Description:**")
                st.write(item['description'])
                
                st.markdown("**Validation Issues:**")
                for issue in item['issues']:
                    st.write(f"• {issue}")
            
            with col2:
                st.markdown("**Details:**")
                st.write(f"**Priority:** {item['priority']}")
                st.write(f"**Date:** {item['date']}")
                st.write(f"**Score:** {item['score']:.1f}/10")
                
                # Action buttons
                col_a, col_b = st.columns(2)
                
                with col_a:
                    if st.button("🔄 Regenerate", key=f"regen_{item['sermon_id']}"):
                        regenerate_description(item['sermon_id'])
                
                with col_b:
                    if st.button("👤 Manual Review", key=f"manual_{item['sermon_id']}"):
                        mark_for_manual_review(item['sermon_id'])
    
    # Bulk actions
    st.markdown("#### 🔄 Bulk Actions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 Regenerate All High Priority", type="primary"):
            regenerate_high_priority()
    
    with col2:
        if st.button("📧 Export Failed List"):
            export_failed_list()
    
    with col3:
        if st.button("📊 Generate Report"):
            generate_validation_report()

def show_batch_validation():
    """Batch validation interface"""
    st.markdown("### 🔄 Batch Validation")
    
    # Batch validation options
    st.markdown("#### ⚙️ Validation Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        validation_scope = st.selectbox(
            "Validation Scope",
            options=[
                "All Recent Descriptions", 
                "Unvalidated Only", 
                "Failed Previous Validation",
                "Specific Date Range",
                "Custom Selection"
            ]
        )
        
        strict_mode = st.checkbox(
            "Strict Validation Mode",
            help="Use stricter validation criteria"
        )
    
    with col2:
        auto_regenerate = st.checkbox(
            "Auto-Regenerate Failed",
            help="Automatically regenerate descriptions that fail validation"
        )
        
        max_items = st.number_input(
            "Max Items to Validate",
            min_value=1,
            max_value=1000,
            value=100
        )
    
    # Date range selection (if applicable)
    if validation_scope == "Specific Date Range":
        col1, col2 = st.columns(2)
        
        with col1:
            start_date = st.date_input("Start Date")
        
        with col2:
            end_date = st.date_input("End Date")
    
    # Custom validation criteria
    with st.expander("🎯 Custom Validation Criteria"):
        st.markdown("Customize validation criteria for this batch:")
        
        criteria = [
            "Contains specific theological content or Bible references",
            "Mentions the speaker's main message or key points", 
            "Is written in a professional, engaging style",
            "Avoids generic Christian phrases without substance",
            "Has clear application or takeaway for listeners"
        ]
        
        selected_criteria = []
        for criterion in criteria:
            if st.checkbox(criterion, value=True, key=f"criteria_{criterion[:20]}"):
                selected_criteria.append(criterion)
        
        custom_criterion = st.text_input("Add custom criterion:")
        if custom_criterion:
            selected_criteria.append(custom_criterion)
    
    # Start batch validation
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("▶️ Start Batch Validation", type="primary"):
            start_batch_validation()
    
    with col2:
        if st.button("📋 Preview Selection"):
            preview_validation_selection()
    
    with col3:
        if st.button("💾 Save as Template"):
            save_validation_template()
    
    # Show batch progress if running
    if st.session_state.get('batch_validation_running'):
        show_batch_validation_progress()

def show_validation_trends():
    """Show validation trends and historical data"""
    st.markdown("### 📈 Validation Trends")
    
    # Time period selector
    period = st.selectbox(
        "Time Period",
        options=["Last 7 Days", "Last 30 Days", "Last 90 Days", "Last Year"]
    )
    
    trends_data = generate_mock_trends_data(period)
    
    # Trend charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Quality Score Trends")
        
        df_quality = pd.DataFrame(trends_data['quality_trends'])
        st.line_chart(df_quality.set_index('date')[['avg_score', 'median_score']])
    
    with col2:
        st.markdown("#### ✅ Pass Rate Trends") 
        
        df_pass_rate = pd.DataFrame(trends_data['pass_rate_trends'])
        st.line_chart(df_pass_rate.set_index('date'))
    
    # Criteria performance over time
    st.markdown("#### 🎯 Criteria Performance Over Time")
    
    df_criteria_trends = pd.DataFrame(trends_data['criteria_trends'])
    st.line_chart(df_criteria_trends.set_index('date'))
    
    # Statistical summary
    st.markdown("#### 📊 Statistical Summary")
    
    stats = trends_data['statistics']
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Mean Quality Score", f"{stats['mean_score']:.2f}")
        st.metric("Score Std Dev", f"{stats['score_std']:.2f}")
    
    with col2:
        st.metric("Best Day Score", f"{stats['best_day_score']:.1f}")
        st.metric("Worst Day Score", f"{stats['worst_day_score']:.1f}")
    
    with col3:
        st.metric("Improvement Rate", f"{stats['improvement_rate']:+.1f}%")
        st.metric("Consistency Score", f"{stats['consistency']:.1f}/10")
    
    with col4:
        st.metric("Total Validations", f"{stats['total_validations']:,}")
        st.metric("Avg Daily Volume", f"{stats['avg_daily_volume']:.0f}")

def regenerate_description(sermon_id):
    """Regenerate description for a specific sermon"""
    st.success(f"✅ Regeneration started for sermon {sermon_id}")

def mark_for_manual_review(sermon_id):
    """Mark sermon for manual review"""
    st.info(f"📝 Sermon {sermon_id} marked for manual review")

def regenerate_high_priority():
    """Regenerate all high priority failed descriptions"""
    st.success("🔄 Started regenerating all high priority descriptions")

def export_failed_list():
    """Export list of failed descriptions"""
    st.success("📥 Failed descriptions list exported")

def generate_validation_report():
    """Generate validation report"""
    st.success("📊 Validation report generated")

def start_batch_validation():
    """Start batch validation process"""
    st.session_state.batch_validation_running = True
    st.success("▶️ Batch validation started")

def preview_validation_selection():
    """Preview what will be validated"""
    st.info("📋 Preview: 45 sermons will be validated based on current criteria")

def save_validation_template():
    """Save current settings as template"""
    st.success("💾 Validation template saved")

def show_batch_validation_progress():
    """Show batch validation progress"""
    st.markdown("#### 🔄 Batch Validation Progress")
    
    progress = st.session_state.get('batch_validation_progress', 0.3)
    st.progress(progress)
    st.text(f"Validating: 15/50 sermons completed")
    
    # Mock completion
    import time
    if progress >= 1.0:
        st.session_state.batch_validation_running = False
        st.success("✅ Batch validation completed!")

def generate_mock_validation_data():
    """Generate mock validation data"""
    return {
        'overall_score': 8.3,
        'score_change': 0.4,
        'validation_rate': 94.2,
        'validation_change': 2.1,
        'auto_pass_rate': 78.5,
        'auto_pass_change': 5.3,
        'avg_validation_time': 2.7,
        'time_change': -0.2,
        'criteria_performance': [
            {'criterion': 'Contains theological content', 'score': 8.7, 'pass_rate': 87.3},
            {'criterion': 'Mentions main message', 'score': 8.1, 'pass_rate': 82.1},
            {'criterion': 'Professional style', 'score': 8.9, 'pass_rate': 91.2},
            {'criterion': 'Avoids generic phrases', 'score': 7.4, 'pass_rate': 73.8},
            {'criterion': 'Clear application', 'score': 8.0, 'pass_rate': 79.5}
        ],
        'recent_results': [
            {'sermon_id': '123456', 'title': 'Grace in Trials', 'speaker': 'Pastor Smith', 
             'score': 8.9, 'passed': True, 'validation_time': '2.3s'},
            {'sermon_id': '123457', 'title': 'Walking in Faith', 'speaker': 'Dr. Johnson',
             'score': 6.2, 'passed': False, 'validation_time': '3.1s'},
            {'sermon_id': '123458', 'title': 'Hope Eternal', 'speaker': 'Rev. Brown',
             'score': 9.1, 'passed': True, 'validation_time': '2.0s'}
        ]
    }

def generate_mock_failed_data():
    """Generate mock failed validation data"""
    return [
        {
            'sermon_id': '123457',
            'title': 'Walking in Faith',
            'speaker': 'Dr. Johnson',
            'description': 'A sermon about faith and walking with God in our daily lives.',
            'score': 6.2,
            'priority': 'High',
            'date': '2024-01-15',
            'issues': [
                'Description too generic',
                'Missing specific biblical references',
                'No clear practical application mentioned'
            ]
        },
        {
            'sermon_id': '123459',
            'title': 'Sunday Message',
            'speaker': 'Pastor Wilson',
            'description': 'God is good and we should trust Him.',
            'score': 4.1,
            'priority': 'High',
            'date': '2024-01-14',
            'issues': [
                'Extremely brief and generic',
                'No mention of specific content',
                'Missing speaker insights'
            ]
        }
    ]

def generate_mock_trends_data(period):
    """Generate mock trends data"""
    return {
        'quality_trends': [
            {'date': '2024-01-01', 'avg_score': 7.8, 'median_score': 8.1},
            {'date': '2024-01-08', 'avg_score': 8.0, 'median_score': 8.3},
            {'date': '2024-01-15', 'avg_score': 8.2, 'median_score': 8.4},
            {'date': '2024-01-22', 'avg_score': 8.1, 'median_score': 8.2},
            {'date': '2024-01-29', 'avg_score': 8.3, 'median_score': 8.5}
        ],
        'pass_rate_trends': [
            {'date': '2024-01-01', 'pass_rate': 76.2},
            {'date': '2024-01-08', 'pass_rate': 78.5},
            {'date': '2024-01-15', 'pass_rate': 81.3},
            {'date': '2024-01-22', 'pass_rate': 79.7},
            {'date': '2024-01-29', 'pass_rate': 83.1}
        ],
        'criteria_trends': [
            {'date': '2024-01-01', 'theological': 8.1, 'style': 8.3, 'application': 7.9},
            {'date': '2024-01-08', 'theological': 8.3, 'style': 8.5, 'application': 8.1},
            {'date': '2024-01-15', 'theological': 8.5, 'style': 8.7, 'application': 8.0},
            {'date': '2024-01-22', 'theological': 8.4, 'style': 8.6, 'application': 8.2},
            {'date': '2024-01-29', 'theological': 8.6, 'style': 8.8, 'application': 8.3}
        ],
        'statistics': {
            'mean_score': 8.17,
            'score_std': 1.23,
            'best_day_score': 9.2,
            'worst_day_score': 7.1,
            'improvement_rate': 12.3,
            'consistency': 8.4,
            'total_validations': 1247,
            'avg_daily_volume': 28.5
        }
    }

if __name__ == "__main__":
    show_validation()