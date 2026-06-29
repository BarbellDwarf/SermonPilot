"""
Validation Page for SermonAudio Processor

Handles description validation, quality metrics, failed descriptions management,
and batch validation with detailed reporting.
"""

import csv
import datetime as dt
import io
import json

import streamlit as st

from ui.pages import jobs


def show_validation():
    """Main validation interface"""
    st.markdown('<div class="main-header">✅ Validation</div>', unsafe_allow_html=True)

    if not st.session_state.config:
        st.error("❌ Configuration not loaded. Please check the Settings page first.")
        return

    # Validation tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Quality Metrics",
        "❌ Failed Descriptions",
        "🔄 Batch Validation",
        "📈 Trends",
        "📝 Manual Review"
    ])

    with tab1:
        show_quality_metrics()

    with tab2:
        show_failed_descriptions()

    with tab3:
        show_batch_validation()

    with tab4:
        show_validation_trends()

    with tab5:
        show_manual_review()

def show_quality_metrics():
    """Display validation metrics and quality scores"""
    st.markdown("### 📊 Quality Metrics Overview")

    try:
        from ui_processor import get_processor
        processor = get_processor()

        # Get real validation results
        validation_results = processor.get_validation_results()

        if not validation_results:
            st.info("📊 No validation data available yet. Run some validations to see metrics here.")
            return

        # Calculate real metrics
        total_results = len(validation_results)
        valid_count = sum(1 for r in validation_results if r.get('is_valid', False))
        invalid_count = total_results - valid_count

        if total_results > 0:
            validation_rate = (valid_count / total_results) * 100
            avg_score = sum(r.get('score', 0) for r in validation_results) / total_results
        else:
            validation_rate = 0
            avg_score = 0

        # Key metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Overall Quality Score",
                f"{avg_score:.1f}/1.0",
                help="Average validation score across all tested sermons"
            )

        with col2:
            st.metric(
                "Validation Rate",
                f"{validation_rate:.1f}%",
                help="Percentage of sermons that passed validation"
            )

        with col3:
            st.metric(
                "Total Validated",
                total_results,
                help="Total number of sermons validated"
            )

        with col4:
            st.metric(
                "Failed Validation",
                invalid_count,
                help="Number of sermons that failed validation"
            )

        # Recent validation results
        st.markdown("#### 📋 Recent Validation Results")

        if validation_results:
            # Show most recent results
            recent_results = validation_results[-10:] if len(validation_results) > 10 else validation_results

            results_data = []
            for result in recent_results:
                results_data.append({
                    'Sermon ID': result.get('sermon_id', 'Unknown'),
                    'Status': '✅ Pass' if result.get('is_valid', False) else '❌ Fail',
                    'Score': f"{result.get('score', 0):.2f}/1.0",
                    'Reason': result.get('reason', 'No reason provided')[:50] + '...' if len(result.get('reason', '')) > 50 else result.get('reason', 'No reason provided'),
                    'Validated': result.get('validated_at', 'Unknown')[:10] if result.get('validated_at') else 'Unknown'
                })

            import pandas as pd
            df_results = pd.DataFrame(results_data)

            st.dataframe(
                df_results,
                width='stretch',
                hide_index=True
            )
        else:
            st.info("No validation results to display")

    except Exception as e:
        st.error(f"❌ Error loading validation metrics: {e}")
        st.info("📊 No validation data available. Run some validations to see metrics here.")

