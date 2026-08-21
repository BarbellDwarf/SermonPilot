"""
Analytics Page for SermonPilot

Displays processing metrics, success rates, content analysis, cost tracking,
performance charts with interactive visualizations, and SermonAudio analytics.
"""

import datetime

import pandas as pd
import streamlit as st

# Import the new analytics chat interface
try:
    from ui.analytics_chat import render_analytics_chat_tab  # noqa: F401
    ANALYTICS_CHAT_AVAILABLE = True
except ImportError:
    ANALYTICS_CHAT_AVAILABLE = False

def show_analytics():
    """Main analytics interface"""
    st.markdown('<div class="main-header">Analytics</div>', unsafe_allow_html=True)

    if not st.session_state.config:
        st.error("Configuration not loaded. Please check the Settings page first.")
        return

    # Analytics tabs
    if ANALYTICS_CHAT_AVAILABLE:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Processing Metrics",
            "Content Analysis",
            "Cost Tracking",
            "Performance",
            "SermonAudio Analytics"
        ])
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "Processing Metrics",
            "Content Analysis",
            "Cost Tracking",
            "Performance"
        ])

    with tab1:
        show_processing_metrics()

    with tab2:
        show_content_analysis()

    with tab3:
        show_cost_tracking()

    with tab4:
        show_performance_metrics()

    # SermonAudio Analytics tab (if available)
    if ANALYTICS_CHAT_AVAILABLE:
        with tab5:
            st.markdown("### SermonAudio Analytics")

            # Create sub-tabs for different views
            data_tab, chat_tab = st.tabs(["Data View", "Chat Interface"])

            with data_tab:
                show_sermonaudio_data_view()

            with chat_tab:
                # Pass configuration to the chat interface
                from ui.analytics_chat import AnalyticsChatInterface
                chat_interface = AnalyticsChatInterface(config=st.session_state.config)
                chat_interface.render_chat_interface()
                chat_interface.render_chat_settings()

def show_processing_metrics():
    """Processing statistics and success rates"""
    st.markdown("### Processing Metrics")

    # Time range selector
    col1, col2 = st.columns([2, 1])

    with col1:
        time_range = st.selectbox(
            "Time Range",
            options=["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"],
            index=1
        )

    with col2:
        if st.button(
            "Refresh Data", help="Clear cached analytics and reload from the database"
        ):
            st.cache_data.clear()
            st.rerun()

    # Generate real data based on time range
    metrics_data = get_real_metrics_data(time_range)

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
    """Show content analysis and speaker metrics"""
    st.markdown("### Content Analysis")

    # Get content data
    content_data = get_real_content_data()

    # Speaker activity
    st.markdown("#### Speaker Activity")

    speaker_stats = content_data.get('speaker_stats', [])

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("**Speaker Processing Volume (Validated/Processed Sermons)**")
        if speaker_stats:
            df_speakers = pd.DataFrame(speaker_stats)
            if 'speaker' in df_speakers.columns and 'sermons_processed' in df_speakers.columns:
                st.bar_chart(df_speakers.set_index('speaker')['sermons_processed'])
            else:
                st.info("No speaker data available with required columns")
        else:
            st.info("No speaker processing data available yet")

    with col2:
        st.markdown("**Top Speakers**")
        if speaker_stats:
            for speaker in speaker_stats[:5]:
                speaker_name = str(speaker.get('speaker', 'Unknown'))
                score = speaker.get('avg_quality_score')
                st.metric(
                    speaker_name,
                    f"{speaker['sermons_processed']} sermons",
                    (
                        f"{score:.1f} avg validation score"
                        if score is not None else None
                    ),
                )
        else:
            st.info("No speaker data available")

    # Event type distribution
    st.markdown("#### Event Type Distribution")

    event_data = content_data.get('event_types', [])

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Event Type Breakdown**")
        if event_data and isinstance(event_data, list):
            for event in event_data:
                if isinstance(event, dict):
                    percentage = event.get('percentage', 0.0)  # Default to 0 if missing
                    event_type = event.get('event_type', 'Unknown')
                    count = event.get('count', 0)
                    st.write(f"• {event_type}: {count} ({percentage:.1f}%)")
                else:
                    st.write(f"• Invalid event data: {event}")
        else:
            st.info("No event type data available yet")

    with col2:
        st.markdown("**Quality by Event Type**")
        scored_events = [
            event for event in (event_data or [])
            if isinstance(event, dict) and event.get('avg_quality') is not None
        ]
        if scored_events:
            for event in scored_events:
                success_rate = event.get('success_rate')
                st.metric(
                    str(event.get('event_type') or 'Unknown'),
                    f"{event['avg_quality']:.1f}/10",
                    (
                        f"{success_rate:.1f}% validated"
                        if success_rate is not None else None
                    ),
                )
        else:
            st.info("No validation data available yet")

    # Content quality trends
    st.markdown("#### Content Quality Trends")

    quality_data = content_data.get('quality_trends', [])

    if quality_data:
        df_quality = pd.DataFrame(quality_data)
        if (
            'date' in df_quality.columns
            and 'quality_score' in df_quality.columns
        ):
            st.line_chart(df_quality.set_index('date')['quality_score'])
        else:
            st.info("Quality trend data structure is incomplete")
    else:
        st.info(
            "No validation data from the last five weeks yet. "
            "Run validations to see quality trends here."
        )

