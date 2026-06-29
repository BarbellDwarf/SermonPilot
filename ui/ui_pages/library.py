"""
Sermon Library Page - Browse and search processed sermons

Provides comprehensive sermon browsing with:
- Clean list view with search and filtering
- Slide-in panel for detailed sermon information
- Quick access to sermon editing with API-backed dropdowns
"""

import csv
import io
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

def push_sermon_metadata_to_api(sermon):
    """Push sermon to SermonAudio — creates new sermon for dry runs, updates metadata for existing ones."""
    try:
        import sermon_updater

        sermon_id = sermon.get('id') or sermon.get('sermon_id')
        if not sermon_id:
            st.error("❌ No sermon ID found")
            return

        status = sermon.get('status', '')

        if status == 'draft':
            with st.spinner("📤 Publishing dry run sermon to SermonAudio (creating + uploading audio)..."):
                result = sermon_updater.publish_dry_run_sermon(sermon_id)
                if result.get('success'):
                    st.success(f"✅ Dry run published! New SermonAudio ID: {result.get('sermon_id')}")
                else:
                    st.error(f"❌ Failed to publish: {result.get('error')}")
            return

        if status == 'error':
            file_paths = sermon.get('file_paths', {})
            audio_path = file_paths.get('audio', '')
            if audio_path and Path(audio_path).exists():
                with st.spinner("📤 Re-uploading media to SermonAudio..."):
                    success = sermon_updater.reupload_media_for_sermon(sermon_id, audio_path)
                    if success:
                        st.success("✅ Media re-uploaded successfully!")
                        from database import SermonRepository
                        repo = SermonRepository()
                        repo.update_sermon_metadata(sermon_id, {'status': 'processed'})
                    else:
                        st.error("❌ Media re-upload failed. Check your API credentials and try again.")
            else:
                st.error("❌ No local media file found for re-upload. The file may have been deleted.")
            return

        # For existing sermons, check if they still exist on SermonAudio
        details = sermon_updater.get_sermon_details(sermon_id)
        if not details:
            # Sermon was deleted from SermonAudio — recreate it
            with st.spinner("📤 Sermon not found on SermonAudio. Recreating..."):
                result = sermon_updater.publish_dry_run_sermon(sermon_id)
                if result.get('success'):
                    st.success(f"✅ Sermon recreated! New SermonAudio ID: {result.get('sermon_id')}")
                else:
                    st.error(f"❌ Failed to recreate: {result.get('error')}")
            return

        with st.spinner("📤 Pushing metadata to SermonAudio..."):
            description = (sermon.get('description') or
                          sermon.get('ai_description') or
                          sermon.get('moreInfoText') or '')

            hashtags = sermon.get('hashtags') or sermon.get('keywords') or []

            if isinstance(hashtags, str):
                if ' ' in hashtags and ',' not in hashtags:
                    hashtags = hashtags.split()
                else:
                    hashtags = [tag.strip() for tag in hashtags.split(',') if tag.strip()]

            success = sermon_updater.update_sermon_metadata(
                sermon_id, description, hashtags,
                series_title=sermon.get('series_title') or None,
            )

            if success:
                st.success("✅ Metadata successfully updated on SermonAudio!")
                st.info("🔄 Refresh the page to see updated data from SermonAudio")
            else:
                st.error("❌ Failed to update metadata on SermonAudio. Check your API credentials and try again.")

    except ImportError:
        st.error("❌ Sermon updater module not available")
    except Exception as e:
        st.error(f"❌ Error updating metadata: {e}")
        if st.checkbox("Show Error Details", key=f"error_details_{sermon_id}"):
            st.exception(e)


def _get_transcript(sermon):
    """Extract transcript from sermon dict, handling both flat and nested content formats"""
    transcript = sermon.get('transcript', '')
    if not transcript:
        content = sermon.get('content', {})
        transcript = content.get('transcript_text', '') if isinstance(content, dict) else ''
    if not transcript:
        transcript = sermon.get('transcript_text', '')
    return transcript