def show_failed_descriptions():
    """Show descriptions that failed validation"""
    st.markdown("### ❌ Failed Descriptions")

    try:
        from ui_processor import get_processor
        processor = get_processor()

        # Get real failed validation results
        all_results = processor.get_validation_results()
        failed_results = [r for r in all_results if not r.get('is_valid', True)]

        if not failed_results:
            st.success("🎉 No failed descriptions found! All validated sermons passed.")
            return

        # Summary stats
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Failed", len(failed_results))

        with col2:
            # Count high priority (very low scores)
            high_priority = sum(1 for r in failed_results if r.get('score', 1.0) < 0.4)
            st.metric("High Priority", high_priority)

        with col3:
            # Check if any have been marked for regeneration (this would need to be tracked)
            st.metric("Available", len(failed_results))

        # Filter options
        col1, col2, col3 = st.columns(3)

        with col1:
            priority_filter = st.selectbox(
                "Filter by Priority",
                options=["All", "High Priority (<0.4)", "Medium Priority (0.4-0.6)", "Low Priority (>0.6)"]
            )

        with col2:
            # Get unique sermon IDs for filtering (speaker info may not be available)
            sermon_ids = list(set(r.get('sermon_id', 'Unknown') for r in failed_results))
            sermon_filter = st.selectbox(
                "Filter by Sermon ID",
                options=["All"] + sermon_ids[:20]  # Limit to first 20 for UI performance
            )

        with col3:
            score_filter = st.selectbox(
                "Filter by Score Range",
                options=["All", "Very Low (0.0-0.2)", "Low (0.2-0.4)", "Medium (0.4-0.6)", "High (0.6-0.8)"]
            )

        # Apply filters
        filtered_results = failed_results.copy()

        if priority_filter == "High Priority (<0.4)":
            filtered_results = [r for r in filtered_results if r.get('score', 1.0) < 0.4]
        elif priority_filter == "Medium Priority (0.4-0.6)":
            filtered_results = [r for r in filtered_results if 0.4 <= r.get('score', 1.0) < 0.6]
        elif priority_filter == "Low Priority (>0.6)":
            filtered_results = [r for r in filtered_results if r.get('score', 1.0) >= 0.6]

        if sermon_filter != "All":
            filtered_results = [r for r in filtered_results if r.get('sermon_id') == sermon_filter]

        if score_filter == "Very Low (0.0-0.2)":
            filtered_results = [r for r in filtered_results if 0.0 <= r.get('score', 1.0) < 0.2]
        elif score_filter == "Low (0.2-0.4)":
            filtered_results = [r for r in filtered_results if 0.2 <= r.get('score', 1.0) < 0.4]
        elif score_filter == "Medium (0.4-0.6)":
            filtered_results = [r for r in filtered_results if 0.4 <= r.get('score', 1.0) < 0.6]
        elif score_filter == "High (0.6-0.8)":
            filtered_results = [r for r in filtered_results if 0.6 <= r.get('score', 1.0) < 0.8]

        # Display failed descriptions
        st.markdown("#### 📋 Failed Descriptions List")

        if not filtered_results:
            st.info("No failed descriptions match the current filters.")
            return

        for i, result in enumerate(filtered_results[:10]):  # Show first 10 items
            sermon_id = result.get('sermon_id', 'Unknown')
            score = result.get('score', 0.0)
            reason = result.get('reason', 'No reason provided')

            priority = "🔴 High" if score < 0.4 else "🟡 Medium" if score < 0.6 else "🟠 Low"

            with st.expander(f"{priority} - Sermon {sermon_id} (Score: {score:.2f}/1.0)"):

                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown("**Validation Result:**")
                    st.write(reason)

                    # Show additional details if available
                    if result.get('criteria_failed'):
                        st.markdown("**Failed Criteria:**")
                        for criterion in result.get('criteria_failed', []):
                            st.write(f"• {criterion}")

                with col2:
                    st.markdown("**Details:**")
                    st.write(f"**Sermon ID:** {sermon_id}")
                    st.write(f"**Score:** {score:.2f}/1.0")
                    st.write(f"**Validated:** {result.get('validated_at', 'Unknown')[:10] if result.get('validated_at') else 'Unknown'}")

                    # Action buttons
                    col_a, col_b = st.columns(2)

                    with col_a:
                        if st.button("🔄 Regenerate", key=f"regen_{sermon_id}_{i}"):
                            regenerate_description(sermon_id)

                    with col_b:
                        if st.button("👤 Manual Review", key=f"manual_{sermon_id}_{i}"):
                            mark_for_manual_review(sermon_id)

        if len(filtered_results) > 10:
            st.info(f"Showing first 10 of {len(filtered_results)} failed descriptions. Use filters to narrow down results.")

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

    except Exception as e:
        st.error(f"❌ Error loading failed descriptions: {e}")
        st.info("No failed descriptions data available.")