def show_cost_tracking():
    """LLM API usage and cost analysis"""
    st.markdown("### Cost Tracking")

    # Cost summary
    cost_data = get_real_cost_data()

    # Current month summary
    st.markdown("#### Current Month Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total API Calls",
            f"{cost_data['total_calls']:,}",
            delta=_metric_delta(
                cost_data['total_calls'],
                f"{cost_data['calls_change']:+,} vs last month",
            ),
        )

    with col2:
        st.metric(
            "Total Tokens",
            f"{cost_data['total_tokens']:,}",
            delta=_metric_delta(
                cost_data['total_tokens'],
                f"{cost_data['tokens_change']:+,} vs last month",
            ),
        )

    with col3:
        st.metric(
            "Total Cost",
            f"${cost_data['total_cost']:.2f}",
            delta=_metric_delta(
                cost_data['total_cost'],
                f"${cost_data['cost_change']:+.2f} vs last month",
            ),
        )

    with col4:
        st.metric(
            "Avg Cost/Sermon",
            f"${cost_data['avg_cost_per_sermon']:.3f}",
            delta=_metric_delta(
                cost_data['avg_cost_per_sermon'],
                f"{cost_data['efficiency_change']:+.1f}% efficiency",
            ),
        )

    # Provider breakdown
    st.markdown("#### Provider Usage Breakdown")

    provider_data = cost_data['provider_breakdown']

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Usage by Provider**")
        for provider in provider_data:
            st.write(f"**{provider.get('name', 'Unknown')}**")
            st.write(f"• Calls: {provider.get('calls', 0):,}")
            st.write(f"• Cost: ${provider.get('cost', 0.0):.2f}")
            st.write(f"• Usage: {provider.get('percentage', 0.0):.1f}%")
            st.write("")

    with col2:
        st.markdown("**Cost Trends (Last 30 Days)**")

        # Get real cost trend data from database
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from ui.database import get_db

            db = get_db()
            usage_summary = db.get_llm_usage_summary(days=30)
            daily_costs = usage_summary.get('daily_costs', [])

            if daily_costs:
                df_costs = pd.DataFrame(daily_costs)
                if 'date' in df_costs.columns and 'daily_cost' in df_costs.columns:
                    df_costs['date'] = pd.to_datetime(df_costs['date'])
                    st.line_chart(df_costs.set_index('date')['daily_cost'])
                else:
                    st.info("No cost trend data available yet")
            else:
                st.info("No cost data recorded yet")

        except Exception:
            # Fallback to no data message
            st.info("Cost tracking not yet available")

    # Model usage details
    st.markdown("#### Model Usage Details")

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
        width='stretch'
    )