def generate_ai_content(sermon):
    """Generate AI description and hashtags from sermon transcript"""
    sermon_id = sermon.get('id') or sermon.get('sermon_id')
    transcript = ''

    # Always try SermonAudio first for the most up-to-date transcript
    import sermon_updater
    with st.spinner("📥 Fetching transcript from SermonAudio..."):
        fetched = sermon_updater.get_sermon_transcript(sermon_id)
        if fetched:
            transcript = fetched
            with st.spinner("💾 Saving fetched transcript to local database..."):
                from database import SermonRepository, get_db
                repo = SermonRepository()
                db = get_db()
                with db.get_connection() as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO sermon_content
                        (sermon_id, transcript_text, updated_at)
                        VALUES (?, ?, ?)
                    """, (sermon_id, transcript, str(datetime.now())))
                    conn.execute("DELETE FROM sermon_search WHERE sermon_id = ?", (sermon_id,))
                    conn.execute("""
                        INSERT INTO sermon_search
                        (sermon_id, title, speaker, transcript_text, description, hashtags)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (sermon_id, sermon.get('title', ''), sermon.get('speaker', ''),
                          transcript, sermon.get('description', ''), sermon.get('hashtags', '')))
                    conn.commit()
            st.success("✅ Transcript fetched from SermonAudio!")
        else:
            # Fall back to local transcript
            transcript = _get_transcript(sermon)
            if not transcript:
                st.error("⚠️ No transcript available locally or on SermonAudio. Use the New Sermon page to process this sermon with transcription.")
                return

    if len(transcript) < 50:
        st.error(f"⚠️ Transcript too short ({len(transcript)} chars). Need at least 50 characters to generate meaningful content.")
        return

    try:
        # Ensure LLM manager is available
        if st.session_state.get('llm_manager') is None:
            from config_utils import load_config_from_file

            from src.llm_manager import LLMManager
            config = load_config_from_file()
            st.session_state.llm_manager = LLMManager(config)
            if st.session_state.llm_manager is None or not st.session_state.llm_manager.primary_provider:
                st.error("⚠️ No LLM provider configured. Go to Settings to configure an LLM provider first.")
                return

        llm = st.session_state.llm_manager

        with st.spinner("🤖 Generating description..."):
            event_type = sermon.get('event_type', '')
            speaker_name = sermon.get('speaker', '')

            # Build description prompt (mirrors sermon_updater.generate_summary)
            is_class = any(c.lower() in (event_type or '').lower() for c in [
                'Sunday School', 'Midweek Service', 'Bible Study', 'Teaching', 'Class',
                'Devotional', 'Conference', 'Camp Meeting', 'Children', 'Youth', 'Question & Answer'
            ])
            role_desc = 'Bible class summarization assistant' if is_class else 'sermon summarization assistant'
            body_desc = 'Sunday School, Midweek, or class/lecture event' if is_class else 'sermon'

            speaker_instruction = (
                f"- The speaker's name is {speaker_name}\n"
                if speaker_name
                else "- Identify the primary speaker from the transcript\n"
            )

            desc_prompt = (
                f"You are a {role_desc}. Read the following {body_desc} transcript and write a single, "
                f"concise description of the main message and application. Focus on what "
                f"the speaker wanted the audience to understand, believe, or do. Avoid generic statements; "
                f"emphasize unique focus.\n\nTranscript:\n{transcript}\n\nGuidelines:\n"
                f"- Maximum 1600 characters (STRICT LIMIT - API will reject longer text)\n"
                f"- One paragraph format\n"
                + speaker_instruction +
                "- No intro/closing words\n- No markdown or bullets\n"
                "- Do not prefix with 'Summary:'\n- If incomplete, infer likely main message\n"
                "- Keep under 1600 characters or the upload will fail\n"
                "- Use the actual speaker name, not placeholder text\n"
                "- IMPORTANT: Return ONLY the final summary paragraph. Do not include any reasoning, "
                "thinking process, explanations, or commentary. Start directly with the summary content."
            )

            description = llm.chat([{'role': 'user', 'content': desc_prompt}])

            description = re.sub(r'^(Okay|Alright|Let me|I\'ll|I need to|Here[^:]*:|Sure[^:]*:).*?\n', '', description, flags=re.IGNORECASE | re.MULTILINE)
            description = description.strip()

            if len(description) > 1600:
                truncated = description[:1600]
                last_space = truncated.rfind(' ')
                description = truncated[:last_space] if last_space > 1500 else truncated

        with st.spinner("🏷️ Generating hashtags..."):
            hashtag_prompt = (
                "Generate 5-10 highly relevant, search-friendly hashtags (<=150 chars total) for this "
                "sermon. Combine multi-word phrases (#ChristianLiving). Avoid duplicates & generic "
                "(#sermon #church) unless uniquely relevant. Output ONLY space-delimited hashtags.\n\n"
                f"Text:\n{transcript[:3000]}\n\nHashtags:"
            )
            hashtags_raw = llm.chat([{'role': 'user', 'content': hashtag_prompt}])
            hashtags = ' '.join(hashtags_raw.replace(',', ' ').split())[:150]

        # Save to database
        with st.spinner("💾 Saving to database..."):
            from database import SermonRepository, get_db
            repo = SermonRepository()

            # Update sermon description via existing method
            repo.update_sermon_metadata(sermon_id, {
                'description': description,
            })

            # Update sermon_content table for hashtags and transcript
            db = get_db()
            with db.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO sermon_content
                    (sermon_id, transcript_text, description, hashtags, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    sermon_id,
                    transcript,
                    description,
                    hashtags,
                    str(datetime.now()),
                ))
                # Update FTS index
                conn.execute("DELETE FROM sermon_search WHERE sermon_id = ?", (sermon_id,))
                title = sermon.get('title', '')
                speaker = sermon.get('speaker', '')
                conn.execute("""
                    INSERT INTO sermon_search
                    (sermon_id, title, speaker, transcript_text, description, hashtags)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (sermon_id, title, speaker, transcript, description, hashtags))
                conn.commit()

            st.success("✅ AI description and hashtags generated and saved!")
            # Refresh session state with updated data
            st.session_state.selected_sermon = repo.get_sermon(sermon_id)

    except Exception as e:
        st.error(f"❌ Error generating AI content: {e}")
        import traceback
        st.code(traceback.format_exc())


def _toggle_favorite(sermon_id, current_value):
    """Toggle the favorite status of a sermon"""
    from database import SermonRepository
    repo = SermonRepository()
    repo.update_sermon_metadata(sermon_id, {'is_favorite': 0 if current_value else 1})
    sermon = repo.get_sermon(sermon_id)
    if sermon:
        st.session_state.selected_sermon = sermon
    st.rerun()


def _export_csv(sermons):
    """Export filtered sermons as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ['id', 'title', 'speaker', 'recorded_date', 'duration', 'event_type',
               'series_title', 'scripture_reference', 'status', 'description', 'hashtags']
    writer.writerow(headers)
    for s in sermons:
        writer.writerow([
            s.get('id', ''), s.get('title', ''), s.get('speaker', ''),
            s.get('recorded_date', ''), s.get('duration', ''),
            s.get('event_type', ''), s.get('series_title', ''),
            s.get('scripture_reference', ''), s.get('status', ''),
            s.get('description', ''), s.get('hashtags', '')
        ])
    return output.getvalue()


def _export_json(sermons):
    """Export filtered sermons as JSON"""
    clean = []
    for s in sermons:
        clean.append({
            'id': s.get('id'), 'title': s.get('title'), 'speaker': s.get('speaker'),
            'recorded_date': s.get('recorded_date'), 'duration': s.get('duration'),
            'event_type': s.get('event_type'), 'series_title': s.get('series_title'),
            'scripture_reference': s.get('scripture_reference'), 'status': s.get('status'),
            'description': s.get('description'), 'hashtags': s.get('hashtags'),
            'church_name': s.get('church_name'), 'is_favorite': s.get('is_favorite', 0)
        })
    return json.dumps(clean, indent=2, default=str)


def _save_notes(sermon_id, notes):
    """Save notes for a sermon"""
    from database import SermonRepository
    repo = SermonRepository()
    repo.update_sermon_metadata(sermon_id, {'notes': notes})


def _batch_delete(sermon_ids):
    """Delete multiple sermons — actual deletion, confirmation handled in display_sermon_list"""
    from database import SermonRepository
    repo = SermonRepository()
    count = 0
    for sid in sermon_ids:
        if repo.delete_sermon(sid):
            count += 1
    st.session_state.selected_sermon_ids = []
    st.session_state.selected_sermon = None
    st.success(f"🗑️ Deleted {count} sermons")
    st.rerun()


def _batch_push(sermon_ids):
    """Push multiple sermons to API via job queue"""
    try:
        from job_queue import JobType, get_job_queue
        job_queue = get_job_queue()
        job_id = job_queue.add_job(
            job_type=JobType.BATCH_PROCESSING,
            title=f"Batch Push: {len(sermon_ids)} sermons",
            description=f"Pushing {len(sermon_ids)} sermons to SermonAudio API",
            parameters={
                'sermon_ids': sermon_ids,
                'actions': {'generate_description': True, 'generate_hashtags': True},
                'config': st.session_state.get('config', {})
            },
            priority=5
        )
        st.success(f"✅ Push job created: {job_id[:8]}")
    except Exception as e:
        st.error(f"❌ Failed to create push job: {e}")


def _batch_generate_ai(sermon_ids):
    """Generate AI content for multiple sermons via job queue"""
    try:
        from job_queue import JobType, get_job_queue
        job_queue = get_job_queue()
        job_id = job_queue.add_job(
            job_type=JobType.METADATA_UPDATE,
            title=f"Batch AI Gen: {len(sermon_ids)} sermons",
            description=f"Generating AI descriptions and hashtags for {len(sermon_ids)} sermons",
            parameters={
                'sermon_ids': sermon_ids,
                'actions': {'generate_description': True, 'generate_hashtags': True},
                'config': st.session_state.get('config', {})
            },
            priority=5
        )
        st.success(f"✅ AI generation job created: {job_id[:8]}")
    except Exception as e:
        st.error(f"❌ Failed to create AI generation job: {e}")


def show_library():
    """Main sermon library interface"""
    st.markdown('<div class="main-header">📚 Sermon Library</div>', unsafe_allow_html=True)
    st.markdown("Browse and search all processed sermons")

    try:
        from database import SermonRepository
        from sermonaudio_api import SermonAudioAPI

        repo = SermonRepository()
        api_client = SermonAudioAPI()

        # Initialize session state for selected sermon
        if 'selected_sermon' not in st.session_state:
            st.session_state.selected_sermon = None
        if 'editing_sermon' not in st.session_state:
            st.session_state.editing_sermon = False
        if 'selected_sermon_ids' not in st.session_state:
            st.session_state.selected_sermon_ids = []
        if 'show_favorites_only' not in st.session_state:
            st.session_state.show_favorites_only = False
        if 'confirm_batch_delete' not in st.session_state:
            st.session_state.confirm_batch_delete = False
        if 'show_reprocess' not in st.session_state:
            st.session_state.show_reprocess = None
        if 'library_sort_by' not in st.session_state:
            st.session_state.library_sort_by = "Date"
        if 'library_sort_order' not in st.session_state:
            st.session_state.library_sort_order = "Descending"

        # Get sermons
        sermons = repo.get_all_sermons(limit=1000)

        if not sermons:
            st.info("No sermons found. Process some sermons first using the 'New Sermon' page.")
            return

        # Search and filter controls
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 0.5])

        with col1:
            search_query = st.text_input(
                "🔍 Search sermons",
                placeholder="Search titles, speakers, content...",
                help="Search across sermon titles, speakers, and descriptions",
                key="library_search"
            )

        with col2:
            # Get unique speakers for filter
            speakers = sorted(set(s.get('speaker', '') for s in sermons if s.get('speaker')))
            speaker_filter = st.selectbox(
                "👤 Speaker",
                ["All"] + speakers,
                key="library_speaker_filter"
            )

        with col3:
            # Date range filter
            date_filter = st.selectbox(
                "📅 Date Range",
                ["All", "Last Month", "Last 3 Months", "Last Year"],
                key="library_date_filter"
            )

        with col4:
            # Processing status filter
            status_filter = st.selectbox(
                "🔄 Status",
                ["All", "Processed", "Pending", "Error"],
                key="library_status_filter"
            )

        with col5:
            st.caption("⭐")
            favorites_only = st.checkbox(
                "Favorites",
                value=st.session_state.show_favorites_only,
                key="library_fav_toggle",
                help="Show only favorited sermons"
            )
            st.session_state.show_favorites_only = favorites_only

        # Sort controls row
        col_s1, col_s2, col_s3, col_s4 = st.columns([1, 1, 2, 2])
        with col_s1:
            sort_by = st.selectbox(
                "Sort by",
                ["Date", "Title", "Speaker", "Duration"],
                index=["Date", "Title", "Speaker", "Duration"].index(st.session_state.library_sort_by),
                key="library_sort_by_sel"
            )
            st.session_state.library_sort_by = sort_by
        with col_s2:
            sort_order = st.selectbox(
                "Order",
                ["Descending", "Ascending"],
                index=0 if st.session_state.library_sort_order == "Descending" else 1,
                key="library_sort_order_sel"
            )
            st.session_state.library_sort_order = sort_order
        # Apply filters
        filtered_sermons = apply_filters(
            sermons, search_query, speaker_filter, date_filter, status_filter,
            favorites_only, sort_by, sort_order
        )

        with col_s3:
            st.caption("")
            if st.button("📥 Export CSV", use_container_width=True):
                csv_data = _export_csv(filtered_sermons)
                st.download_button(
                    "Download CSV", data=csv_data,
                    file_name=f"sermons_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv", key="dl_csv"
                )
        with col_s4:
            st.caption("")
            if st.button("📥 Export JSON", use_container_width=True):
                json_data = _export_json(filtered_sermons)
                st.download_button(
                    "Download JSON", data=json_data,
                    file_name=f"sermons_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json", key="dl_json"
                )

        # Main layout with two columns
        col_list, col_detail = st.columns([2, 3])

        with col_list:
            st.markdown("### Sermons")
            display_sermon_list(filtered_sermons, sermons)

        with col_detail:
            if st.session_state.selected_sermon:
                if st.session_state.editing_sermon:
                    display_sermon_editor(st.session_state.selected_sermon, api_client, repo)
                else:
                    display_sermon_details(st.session_state.selected_sermon)
            else:
                st.markdown("### Select a Sermon")
                st.info("👈 Select a sermon from the list to view details")

    except ImportError as e:
        st.error(f"❌ Import error: {e}")
        st.error("Please ensure all required modules are available.")
    except Exception as e:
        st.error(f"❌ Error loading sermon library: {e}")
        import traceback
        st.code(traceback.format_exc())