def show_batch_validation():
    """Real batch validation interface with progress tracking"""
    st.markdown("### 🔄 Batch Validation")

    # Validation scope selection
    st.markdown("#### 📋 Select Validation Scope")

    col1, col2 = st.columns(2)

    with col1:
        validation_scope = st.selectbox(
            "Validation Scope",
            ["Recent Sermons (Last 30 days)", "All Processed Sermons", "Specific Sermon IDs", "Failed Descriptions Only"],
            key="validation_scope"
        )

    with col2:
        if validation_scope == "Recent Sermons (Last 30 days)":
            max_sermons = st.number_input("Max Sermons", 1, 1000, 50)
        elif validation_scope == "Specific Sermon IDs":
            sermon_ids_input = st.text_area(
                "Sermon IDs (one per line or comma-separated)",
                placeholder="1234567890123\n2345678901234\n...",
                height=100
            )

    # Validation options
    st.markdown("#### ⚙️ Validation Options")

    col1, col2, col3 = st.columns(3)

    with col1:
        regenerate_failed = st.checkbox(
            "Regenerate Failed Descriptions",
            value=False,
            help="Automatically regenerate descriptions that fail validation"
        )

    with col2:
        dry_run = st.checkbox(
            "Dry Run Mode",
            value=True,
            help="Test validation without making changes"
        )

    with col3:
        detailed_report = st.checkbox(
            "Detailed Report",
            value=True,
            help="Generate detailed validation report"
        )

    # Start validation button
    if st.button("🚀 Start Validation", type="primary", width='stretch'):
        start_background_validation(validation_scope, {
            'regenerate_failed': regenerate_failed,
            'dry_run': dry_run,
            'detailed_report': detailed_report,
            'max_sermons': locals().get('max_sermons', 50),
            'sermon_ids_input': locals().get('sermon_ids_input', '')
        })

    # Show current validation status
    st.markdown("#### 📊 Current Validation Status")
    show_current_validation_status()