def show_performance_metrics():
    """System performance and optimization metrics"""
    st.markdown("### Performance Metrics")

    # Performance summary
    perf_data = get_real_performance_data()

    # System health
    st.markdown("#### System Health")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Avg Processing Time",
            f"{perf_data['avg_processing_time']:.1f} min",
            delta=_metric_delta(
                perf_data['avg_processing_time'],
                f"{perf_data['processing_time_change']:+.1f} min vs last week",
            ),
        )

    with col2:
        st.metric(
            "Success Rate",
            f"{perf_data['success_rate']:.1f}%",
            delta=_metric_delta(
                perf_data['success_rate'],
                f"{perf_data['success_rate_change']:+.1f}% vs last week",
            ),
        )

    with col3:
        st.metric(
            "Queue Length",
            f"{perf_data['queue_length']}",
            delta=_metric_delta(
                perf_data['queue_length'],
                f"{perf_data['queue_change']:+d} vs yesterday",
            ),
        )

    with col4:
        st.metric(
            "Error Rate",
            f"{perf_data['error_rate']:.1f}%",
            delta=_metric_delta(
                perf_data['error_rate'],
                f"{perf_data['error_rate_change']:+.1f}% vs last week",
            ),
        )

    # Performance charts
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Processing Time Distribution")

        df_times = _processing_time_distribution()
        if df_times is not None:
            st.bar_chart(df_times.set_index('time_bucket'))
        else:
            st.info("No processing time data available yet")

    with col2:
        st.markdown("#### Processing Steps Performance")

        step_data = perf_data.get('step_performance') or []
        if step_data:
            df_steps = pd.DataFrame(step_data)

            st.dataframe(
                df_steps,
                column_config={
                    "step": "Processing Step",
                    "avg_time": st.column_config.NumberColumn("Avg Time (s)", format="%.1f"),
                    "success_rate": st.column_config.NumberColumn(
                        "Success Rate", format="%.1f%%"
                    ),
                    "bottleneck_score": st.column_config.NumberColumn(
                        "Bottleneck Score", format="%.2f"
                    )
                },
                hide_index=True,
                width='stretch'
            )
        else:
            st.info("No step performance data available yet")

    # Resource usage
    st.markdown("#### Resource Usage")

    resource_data = perf_data['resource_usage']

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("CPU Usage", f"{resource_data.get('cpu_usage', 0):.1f}%")
        st.metric("Memory Usage", f"{resource_data.get('memory_usage', 0):.1f}%")

    with col2:
        st.metric("Disk Usage", f"{resource_data.get('disk_usage', 0):.1f}%")
        st.metric("Network I/O", f"{resource_data.get('network_io', 0):.1f} MB/s")

    with col3:
        st.metric("GPU Usage", f"{resource_data.get('gpu_usage', 0):.1f}%")
        st.metric("GPU Memory", f"{resource_data.get('gpu_memory', 0):.1f}%")

    # Optimization recommendations
    st.markdown("#### Optimization Recommendations")

    recommendations = perf_data['recommendations']

    for rec in recommendations:
        with st.expander(f"{rec['title']} ({rec['priority']} Priority)"):
            st.write(rec['description'])
            st.write(f"**Impact:** {rec['impact']}")
            st.write(f"**Effort:** {rec['effort']}")

def _metric_delta(base: float, delta: str) -> str | None:
    """Return the delta label only when the base metric has data"""
    if base == 0:
        return None
    return delta


def _period_delta(current: float, previous: float, fmt: str) -> str | None:
    """Build a comparison delta, or None when either period has no data"""
    if current == 0 or previous == 0:
        return None
    return fmt.format(current - previous)


def show_key_metrics(metrics_data):
    """Display key processing metrics"""
    st.markdown("#### Key Metrics")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Processed",
            f"{metrics_data['total_processed']:,}",
            delta=_period_delta(
                metrics_data['total_processed'],
                metrics_data['prev_total_processed'],
                "{:+,} vs previous period",
            ),
        )

    with col2:
        st.metric(
            "Success Rate",
            f"{metrics_data['success_rate']:.1f}%",
            delta=_period_delta(
                metrics_data['success_rate'],
                metrics_data['prev_success_rate'],
                "{:+.1f}% vs previous period",
            ),
        )

    with col3:
        st.metric(
            "Avg Processing Time",
            f"{metrics_data['avg_time']:.1f} min",
            delta=_period_delta(
                metrics_data['avg_time'],
                metrics_data['prev_avg_time'],
                "{:+.1f} min vs previous period",
            ),
        )

    with col4:
        st.metric(
            "Total Errors",
            f"{metrics_data['total_errors']:,}",
            delta=_period_delta(
                metrics_data['total_errors'],
                metrics_data['prev_total_errors'],
                "{:+,} vs previous period",
            ),
        )

def show_success_rate_chart(metrics_data):
    """Show success rate over time"""
    st.markdown("#### Success Rate Trend")

    if metrics_data.get('trend_data'):
        df = pd.DataFrame(metrics_data['trend_data'])
        if 'date' in df.columns and 'rate' in df.columns:
            st.line_chart(df.set_index('date'))
        else:
            st.info("Insufficient data for trend chart")
    else:
        st.info("No trend data available yet — data appears after multiple processing sessions")

def show_processing_volume_chart(metrics_data):
    """Show processing volume over time"""
    st.markdown("#### Processing Volume")

    if metrics_data.get('volume_data'):
        df = pd.DataFrame(metrics_data['volume_data'])
        if 'date' in df.columns and 'count' in df.columns:
            st.area_chart(df.set_index('date'))
        else:
            st.info("Insufficient data for volume chart")
    else:
        st.info("No volume data available yet — data appears after multiple processing sessions")

def show_error_types_chart(metrics_data):
    """Show error type distribution"""
    st.markdown("#### Error Types")

    if metrics_data.get('error_data'):
        df = pd.DataFrame(metrics_data['error_data'])
        if 'type' in df.columns and 'count' in df.columns:
            st.bar_chart(df.set_index('type'))
        else:
            st.info("Insufficient error data for chart")
    elif metrics_data.get('total_errors', 0) == 0:
        st.info("No errors recorded — great job!")
    else:
        st.info("No detailed error breakdown available yet")

