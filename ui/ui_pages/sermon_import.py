import sys
from pathlib import Path

import streamlit as st


def show_sermon_import():
    st.markdown('<div class="main-header">📥 Import Sermons</div>', unsafe_allow_html=True)
    st.markdown("Scan the processed_sermons folder and import any missing sermons into the database.")

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from sermon_importer import get_import_status, import_missing_sermons, import_single_sermon

        status = get_import_status()

        st.markdown("#### 📊 Current Status")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Sermons in Folder", status['total_in_folder'])
        with col2:
            st.metric("In Database", status['in_database'])
        with col3:
            st.metric("Missing from Database", status['missing_from_database'])
        st.markdown(f"**Folder Path:** `{status['folder_path']}`")

        if status['missing_sermon_ids']:
            st.markdown("#### 🔍 Missing Sermons (Preview)")
            missing_count = status['missing_from_database']
            preview_sermons = status['missing_sermon_ids']

            if missing_count > 10:
                st.info(f"Showing first 10 of {missing_count} missing sermons:")

            for sermon_id in preview_sermons:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"📄 Sermon ID: `{sermon_id}`")
                with col2:
                    if st.button("Import", key=f"import_single_{sermon_id}"):
                        with st.spinner(f"Importing sermon {sermon_id}..."):
                            success = import_single_sermon(sermon_id)
                            if success:
                                st.success(f"✅ Successfully imported sermon {sermon_id}")
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to import sermon {sermon_id}")

            st.divider()
            st.markdown("#### 🚀 Bulk Import")
            col1, col2 = st.columns(2)

            with col1:
                if st.button("📥 Import All Missing Sermons", type="primary"):
                    if status['missing_from_database'] > 0:
                        try:
                            from job_queue import JobType, get_job_queue
                            job_queue = get_job_queue()
                            config = st.session_state.get('config', {})
                            processed_sermons_dir = config.get('output_directory', 'processed_sermons')

                            job_id = job_queue.add_job(
                                job_type=JobType.SERMON_IMPORT,
                                title="Bulk Sermon Import",
                                description=f"Importing {status['missing_from_database']} missing sermons from processed_sermons folder",
                                parameters={
                                    'processed_sermons_dir': processed_sermons_dir,
                                    'force_reimport': False
                                },
                                priority=6
                            )

                            st.success(f"✅ Import job started! Job ID: {job_id[:8]}")
                            st.info(f"📥 Importing {status['missing_from_database']} sermons in the background. Monitor progress on the Jobs page.")

                            if st.button("📊 View Job Progress", type="secondary"):
                                st.switch_page("jobs")

                        except Exception as e:
                            st.error(f"❌ Failed to start import job: {e}")
                            with st.spinner(f"Importing {status['missing_from_database']} sermons..."):
                                successful, failed, failed_ids = import_missing_sermons()
                                if successful > 0:
                                    st.success(f"✅ Successfully imported {successful} sermons!")
                                if failed > 0:
                                    st.error(f"❌ Failed to import {failed} sermons")
                                    if failed_ids:
                                        st.write("Failed sermon IDs:")
                                        for failed_id in failed_ids[:5]:
                                            st.write(f"• {failed_id}")
                                        if len(failed_ids) > 5:
                                            st.write(f"• ... and {len(failed_ids) - 5} more")
                                st.rerun()
                    else:
                        st.info("No missing sermons to import")

            with col2:
                st.markdown("**🔄 Force Re-import Options**")
                force_refresh_api = st.checkbox("Refresh API metadata", value=False, help="Re-fetch sermon metadata from SermonAudio API")

                if st.button("🔄 Force Re-import All Sermons", type="secondary"):
                    if st.session_state.get('confirm_reimport', False):
                        try:
                            from job_queue import JobType, get_job_queue
                            job_queue = get_job_queue()
                            config = st.session_state.get('config', {})
                            processed_sermons_dir = config.get('output_directory', 'processed_sermons')

                            job_id = job_queue.add_job(
                                job_type=JobType.SERMON_IMPORT,
                                title="Force Re-import All Sermons",
                                description=f"Re-importing all {status['total_in_folder']} sermons with fresh API data",
                                parameters={
                                    'processed_sermons_dir': processed_sermons_dir,
                                    'force_reimport': True,
                                    'refresh_api_data': force_refresh_api
                                },
                                priority=5
                            )

                            st.success(f"✅ Force re-import job started! Job ID: {job_id[:8]}")
                            st.info(f"🔄 Re-importing all {status['total_in_folder']} sermons in the background. Monitor progress on the Jobs page.")
                            st.session_state.confirm_reimport = False
                        except Exception as e:
                            st.error(f"❌ Failed to start re-import job: {e}")
                    else:
                        st.warning("⚠️ This will re-import ALL sermons and may take a long time. Click again to confirm.")
                        st.session_state.confirm_reimport = True
        else:
            st.success("✅ All sermons in the processed_sermons folder are already in the database!")
            if st.button("🔄 Refresh Status"):
                st.rerun()

        st.markdown("#### ℹ️ How It Works")
        with st.expander("📚 Import Process Details"):
            st.markdown("""
            **The import process will:**

            1. **Scan the processed_sermons folder** for directories with numeric names (sermon IDs)
            2. **Check each sermon ID** against the database to see if it already exists
            3. **Extract metadata** from files in each sermon directory
            4. **Create database records** with extracted metadata and file paths
            5. **Preserve all existing data** - only adds missing sermons, never overwrites

            **Safe Operation:**
            - Only imports sermons that don't exist in the database
            - Does not modify or overwrite existing database entries
            - Gracefully handles missing files or incomplete data
            - Logs all actions for troubleshooting
            """)

    except ImportError as e:
        st.error(f"❌ Could not load sermon importer: {e}")
        st.info("Please ensure the sermon_importer module is available.")
    except Exception as e:
        st.error(f"❌ Error checking import status: {e}")
        st.info("Please check that the processed_sermons directory exists and is accessible.")


if __name__ == "__main__":
    show_sermon_import()