def start_background_validation(scope: str, options: dict):
    """Start background validation process using job queue"""
    try:
        from job_queue import JobType, get_job_queue

        # Determine sermon IDs to validate
        sermon_ids = []

        if scope == "Specific Sermon IDs":
            ids_input = options.get('sermon_ids_input', '').strip()
            if ids_input:
                # Parse comma-separated or line-separated IDs
                if ',' in ids_input:
                    sermon_ids = [id.strip() for id in ids_input.split(',') if id.strip()]
                else:
                    sermon_ids = [id.strip() for id in ids_input.split('\n') if id.strip()]

            if not sermon_ids:
                st.error("❌ Please provide sermon IDs to validate")
                return

        elif scope == "Recent Sermons (Last 30 days)":
            # Get recent sermons from SermonAudio API
            try:
                import sermon_updater

                # Get recent sermons using the API
                end_date = dt.datetime.now()
                start_date = end_date - dt.timedelta(days=30)

                max_sermons = options.get('max_sermons', 50)

                # Use get_sermons_in_date_range to get real sermon data
                sermons = sermon_updater.get_sermons_in_date_range(
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d')
                )

                # Apply limit after fetching
                if len(sermons) > max_sermons:
                    sermons = sermons[:max_sermons]

                sermon_ids = [str(sermon['sermonID']) for sermon in sermons if sermon.get('sermonID')]

                if not sermon_ids:
                    st.info("✅ No recent sermons found!")
                    return

            except Exception as e:
                st.error(f"❌ Failed to fetch recent sermons: {e}")
                return

        elif scope == "All Processed Sermons":
            # Scan the processed_sermons directory for real sermon IDs
            try:
                from pathlib import Path

                config = st.session_state.get('config', {})
                output_dir = config.get('output_directory', 'processed_sermons')
                processed_dir = Path(output_dir)

                if processed_dir.exists():
                    sermon_dirs = [d.name for d in processed_dir.iterdir() if d.is_dir()]
                    sermon_ids = sermon_dirs

                    if not sermon_ids:
                        st.info("✅ No processed sermons found in local directory!")
                        return
                else:
                    st.error(f"❌ Processed sermons directory not found: {processed_dir}")
                    return

            except Exception as e:
                st.error(f"❌ Failed to scan processed sermons: {e}")
                return

        elif scope == "Failed Descriptions Only":
            # Get previously failed validations from database
            try:
                from ui_processor import get_processor
                processor = get_processor()
                failed_results = [r for r in processor.get_validation_results() if not r['is_valid']]
                sermon_ids = [r['sermon_id'] for r in failed_results]

                if not sermon_ids:
                    st.info("✅ No previously failed descriptions found!")
                    return
            except Exception as e:
                st.error(f"❌ Failed to get failed descriptions: {e}")
                return

        if not sermon_ids:
            st.error("❌ No sermons found for validation")
            return

        # Create validation job
        job_queue = get_job_queue()

        job_title = f"Validation: {scope}"
        if scope == "Specific Sermon IDs":
            job_description = f"Validating {len(sermon_ids)} specific sermons"
        else:
            job_description = f"Validating {len(sermon_ids)} sermons from {scope.lower()}"

        # Get current configuration from session state
        config = st.session_state.get('config', {})
        if not config:
            st.error("❌ No configuration loaded. Please check the Settings page first.")
            st.info("💡 Try going to Settings → Configuration and saving your settings, then return to this page.")
            return

        # Validate that essential config fields are present
        required_fields = ['api_key', 'broadcaster_id']
        missing_fields = [field for field in required_fields if not config.get(field)]
        if missing_fields:
            st.error(f"❌ Configuration is missing required fields: {', '.join(missing_fields)}")
            st.info("Please go to Settings → Configuration and ensure all required fields are filled out.")
            return

        job_id = job_queue.add_job(
            job_type=JobType.VALIDATION,
            title=job_title,
            description=job_description,
            parameters={
                'sermon_ids': sermon_ids,
                'scope': scope,
                'options': options,
                'config': config  # Pass configuration to the job
            },
            priority=7  # High priority for validation jobs
        )

        st.success(f"✅ Validation job created! Job ID: {job_id[:8]}")
        st.info(f"🔍 Validating {len(sermon_ids)} sermons in the background. You can monitor progress on the Jobs page.")

        # Add button to go to jobs page
        if st.button("📊 View Job Progress", type="secondary"):
            st.switch_page(jobs)

    except Exception as e:
        st.error(f"❌ Failed to start validation job: {e}")


def start_real_validation(scope: str, options: dict):
    """Start real validation process with progress tracking (DEPRECATED - use start_background_validation)"""
    st.warning("⚠️ This function is deprecated. Validation now runs in the background. Redirecting to background validation...")
    start_background_validation(scope, options)


def show_current_validation_status():
    """Show current validation status and recent results"""
    try:
        from ui_processor import get_processor

        processor = get_processor()

        # Show processing status
        validation_status = processor.get_processing_status(operation='validation')

        if validation_status:
            st.markdown("##### 🔄 Active Validations")

            for status in validation_status[:5]:  # Show recent 5
                col1, col2, col3, col4 = st.columns([2, 1, 2, 2])

                with col1:
                    st.text(f"Sermon {status['sermon_id']}")

                with col2:
                    status_icon = {
                        'processing': '🟡',
                        'completed': '🟢',
                        'failed': '🔴',
                        'starting': '🔵'
                    }.get(status['status'], '⚪')
                    st.text(f"{status_icon} {status['status']}")

                with col3:
                    if status['status'] == 'processing':
                        st.progress(status['progress'] / 100.0)
                    else:
                        st.text(f"{status['progress']:.1f}%")

                with col4:
                    st.text(status['message'] or '')

        # Show recent validation results if available
        if 'last_validation_results' in st.session_state:
            st.markdown("##### 📊 Latest Validation Results")
            results = st.session_state['last_validation_results']

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Validated", results['total'])
            with col2:
                st.metric("Valid", results['valid'], f"{results['valid']/results['total']*100:.1f}%")
            with col3:
                st.metric("Invalid", results['invalid'], f"{results['invalid']/results['total']*100:.1f}%")
            with col4:
                st.metric("Errors", results['errors'])

            # Show detailed results
            if results.get('details'):
                st.markdown("##### 📋 Detailed Results")

                details_df = []
                for detail in results['details']:
                    details_df.append({
                        'Sermon ID': detail['sermon_id'],
                        'Status': '✅ Valid' if detail.get('is_valid') else '❌ Invalid' if 'is_valid' in detail else '⚠️ Error',
                        'Score': f"{detail.get('score', 0):.2f}" if 'score' in detail else 'N/A',
                        'Reason': detail.get('reason', detail.get('error', ''))
                    })

                if details_df:
                    import pandas as pd
                    df = pd.DataFrame(details_df)
                    st.dataframe(df, width='stretch')

                    # Clear results button
                    if st.button("🗑️ Clear Results"):
                        del st.session_state['last_validation_results']
                        st.rerun()

    except Exception as e:
        st.warning(f"Could not load validation status: {e}")