def show_processing_time_trend(metrics_data):
    """Show processing time trend"""
    st.markdown("#### Processing Time Trend")

    if metrics_data.get('time_trend_data'):
        df = pd.DataFrame(metrics_data['time_trend_data'])
        if 'date' in df.columns and 'avg_time' in df.columns:
            st.line_chart(df.set_index('date'))
        else:
            st.info("Insufficient data for time trend chart")
    else:
        st.info("No processing time data available yet")

def _summarize_processing(processing_data, start_date, end_date):
    """Summarize processing records within a date range"""
    from datetime import datetime

    total = 0
    success = 0
    errors = 0
    times = []

    for item in processing_data:
        try:
            item_date = datetime.fromisoformat(item.get('timestamp', '2024-01-01'))
        except Exception:
            continue
        if start_date is not None and item_date < start_date:
            continue
        if item_date >= end_date:
            continue
        total += 1
        status = item.get('status')
        if status == 'completed':
            success += 1
        elif status == 'failed':
            errors += 1
        if item.get('duration'):
            try:
                duration_str = str(item.get('duration', '0'))
                if 'min' in duration_str:
                    times.append(float(duration_str.replace('min', '').strip()))
                elif 'sec' in duration_str:
                    times.append(float(duration_str.replace('sec', '').strip()) / 60)
            except Exception:
                continue

    avg_time = sum(times) / len(times) if times else 0.0
    success_rate = (success / total * 100) if total > 0 else 0.0

    return {
        'total': total,
        'success_rate': success_rate,
        'avg_time': avg_time,
        'errors': errors,
    }


def get_real_metrics_data(time_range):
    """Get real metrics data from database"""
    try:
        # Import database module
        import sys
        from datetime import datetime, timedelta
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ui.database import get_db

        db = get_db()
        processing_data = db.get_processing_status()

        end_date = datetime.now()
        period_days = {"Last 7 Days": 7, "Last 30 Days": 30, "Last 90 Days": 90}

        if time_range == "All Time":
            current = _summarize_processing(processing_data, None, end_date)
            return {
                'total_processed': current['total'],
                'prev_total_processed': 0,
                'success_rate': current['success_rate'],
                'prev_success_rate': 0,
                'avg_time': current['avg_time'],
                'prev_avg_time': 0,
                'total_errors': current['errors'],
                'prev_total_errors': 0,
            }

        days = period_days[time_range]
        start_date = end_date - timedelta(days=days)
        current = _summarize_processing(processing_data, start_date, end_date)
        previous = _summarize_processing(
            processing_data, start_date - timedelta(days=days), start_date
        )

        return {
            'total_processed': current['total'],
            'prev_total_processed': previous['total'],
            'success_rate': current['success_rate'],
            'prev_success_rate': previous['success_rate'],
            'avg_time': current['avg_time'],
            'prev_avg_time': previous['avg_time'],
            'total_errors': current['errors'],
            'prev_total_errors': previous['errors'],
        }

    except Exception:
        # Fallback to reasonable defaults if database fails
        return {
            'total_processed': 0,
            'prev_total_processed': 0,
            'success_rate': 0,
            'prev_success_rate': 0,
            'avg_time': 0,
            'prev_avg_time': 0,
            'total_errors': 0,
            'prev_total_errors': 0,
        }