def apply_filters(sermons, search_query, speaker_filter, date_filter, status_filter,
                  favorites_only=False, sort_by="Date", sort_order="Descending"):
    """Apply search and filter criteria to sermons"""
    filtered_sermons = sermons[:]

    # FTS5 search if query is provided
    if search_query:
        try:
            from database import SermonRepository
            repo = SermonRepository()
            fts_results = repo.search_sermons(search_query, limit=1000)
            fts_ids = {s['id'] for s in fts_results if s.get('id')}
            filtered_sermons = [s for s in filtered_sermons if s.get('id') in fts_ids]
        except Exception:
            # Fallback to substring matching
            search_lower = search_query.lower()
            filtered_sermons = [
                s for s in filtered_sermons
                if search_lower in (s.get('title', '') or '').lower() or
                   search_lower in (s.get('speaker', '') or '').lower() or
                   search_lower in (s.get('description', '') or '').lower() or
                   search_lower in (s.get('ai_description', '') or '').lower() or
                   search_lower in (s.get('scripture_reference', '') or '').lower() or
                   search_lower in (s.get('series_title', '') or '').lower() or
                   search_lower in str(s.get('hashtags', '') or '').lower() or
                   search_lower in str(s.get('key_topics', '') or '').lower() or
                   (s.get('content') and search_lower in str(s['content'].get('key_topics', '') or '').lower())
            ]

    # Speaker filter
    if speaker_filter != "All":
        filtered_sermons = [s for s in filtered_sermons if s.get('speaker') == speaker_filter]

    # Date filter
    if date_filter != "All":
        cutoff_date = datetime.now()
        if date_filter == "Last Month":
            cutoff_date -= timedelta(days=30)
        elif date_filter == "Last 3 Months":
            cutoff_date -= timedelta(days=90)
        elif date_filter == "Last Year":
            cutoff_date -= timedelta(days=365)

        filtered_sermons = [
            s for s in filtered_sermons
            if s.get('recorded_date') and
            datetime.fromisoformat(s['recorded_date'].replace('Z', '+00:00')) >= cutoff_date
        ]

    # Status filter
    if status_filter != "All":
        status_map = {
            "Processed": ["completed", "processed"],
            "Pending": ["processing"],
            "Error": ["failed"]
        }
        target_statuses = status_map.get(status_filter, [status_filter.lower()])
        filtered_sermons = [s for s in filtered_sermons if s.get('status') in target_statuses]

    # Favorites filter
    if favorites_only:
        filtered_sermons = [s for s in filtered_sermons if s.get('is_favorite', 0)]

    # Sorting
    reverse = sort_order == "Descending"
    if sort_by == "Date":
        def sort_key(s):
            d = s.get('recorded_date')
            return d or ''
        filtered_sermons.sort(key=sort_key, reverse=reverse)
    elif sort_by == "Title":
        filtered_sermons.sort(key=lambda s: (s.get('title', '') or '').lower(), reverse=reverse)
    elif sort_by == "Speaker":
        filtered_sermons.sort(key=lambda s: (s.get('speaker', '') or '').lower(), reverse=reverse)
    elif sort_by == "Duration":
        def dur_key(s):
            d = s.get('duration', 0)
            if isinstance(d, str):
                try:
                    return float(d)
                except ValueError:
                    return 0
            return d or 0
        filtered_sermons.sort(key=dur_key, reverse=reverse)

    return filtered_sermons