def show_validation_trends():
    """Show validation trends and historical data"""
    st.markdown("### 📈 Validation Trends")

    try:
        from ui_processor import get_processor
        processor = get_processor()

        # Get real validation results
        all_results = processor.get_validation_results()

        if not all_results:
            st.info("📈 No validation trend data available yet. Run validations over time to see trends here.")
            return

        # Time period selector
        period = st.selectbox(
            "Time Period",
            options=["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"]
        )

        # Filter results by period if we have datetime data
        filtered_results = all_results  # For now, show all results

        if filtered_results:
            # Basic statistics
            total_count = len(filtered_results)
            valid_count = sum(1 for r in filtered_results if r.get('is_valid', False))
            invalid_count = total_count - valid_count

            if total_count > 0:
                validation_rate = (valid_count / total_count) * 100
                avg_score = sum(r.get('score', 0) for r in filtered_results) / total_count
            else:
                validation_rate = 0
                avg_score = 0

            # Display summary statistics
            st.markdown("#### 📊 Statistical Summary")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Validations", total_count)
                st.metric("Mean Quality Score", f"{avg_score:.2f}")

            with col2:
                st.metric("Valid Descriptions", valid_count)
                st.metric("Validation Rate", f"{validation_rate:.1f}%")

            with col3:
                st.metric("Invalid Descriptions", invalid_count)
                if filtered_results:
                    max_score = max(r.get('score', 0) for r in filtered_results)
                    st.metric("Best Score", f"{max_score:.2f}")

            with col4:
                needs_regen = sum(1 for r in filtered_results if r.get('score', 1.0) < 0.6)
                st.metric("Needs Regeneration", needs_regen)
                if filtered_results:
                    min_score = min(r.get('score', 1.0) for r in filtered_results)
                    st.metric("Lowest Score", f"{min_score:.2f}")

            # Score distribution
            st.markdown("#### 📊 Score Distribution")

            scores = [r.get('score', 0) for r in filtered_results]

            if scores:
                # Create score ranges
                excellent = sum(1 for s in scores if s >= 0.8)
                good = sum(1 for s in scores if 0.6 <= s < 0.8)
                fair = sum(1 for s in scores if 0.4 <= s < 0.6)
                poor = sum(1 for s in scores if s < 0.4)

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("🟢 Excellent (≥0.8)", excellent, f"{excellent/total_count*100:.1f}%")

                with col2:
                    st.metric("🟡 Good (0.6-0.8)", good, f"{good/total_count*100:.1f}%")

                with col3:
                    st.metric("🟠 Fair (0.4-0.6)", fair, f"{fair/total_count*100:.1f}%")

                with col4:
                    st.metric("🔴 Poor (<0.4)", poor, f"{poor/total_count*100:.1f}%")

                # Show recent validation activity
                st.markdown("#### 📋 Recent Validation Activity")

                # Show last 20 validations
                recent_validations = filtered_results[-20:] if len(filtered_results) > 20 else filtered_results

                activity_data = []
                for result in recent_validations:
                    activity_data.append({
                        'Sermon ID': result.get('sermon_id', 'Unknown'),
                        'Score': f"{result.get('score', 0):.2f}",
                        'Status': '✅ Valid' if result.get('is_valid', False) else '❌ Invalid',
                        'Date': result.get('validated_at', 'Unknown')[:10] if result.get('validated_at') else 'Unknown'
                    })

                if activity_data:
                    import pandas as pd
                    df_activity = pd.DataFrame(activity_data)
                    st.dataframe(df_activity, width='stretch', hide_index=True)
            else:
                st.info("No score data available for analysis")
        else:
            st.info(f"No validation data available for {period}")

    except Exception as e:
        st.error(f"❌ Error loading validation trends: {e}")
        st.info("📈 No trend data available. Run validations over time to see trends here.")