def get_real_content_data():
    """Get real content analysis data from database and API"""
    try:
        # Import required modules
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ui.database import SermonRepository, get_db

        db = get_db()
        repo = SermonRepository(db)

        # Get processing status data
        processing_data = db.get_processing_status()

        # Get all validated/interacted sermons from database
        validated_sermon_ids = get_validated_sermon_ids(db)

        try:
            validation_results = db.get_validation_results()
        except Exception:
            validation_results = []
        result_by_sermon = {
            r['sermon_id']: r for r in validation_results
            if r.get('sermon_id') and isinstance(r.get('score'), (int, float))
        }

        all_sermons = repo.get_all_sermons()
        sermon_lookup = {s['id']: s for s in all_sermons}

        speaker_list = []
        event_list = []

        if not validated_sermon_ids:
            st.info("No validated or processed sermons found. Process some sermons first!")
            speaker_list = [{
                'speaker': 'System Processed' if processing_data else 'No Processing Data',
                'sermons_processed': len(processing_data) if processing_data else 0,
                'avg_quality_score': None,
                'total_downloads': 0,
                'total_listens': 0,
            }]
        else:
            speaker_counts: dict[str, int] = {}
            speaker_scores: dict[str, list[float]] = {}
            event_counts: dict[str, int] = {}
            event_scores: dict[str, list[float]] = {}
            event_valid: dict[str, list[bool]] = {}

            for sermon_id in validated_sermon_ids:
                sermon_data = sermon_lookup.get(sermon_id) or {}
                speaker = sermon_data.get('speaker') or 'Unknown Speaker'
                event_type = sermon_data.get('event_type') or 'Unknown Event'
                speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
                event_counts[event_type] = event_counts.get(event_type, 0) + 1

                result = result_by_sermon.get(sermon_id)
                if result:
                    speaker_scores.setdefault(speaker, []).append(result['score'])
                    event_scores.setdefault(event_type, []).append(result['score'])
                    event_valid.setdefault(event_type, []).append(bool(result.get('is_valid')))

            speaker_list = [
                {
                    'speaker': speaker,
                    'sermons_processed': count,
                    'avg_quality_score': _mean_score(speaker_scores.get(speaker)),
                    'total_downloads': 0,
                    'total_listens': 0,
                }
                for speaker, count in sorted(
                    speaker_counts.items(), key=lambda item: -item[1]
                )
            ]

            total_events = sum(event_counts.values())
            for event_type, count in event_counts.items():
                valid_flags = event_valid.get(event_type, [])
                event_list.append({
                    'event_type': event_type,
                    'count': count,
                    'percentage': (count / total_events * 100) if total_events else 0.0,
                    'avg_quality': _mean_score(event_scores.get(event_type)),
                    'success_rate': (
                        sum(1 for v in valid_flags if v) / len(valid_flags) * 100
                        if valid_flags else None
                    ),
                })
            event_list.sort(key=lambda item: -item['count'])

        return {
            'speaker_stats': speaker_list,
            'event_types': event_list,
            'quality_trends': _quality_trends(result_by_sermon),
        }

    except Exception as e:
        # Show the actual error for debugging
        st.error(f"ERROR in get_real_content_data: {str(e)}")
        st.write(f"Exception type: {type(e).__name__}")
        import traceback
        st.code(traceback.format_exc())

        # Return empty data if anything fails
        return {
            'speaker_stats': [],
            'event_types': [],
            'quality_trends': []
        }


def _mean_score(values):
    """Average of a score list rounded to 2dp, or None when there is no data"""
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _processing_time_distribution():
    """Bucket real recorded processing durations, or None when there is no data"""
    try:
        from database import get_db

        rows = get_db().get_processing_status()
    except Exception:
        return None

    minutes = []
    for item in rows:
        raw = item.get('duration')
        if not raw:
            continue
        try:
            if 'min' in str(raw):
                minutes.append(float(str(raw).replace('min', '').strip()))
            elif 'sec' in str(raw):
                minutes.append(float(str(raw).replace('sec', '').strip()) / 60)
        except ValueError:
            continue

    if not minutes:
        return None

    counts = [0, 0, 0, 0, 0]
    for value in minutes:
        if value <= 2:
            counts[0] += 1
        elif value <= 5:
            counts[1] += 1
        elif value <= 10:
            counts[2] += 1
        elif value <= 20:
            counts[3] += 1
        else:
            counts[4] += 1

    return pd.DataFrame({
        'time_bucket': ["0-2 min", "2-5 min", "5-10 min", "10-20 min", "20+ min"],
        'count': counts,
    })