def _format_date(date_str):
    """Try to format a date string as YYYY-MM-DD"""
    try:
        if date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except:
        pass
    return date_str or 'Unknown'

def display_sermon_list(filtered_sermons, all_sermons):
    """Display the sermon list with compact clickable rows"""

    st.markdown(f"**{len(filtered_sermons)}** sermons shown (of {len(all_sermons)} total)")

    # Bulk action bar
    selected_ids = st.session_state.get('selected_sermon_ids', [])
    if selected_ids:
        if st.session_state.get('confirm_batch_delete'):
            st.warning(f"⚠️ Delete {len(selected_ids)} sermons? This cannot be undone.")
            bc1, bc2 = st.columns([1, 5])
            with bc1:
                if st.button("Yes, delete all", type="primary", key="batch_del_yes"):
                    st.session_state.confirm_batch_delete = False
                    _batch_delete(selected_ids)
            with bc2:
                if st.button("Cancel", key="batch_del_no"):
                    st.session_state.confirm_batch_delete = False
                    st.rerun()
        else:
            st.info(f"📌 {len(selected_ids)} sermon(s) selected")
            bcol1, bcol2, bcol3, bcol4 = st.columns([1, 1, 1, 2])
            with bcol1:
                if st.button("🗑️ Batch Delete", type="primary", use_container_width=True):
                    st.session_state.confirm_batch_delete = True
                    st.rerun()
            with bcol2:
                if st.button("📤 Batch Push", use_container_width=True):
                    _batch_push(selected_ids)
            with bcol3:
                if st.button("🤖 Batch AI", use_container_width=True):
                    _batch_generate_ai(selected_ids)
            with bcol4:
                if st.button("Clear Selection", use_container_width=True):
                    st.session_state.selected_sermon_ids = []
                    st.rerun()

    items_per_page = 20
    total_pages = (len(filtered_sermons) + items_per_page - 1) // items_per_page

    page = 0
    if total_pages > 1:
        prev, mid, next = st.columns([1, 3, 1])
        with prev:
            if st.button("◀ Prev", width='stretch', disabled=(st.session_state.get('library_page', 0) == 0)):
                st.session_state.library_page = max(0, st.session_state.get('library_page', 0) - 1)
        with mid:
            st.caption(f"Page {st.session_state.get('library_page', 0) + 1} of {total_pages}")
        with next:
            if st.button("Next ▶", width='stretch', disabled=(st.session_state.get('library_page', 0) >= total_pages - 1)):
                st.session_state.library_page = min(total_pages - 1, st.session_state.get('library_page', 0) + 1)
        page = st.session_state.get('library_page', 0)
    else:
        st.session_state.library_page = 0

    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_sermons))
    page_sermons = filtered_sermons[start_idx:end_idx]

    for sermon in page_sermons:
        sid = sermon['id']
        is_fav = sermon.get('is_favorite', 0)
        is_selected = sid in st.session_state.selected_sermon_ids

        cols = st.columns([0.3, 0.3, 4.5, 1.2, 0.8])
        with cols[0]:
            checked = st.checkbox("Select", value=is_selected, key=f"bulk_{sid}",
                                  label_visibility="collapsed",
                                  help="Select for batch actions")
            if checked and sid not in st.session_state.selected_sermon_ids:
                st.session_state.selected_sermon_ids.append(sid)
                st.rerun()
            elif not checked and sid in st.session_state.selected_sermon_ids:
                st.session_state.selected_sermon_ids.remove(sid)
                st.rerun()
        with cols[1]:
            status = sermon.get('status', 'unknown')
            icon = "✅" if status in ['completed', 'processed'] else "⏳" if status == 'processing' else "❌"
            st.markdown(f"<span style='font-size:0.8rem'>{icon}</span>", unsafe_allow_html=True)
        with cols[2]:
            title = sermon.get('title', 'Untitled')
            speaker = sermon.get('speaker', '')
            date = _format_date(sermon.get('recorded_date'))
            fav_star = "⭐" if is_fav else "☆"
            st.markdown(f"**{title}** {fav_star}")
            if speaker or date:
                st.caption(f"{speaker} · {date}")
        with cols[3]:
            dur = sermon.get('duration', '')
            if dur:
                st.caption(f"⏱ {dur}")
        with cols[4]:
            if st.button("→", key=f"sel_{sid}", help="View details"):
                st.session_state.selected_sermon = sermon
                st.session_state.editing_sermon = False
                st.rerun()