def regenerate_description(sermon_id):
    """Submit a regeneration job for a specific sermon"""
    try:
        from job_queue import JobType, get_job_queue
        config = st.session_state.get('config', {})
        if not config:
            st.error("❌ No configuration loaded")
            return
        job_queue = get_job_queue()
        job_id = job_queue.add_job(
            job_type=JobType.METADATA_UPDATE,
            title=f"Regenerate: {sermon_id}",
            description=f"Regenerating description for sermon {sermon_id}",
            parameters={
                'sermon_ids': [sermon_id],
                'actions': {'generate_description': True, 'generate_hashtags': True},
                'config': config
            },
            priority=7
        )
        st.success(f"✅ Regeneration job created: {job_id[:8]}")
    except Exception as e:
        st.error(f"❌ Failed to create regeneration job: {e}")

def mark_for_manual_review(sermon_id):
    """Mark sermon for manual review and navigate to library"""
    try:
        from database import SermonRepository, get_db
        db = get_db()
        db.add_manual_review(sermon_id, reason="Marked from validation page")
        st.success(f"📝 Sermon {sermon_id} added to manual review queue")
        # Store selected sermon and navigate to library
        repo = SermonRepository()
        sermon = repo.get_sermon(sermon_id)
        if sermon:
            st.session_state.selected_sermon = sermon
        st.switch_page("ui/ui_pages/library.py")
    except Exception as e:
        st.error(f"❌ Error marking for manual review: {e}")

def regenerate_high_priority():
    """Submit a batch regeneration job for all high-priority failures"""
    try:
        from job_queue import JobType, get_job_queue
        from ui_processor import get_processor
        processor = get_processor()
        all_results = processor.get_validation_results()
        failed_ids = [
            r['sermon_id'] for r in all_results
            if not r.get('is_valid', True) and r.get('score', 1.0) < 0.4
        ]
        if not failed_ids:
            st.info("No high-priority failures found")
            return
        config = st.session_state.get('config', {})
        if not config:
            st.error("❌ No configuration loaded")
            return
        job_queue = get_job_queue()
        job_id = job_queue.add_job(
            job_type=JobType.METADATA_UPDATE,
            title=f"Bulk Regeneration: {len(failed_ids)} sermons",
            description=f"Regenerating {len(failed_ids)} high-priority failed descriptions",
            parameters={
                'sermon_ids': failed_ids,
                'actions': {'generate_description': True, 'generate_hashtags': True},
                'config': config
            },
            priority=8
        )
        st.success(f"✅ Bulk regeneration job created: {job_id[:8]} for {len(failed_ids)} sermons")
    except Exception as e:
        st.error(f"❌ Failed to create bulk regeneration job: {e}")

def export_failed_list():
    """Export list of failed descriptions as CSV"""
    try:
        from ui_processor import get_processor
        processor = get_processor()
        all_results = processor.get_validation_results()
        failed = [r for r in all_results if not r.get('is_valid', True)]
        if not failed:
            st.info("No failed descriptions to export")
            return
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Sermon ID', 'Score', 'Reason', 'Validated At'])
        for r in failed:
            writer.writerow([
                r.get('sermon_id', ''),
                f"{r.get('score', 0):.2f}",
                r.get('reason', ''),
                str(r.get('validated_at', ''))[:10]
            ])
        st.download_button(
            "📥 Download CSV",
            data=output.getvalue(),
            file_name=f"failed_descriptions_{dt.datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            key="dl_failed_csv"
        )
    except Exception as e:
        st.error(f"❌ Error exporting failed list: {e}")