def _quality_trends(result_by_sermon):
    """Weekly average validation scores over the last five weeks"""
    now = datetime.datetime.now()
    buckets: dict[int, list[float]] = {}
    for result in result_by_sermon.values():
        validated_at = _parse_timestamp(result.get('validated_at'))
        if validated_at is None:
            continue
        age_weeks = int((now - validated_at).days // 7)
        if 0 <= age_weeks < 5:
            buckets.setdefault(age_weeks, []).append(result['score'])

    trends = []
    for age_weeks in range(4, -1, -1):
        scores = buckets.get(age_weeks)
        if scores:
            trends.append({
                'date': (now - datetime.timedelta(weeks=age_weeks)).strftime('%Y-%m-%d'),
                'quality_score': round(sum(scores) / len(scores), 2),
            })
    return trends


def _parse_timestamp(value):
    """Parse a validation timestamp into a datetime, or None"""
    if isinstance(value, datetime.datetime):
        return value
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value))
    except ValueError:
        try:
            return datetime.datetime.strptime(str(value)[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None


def get_real_cost_data():
    """Get real cost tracking data from database"""
    try:
        # Import database module
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ui.database import get_db

        db = get_db()

        # Get current month data (30 days)
        usage_summary = db.get_llm_usage_summary(days=30)

        # Get last month data for comparison (30-60 days ago)
        previous_summary = db.get_llm_usage_summary(days=60)

        # Extract current data
        current = usage_summary.get('summary', {})
        providers = usage_summary.get('providers', [])
        models = usage_summary.get('models', [])

        # Calculate changes vs previous month
        # For simplicity, we'll approximate by comparing 30-day vs 60-day totals
        total_calls = current.get('total_calls', 0)
        total_tokens = current.get('total_tokens', 0)
        total_cost = current.get('total_cost', 0.0)

        # Previous period data (rough approximation)
        prev_total = previous_summary.get('summary', {})
        prev_calls = prev_total.get('total_calls', 0) - total_calls
        prev_tokens = prev_total.get('total_tokens', 0) - total_tokens
        prev_cost = prev_total.get('total_cost', 0.0) - total_cost

        calls_change = total_calls - prev_calls
        tokens_change = total_tokens - prev_tokens
        cost_change = total_cost - prev_cost

        # Calculate average cost per sermon
        processed_sermons = db.get_processing_status()
        sermon_count = len([s for s in processed_sermons if s.get('status') == 'completed'])
        avg_cost_per_sermon = total_cost / sermon_count if sermon_count > 0 else 0.0

        # Format provider breakdown for UI
        provider_breakdown = []
        for provider in providers:
            provider_breakdown.append({
                'name': provider.get('provider', 'Unknown'),
                'calls': provider.get('calls', 0),
                'cost': provider.get('cost', 0.0),
                'percentage': (
                    (provider.get('cost', 0.0) / total_cost * 100) if total_cost > 0 else 0.0
                )
            })

        # Format model usage for UI
        model_usage = []
        for model in models:
            model_usage.append({
                'provider': model.get('provider', 'Unknown'),
                'model': model.get('model', 'Unknown'),
                'calls': model.get('calls', 0),
                'tokens': model.get('tokens', 0),
                'cost': model.get('cost', 0.0),
                'avg_duration_ms': model.get('avg_duration_ms', 0.0)
            })

        # Calculate efficiency change (rough approximation)
        efficiency_change = 0.0
        if prev_cost > 0 and prev_calls > 0:
            current_efficiency = total_cost / total_calls if total_calls > 0 else 0
            prev_efficiency = prev_cost / prev_calls
            efficiency_change = (
                ((prev_efficiency - current_efficiency) / prev_efficiency * 100)
                if prev_efficiency > 0 else 0
            )

        return {
            'total_calls': total_calls,
            'calls_change': calls_change,
            'total_tokens': total_tokens,
            'tokens_change': tokens_change,
            'total_cost': total_cost,
            'cost_change': cost_change,
            'avg_cost_per_sermon': avg_cost_per_sermon,
            'efficiency_change': efficiency_change,
            'provider_breakdown': provider_breakdown,
            'model_usage': model_usage
        }

    except Exception:
        # Fallback to empty data if database isn't available or has no data yet
        return {
            'total_calls': 0,
            'calls_change': 0,
            'total_tokens': 0,
            'tokens_change': 0,
            'total_cost': 0.00,
            'cost_change': 0.00,
            'avg_cost_per_sermon': 0.000,
            'efficiency_change': 0.0,
            'provider_breakdown': [],
            'model_usage': []
        }

def get_real_performance_data():
    """Get real performance metrics using the new performance monitor"""
    try:
        # Use the new performance monitor
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from performance_monitor import get_comprehensive_performance_data

        return get_comprehensive_performance_data()

    except Exception:
        # Fallback to existing database-based metrics if performance monitor fails
        try:
            from ui.database import get_db

            db = get_db()
            processing_data = db.get_processing_status()

            # Calculate real metrics
            total_items = len(processing_data)
            success_count = sum(1 for item in processing_data if item.get('status') == 'completed')
            success_rate = (success_count / total_items * 100) if total_items > 0 else 0
            error_count = sum(1 for item in processing_data if item.get('status') == 'failed')
            error_rate = (error_count / total_items * 100) if total_items > 0 else 0

            # Calculate processing times
            times = []
            for item in processing_data:
                if item.get('duration'):
                    try:
                        duration_str = item.get('duration', '0')
                        if 'min' in duration_str:
                            times.append(float(duration_str.replace('min', '').strip()))
                        elif 'sec' in duration_str:
                            times.append(float(duration_str.replace('sec', '').strip()) / 60)
                    except Exception:
                        continue

            avg_processing_time = sum(times) / len(times) if times else 0

            return {
                'avg_processing_time': avg_processing_time,
                'processing_time_change': 0,
                'success_rate': success_rate,
                'success_rate_change': 0,
                'queue_length': 0,
                'queue_change': 0,
                'error_rate': error_rate,
                'error_rate_change': 0,
                'step_performance': [],
                'resource_usage': {},
                'recommendations': []
            }

        except Exception:
            return {
                'avg_processing_time': 0,
                'processing_time_change': 0,
                'success_rate': 0,
                'success_rate_change': 0,
                'queue_length': 0,
                'queue_change': 0,
                'error_rate': 0,
                'error_rate_change': 0,
                'step_performance': [],
                'resource_usage': {},
                'recommendations': []
            }
def get_validated_sermon_ids(db):
    """Get all sermon IDs that have been validated or processed"""
    validated_ids = set()

    try:
        # Use SermonRepository to get all sermons
        from ui.database import SermonRepository
        repo = SermonRepository()

        # Get completed/processed sermons
        completed_sermons = repo.get_all_sermons()
        for sermon in completed_sermons:
            if sermon.get('status') in ['completed', 'processed']:
                validated_ids.add(sermon.get('id'))

        # Get validated sermons and completed processing statuses via the
        # shared database handle so DATABASE_URL overrides are respected
        with db.get_connection() as conn:
            valid_rows = conn.execute(
                'SELECT DISTINCT sermon_id FROM validation_results WHERE is_valid = 1'
            ).fetchall()
            for row in valid_rows:
                validated_ids.add(row['sermon_id'])

            done_rows = conn.execute(
                'SELECT DISTINCT sermon_id FROM processing_status WHERE status = ?',
                ("completed",),
            ).fetchall()
            for row in done_rows:
                validated_ids.add(row['sermon_id'])

    except Exception as e:
        st.warning(f"Error accessing database: {str(e)}")

    return list(filter(None, validated_ids))


def show_sermonaudio_data_view():
    """Display SermonAudio analytics data in tables and charts"""
    st.markdown("#### SermonAudio Data Overview")

    # Show API limitation notice for views
    st.info("""
    **Note about View Data**: The SermonAudio API v2 does not provide play/view counts
    through the public API.
    View data shows as 0 due to this API limitation. Download counts and other metrics are accurate.
    """)

    # Initialize analytics if needed
    try:
        from ui.sermonaudio_analytics import SermonAudioAnalytics

        # Extract credentials from config
        api_key = st.session_state.config.get('api_key', '')
        broadcaster_id = st.session_state.config.get('broadcaster_id', '')

        # Initialize with real credentials
        analytics = SermonAudioAnalytics(
            api_key=api_key,
            broadcaster_id=broadcaster_id
        )

        # Show credential status
        if not api_key or not broadcaster_id:
            st.warning("SermonAudio credentials not configured. Data will be mock/demo only.")
        else:
            st.info(f"Connected to SermonAudio for broadcaster: {broadcaster_id[:8]}...")

        # Data filtering options
        st.markdown("#### Data Options")
        col1, col2, col3 = st.columns([2, 1, 1])

        # Initialize default values
        start_date = datetime.datetime.now().date() - datetime.timedelta(days=365)
        end_date = datetime.datetime.now().date()

        with col1:
            use_date_range = st.checkbox("Use Date Range", help="Filter sermons by date range")
            if use_date_range:
                col_start, col_end = st.columns(2)
                with col_start:
                    start_date = st.date_input(
                        "Start Date",
                        value=start_date,
                        help="Start date for sermon filtering"
                    )
                with col_end:
                    end_date = st.date_input(
                        "End Date",
                        value=end_date,
                        help="End date for sermon filtering"
                    )

        with col2:
            fetch_all = st.checkbox(
                "Fetch All Data",
                help="Fetch all available sermons (may take longer)",
                value=False
            )

        with col3:
            if fetch_all:
                st.info("May take longer")
            else:
                st.info("Limited to 100 sermons")

        # Load data button
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("Load Data", help="Load SermonAudio analytics data"):
                with st.spinner("Loading SermonAudio data..."):
                    # Prepare parameters
                    date_range = None
                    if use_date_range:
                        date_range = (
                            start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
                        )

                    # Load data with parameters
                    st.session_state.analytics_data = analytics.get_all_sermon_analytics(
                        date_range=date_range,
                        fetch_all=fetch_all
                    )
                    st.session_state.analytics_using_mock = analytics.using_mock_data

                    # Show success message with details
                    count = len(st.session_state.analytics_data)
                    date_info = f" from {start_date} to {end_date}" if use_date_range else ""
                    all_info = " (all available)" if fetch_all else ""
                    if analytics.using_mock_data:
                        st.warning(
                            "Could not load live data from SermonAudio. "
                            "Showing fallback data instead. Check your API credentials "
                            "and network connection."
                        )
                    else:
                        st.success(
                            f"Data loaded successfully! {count} sermons{date_info}{all_info}"
                        )

        with col2:
            if st.button("Export Data", help="Export data to CSV"):
                if st.session_state.get('analytics_data'):
                    import pandas as pd
                    df = pd.DataFrame(st.session_state.analytics_data)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"sermonaudio_analytics_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )

        with col3:
            if st.session_state.get('analytics_data'):
                st.info(f"Currently showing {len(st.session_state.analytics_data)} sermons")

        # Display data if available
        if st.session_state.get('analytics_data'):
            analytics_data = st.session_state.analytics_data

            if st.session_state.get('analytics_using_mock'):
                st.warning(
                    "Showing fallback data: the SermonAudio API request failed. "
                    "The metrics below are not live analytics."
                )

            # Summary metrics
            st.markdown("#### Key Metrics")
            col1, col2, col3, col4 = st.columns(4)

            total_sermons = len(analytics_data)
            total_views = sum(item.get('views', 0) for item in analytics_data)
            total_downloads = sum(item.get('downloads', 0) for item in analytics_data)
            total_likes = sum(item.get('likes', 0) for item in analytics_data)

            with col1:
                st.metric("Total Sermons", total_sermons)
            with col2:
                st.metric("Total Views", f"{total_views:,}")
            with col3:
                st.metric("Total Downloads", f"{total_downloads:,}")
            with col4:
                st.metric("Total Likes", f"{total_likes:,}")

            # Top performers
            st.markdown("#### Top Performing Sermons")

            # Sort by views
            sorted_by_views = sorted(
                analytics_data, key=lambda x: x.get('views', 0), reverse=True
            )[:10]

            import pandas as pd
            df = pd.DataFrame(sorted_by_views)

            # Select relevant columns for display
            display_columns = ['title', 'speaker', 'views', 'downloads', 'likes', 'published_date']
            available_columns = [col for col in display_columns if col in df.columns]

            if available_columns:
                st.dataframe(
                    df[available_columns],
                    width='stretch',
                    hide_index=True
                )
            else:
                st.dataframe(df, width='stretch', hide_index=True)

            # Charts
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("##### Views Distribution")
                if 'views' in df.columns:
                    st.bar_chart(df.set_index('title')['views'].head(10))
                else:
                    st.info("Views data not available")

            with col2:
                st.markdown("##### Downloads Distribution")
                if 'downloads' in df.columns:
                    st.bar_chart(df.set_index('title')['downloads'].head(10))
                else:
                    st.info("Downloads data not available")

            # Speaker analysis
            st.markdown("#### Speaker Analytics")

            # Group by speaker
            try:
                speaker_stats = {}
                for item in analytics_data:
                    # Extract speaker name safely - handle both string and dict cases
                    speaker_data = item.get('speaker', 'Unknown')
                    if isinstance(speaker_data, dict):
                        speaker = speaker_data.get('displayName', 'Unknown Speaker')
                    elif isinstance(speaker_data, str):
                        speaker = speaker_data
                    else:
                        speaker = str(speaker_data) if speaker_data else 'Unknown Speaker'

                    if speaker not in speaker_stats:
                        speaker_stats[speaker] = {
                            'sermons': 0,
                            'total_views': 0,
                            'total_downloads': 0,
                            'total_likes': 0
                        }

                    speaker_stats[speaker]['sermons'] += 1
                    speaker_stats[speaker]['total_views'] += item.get('views', 0)
                    speaker_stats[speaker]['total_downloads'] += item.get('downloads', 0)
                    speaker_stats[speaker]['total_likes'] += item.get('likes', 0)

                # Convert to DataFrame
                speaker_df = pd.DataFrame.from_dict(speaker_stats, orient='index')
                speaker_df = speaker_df.sort_values('total_views', ascending=False)

                st.dataframe(speaker_df, width='stretch')

            except Exception as e:
                st.error(f"Error processing speaker data: {e}")
                st.write("Raw speaker data for debugging:")
                sample_speakers = [item.get('speaker', 'N/A') for item in analytics_data[:3]]
                st.write(sample_speakers)

            # Raw data view
            with st.expander("View Raw Data"):
                st.dataframe(df, width='stretch', hide_index=True)

        else:
            st.info("No SermonAudio data loaded. Click 'Load Data' to fetch analytics.")
            st.markdown("""
            **Available Data:**
            - Sermon titles and descriptions
            - Speaker information
            - View counts and engagement metrics
            - Download statistics
            - Publication dates
            - Content analysis
            """)

    except Exception as e:
        st.error(f"Error loading SermonAudio data: {e}")
        st.info(
            "This feature requires proper SermonAudio API configuration "
            "or will show mock data for demonstration."
        )


if __name__ == "__main__":
    show_analytics()