def _get_hashtags_list(hashtags_source):
    """Normalize hashtags from various formats into a list"""
    if not hashtags_source:
        return None
    if isinstance(hashtags_source, str):
        if ' ' in hashtags_source and ',' not in hashtags_source:
            return hashtags_source.split()
        return [tag.strip() for tag in hashtags_source.split(',') if tag.strip()]
    if isinstance(hashtags_source, list):
        return hashtags_source
    return None

def _format_duration(seconds):
    """Convert seconds to HH:MM:SS or MM:SS"""
    if not seconds:
        return None
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

def display_sermon_details(sermon):
    """Display detailed sermon information with API data"""
    st.markdown("### Sermon Details")

    col1, col2, col3, col4, col5, col6, col7 = st.columns([1.5, 1, 1, 1, 1, 0.7, 0.5])
    with col1:
        st.markdown(f"## {sermon.get('title', 'Untitled')}")
    with col2:
        is_fav = sermon.get('is_favorite', 0)
        fav_label = "⭐" if is_fav else "☆"
        if st.button(fav_label, key=f"fav_{sermon['id']}", width='stretch',
                    help="Toggle favorite"):
            _toggle_favorite(sermon['id'], is_fav)
    with col3:
        if st.button("✏️ Edit", key=f"edit_{sermon['id']}", width='stretch'):
            st.session_state.editing_sermon = True
            st.rerun()
    with col4:
        if st.button("🤖 Generate", key=f"generate_{sermon['id']}",
                    help="Generate AI description and hashtags from transcript",
                    width='stretch'):
            generate_ai_content(sermon)
            st.rerun()
    with col5:
        push_help = "Publish dry run to SermonAudio" if sermon.get('status') == 'draft' else "Update metadata on SermonAudio"
        if st.button("📤 Push", key=f"push_{sermon['id']}",
                    help=push_help,
                    width='stretch'):
            push_sermon_metadata_to_api(sermon)
            st.rerun()
    with col6:
        if st.button("🗑️", key=f"delete_{sermon['id']}",
                    help="Delete this sermon", width='stretch'):
            st.session_state.confirm_delete_sermon = sermon['id']
            st.rerun()
    with col7:
        if st.button("🔄", key=f"reproc_{sermon['id']}",
                    help="Re-process this sermon", width='stretch'):
            st.session_state.show_reprocess = sermon['id']
            st.rerun()

    if st.session_state.get('confirm_delete_sermon') == sermon['id']:
        st.warning("Are you sure you want to delete this sermon? This cannot be undone.")
        c1, c2 = st.columns([1, 5])
        with c1:
            if st.button("Yes, delete", type="primary", key=f"confirm_del_{sermon['id']}"):
                from database import SermonRepository
                repo = SermonRepository()
                if repo.delete_sermon(sermon['id']):
                    file_paths = sermon.get('file_paths', sermon.get('files', {}))
                    for ftype, fpath in file_paths.items():
                        if fpath and Path(fpath).exists():
                            Path(fpath).unlink(missing_ok=True)
                    st.success("✅ Sermon deleted")
                    st.session_state.selected_sermon = None
                    st.session_state.confirm_delete_sermon = None
                    st.rerun()
                else:
                    st.error("❌ Failed to delete sermon")
        with c2:
            if st.button("Cancel", key=f"cancel_del_{sermon['id']}"):
                st.session_state.confirm_delete_sermon = None
                st.rerun()

    sermon_id = sermon.get('id') or sermon.get('sermon_id')
    api_sermon_data = None

    if sermon_id:
        api_sermon_data = None
        try:
            from sermonaudio_api import SermonAudioAPI
            api_client = SermonAudioAPI()
            if api_client.is_configured():
                with st.spinner("🔄 Loading enhanced sermon data..."):
                    api_response = api_client.get_sermon_details(sermon_id)
                    if api_response and isinstance(api_response, dict):
                        api_sermon_data = api_response.get('sermon', api_response)
                    if not api_response:
                        st.info("Sermon not found on SermonAudio (may have been deleted). Use the Push button to recreate it.")
        except Exception as e:
            st.warning(f"Could not load enhanced sermon data: {e}")

    display_data = sermon.copy()

    if api_sermon_data:
        field_mapping = {
            'fullTitle': 'title', 'displayTitle': 'title',
            'moreInfoText': 'ai_description', 'bibleText': 'scripture_reference',
            'keywords': 'hashtags', 'audioDurationSeconds': 'duration_seconds',
            'preachDate': 'recorded_date', 'eventType': 'event_type',
            'displayEventType': 'event_type'
        }
        for api_field, display_field in field_mapping.items():
            if api_field in api_sermon_data:
                display_data[display_field] = api_sermon_data[api_field]
        if isinstance(api_sermon_data.get('speaker'), dict):
            display_data['speaker'] = api_sermon_data['speaker'].get('displayName', display_data.get('speaker', 'Unknown'))
        if isinstance(api_sermon_data.get('series'), dict):
            display_data['series_title'] = api_sermon_data['series'].get('title', display_data.get('series_title', ''))
        if isinstance(api_sermon_data.get('broadcaster'), dict):
            display_data['church_name'] = api_sermon_data['broadcaster'].get('displayName', display_data.get('church_name', ''))
        if 'media' in api_sermon_data and 'audio' in api_sermon_data['media']:
            audio_files = api_sermon_data['media']['audio']
            if audio_files:
                display_data['audio_url'] = audio_files[0].get('streamURL')
        if 'duration_seconds' in display_data:
            formatted = _format_duration(display_data['duration_seconds'])
            if formatted:
                display_data['duration'] = formatted

        db_updates = {}
        api = api_sermon_data
        if api.get('fullTitle') and not sermon.get('title'):
            db_updates['title'] = api['fullTitle']
        speaker = api.get('speaker', {})
        speaker_name = speaker.get('displayName') if isinstance(speaker, dict) else (str(speaker) if speaker else None)
        if speaker_name and not sermon.get('speaker'):
            db_updates['speaker'] = speaker_name
        if api.get('eventType') and not sermon.get('event_type'):
            db_updates['event_type'] = api['eventType']
        if (api.get('displayEventDate') or api.get('preachDate')) and not sermon.get('recorded_date'):
            db_updates['recorded_date'] = api.get('displayEventDate') or api.get('preachDate')
        if api.get('bibleText') and (not sermon.get('bible_text') or not sermon.get('scripture_reference')):
            db_updates['bible_text'] = api['bibleText']
            db_updates['scripture_reference'] = api['bibleText']
        series_title = api.get('series', {}).get('title') if isinstance(api.get('series'), dict) else api.get('seriesTitle')
        if series_title and not sermon.get('series_title'):
            db_updates['series_title'] = series_title
        if api.get('subtitle') and not sermon.get('subtitle'):
            db_updates['subtitle'] = api['subtitle']
        if db_updates:
            try:
                from database import SermonRepository
                repo = SermonRepository()
                repo.update_sermon_metadata(sermon_id, db_updates)
            except Exception:
                pass

    st.markdown("### 📋 Information")
    col1, col2 = st.columns(2)
    with col1:
        speaker_name = display_data.get('speaker', 'Unknown')
        if isinstance(speaker_name, dict):
            speaker_name = speaker_name.get('displayName', 'Unknown')
        st.text(f"🎤 Speaker: {speaker_name}")
        st.text(f"📅 Date: {_format_date(display_data.get('recorded_date'))}")
        st.text(f"📍 Church: {display_data.get('church_name', 'Unknown')}")
        st.text(f"⏱️ Duration: {display_data.get('duration', 'Unknown')}")
    with col2:
        series_title = display_data.get('series_title', 'None')
        if isinstance(series_title, dict):
            series_title = series_title.get('title', 'None')
        st.text(f"📚 Series: {series_title}")
        st.text(f"🎯 Event: {display_data.get('event_type', 'Unknown')}")
        st.text(f"📖 Scripture: {display_data.get('scripture_reference', 'None')}")

    if sermon_id:
        sermon_url = f"https://www.sermonaudio.com/sermoninfo.asp?SID={sermon_id}"
        st.markdown(f"[🎧 Listen on SermonAudio]({sermon_url})")
        audio_url = display_data.get('audio_url')
        if audio_url:
            try:
                st.audio(audio_url)
            except Exception:
                st.caption(f"Audio link: {audio_url}")
        else:
            file_paths = display_data.get('file_paths', display_data.get('files', {}))
            if file_paths and file_paths.get('audio'):
                audio_path = file_paths['audio']
                if Path(audio_path).exists():
                    st.audio(audio_path)
                else:
                    st.caption("Audio file not found locally")

    st.markdown("### 📝 Description")
    description = display_data.get('description', '')
    ai_description = display_data.get('ai_description', '')
    if ai_description and ai_description != description:
        tab1, tab2 = st.tabs(["🤖 AI Generated", "📄 Original"])
        with tab1:
            if ai_description:
                st.markdown(ai_description)
            else:
                st.info("No AI-generated description available")
        with tab2:
            if description:
                st.markdown(description)
            else:
                st.info("No original description available")
    else:
        if description:
            st.markdown(description)
        elif ai_description:
            st.markdown(ai_description)
        else:
            st.info("No description available")

    hashtags = _get_hashtags_list(display_data.get('hashtags'))
    if hashtags:
        tags_display = ' · '.join(
            re.sub(r'([a-z])([A-Z])', r'\1 \2', t.replace('#', '').strip())
            for t in hashtags if t.strip()
        )
        st.markdown(f"**🏷️ Keywords & Topics:** {tags_display}")

    scripture_ref = display_data.get('scripture_reference')
    verses = display_data.get('verses', display_data.get('scripture_text'))
    if scripture_ref or verses:
        st.markdown("### 📖 Scripture")
        if scripture_ref:
            st.markdown(f"**Reference:** {scripture_ref}")
        if verses:
            with st.expander("📜 Scripture Text", expanded=False):
                st.markdown(verses)

    topics = display_data.get('key_topics') or display_data.get('content', {}).get('key_topics', [])
    if isinstance(topics, str):
        topics = [t.strip() for t in topics.split(',') if t.strip()]
    if topics:
        st.markdown(f"**🔑 Key Topics:** {' · '.join(topics)}")

    with st.expander("📁 Files & Processing", expanded=False):
        files = display_data.get('files', display_data.get('file_paths', {}))
        if files:
            for file_type, file_path in files.items():
                file_name = Path(file_path).name if file_path else "Not available"
                st.text(f"{file_type.title()}: {file_name}")
        status = display_data.get('status', 'unknown')
        if status in ['completed', 'processed']:
            st.success("✅ Processing completed")
        elif status == 'processing':
            st.info("⏳ Processing in progress")
        elif status == 'failed':
            st.error("❌ Processing failed")
        else:
            st.info(f"ℹ️ Status: {status.title()}")

        processing_info = display_data.get('processing_info', {})
        upload_info = display_data.get('upload_info', {})
        if processing_info.get('processed_at'):
            st.text(f"Processed: {processing_info['processed_at']}")
        if upload_info.get('uploaded_at'):
            st.text(f"Uploaded: {upload_info['uploaded_at']}")
        if processing_info.get('enhancement_method'):
            st.text(f"Enhancement: {processing_info['enhancement_method']}")

    if processing_info or api_sermon_data:
        with st.expander("🔬 Advanced Information", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                if processing_info:
                    for key, value in processing_info.items():
                        if key not in ['processed_at', 'enhancement_method'] and value:
                            display_key = key.replace('_', ' ').title()
                            if isinstance(value, (dict, list)):
                                st.json({display_key: value})
                            else:
                                st.text(f"{display_key}: {value}")
            with col2:
                if api_sermon_data:
                    for key in ['broadcaster_id', 'speaker_id', 'series_id', 'event_type_id']:
                        if key in api_sermon_data and api_sermon_data[key]:
                            st.text(f"{key.replace('_', ' ').title()}: {api_sermon_data[key]}")

    # Re-process form
    if st.session_state.get('show_reprocess') == sermon.get('id'):
        with st.expander("🔄 Re-process Sermon", expanded=True):
            st.markdown("Select which processing steps to run:")
            rp_audio = st.checkbox("Audio enhancement", value=True, key=f"rp_audio_{sermon['id']}")
            rp_transcript = st.checkbox("Transcription", value=True, key=f"rp_trans_{sermon['id']}")
            rp_ai = st.checkbox("AI description & hashtags", value=True, key=f"rp_ai_{sermon['id']}")
            rp_dry_run = st.checkbox("Dry run (no upload)", value=False, key=f"rp_dry_{sermon['id']}")
            rp_col1, rp_col2 = st.columns(2)
            with rp_col1:
                if st.button("▶️ Start Re-processing", type="primary", key=f"rp_start_{sermon['id']}"):
                    try:
                        from job_queue import JobType, get_job_queue
                        job_queue = get_job_queue()
                        job_id = job_queue.add_job(
                            job_type=JobType.SERMON_PROCESSING,
                            title=f"Re-process: {sermon.get('title', sermon['id'])}",
                            description=f"Re-processing sermon {sermon['id']}",
                            parameters={
                                'sermon_ids': [sermon['id']],
                                'config': st.session_state.get('config', {}),
                                'form_data': {
                                    'skip_audio': not rp_audio,
                                    'skip_transcription': not rp_transcript,
                                    'skip_ai_generation': not rp_ai,
                                    'dry_run': rp_dry_run,
                                }
                            },
                            priority=5
                        )
                        st.success(f"✅ Re-process job created: {job_id[:8]}")
                        st.session_state.show_reprocess = None
                    except Exception as e:
                        st.error(f"❌ Failed: {e}")
            with rp_col2:
                if st.button("Cancel", key=f"rp_cancel_{sermon['id']}"):
                    st.session_state.show_reprocess = None
                    st.rerun()

    # Transcript viewer/editor
    with st.expander("📝 Transcript", expanded=False):
        transcript = sermon.get('transcript') or sermon.get('transcript_text', '')
        if sermon.get('content') and isinstance(sermon.get('content'), dict):
            transcript = transcript or sermon['content'].get('transcript_text', '')
        edited_transcript = st.text_area(
            "Edit transcript",
            value=transcript,
            height=200,
            key=f"transcript_{sermon['id']}"
        )
        if edited_transcript != transcript and st.button("💾 Save Transcript", key=f"save_trans_{sermon['id']}"):
            from database import SermonRepository
            repo = SermonRepository()
            repo.update_sermon(sermon['id'], {'transcript': edited_transcript})
            st.success("✅ Transcript saved")
            st.session_state.selected_sermon = repo.get_sermon(sermon['id'])
            st.rerun()

    # Notes
    with st.expander("📋 Notes", expanded=False):
        current_notes = sermon.get('notes', '') or ''
        new_notes = st.text_area(
            "Sermon notes",
            value=current_notes,
            height=100,
            key=f"notes_{sermon['id']}"
        )
        if new_notes != current_notes:
            _save_notes(sermon['id'], new_notes)

    if api_sermon_data:
        if st.button("🔄 Refresh from SermonAudio", help="Fetch the latest data from SermonAudio API"):
            try:
                from database import SermonRepository
                from sermonaudio_api import SermonAudioAPI
                api_client = SermonAudioAPI()
                fresh_data = api_client.get_sermon_details(sermon_id, force_refresh=True)
                if fresh_data:
                    api = fresh_data.get('sermon', fresh_data)
                    speaker = api.get('speaker', {})
                    raw_updates = {
                        'title': api.get('fullTitle') or api.get('title'),
                        'subtitle': api.get('subtitle'),
                        'speaker': speaker.get('displayName') if isinstance(speaker, dict) else str(speaker) if speaker else None,
                        'event_type': api.get('eventType') or api.get('displayEventType'),
                        'recorded_date': api.get('displayEventDate') or api.get('preachDate'),
                        'bible_text': api.get('bibleText'),
                        'scripture_reference': api.get('bibleText'),
                        'series_title': api.get('series', {}).get('title') if isinstance(api.get('series'), dict) else api.get('seriesTitle'),
                        'church_name': api.get('broadcaster', {}).get('displayName') if isinstance(api.get('broadcaster'), dict) else None,
                        'description': api.get('moreInfoText') or api.get('description'),
                    }
                    db_updates = {k: v for k, v in raw_updates.items() if v is not None}
                    repo = SermonRepository()
                    if db_updates and repo.update_sermon_metadata(sermon_id, db_updates):
                        st.success("✅ Sermon data refreshed and saved!")
                        st.session_state.selected_sermon = repo.get_sermon(sermon_id)
                        st.rerun()
                    else:
                        st.error("❌ Failed to save refreshed data")
                else:
                    st.error("❌ Failed to refresh data")
            except Exception as e:
                st.error(f"❌ Error refreshing data: {e}")

def display_sermon_editor(sermon, api_client, repo):
    """Display sermon editor with API-backed dropdowns"""
    st.markdown("### ✏️ Edit Sermon")

    # Get API data for dropdowns
    speakers = []
    series = []

    if api_client.is_configured():
        try:
            # Get speakers and extract names from dictionary format
            speaker_data = api_client.get_speakers()
            speakers = [s.get('name', str(s)) for s in speaker_data] if speaker_data else []

            # Get series and extract names from dictionary format
            series_data = api_client.get_series()
            series = [s.get('name', str(s)) for s in series_data] if series_data else []

        except Exception as e:
            st.warning(f"Could not load API data: {e}")
            # Fallback to empty lists
            speakers = []
            series = []

    # Edit form
    with st.form(f"edit_sermon_{sermon['id']}"):
        col1, col2 = st.columns(2)

        with col1:
            title = st.text_input("Title", value=sermon.get('title', ''))

            # Speaker dropdown or text input
            if speakers:
                current_speaker = sermon.get('speaker', '')
                speaker_options = [''] + speakers
                speaker_idx = 0
                if current_speaker in speaker_options:
                    speaker_idx = speaker_options.index(current_speaker)
                speaker = st.selectbox("Speaker", speaker_options, index=speaker_idx)
            else:
                speaker = st.text_input("Speaker", value=sermon.get('speaker', ''))

            recorded_date = st.date_input("Recorded Date",
                                        value=datetime.fromisoformat(sermon.get('recorded_date', '2024-01-01').replace('Z', '+00:00')).date() if sermon.get('recorded_date') else datetime.now().date())

        with col2:
            # Series dropdown or text input
            if series:
                current_series = sermon.get('series_title', '')
                series_options = [''] + series
                series_idx = 0
                if current_series in series_options:
                    series_idx = series_options.index(current_series)
                series_title = st.selectbox("Series", series_options, index=series_idx)
            else:
                series_title = st.text_input("Series", value=sermon.get('series_title', ''))

            scripture_reference = st.text_input("Scripture Reference", value=sermon.get('scripture_reference', ''))
            event_type = st.text_input("Event Type", value=sermon.get('event_type', ''))

        description = st.text_area("Description", value=sermon.get('description', ''), height=100)

        # Form buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            save = st.form_submit_button("💾 Save", type="primary")
        with col2:
            cancel = st.form_submit_button("❌ Cancel")

        # Handle form submission
        if save:
            try:
                updated_data = {
                    'title': title,
                    'speaker': speaker,
                    'series_title': series_title,
                    'recorded_date': recorded_date.isoformat(),
                    'scripture_reference': scripture_reference,
                    'event_type': event_type,
                    'description': description
                }

                success = repo.update_sermon_metadata(sermon['id'], updated_data)
                if success:
                    st.success("✅ Sermon updated successfully!")
                    st.session_state.editing_sermon = False
                    # Refresh the selected sermon data
                    st.session_state.selected_sermon = repo.get_sermon(sermon['id'])
                    st.rerun()
                else:
                    st.error("Failed to update sermon metadata")
            except Exception as e:
                st.error(f"Error updating sermon: {e}")

        if cancel:
            st.session_state.editing_sermon = False
            st.rerun()

if __name__ == "__main__":
    show_library()