def generate_validation_report():
    """Generate a validation report as downloadable JSON"""
    try:
        from ui_processor import get_processor
        processor = get_processor()
        all_results = processor.get_validation_results()
        if not all_results:
            st.info("No validation data to report")
            return
        total = len(all_results)
        valid = sum(1 for r in all_results if r.get('is_valid', False))
        invalid = total - valid
        scores = [r.get('score', 0) for r in all_results]
        avg_score = sum(scores) / total if total else 0
        excellent = sum(1 for s in scores if s >= 0.8)
        good = sum(1 for s in scores if 0.6 <= s < 0.8)
        fair = sum(1 for s in scores if 0.4 <= s < 0.6)
        poor = sum(1 for s in scores if s < 0.4)
        report = {
            'generated_at': str(dt.datetime.now()),
            'summary': {
                'total_validated': total,
                'valid': valid,
                'invalid': invalid,
                'validation_rate': round(valid / total * 100, 1) if total else 0,
                'average_score': round(avg_score, 2)
            },
            'score_distribution': {
                'excellent_ge_0.8': excellent,
                'good_0.6_0.8': good,
                'fair_0.4_0.6': fair,
                'poor_lt_0.4': poor
            }
        }
        report_json = json.dumps(report, indent=2)
        st.download_button(
            "📥 Download Report (JSON)",
            data=report_json,
            file_name=f"validation_report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key="dl_report"
        )
        st.json(report)
    except Exception as e:
        st.error(f"❌ Error generating report: {e}")

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
    st.text("Validating: 15/50 sermons completed")

    # Mock completion
    if progress >= 1.0:
        st.session_state.batch_validation_running = False
        st.success("✅ Batch validation completed!")

def show_manual_review():
    """Display and manage the manual review queue"""
    st.markdown("### 📝 Manual Review Queue")

    try:
        from database import get_db
        db = get_db()

        status_filter = st.selectbox(
            "Filter by status",
            ["All", "pending", "reviewed"],
            key="manual_review_status"
        )

        reviews = db.get_manual_reviews(
            status=None if status_filter == "All" else status_filter
        )

        if not reviews:
            st.info("No sermons in the manual review queue.")
            st.markdown("""
            **How to add to manual review:**
            1. Go to **Failed Descriptions** tab
            2. Click **Manual Review** on any failed sermon
            3. The sermon will appear here and open in the Library for editing
            """)
            return

        for review in reviews:
            with st.expander(
                f"{'🟡' if review['status'] == 'pending' else '🟢'} "
                f"Sermon {review['sermon_id']} — {review['status'].title()}"
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Reason:** {review.get('reason', 'No reason')}")
                    st.markdown(f"**Created:** {review.get('created_at', 'Unknown')[:19]}")
                    if review.get('notes'):
                        st.markdown(f"**Review Notes:** {review['notes']}")
                with col2:
                    sid = review['sermon_id']
                    st.markdown("**Actions:**")
                    if st.button("🔍 Open in Library", key=f"open_review_{review['id']}"):
                        from database import SermonRepository
                        repo = SermonRepository()
                        sermon = repo.get_sermon(sid)
                        if sermon:
                            st.session_state.selected_sermon = sermon
                        st.switch_page("ui/ui_pages/library.py")
                    if review['status'] == 'pending':
                        if st.button("✅ Mark Reviewed", key=f"mark_reviewed_{review['id']}"):
                            db.update_manual_review_status(review['id'], 'reviewed')
                            st.rerun()

    except Exception as e:
        st.error(f"❌ Error loading manual review queue: {e}")
        st.info("Manual review queue requires database setup.")


if __name__ == "__main__":
    show_validation()
