"""
Sermon Library Page - Browse and search processed sermons

Provides comprehensive sermon browsing with:
- Clean list view with search and filtering
- Slide-in panel for detailed sermon information
- Quick access to sermon editing with API-backed dropdowns
"""

import csv
import html
import io
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from ui.ui_state import managed_expander, managed_popover

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

logger = logging.getLogger(__name__)


def _set_feedback(message, kind="success", details=None):
    """Persist feedback in session state so it survives reruns"""
    st.session_state['library_feedback'] = {'kind': kind, 'message': message, 'details': details}


def _show_feedback():
    """Render persisted feedback once, then clear it"""
    feedback = st.session_state.get('library_feedback')
    if not feedback:
        return
    del st.session_state['library_feedback']
    kind = feedback.get('kind', 'success')
    message = feedback.get('message', '')
    if kind == 'error':
        st.error(message)
    elif kind == 'warning':
        st.warning(message)
    else:
        st.success(message)
    details = feedback.get('details')
    if details:
        st.code(details)


def push_sermon_metadata_to_api(sermon):
    """Push sermon to SermonAudio — creates new sermon for dry runs,
    updates metadata for existing ones."""
    try:
        import sermon_updater

        sermon_id = sermon.get('id') or sermon.get('sermon_id')
        if not sermon_id:
            _set_feedback("No sermon ID found", kind="error")
            return

        status = sermon.get('status', '')

        if status == 'draft':
            with st.spinner(
                "Publishing dry run sermon to SermonAudio (creating + uploading audio)..."
            ):
                result = sermon_updater.publish_dry_run_sermon(sermon_id)
                if result.get('success'):
                    _set_feedback(
                        f"Dry run published! New SermonAudio ID: {result.get('sermon_id')}"
                    )
                else:
                    _set_feedback(f"Failed to publish: {result.get('error')}", kind="error")
            return

        if status == 'error':
            file_paths = sermon.get('file_paths', {})
            audio_path = file_paths.get('audio', '')
            if audio_path and Path(audio_path).exists():
                with st.spinner("Re-uploading media to SermonAudio..."):
                    success = sermon_updater.reupload_media_for_sermon(sermon_id, audio_path)
                    if success:
                        _set_feedback("Media re-uploaded successfully!")
                        from ui.database import SermonRepository
                        repo = SermonRepository()
                        repo.update_sermon(sermon_id, {'status': 'processed'})
                    else:
                        _set_feedback(
                            "Media re-upload failed. Check your API credentials and try again.",
                            kind="error",
                        )
            else:
                _set_feedback(
                    "No local media file found for re-upload. The file may have been deleted.",
                    kind="error",
                )
            return

        # For existing sermons, check if they still exist on SermonAudio
        details = sermon_updater.get_sermon_details(sermon_id)
        if not details:
            # Sermon was deleted from SermonAudio — recreate it
            with st.spinner("Sermon not found on SermonAudio. Recreating..."):
                result = sermon_updater.publish_dry_run_sermon(sermon_id)
                if result.get('success'):
                    _set_feedback(
                        f"Sermon recreated! New SermonAudio ID: {result.get('sermon_id')}"
                    )
                else:
                    _set_feedback(f"Failed to recreate: {result.get('error')}", kind="error")
            return

        with st.spinner("Pushing metadata to SermonAudio..."):
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
                _set_feedback("Metadata successfully updated on SermonAudio!")
            else:
                _set_feedback(
                    "Failed to update metadata on SermonAudio. "
                    "Check your API credentials and try again.",
                    kind="error",
                )

    except ImportError:
        _set_feedback("Sermon updater module not available", kind="error")
    except Exception as e:
        _set_feedback(f"Error updating metadata: {e}", kind="error")


def _get_transcript(sermon):
    """Extract transcript from sermon dict, handling both flat and nested content formats"""
    transcript = sermon.get('transcript', '')
    if not transcript:
        content = sermon.get('content', {})
        transcript = content.get('transcript_text', '') if isinstance(content, dict) else ''
    if not transcript:
        transcript = sermon.get('transcript_text', '')
    return transcript


def generate_ai_content(sermon, gen_description=True, gen_hashtags=True):
    """Generate AI description and/or hashtags from sermon transcript"""
    sermon_id = sermon.get('id') or sermon.get('sermon_id')
    transcript = ''

    # Always try SermonAudio first for the most up-to-date transcript
    import sermon_updater
    with st.spinner("Fetching transcript from SermonAudio..."):
        fetched = sermon_updater.get_sermon_transcript(sermon_id)
        if fetched:
            transcript = fetched
            with st.spinner("Saving fetched transcript to local database..."):
                from ui.database import SermonRepository
                repo = SermonRepository()
                if not repo.update_sermon_metadata(
                    sermon_id, {'transcript_text': transcript}
                ):
                    _set_feedback(
                        "Transcript fetched but could not be saved locally.",
                        kind="warning",
                    )
            st.success("Transcript fetched from SermonAudio!")
        else:
            # Fall back to local transcript
            transcript = _get_transcript(sermon)
            if not transcript:
                _set_feedback(
                    "No transcript available locally or on SermonAudio. "
                    "Use the New Sermon page to process this sermon with transcription.",
                    kind="error",
                )
                return

    if not gen_description and not gen_hashtags:
        _set_feedback("Select at least one item to generate.", kind="warning")
        return

    if len(transcript) < 50:
        _set_feedback(
            f"Transcript too short ({len(transcript)} chars). "
            "Need at least 50 characters to generate meaningful content.",
            kind="error",
        )
        return

    try:
        # Ensure LLM manager is available
        if st.session_state.get('llm_manager') is None:
            from config_utils import load_config_from_file

            from src.llm_manager import LLMManager
            config = load_config_from_file()
            st.session_state.llm_manager = LLMManager(config)
            if (
                st.session_state.llm_manager is None
                or not st.session_state.llm_manager.primary_provider
            ):
                _set_feedback(
                    "No LLM provider configured. "
                    "Go to Settings to configure an LLM provider first.",
                    kind="error",
                )
                return

        llm = st.session_state.llm_manager

        description = None
        hashtags = None

        if gen_description:
            with st.spinner("Generating description..."):
                event_type = sermon.get('event_type', '')
                speaker_name = sermon.get('speaker', '')

                # Build description prompt (mirrors sermon_updater.generate_summary)
                is_class = any(c.lower() in (event_type or '').lower() for c in [
                    'Sunday School', 'Midweek Service', 'Bible Study', 'Teaching', 'Class',
                    'Devotional', 'Conference', 'Camp Meeting', 'Children', 'Youth',
                    'Question & Answer',
                ])
                role_desc = (
                    'Bible class summarization assistant' if is_class
                    else 'sermon summarization assistant'
                )
                body_desc = (
                    'Sunday School, Midweek, or class/lecture event' if is_class else 'sermon'
                )

                speaker_instruction = (
                    f"- The speaker's name is {speaker_name}\n"
                    if speaker_name
                    else "- Identify the primary speaker from the transcript\n"
                )

                desc_prompt = (
                    f"You are a {role_desc}. Read the following {body_desc} transcript "
                    f"and write a single, "
                    f"concise description of the main message and application. Focus on what "
                    f"the speaker wanted the audience to understand, believe, or do. "
                    f"Avoid generic statements; "
                    f"emphasize unique focus.\n\nTranscript:\n{transcript}\n\nGuidelines:\n"
                    f"- Target 900 to 1200 characters; stay under 1400 "
                    f"(the API rejects text over 1700)\n"
                    f"- One paragraph format\n"
                    + speaker_instruction +
                    "- No intro/closing words\n- No markdown or bullets\n"
                    "- Do not prefix with 'Summary:'\n- If incomplete, infer likely main message\n"
                    "- Keep within the target length or the upload will fail\n"
                    "- Use the actual speaker name, not placeholder text\n"
                    "- IMPORTANT: Return ONLY the final summary paragraph. Do not include any "
                    "reasoning, "
                    "thinking process, explanations, or commentary. "
                    "Start directly with the summary content."
                )

                description = llm.chat([{'role': 'user', 'content': desc_prompt}])
                from src.llm_manager import extract_final_answer

                description = extract_final_answer(description)

                description = re.sub(
                    r'^(Okay|Alright|Let me|I\'ll|I need to|Here[^:]*:|Sure[^:]*:).*?\n',
                    '', description, flags=re.IGNORECASE | re.MULTILINE,
                )
                description = description.strip()

                if len(description) > 1600:
                    from src.llm_manager import trim_to_sentence

                    description = trim_to_sentence(description, 1600)

        if gen_hashtags:
            with st.spinner("Generating hashtags..."):
                hashtag_prompt = (
                    "Generate 5-10 highly relevant, search-friendly hashtags "
                    "(<=150 chars total) for this "
                    "sermon. Combine multi-word phrases (#ChristianLiving). "
                    "Avoid duplicates & generic "
                    "(#sermon #church) unless uniquely relevant. "
                    "Output ONLY space-delimited hashtags.\n\n"
                    f"Text:\n{transcript[:3000]}\n\nHashtags:"
                )
                hashtags_raw = llm.chat([{'role': 'user', 'content': hashtag_prompt}])
                hashtags = ' '.join(hashtags_raw.replace(',', ' ').split())[:150]

        # Save to database
        with st.spinner("Saving to database..."):
            from ui.database import SermonRepository, get_db
            repo = SermonRepository()

            if not repo.get_sermon(sermon_id):
                _set_feedback(
                    "This sermon is no longer in the local database "
                    "(it may have been removed or reprocessed). "
                    "Refresh the Library page and try again.",
                    kind="error",
                )
                return

            update_data = {}
            if description:
                update_data['description'] = description
            if hashtags:
                update_data['hashtags'] = hashtags
            if update_data:
                repo.update_sermon_metadata(sermon_id, update_data)

            # Update sermon_content table
            db = get_db()
            with db.get_connection() as conn:
                existing = conn.execute(
                    "SELECT transcript_text, description, hashtags FROM sermon_content "
                    "WHERE sermon_id = ?",
                    (sermon_id,)
                ).fetchone()
                cur_transcript = existing['transcript_text'] if existing else transcript
                cur_description = (
                    description if description else (existing['description'] if existing else '')
                )
                cur_hashtags = (
                    hashtags if hashtags else (existing['hashtags'] if existing else '')
                )

                conn.execute("""
                    INSERT OR REPLACE INTO sermon_content
                    (sermon_id, transcript_text, description, hashtags, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    sermon_id,
                    cur_transcript,
                    cur_description,
                    cur_hashtags,
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
                """, (sermon_id, title, speaker, cur_transcript, cur_description, cur_hashtags))
                conn.commit()

            parts = []
            if description:
                parts.append("description")
            if hashtags:
                parts.append("hashtags")
            _set_feedback(f"AI {' and '.join(parts)} generated and saved!")
            # Refresh session state with updated data
            st.session_state.selected_sermon = repo.get_sermon(sermon_id)

    except Exception as e:
        import traceback
        _set_feedback(
            f"Error generating AI content: {e}",
            kind="error",
            details=traceback.format_exc(),
        )


def _toggle_favorite(sermon_id, current_value):
    """Toggle the favorite status of a sermon"""
    from ui.database import SermonRepository
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
    from ui.database import SermonRepository
    repo = SermonRepository()
    repo.update_sermon_metadata(sermon_id, {'notes': notes})


def _batch_delete(sermon_ids):
    """Delete multiple sermons — actual deletion, confirmation handled in display_sermon_list"""
    from ui.database import SermonRepository
    repo = SermonRepository()
    count = 0
    for sid in sermon_ids:
        if repo.delete_sermon(sid):
            count += 1
    st.session_state.selected_sermon_ids = []
    st.session_state.selected_sermon = None
    _set_feedback(f"Deleted {count} sermons")
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
        _set_feedback(f"Push job created: {job_id[:8]}. Monitor it on the Jobs page.")
        st.rerun()
    except Exception as e:
        _set_feedback(f"Failed to create push job: {e}", kind="error")


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
        _set_feedback(f"AI generation job created: {job_id[:8]}. Monitor it on the Jobs page.")
        st.rerun()
    except Exception as e:
        _set_feedback(f"Failed to create AI generation job: {e}", kind="error")


def show_library():
    """Main sermon library interface"""
    _show_feedback()
    st.markdown('<div class="main-header">Sermon Library</div>', unsafe_allow_html=True)
    st.markdown("Browse and search all processed sermons")

    try:
        from sermonaudio_api import SermonAudioAPI

        from ui.database import SermonRepository

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
        sermons = repo.get_all_sermons(limit=1001)
        list_truncated = len(sermons) > 1000
        if list_truncated:
            sermons = sermons[:1000]

        if not sermons:
            st.info("No sermons found. Process some sermons first using the 'New Sermon' page.")
            return

        # Library toolbar: search, sort, filters, export
        sort_labels = {
            ("Date", "Descending"): "Date (newest)",
            ("Date", "Ascending"): "Date (oldest)",
            ("Title", "Ascending"): "Title (A-Z)",
            ("Title", "Descending"): "Title (Z-A)",
            ("Speaker", "Ascending"): "Speaker (A-Z)",
            ("Speaker", "Descending"): "Speaker (Z-A)",
            ("Duration", "Descending"): "Duration (longest)",
            ("Duration", "Ascending"): "Duration (shortest)",
        }
        sort_label_to_pair = {v: k for k, v in sort_labels.items()}
        speakers = sorted({s.get('speaker', '') for s in sermons if s.get('speaker')})

        toolbar = st.columns([2.4, 1, 1, 1])

        with toolbar[0]:
            search_query = st.text_input(
                "Search sermons",
                placeholder="Search titles, speakers, content...",
                help="Search across sermon titles, speakers, and descriptions",
                label_visibility="collapsed",
                key="library_search"
            )

        with toolbar[1]:
            with managed_popover("Sort", use_container_width=True,
                            key="library_sort_popover"):
                sort_labels_list = list(sort_labels.values())
                current_pair = (
                    st.session_state.get('library_sort_by', 'Date'),
                    st.session_state.get('library_sort_order', 'Descending'),
                )
                default_label = sort_labels.get(current_pair, "Date (newest)")
                st.selectbox(
                    "Sort by",
                    sort_labels_list,
                    index=sort_labels_list.index(default_label),
                    key="library_sort_label",
                )
            sort_label = st.session_state.get("library_sort_label", "Date (newest)")
            sort_by, sort_order = sort_label_to_pair.get(sort_label, ("Date", "Descending"))
            st.session_state.library_sort_by = sort_by
            st.session_state.library_sort_order = sort_order

        with toolbar[2]:
            with managed_popover("Filters", use_container_width=True,
                            key="library_filters_popover"):
                fcol1, fcol2 = st.columns(2)
                with fcol1:
                    st.selectbox(
                        "Speaker",
                        ["All"] + speakers,
                        key="library_speaker_filter"
                    )
                    st.selectbox(
                        "Status",
                        ["All", "Processed", "Pending", "Draft", "Error"],
                        key="library_status_filter"
                    )
                with fcol2:
                    st.selectbox(
                        "Date range",
                        ["All", "Last Month", "Last 3 Months", "Last Year"],
                        key="library_date_filter"
                    )
                    st.checkbox(
                        "Favorites",
                        value=st.session_state.show_favorites_only,
                        key="library_fav_toggle",
                        help="Show only favorited sermons"
                    )
            speaker_filter = st.session_state.get("library_speaker_filter", "All")
            date_filter = st.session_state.get("library_date_filter", "All")
            status_filter = st.session_state.get("library_status_filter", "All")
            favorites_only = st.session_state.get("library_fav_toggle", False)
            st.session_state.show_favorites_only = favorites_only

        # Apply filters
        filtered_sermons = apply_filters(
            sermons, search_query, speaker_filter, date_filter, status_filter,
            favorites_only, sort_by, sort_order
        )

        with toolbar[3]:
            with managed_popover("Export", use_container_width=True,
                            key="library_export_popover"):
                st.caption(f"{len(filtered_sermons)} sermons in this view")
                st.download_button(
                    "Download CSV", data=_export_csv(filtered_sermons),
                    file_name=f"sermons_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv", key="dl_csv"
                )
                st.download_button(
                    "Download JSON", data=_export_json(filtered_sermons),
                    file_name=f"sermons_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json", key="dl_json"
                )

        # Main layout with two columns
        col_list, col_detail = st.columns([2, 3])

        with col_list:
            st.markdown("### Sermons")
            if list_truncated:
                st.info("Showing first 1000 sermons. Use search or filters to narrow results.")
            with st.container(key="sermon_list"):
                display_sermon_list(filtered_sermons, sermons)

        with col_detail:
            if st.session_state.selected_sermon:
                if st.session_state.editing_sermon:
                    display_sermon_editor(st.session_state.selected_sermon, api_client, repo)
                else:
                    display_sermon_details(st.session_state.selected_sermon)
            else:
                st.markdown("### Select a Sermon")
                st.info("Select a sermon from the list to view details")

    except ImportError as e:
        st.error(f"Import error: {e}")
        st.error("Please ensure all required modules are available.")
    except Exception as e:
        st.error(f"Error loading sermon library: {e}")
        import traceback
        st.code(traceback.format_exc())

def apply_filters(sermons, search_query, speaker_filter, date_filter, status_filter,
                  favorites_only=False, sort_by="Date", sort_order="Descending"):
    """Apply search and filter criteria to sermons"""
    filtered_sermons = sermons[:]

    # FTS5 search if query is provided
    if search_query:
        try:
            from ui.database import SermonRepository
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
                   (
                       s.get('content')
                       and search_lower in str(s['content'].get('key_topics', '') or '').lower()
                   )
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

        def _within_cutoff(s):
            parsed = _parse_date(s.get('recorded_date'))
            return parsed is not None and parsed >= cutoff_date

        filtered_sermons = [s for s in filtered_sermons if _within_cutoff(s)]

    # Status filter
    if status_filter != "All":
        status_map = {
            "Processed": ["processed"],
            "Pending": ["pending"],
            "Draft": ["draft"],
            "Error": ["error"],
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
            parsed = _parse_date(s.get('recorded_date'))
            return parsed if parsed else datetime.min
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

def _parse_date(date_str):
    """Parse a date string to datetime, returning None for invalid values"""
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        parsed = date_str
    elif isinstance(date_str, date):
        parsed = datetime.combine(date_str, datetime.min.time())
    else:
        try:
            parsed = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _format_date(date_str):
    """Try to format a date string as YYYY-MM-DD"""
    parsed = _parse_date(date_str)
    if parsed:
        return parsed.strftime('%Y-%m-%d')
    return date_str or 'Unknown'

def display_sermon_list(filtered_sermons, all_sermons):
    """Display the sermon list with compact clickable rows"""

    if not filtered_sermons:
        st.info("No sermons match your search or filters.")
        if st.button("Clear Search & Filters", key="library_clear_filters"):
            for key in (
                'library_search', 'library_speaker_filter', 'library_date_filter',
                'library_status_filter', 'library_fav_toggle', 'library_page',
            ):
                st.session_state.pop(key, None)
            st.session_state.show_favorites_only = False
            st.rerun()
        return

    st.markdown(f"**{len(filtered_sermons)}** sermons shown (of {len(all_sermons)} total)")

    # Bulk action bar
    selected_ids = st.session_state.get('selected_sermon_ids', [])
    if selected_ids:
        if st.session_state.get('confirm_batch_delete'):
            st.warning(f"Delete {len(selected_ids)} sermons? This cannot be undone.")
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
            st.info(f"{len(selected_ids)} sermon(s) selected")
            bcol1, bcol2, bcol3, bcol4 = st.columns([1, 1, 1, 2])
            with bcol1:
                if st.button("Batch Delete", type="primary", use_container_width=True):
                    st.session_state.confirm_batch_delete = True
                    st.rerun()
            with bcol2:
                if st.button("Batch Push", use_container_width=True):
                    _batch_push(selected_ids)
            with bcol3:
                if st.button("Batch AI", use_container_width=True):
                    _batch_generate_ai(selected_ids)
            with bcol4:
                if st.button("Clear Selection", use_container_width=True):
                    st.session_state.selected_sermon_ids = []
                    st.rerun()

    items_per_page = 20
    total_pages = (len(filtered_sermons) + items_per_page - 1) // items_per_page

    if st.session_state.get('library_page', 0) > total_pages - 1:
        st.session_state.library_page = max(0, total_pages - 1)

    page = 0
    if total_pages > 1:
        prev, mid, next = st.columns([1, 3, 1])
        with prev:
            if st.button(
                "Previous", width='stretch',
                disabled=(st.session_state.get('library_page', 0) == 0),
            ):
                st.session_state.library_page = max(0, st.session_state.get('library_page', 0) - 1)
        with mid:
            st.caption(f"Page {st.session_state.get('library_page', 0) + 1} of {total_pages}")
        with next:
            if st.button(
                "Next", width='stretch',
                disabled=(st.session_state.get('library_page', 0) >= total_pages - 1),
            ):
                st.session_state.library_page = min(
                    total_pages - 1, st.session_state.get('library_page', 0) + 1
                )
        page = st.session_state.get('library_page', 0)
    else:
        st.session_state.library_page = 0

    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_sermons))
    page_sermons = filtered_sermons[start_idx:end_idx]

    header_cols = st.columns([0.3, 1.5, 4.2, 1.4, 1.2], vertical_alignment="center")
    with header_cols[2]:
        st.caption("Title · Speaker · Date")
    with header_cols[3]:
        st.caption("Duration")

    with st.container(key="sermon_rows"):
        for sermon in page_sermons:
            sid = sermon['id']
            is_selected = sid in st.session_state.selected_sermon_ids

            cols = st.columns([0.3, 1.5, 4.2, 1.4, 1.2], vertical_alignment="center")
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
                if sermon.get('upload_status') == 'failed' or status in ('failed', 'error'):
                    status_cls, status_label = 'status-error', 'Error'
                elif status in ('completed', 'processed'):
                    status_cls, status_label = 'status-ok', 'Processed'
                elif status == 'processing':
                    status_cls, status_label = 'status-progress', 'Processing'
                else:
                    status_cls, status_label = 'status-neutral', status.capitalize()
                st.markdown(
                    f'<span class="{status_cls}">{status_label}</span>',
                    unsafe_allow_html=True,
                )
            with cols[2]:
                title = sermon.get('title', 'Untitled')
                speaker = sermon.get('speaker', '')
                date = _format_date(sermon.get('recorded_date'))
                safe_title = html.escape(str(title))
                st.markdown(
                    f'<span class="sermon-title" title="{safe_title}">{title}</span>',
                    unsafe_allow_html=True,
                )
                meta = f"{speaker} · {date}" if (speaker or date) else "\u00a0"
                st.markdown(
                    f'<span class="sermon-meta">{meta}</span>',
                    unsafe_allow_html=True,
                )
            with cols[3]:
                dur = sermon.get('duration', '')
                if dur:
                    st.caption(_format_duration(dur))
            with cols[4]:
                if st.button("View", key=f"sel_{sid}", help="View details"):
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
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours)}:{int(minutes):02d}:{int(secs):02d}"
    return f"{int(minutes):02d}:{int(secs):02d}"

def _format_edit_timestamp(seconds: float) -> str:
    try:
        value = max(float(seconds or 0), 0.0)
    except (TypeError, ValueError):
        value = 0.0
    total = int(value)
    tenths = int(round((value - total) * 10))
    if tenths >= 10:
        total += 1
        tenths = 0
    return f"{total // 60:02d}:{total % 60:02d}.{tenths}"


def _edit_status_badge(status: str) -> str:
    labels = {
        "pending_review": "Pending review",
        "auto_applied": "Auto-applied",
        "applied": "Applied",
        "applied_local": "Rendered, not uploaded",
        "rejected": "Rejected",
        "reverted": "Reverted",
    }
    return labels.get(status, status.replace("_", " ").title() if status else "Unknown")


def _default_apply_mode(sermon_id: str) -> str:
    """Drafts default to a local render; uploaded sermons default to render+upload."""
    return "render_only" if str(sermon_id or "").startswith("draft_") else "upload"


def _sermon_has_upload(
    repo: Any, sermon: dict[str, Any], applied_media_id: str | None = None
) -> bool:
    """True once anything is actually on SermonAudio for this sermon.

    Checks the row hints first (``upload_status`` from the library query or a
    nested ``upload_info`` record), then ``upload_info`` rows for the sermon
    id and, for applied_local plans, the rendered record id: Upload now
    publishes the rendered record, so its row lands under
    ``applied_media_id`` rather than the source sermon id.
    """
    if sermon.get("upload_info") or sermon.get("upload_status"):
        return True
    candidates: list[str] = []
    for value in (sermon.get("id") or sermon.get("sermon_id"), applied_media_id):
        text = str(value or "")
        if text and text not in candidates:
            candidates.append(text)
    for candidate in candidates:
        try:
            full = repo.get_sermon(candidate) if repo is not None else None
        except Exception:
            continue
        if isinstance(full, dict) and full.get("upload_info"):
            return True
    return False


def _allow_apply_upload(status: str, ever_uploaded: bool) -> bool:
    """Whether the Adjust panel may offer render+upload.

    An applied_local plan that was never uploaded stays render-only: the
    upload choice belongs to Upload now (or a fresh plan after upload), so a
    re-apply cannot silently publish a draft that only exists locally.
    """
    return not (status == "applied_local" and not ever_uploaded)


def _load_edit_duration(sermon: dict[str, Any]) -> float | None:
    try:
        duration = float(sermon.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        return None
    return duration


def _apply_core():
    try:
        import auto_edit_apply as core
    except ImportError:
        from ui import auto_edit_apply as core
    return core


def _read_edit_plan_metadata(sermon: dict[str, Any]) -> dict[str, Any]:
    return _apply_core()._read_edit_plan_metadata(sermon)


def _full_sermon_or_none(sermon: dict[str, Any], repo: Any) -> dict[str, Any] | None:
    return _apply_core()._full_sermon_or_none(sermon, repo)


def _resolve_edit_media_path(sermon: dict[str, Any], repo: Any) -> str | None:
    return _apply_core()._resolve_edit_media_path(sermon, repo)


def _load_library_config() -> dict[str, Any]:
    try:
        from config_utils import load_config_from_file

        return load_config_from_file()
    except Exception:
        return {}


def _effective_auto_edit_cfg(sermon: dict[str, Any], repo: Any) -> dict[str, Any]:
    """Library config auto_edit defaults overlaid with the draft's stored ending-card prefs."""
    auto_cfg = dict(_load_library_config().get("auto_edit") or {})
    try:
        full = _full_sermon_or_none(sermon, repo) or sermon
        prefs = _read_edit_plan_metadata(full).get("auto_edit")
    except Exception:
        prefs = None
    if isinstance(prefs, dict):
        for key in ("logo_path", "logo_hold", "fade_to_black", "fade_out_tail_seconds"):
            if key in prefs:
                auto_cfg[key] = prefs[key]
    return auto_cfg


def _render_media_player(sermon: dict[str, Any]) -> None:
    try:
        from urllib.parse import urlparse

        from ui.media_server import get_media_server

        server = get_media_server()
        if server is None or not server.base_url:
            return
        hostname = urlparse(server.base_url).hostname or ""
        if hostname in {"127.0.0.1", "localhost"}:
            st.caption(
                "Media preview unavailable: the media server is only reachable on localhost. "
                "Set MEDIA_SERVER_PUBLIC_HOST and publish its port to enable previews."
            )
            return
        candidates: list[Path] = []
        try:
            from ui.database import SermonRepository

            repo = SermonRepository()
            sermon_id = sermon.get("id") or sermon.get("sermon_id") or ""
            for row in repo.get_sermon_files(sermon_id):
                value = row.get("file_path")
                if value:
                    candidates.append(Path(value))
        except Exception:
            pass
        file_paths = sermon.get("file_paths") or sermon.get("files") or {}
        for key in (
            "processed_video",
            "enhanced_video",
            "processed_file",
            "enhanced_audio",
            "original_video",
            "original_audio",
            "video",
            "audio",
        ):
            value = file_paths.get(key)
            if value:
                candidates.append(Path(value))
        for candidate in candidates:
            try:
                if not candidate.is_file():
                    continue
            except OSError:
                continue
            token = server.register(sermon.get("id") or "", candidate)
            url = f"{server.base_url}/m/{token}"
            if candidate.suffix.lower() in {".mp3", ".wav"}:
                st.audio(url)
            else:
                st.video(url)
            return
    except Exception as e:
        st.caption(f"Media player unavailable: {e}")


def _cached_edit_snippets(
    snippet_dir: Path, signature: dict[str, float]
) -> list[Path] | None:
    sidecar = snippet_dir / "snippets.json"
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data != signature:
        return None
    found = [
        snippet_dir / name
        for name in ("snippet_start.mp4", "snippet_end.mp4", "snippet_ending.mp4")
        if (snippet_dir / name).is_file()
    ]
    return found or None


def _render_edit_snippets(sermon: dict[str, Any], plan: dict[str, Any], repo: Any) -> None:
    media_path = _resolve_edit_media_path(sermon, repo)
    if not media_path:
        return
    try:
        from src.auto_edit import EditPlan, render_review_snippets
    except Exception:
        st.caption("Review snippet module unavailable")
        return
    auto_cfg = _effective_auto_edit_cfg(sermon, repo)
    logo_value = auto_cfg.get("logo_path")
    logo = Path(logo_value) if logo_value else None
    source = Path(media_path)
    snippet_dir = source.parent / "snippets"
    start = float(plan.get("proposed_start") or 0.0)
    end = float(plan.get("proposed_end") or 0.0)
    signature = {
        "start": start,
        "end": end,
        "logo": str(auto_cfg.get("logo_path") or ""),
        "fade_to_black": bool(auto_cfg.get("fade_to_black", True)),
    }
    snippet_paths = _cached_edit_snippets(snippet_dir, signature)
    if snippet_paths is None:
        edit_plan = EditPlan(
            start=start,
            end=end,
            fade_in=float(auto_cfg.get("fade_in", 1.0)),
            logo_hold=float(auto_cfg.get("logo_hold", 3.0)),
            fade_to_black=bool(auto_cfg.get("fade_to_black", True)),
            needs_review=True,
        )
        try:
            snippet_dir.mkdir(parents=True, exist_ok=True)
            snippet_paths = render_review_snippets(
                source,
                edit_plan,
                snippet_dir,
                logo,
                fade_out_tail_seconds=float(auto_cfg.get("fade_out_tail_seconds", 2.0)),
            )
            (snippet_dir / "snippets.json").write_text(
                json.dumps(signature), encoding="utf-8"
            )
        except Exception as e:
            st.caption(f"Review snippet render failed: {e}")
            return
    captions = {
        "snippet_start": (
            "Start cut preview ("
            f"{_format_edit_timestamp(max(start - 10.0, 0.0))} to "
            f"{_format_edit_timestamp(start + 10.0)})"
        ),
        "snippet_end": (
            "End cut preview ("
            f"{_format_edit_timestamp(max(end - 10.0, 0.0))} to "
            f"{_format_edit_timestamp(end + 10.0)})"
        ),
        "snippet_ending": (
            "Proposed ending ("
            f"{_format_edit_timestamp(max(start, end - 30.0))} to "
            f"{_format_edit_timestamp(end)})"
        ),
    }
    for path in snippet_paths:
        st.caption(captions.get(path.stem, path.stem))
        try:
            st.video(str(path))
        except Exception:
            st.caption(f"Snippet not downloadable from UI: {path.name}")


def _write_edit_plan_file(plan_id: int, start: float, end: float,
                          audio_offset: float = 0.0) -> str | None:
    return _apply_core()._write_edit_plan_file(plan_id, start, end, audio_offset)


def _enqueue_edit_refine(sermon_id: str, notes: str = "") -> str | None:
    """Queue a re-detection job that uses reviewer notes as refinement context."""
    try:
        from job_queue import JobType, get_job_queue

        job_queue = get_job_queue()
        return job_queue.add_job(
            job_type=JobType.AUTO_EDIT,
            title=f"Re-detect cut points: {sermon_id}",
            description="Re-run cut detection with reviewer notes",
            parameters={
                'refine': True,
                'sermon_id': sermon_id,
                'notes': notes,
                'config': st.session_state.get('config', {}),
            },
            priority=7,
        )
    except Exception as e:
        _set_feedback(f"Could not start re-detection: {e}", kind="error")
        return None


def _looks_like_processed_artifact(value: str) -> bool:
    return _apply_core()._looks_like_processed_artifact(value)


def _resolve_apply_source(sermon: dict[str, Any], repo: Any) -> tuple[str | None, bool]:
    """Media to trim for an apply plus whether it is already enhanced.

    The processed file already carries the enhanced audio, so trimming it skips
    the DeepFilterNet stage entirely (and its GPU memory).
    """
    return _apply_core()._resolve_apply_source(sermon, repo)


def _build_apply_kwargs(
    full_sermon: dict[str, Any],
    media_path: str,
    plan_file: str | None,
    render_only: bool,
    audio_offset: float,
    skip_audio: bool = False,
) -> dict[str, Any]:
    return _apply_core()._build_apply_kwargs(
        full_sermon, media_path, plan_file, render_only, audio_offset,
        skip_audio=skip_audio,
    )


def _active_apply_job(sermon_id: str, plan_revision: int | None = None,
                      repo: Any | None = None) -> dict[str, Any] | None:
    try:
        repo = repo or _apply_repo()
    except Exception:
        return None
    try:
        return _apply_core().get_active_apply_job(repo, str(sermon_id), plan_revision)
    except Exception:
        return None


def _apply_repo() -> Any:
    try:
        from ui.database import SermonRepository
    except ImportError:
        from database import SermonRepository
    return SermonRepository()


def _enqueue_apply_job(
    sermon: dict[str, Any],
    plan: dict[str, Any],
    repo: Any,
    start: float,
    end: float,
    audio_offset: float,
    render_only: bool,
    re_detect: bool = False,
) -> str | None:
    try:
        from job_queue import JobType, get_job_queue
    except ImportError:
        from ui.job_queue import JobType, get_job_queue
    sermon_id = str(sermon.get("id") or sermon.get("sermon_id") or "")
    revision = plan.get("revision") if isinstance(plan, dict) else None
    existing = _active_apply_job(sermon_id, revision, repo)
    if existing:
        _set_feedback(
            f"Render already {existing.get('status', 'queued')} for this sermon "
            "(revision "
            f"{revision}). Watch the Jobs page; wait until it finishes "
            "before queueing another.",
            kind="warning",
        )
        return None
    params = _apply_core().build_apply_job_params(
        sermon_id,
        plan.get("id") if isinstance(plan, dict) else None,
        revision,
        float(start),
        float(end),
        float(audio_offset or 0.0),
        bool(render_only),
        bool(re_detect),
        dict(st.session_state.get("config", {})),
    )
    try:
        full = _full_sermon_or_none(sermon, repo) or sermon
        title = str(full.get("title") or sermon_id)
    except Exception:
        title = sermon_id
    try:
        job_queue = get_job_queue()
        return job_queue.add_job(
            job_type=JobType.AUTO_EDIT_APPLY,
            title=f"Apply edit: {title}",
            description=(
                f"Render only {start:.1f}s-{end:.1f}s" if render_only
                else f"Apply edit {start:.1f}s-{end:.1f}s and upload"
            ),
            parameters=params,
            priority=7,
        )
    except Exception as e:
        _set_feedback(f"Could not queue render: {e}", kind="error")
        return None


def _apply_approved_edit(
    sermon: dict[str, Any],
    plan: dict[str, Any],
    repo: Any,
    start: float,
    end: float,
    re_detect: bool = False,
    audio_offset: float | None = None,
    render_only: bool = False,
) -> None:
    if audio_offset is None:
        audio_offset = float(plan.get("audio_offset") or 0.0)
    job_id = _enqueue_apply_job(
        sermon, plan, repo, float(start), float(end), float(audio_offset),
        bool(render_only), bool(re_detect),
    )
    if job_id:
        _set_feedback(
            f"Render queued ({str(job_id)[:8]}). Watch the Jobs page; "
            "this page stays usable while it runs."
        )


def _plan_working_values(plan: dict[str, Any],
                         full_reset: bool = False) -> tuple[float, float, float]:
    """Working values for the offset editor: (start, end, audio_offset)."""
    start = float(plan.get("proposed_start") or 0.0)
    end = float(plan.get("proposed_end") or 0.0)
    offset = 0.0 if full_reset else float(plan.get("audio_offset") or 0.0)
    return start, end, offset


def _preview_offset_snippets(sermon: dict[str, Any], plan: dict[str, Any], repo: Any,
                             start: float, end: float, audio_offset: float) -> list[Path]:
    """Render offset-preview snippets without touching the plan or source files."""
    try:
        from src.auto_edit import EditPlan, render_review_snippets, shift_snippet_audio
    except Exception:
        return []
    media_path = _resolve_edit_media_path(sermon, repo)
    if not media_path:
        return []
    source = Path(media_path)
    snippet_dir = source.parent / "snippets"
    auto_cfg = _effective_auto_edit_cfg(sermon, repo)
    logo_value = auto_cfg.get("logo_path")
    signature = {
        "start": float(start),
        "end": float(end),
        "logo": str(logo_value or ""),
        "fade_to_black": bool(auto_cfg.get("fade_to_black", True)),
    }
    try:
        bases = _cached_edit_snippets(snippet_dir, signature)
        if bases is None:
            snippet_dir.mkdir(parents=True, exist_ok=True)
            edit_plan = EditPlan(
                start=float(start),
                end=float(end),
                fade_in=float(auto_cfg.get("fade_in", 1.0)),
                logo_hold=float(auto_cfg.get("logo_hold", 3.0)),
                fade_to_black=bool(auto_cfg.get("fade_to_black", True)),
                needs_review=True,
            )
            bases = render_review_snippets(
                source,
                edit_plan,
                snippet_dir,
                Path(logo_value) if logo_value else None,
                fade_out_tail_seconds=float(auto_cfg.get("fade_out_tail_seconds", 2.0)),
            )
            (snippet_dir / "snippets.json").write_text(
                json.dumps(signature), encoding="utf-8"
            )
        shifted: list[Path] = []
        for base in bases:
            if abs(audio_offset) < 1e-6:
                shifted.append(base)
                continue
            target = base.with_name(f"{base.stem}_off_{audio_offset:+.1f}.mp4")
            if not target.exists() or target.stat().st_mtime < base.stat().st_mtime:
                try:
                    shift_snippet_audio(base, float(audio_offset), target)
                except Exception:
                    continue
            shifted.append(target)
        return shifted
    except Exception:
        return []


def show_edit_review_panel(sermon: dict[str, Any]) -> None:
    """Review panel for the sermon's current auto-edit plan"""
    if not sermon or not isinstance(sermon, dict):
        return
    sermon_id = sermon.get("id") or sermon.get("sermon_id")
    if not sermon_id:
        return

    try:
        from src.auto_edit import EditPlan, validate_plan
        from ui.database import SermonRepository

        repo = SermonRepository()
        plan = repo.get_current_edit_plan(sermon_id)
        if not plan:
            return
    except Exception as e:
        st.warning(f"Could not load edit plan: {e}")
        return

    status = plan.get("status") or "pending_review"
    proposed_start = float(plan.get("proposed_start") or 0.0)
    proposed_end = float(plan.get("proposed_end") or 0.0)
    confidence = float(plan.get("confidence") or 0.0)

    history = []
    try:
        history = repo.get_edit_plan_history(sermon_id)
    except Exception:
        history = []
    st.markdown(
        f"#### Auto Edit Review — {_edit_status_badge(status)} "
        f"(revision {plan.get('revision', 1)} of {len(history)})"
    )
    with st.container():
        if status == "auto_applied":
            st.warning(
                f"This edit was applied automatically (confidence {confidence:.2f}). "
                "Restore the original if it cut the wrong material, or re-edit below."
            )

        try:
            latest_apply = repo.get_latest_apply_job(str(sermon_id))
        except Exception:
            latest_apply = None
        if latest_apply:
            st.caption(
                f"Latest apply: {latest_apply.get('status')} "
                f"({int(latest_apply.get('progress') or 0)}%) | "
                f"started {latest_apply.get('created_at')}"
            )
        try:
            active_apply = _active_apply_job(
                str(sermon_id), plan.get("revision"), repo
            )
        except Exception:
            active_apply = None
        apply_busy = bool(active_apply) and str(
            active_apply.get("status") or ""
        ) in ("queued", "running")
        if apply_busy:
            st.info(
                f"Render {active_apply.get('status')} for this sermon "
                "(background job). This page stays usable; check the Jobs "
                "page for live progress."
            )
            if st.button("Refresh status", key=f"editplan_apply_refresh_{sermon_id}"):
                st.rerun()

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Proposed start", _format_edit_timestamp(proposed_start))
        with m2:
            st.metric("Proposed end", _format_edit_timestamp(proposed_end))
        with m3:
            st.metric("Confidence", f"{confidence:.2f}")
        with m4:
            qa = plan.get("qa_judgment") or "cut"
            qa_label = f"QA: {qa}" + (" (needs review)" if plan.get("needs_review") else "")
            st.metric("QA", qa_label)

        evidence = plan.get("evidence") or ""
        reasoning = plan.get("reasoning") or ""
        if evidence:
            st.info(f"**Evidence:** {evidence}")
        if reasoning:
            st.caption(f"Reasoning: {reasoning}")

        try:
            _render_edit_snippets(sermon, plan, repo)
        except Exception as e:
            st.caption(f"Review snippets unavailable: {e}")

        if status == "rejected":
            st.info("This plan was rejected. Regenerate to get a fresh proposal.")
            reject_notes_prev = plan.get("notes") or ""
            if reject_notes_prev:
                st.caption(f"Your notes: {reject_notes_prev}")
            if st.button(
                "Regenerate with notes",
                type="primary",
                key=f"editplan_regen_rejected_{sermon_id}",
            ):
                if _enqueue_edit_refine(sermon_id, reject_notes_prev):
                    _set_feedback("Re-running detection with your notes. Watch the Jobs page.")
                st.rerun()
            return

        if status == "applied_local":
            st.info(
                "Rendered locally, not uploaded. The local record is in the Library; "
                "upload it when you are ready."
            )
            rendered_id = str(plan.get("applied_media_id") or "")
            if st.button(
                "Upload now",
                type="primary",
                key=f"editplan_upload_now_{sermon_id}",
                width="stretch",
            ):
                import sermon_updater

                if not rendered_id:
                    _set_feedback(
                        "No locally rendered record linked to this plan. Re-render first.",
                        kind="error",
                    )
                else:
                    with st.spinner("Uploading rendered media to SermonAudio..."):
                        upload_result = sermon_updater.publish_dry_run_sermon(rendered_id)
                    if upload_result.get("success"):
                        repo.update_edit_plan_status(
                            plan.get("id"),
                            "applied",
                            notes=(
                                (plan.get("notes") or "") + "; uploaded from Upload now"
                            ).strip("; "),
                        )
                        _set_feedback("Uploaded to SermonAudio.")
                    else:
                        _set_feedback(
                            f"Upload failed: "
                            f"{upload_result.get('error') or 'unknown error'}",
                            kind="error",
                        )
                st.rerun()

        full_sermon = _full_sermon_or_none(sermon, repo) or {}
        duration = _load_edit_duration(full_sermon) or _load_edit_duration(sermon)
        max_ts = duration if duration and duration > 0 else None

        if status in ("applied", "auto_applied", "reverted", "applied_local"):
            last_start = plan.get("final_start")
            last_end = plan.get("final_end")
            if last_start is None:
                last_start = proposed_start
            if last_end is None:
                last_end = proposed_end
            ever_uploaded = _sermon_has_upload(repo, sermon, plan.get("applied_media_id"))
            re_render_only = not _allow_apply_upload(status, ever_uploaded)
            st.markdown("#### Adjust and re-apply")
            re_detect = st.checkbox(
                "Re-detect with LLM instead", key=f"editplan_redetect_{sermon_id}"
            )
            start_val = st.number_input(
                "New start (s)",
                min_value=0.0,
                max_value=max_ts if max_ts else max(float(last_start), 1.0) + 3600.0,
                value=min(float(last_start), max_ts or float(last_start)),
                step=0.1,
                key=f"editplan_re_start_{sermon_id}",
            )
            end_val = st.number_input(
                "New end (s)",
                min_value=0.0,
                max_value=max_ts if max_ts else max(float(last_end), float(start_val)) + 3600.0,
                value=min(float(last_end), max_ts or max(float(last_end), float(start_val))),
                step=0.1,
                key=f"editplan_re_end_{sermon_id}",
            )
            audio_offset_re = st.number_input(
                "Audio offset (s)",
                min_value=-5.0,
                max_value=5.0,
                value=float(plan.get("audio_offset") or 0.0),
                step=0.1,
                key=f"editplan_re_audio_offset_{sermon_id}",
                help="Positive delays the audio later relative to video; negative moves it earlier.",  # noqa: E501
            )
            apply_mode_re = None
            if re_render_only:
                st.caption(
                    "Not uploaded yet: re-renders stay local. "
                    "Use Upload now above when you are ready to publish."
                )
            else:
                apply_mode_re = st.radio(
                    "Apply target",
                    options=["render_only", "upload"],
                    format_func=lambda value: (
                        "Render only (no upload)"
                        if value == "render_only"
                        else "Render + upload to SermonAudio"
                    ),
                    index=0 if _default_apply_mode(str(sermon_id)) == "render_only" else 1,
                    key=f"editplan_re_apply_mode_{sermon_id}",
                    horizontal=True,
                )
            candidate = EditPlan(
                start=float(start_val),
                end=float(end_val),
                audio_offset=float(audio_offset_re),
            )
            problems = [] if re_detect else validate_plan(candidate, duration)
            for problem in problems:
                st.warning(problem)
            re_notes = st.text_input("Notes (optional)", key=f"editplan_re_notes_{sermon_id}")
            if apply_busy:
                re_help = "Disabled while a render is queued/running for this sermon."
            else:
                re_help = (
                    "Disabled while validation reports problems: " + "; ".join(problems)
                    if problems
                    else "Queue the adjusted edit as a background job"
                )
            if st.button(
                "Re-render (no upload)" if re_render_only else "Apply adjusted edit",
                type="primary",
                key=f"editplan_re_apply_{sermon_id}",
                disabled=bool(problems) or apply_busy,
                help=re_help,
            ):
                try:
                    new_plan_id = repo.save_edit_plan_revision(
                        sermon_id,
                        {
                            "proposed_start": float(start_val),
                            "proposed_end": float(end_val),
                            "final_start": float(start_val) if not re_detect else None,
                            "final_end": float(end_val) if not re_detect else None,
                            "confidence": confidence,
                            "needs_review": True,
                            "evidence": evidence,
                            "qa_judgment": qa,
                            "reasoning": reasoning,
                            "audio_offset": float(audio_offset_re),
                            "status": "pending_review",
                            "source_path": plan.get("source_path"),
                            "applied_media_id": plan.get("applied_media_id"),
                            "notes": (
                                f"{re_notes}; re-detect with LLM requested in Library"
                                if re_detect
                                else f"{re_notes}; re-edit from Library"
                            ).strip("; "),
                        },
                    )
                    try:
                        plan = repo.get_current_edit_plan(sermon_id) or {
                            **plan, "id": new_plan_id,
                        }
                    except Exception:
                        plan = {**plan, "id": new_plan_id}
                except Exception as e:
                    _set_feedback(f"Could not save plan revision: {e}", kind="error")
                    return
                _apply_approved_edit(
                    sermon,
                    plan,
                    repo,
                    float(start_val),
                    float(end_val),
                    re_detect=re_detect,
                    audio_offset=float(audio_offset_re),
                    render_only=True if re_render_only else (apply_mode_re == "render_only"),
                )
                st.rerun()

            if status in ("auto_applied", "applied"):
                st.markdown("#### Restore original")
                restore_confirm = st.checkbox(
                    "I understand this will re-upload the original media to SermonAudio",
                    key=f"editplan_restore_confirm_{sermon_id}",
                )
                if st.button(
                    "Restore original",
                    key=f"editplan_restore_{sermon_id}",
                    disabled=not restore_confirm,
                ):
                    import sermon_updater

                    original_path = _resolve_edit_media_path(sermon, repo)
                    if not original_path:
                        _set_feedback(
                            "No original media file found locally to restore.",
                            kind="error",
                        )
                        return
                    try:
                        with st.spinner("Re-uploading original media..."):
                            ok = sermon_updater.reupload_media_for_sermon(sermon_id, original_path)
                    except Exception as e:
                        _set_feedback(f"Restore failed: {e}", kind="error")
                        return
                    if ok:
                        repo.update_edit_plan_status(
                            plan.get("id"),
                            "reverted",
                            notes=plan.get("notes") or "restored original",
                        )
                        _set_feedback("Original media restored on SermonAudio")
                    else:
                        _set_feedback(
                            "Media re-upload failed. Check your API credentials " "and try again.",
                            kind="error",
                        )
                    st.rerun()
            return

        st.markdown("#### Review timestamps")
        gen = st.session_state.get(f"editplan_gen_{sermon_id}", 0)
        default_start, default_end, default_offset = _plan_working_values(plan)
        ts_col1, ts_col2, off_col = st.columns([1, 1, 1])
        with ts_col1:
            start_val = st.number_input(
                "Start (s)",
                min_value=0.0,
                max_value=max_ts if max_ts else proposed_end + 3600.0,
                value=min(default_start, max_ts or default_start),
                step=0.1,
                key=f"editplan_start_{sermon_id}_{gen}",
            )
        with ts_col2:
            end_val = st.number_input(
                "End (s)",
                min_value=0.0,
                max_value=max_ts if max_ts else max(proposed_end, start_val) + 3600.0,
                value=min(default_end, max_ts or default_end),
                step=0.1,
                key=f"editplan_end_{sermon_id}_{gen}",
            )
        with off_col:
            audio_offset_val = st.number_input(
                "Audio offset (s)",
                min_value=-5.0,
                max_value=5.0,
                value=default_offset,
                step=0.1,
                key=f"editplan_audio_offset_{sermon_id}_{gen}",
                help="Positive delays the audio later relative to video; negative moves it earlier.",  # noqa: E501
            )
        st.caption(
            "Audio offset: positive shifts audio later than video (use when sound comes early), "
            "negative shifts it earlier."
        )
        apply_mode = st.radio(
            "Apply target",
            options=["render_only", "upload"],
            format_func=lambda value: (
                "Render only (no upload)"
                if value == "render_only"
                else "Render + upload to SermonAudio"
            ),
            index=0 if _default_apply_mode(str(sermon_id)) == "render_only" else 1,
            key=f"editplan_apply_mode_{sermon_id}",
            horizontal=True,
            help=(
                "Render only encodes the edit locally and skips SermonAudio; "
                "use Upload now when you are ready to publish."
            ),
        )

        candidate = EditPlan(
            start=float(start_val),
            end=float(end_val),
            audio_offset=float(audio_offset_val),
        )
        problems = validate_plan(candidate, duration)
        for problem in problems:
            st.warning(problem)
        if not problems:
            st.success("Plan validates cleanly")

        preview_cols = st.columns(4)
        with preview_cols[0]:
            preview_clicked = st.button(
                "Preview offset",
                key=f"editplan_preview_{sermon_id}",
                width="stretch",
                help="Render short snippets with the current offset; no plan or file changes.",
            )
        with preview_cols[1]:
            save_values_clicked = st.button(
                "Apply to plan",
                key=f"editplan_save_values_{sermon_id}",
                width="stretch",
                help="Save the current values as a new plan revision; nothing is uploaded.",
            )
        with preview_cols[2]:
            reset_values_clicked = st.button(
                "Reset values",
                key=f"editplan_reset_values_{sermon_id}",
                width="stretch",
                help="Revert the fields to the plan's saved values.",
            )
        with preview_cols[3]:
            full_reset_clicked = st.button(
                "Reset to proposal",
                key=f"editplan_full_reset_{sermon_id}",
                width="stretch",
                help="Restore the original proposal timestamps and set the audio offset to 0.",
            )

        if preview_clicked:
            with st.spinner("Rendering offset preview (no plan changes)..."):
                preview_paths = _preview_offset_snippets(
                    sermon, plan, repo, float(start_val), float(end_val),
                    float(audio_offset_val),
                )
            st.session_state[f"editplan_preview_paths_{sermon_id}"] = [
                str(path) for path in preview_paths
            ]
            _set_feedback("Preview rendered. The plan and media files were not changed.")

        preview_paths = st.session_state.get(f"editplan_preview_paths_{sermon_id}") or []
        if preview_paths:
            st.caption(
                f"Offset preview @ {float(audio_offset_val):+.1f}s "
                f"(plan and files unchanged):"
            )
            for path in preview_paths:
                if Path(path).exists():
                    st.video(str(path))

        if save_values_clicked:
            try:
                repo.save_edit_plan_revision(
                    sermon_id,
                    {
                        "proposed_start": float(start_val),
                        "proposed_end": float(end_val),
                        "final_start": float(start_val),
                        "final_end": float(end_val),
                        "audio_offset": float(audio_offset_val),
                        "confidence": confidence,
                        "needs_review": True,
                        "evidence": evidence,
                        "qa_judgment": qa,
                        "reasoning": reasoning,
                        "status": "pending_review",
                        "source_path": plan.get("source_path"),
                        "applied_media_id": plan.get("applied_media_id"),
                        "notes": (
                            (plan.get("notes") or "") + "; values saved from Library"
                        ).strip("; "),
                    },
                )
            except Exception as e:
                _set_feedback(f"Could not save plan revision: {e}", kind="error")
                return
            _set_feedback("Values saved as a new plan revision (no upload).")
            st.rerun()

        if reset_values_clicked:
            st.session_state[f"editplan_gen_{sermon_id}"] = gen + 1
            _set_feedback("Fields reset to the plan's saved values.")
            st.rerun()

        if full_reset_clicked:
            st.session_state[f"editplan_gen_{sermon_id}"] = gen + 1
            _set_feedback(
                "Reset to the original proposal: timestamps restored, audio offset 0."
            )
            st.rerun()

        prior_notes = []
        for row in history:
            row_notes = str(row.get("notes") or "").strip()
            row_offset = float(row.get("audio_offset") or 0.0)
            label = f"r{row.get('revision')}: {row_notes}" if row_notes else f"r{row.get('revision')}"  # noqa: E501
            if abs(row_offset) > 1e-6:
                label += f" [audio offset {row_offset:+.1f}s]"
            if label and label not in prior_notes:
                prior_notes.append(label)
        if prior_notes:
            with managed_expander("Review notes history", expanded=False,
                             key=f"review_notes_history_{sermon_id}"):
                for idx, note in enumerate(prior_notes, start=1):
                    st.caption(f"{idx}. {note}")

        reject_notes = st.text_input(
            "Rejection notes / re-detection instructions (optional)",
            key=f"editplan_reject_notes_{sermon_id}",
            help=(
                "Rejecting with notes re-runs detection and sends these instructions "
                "to the LLM (for example: keep only the second class)."
            ),
        )

        col_approve, col_reject, col_regen = st.columns([1, 1, 1])
        if apply_busy:
            approve_help = "Disabled while a render is queued/running for this sermon."
        else:
            approve_help = (
                "Disabled while validation reports problems: " + "; ".join(problems)
                if problems
                else "Queue this edit as a background job"
            )
        with col_approve:
            if st.button(
                "Approve & apply",
                type="primary",
                key=f"editplan_approve_{sermon_id}",
                disabled=bool(problems) or apply_busy,
                help=approve_help,
                width="stretch",
            ):
                if not repo.update_edit_plan_status(
                    plan.get("id"),
                    "approved",
                    notes=plan.get("notes") or "",
                    final_start=float(start_val),
                    final_end=float(end_val),
                    audio_offset=float(audio_offset_val),
                ):
                    _set_feedback("Could not update plan status.", kind="error")
                    return
                _apply_approved_edit(
                    sermon,
                    plan,
                    repo,
                    float(start_val),
                    float(end_val),
                    audio_offset=float(audio_offset_val),
                    render_only=(apply_mode == "render_only"),
                )
                st.rerun()
        with col_reject:
            if st.button("Reject", key=f"editplan_reject_{sermon_id}", width="stretch"):
                if repo.update_edit_plan_status(
                    plan.get("id"),
                    "rejected",
                    notes=reject_notes,
                ):
                    if reject_notes.strip():
                        if _enqueue_edit_refine(sermon_id, reject_notes.strip()):
                            _set_feedback(
                                "Plan rejected. Re-running detection with your notes; "
                                "watch the Jobs page."
                            )
                    else:
                        _set_feedback("Edit plan rejected. Use Regenerate to re-run detection.")
                else:
                    _set_feedback("Could not reject the plan.", kind="error")
                st.rerun()
        with col_regen:
            if st.button(
                "Regenerate",
                key=f"editplan_regen_{sermon_id}",
                help="Re-run detection now, sending all notes from previous rejections.",
                width="stretch",
            ):
                if _enqueue_edit_refine(sermon_id, reject_notes.strip()):
                    _set_feedback(
                        "Re-running detection with accumulated notes. Watch the Jobs page."
                    )
                st.rerun()


def _load_local_transcript_files(audio_path: str | None) -> tuple[str, str]:
    """Return (plain, timestamped) transcript text from the sermon directory."""
    if not audio_path:
        return "", ""
    base = Path(audio_path).parent
    plain = ""
    stamped = ""
    txt_file = base / "transcript.txt"
    ts_file = base / "transcript_timestamps.json"
    if txt_file.is_file():
        try:
            plain = txt_file.read_text(encoding="utf-8")
        except OSError:
            plain = ""
    if ts_file.is_file():
        try:
            segments = json.loads(ts_file.read_text(encoding="utf-8"))
            lines = []
            for segment in segments:
                start = float(segment.get("start") or 0.0)
                text = str(segment.get("text") or "").strip()
                lines.append(f"[{int(start) // 60:02d}:{int(start) % 60:02d}] {text}")
            stamped = "\n".join(lines)
        except Exception:
            stamped = ""
        if not plain:
            plain = stamped
    return plain, stamped


def _resolve_local_transcript(sermon: dict[str, Any], repo: Any) -> tuple[str, str]:
    """Local-first transcript lookup: DB content, then files next to the media."""
    transcript = str(sermon.get("transcript") or sermon.get("transcript_text") or "")
    content = sermon.get("content")
    if not transcript and isinstance(content, dict):
        transcript = str(content.get("transcript_text") or "")

    full = None
    if not transcript:
        full = _full_sermon_or_none(sermon, repo) or {}
        transcript = str(full.get("transcript") or full.get("transcript_text") or "")
        content = full.get("content")
        if not transcript and isinstance(content, dict):
            transcript = str(content.get("transcript_text") or "")

    stamped = ""
    sermon_id = sermon.get("id") or sermon.get("sermon_id") or ""
    audio_path = None
    try:
        for row in repo.get_sermon_files(sermon_id):
            if row.get("file_type") in (
                "audio", "video", "processed_video", "original_audio", "original_video",
            ):
                audio_path = row.get("file_path")
                break
    except Exception:
        audio_path = None
    if not transcript or not stamped:
        file_plain, file_stamped = _load_local_transcript_files(audio_path)
        transcript = transcript or file_plain
        stamped = stamped or file_stamped

    if not transcript:
        media_path = _resolve_edit_media_path(sermon, repo)
        if media_path:
            file_plain, file_stamped = _load_local_transcript_files(media_path)
            transcript = transcript or file_plain
            stamped = stamped or file_stamped
    return transcript, stamped


def display_sermon_details(sermon):
    """Display detailed sermon information with API data"""
    st.markdown("### Sermon Details")

    st.markdown(f"## {sermon.get('title', 'Untitled')}")
    header_row1 = st.columns(3)
    with header_row1[0]:
        is_fav = sermon.get('is_favorite', 0)
        if st.button("Favorite", key=f"fav_{sermon['id']}", width='stretch',
                    help="Toggle favorite"):
            _toggle_favorite(sermon['id'], is_fav)
    with header_row1[1]:
        if st.button("Edit", key=f"edit_{sermon['id']}", width='stretch'):
            st.session_state.editing_sermon = True
            st.rerun()
    with header_row1[2]:
        gen_key = f"gen_show_{sermon['id']}"
        if st.button("Generate", key=f"generate_{sermon['id']}",
                    help="Generate AI description and/or hashtags from transcript",
                    width='stretch'):
            st.session_state[gen_key] = True
            st.rerun()
        if st.session_state.get(gen_key):
            with managed_popover("Select what to generate",
                            key=f"generate_popover_{sermon['id']}"):
                gen_desc = st.checkbox("Description", value=True, key=f"gen_desc_{sermon['id']}")
                gen_tags = st.checkbox("Hashtags", value=True, key=f"gen_tags_{sermon['id']}")
                if st.button("Generate", type="primary", key=f"gen_go_{sermon['id']}"):
                    generate_ai_content(sermon, gen_description=gen_desc, gen_hashtags=gen_tags)
                    st.session_state[gen_key] = False
                    st.rerun()
    header_row2 = st.columns(3)
    with header_row2[0]:
        push_help = (
            "Publish dry run to SermonAudio" if sermon.get('status') == 'draft'
            else "Update metadata on SermonAudio"
        )
        if st.button("Push", key=f"push_{sermon['id']}",
                    help=push_help,
                    width='stretch'):
            push_sermon_metadata_to_api(sermon)
            st.rerun()
    with header_row2[1]:
        if st.button("Delete", key=f"delete_{sermon['id']}",
                    help="Delete this sermon", width='stretch'):
            st.session_state.confirm_delete_sermon = sermon['id']
            st.rerun()
    with header_row2[2]:
        if st.button("Re-process", key=f"reproc_{sermon['id']}",
                    help="Re-process this sermon", width='stretch'):
            st.session_state.show_reprocess = sermon['id']
            st.rerun()

    try:
        show_edit_review_panel(sermon)
    except Exception as e:
        st.warning(f"Edit review panel unavailable: {e}")

    if st.session_state.get('confirm_delete_sermon') == sermon['id']:
        st.warning("Are you sure you want to delete this sermon? This cannot be undone.")
        c1, c2 = st.columns([1, 5])
        with c1:
            if st.button("Yes, delete", type="primary", key=f"confirm_del_{sermon['id']}"):
                from ui.database import SermonRepository
                repo = SermonRepository()
                if repo.delete_sermon(sermon['id']):
                    file_paths = sermon.get('file_paths', sermon.get('files', {}))
                    for _ftype, fpath in file_paths.items():
                        if fpath and Path(fpath).exists():
                            Path(fpath).unlink(missing_ok=True)
                    _set_feedback("Sermon deleted")
                    st.session_state.selected_sermon = None
                    st.session_state.confirm_delete_sermon = None
                    st.rerun()
                else:
                    st.error("Failed to delete sermon")
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
                with st.spinner("Loading enhanced sermon data..."):
                    api_response = api_client.get_sermon_details(sermon_id)
                    if api_response and isinstance(api_response, dict):
                        api_sermon_data = api_response.get('sermon', api_response)
                    if not api_response:
                        st.info(
                            "Sermon not found on SermonAudio (may have been deleted). "
                            "Use the Push button to recreate it."
                        )
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
            value = api_sermon_data.get(api_field)
            if value not in (None, "", []):
                display_data[display_field] = value
        if isinstance(api_sermon_data.get('speaker'), dict):
            display_data['speaker'] = api_sermon_data['speaker'].get(
                'displayName', display_data.get('speaker', 'Unknown')
            )
        if isinstance(api_sermon_data.get('series'), dict):
            display_data['series_title'] = api_sermon_data['series'].get(
                'title', display_data.get('series_title', '')
            )
        if isinstance(api_sermon_data.get('broadcaster'), dict):
            display_data['church_name'] = api_sermon_data['broadcaster'].get(
                'displayName', display_data.get('church_name', '')
            )
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
        speaker_name = (
            speaker.get('displayName') if isinstance(speaker, dict)
            else (str(speaker) if speaker else None)
        )
        if speaker_name and not sermon.get('speaker'):
            db_updates['speaker'] = speaker_name
        if api.get('eventType') and not sermon.get('event_type'):
            db_updates['event_type'] = api['eventType']
        if (
            (api.get('displayEventDate') or api.get('preachDate'))
            and not sermon.get('recorded_date')
        ):
            db_updates['recorded_date'] = api.get('displayEventDate') or api.get('preachDate')
        if (
            api.get('bibleText')
            and (not sermon.get('bible_text') or not sermon.get('scripture_reference'))
        ):
            db_updates['bible_text'] = api['bibleText']
            db_updates['scripture_reference'] = api['bibleText']
        series_title = (
            api.get('series', {}).get('title')
            if isinstance(api.get('series'), dict) else api.get('seriesTitle')
        )
        if series_title and not sermon.get('series_title'):
            db_updates['series_title'] = series_title
        if api.get('subtitle') and not sermon.get('subtitle'):
            db_updates['subtitle'] = api['subtitle']
        if db_updates:
            try:
                from ui.database import SermonRepository
                repo = SermonRepository()
                repo.update_sermon_metadata(sermon_id, db_updates)
            except Exception:
                pass

    st.markdown("### Information")
    col1, col2 = st.columns(2)
    with col1:
        speaker_name = display_data.get('speaker', 'Unknown')
        if isinstance(speaker_name, dict):
            speaker_name = speaker_name.get('displayName', 'Unknown')
        st.text(f"Speaker: {speaker_name}")
        st.text(f"Date: {_format_date(display_data.get('recorded_date'))}")
        st.text(f"Church: {display_data.get('church_name', 'Unknown')}")
        st.text(f"Duration: {_format_duration(display_data.get('duration')) or 'Unknown'}")
    with col2:
        series_title = display_data.get('series_title', 'None')
        if isinstance(series_title, dict):
            series_title = series_title.get('title', 'None')
        st.text(f"Series: {series_title}")
        st.text(f"Event: {display_data.get('event_type', 'Unknown')}")
        st.text(f"Scripture: {display_data.get('scripture_reference', 'None')}")

    if sermon_id:
        sermon_url = f"https://www.sermonaudio.com/sermoninfo.asp?SID={sermon_id}"
        st.markdown(f"[Listen on SermonAudio]({sermon_url})")
        file_paths = display_data.get('file_paths', display_data.get('files', {}))
        local_audio = file_paths.get('audio') if file_paths else None
        audio_url = display_data.get('audio_url')
        if audio_url:
            try:
                st.audio(audio_url)
            except Exception:
                st.caption(f"Audio link: {audio_url}")
        if local_audio and Path(local_audio).exists():
            with st.expander("Local copy", expanded=not audio_url):
                st.audio(local_audio)
                st.caption(local_audio)
        elif not audio_url:
            st.caption("Audio file not found locally")

        if display_data.get('status') == 'processed' and api_sermon_data is not None:
            published = bool(api_sermon_data.get('publishTimestamp'))
            label = (
                "Unpublish from SermonAudio" if published else "Publish to SermonAudio"
            )
            if st.button(label, key=f"publish_toggle_{sermon_id}"):
                with st.spinner("Updating publish state..."):
                    import sermon_updater

                    ok = sermon_updater.set_sermon_published(sermon_id, not published)
                if ok:
                    message = (
                        "Sermon unpublished. It is now a draft on SermonAudio."
                        if published
                        else "Sermon published. It is now visible on SermonAudio."
                    )
                    _set_feedback(message, kind="success")
                    st.rerun()
                else:
                    _set_feedback(
                        "Publish state change failed. Check the API credentials and try again.",
                        kind="error",
                    )

    st.markdown("### Description")
    description = display_data.get('description', '')
    ai_description = display_data.get('ai_description', '')
    if ai_description and ai_description != description:
        tab1, tab2 = st.tabs(["AI Generated", "Original"])
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
        st.markdown(f"**Keywords & Topics:** {tags_display}")

    scripture_ref = display_data.get('scripture_reference')
    verses = display_data.get('verses', display_data.get('scripture_text'))
    if scripture_ref or verses:
        st.markdown("### Scripture")
        if scripture_ref:
            st.markdown(f"**Reference:** {scripture_ref}")
        if verses:
            with managed_expander("Scripture Text", expanded=False,
                             key=f"scripture_text_{sermon['id']}"):
                st.markdown(verses)

    topics = display_data.get('key_topics') or display_data.get('content', {}).get('key_topics', [])
    if isinstance(topics, str):
        topics = [t.strip() for t in topics.split(',') if t.strip()]
    if topics:
        st.markdown(f"**Key Topics:** {' · '.join(topics)}")

    with managed_expander("Files & Processing", expanded=False,
                     key=f"files_processing_{sermon['id']}"):
        files = display_data.get('files', display_data.get('file_paths', {}))
        if files:
            for file_type, file_path in files.items():
                file_name = Path(file_path).name if file_path else "Not available"
                st.text(f"{file_type.title()}: {file_name}")
        try:
            _render_media_player(display_data)
        except Exception as e:
            st.caption(f"Media player unavailable: {e}")
        status = display_data.get('status', 'unknown')
        if status in ['completed', 'processed'] and (
            display_data.get('upload_status') != 'failed'
            and not ((display_data.get('upload_info') or {}).get('upload_status') == 'failed')
        ):
            st.success("Processing completed")
        elif status == 'processing':
            st.info("Processing in progress")
        elif status in ('failed', 'error') or (
            display_data.get('upload_status') == 'failed'
        ) or (
            (display_data.get('upload_info') or {}).get('upload_status') == 'failed'
        ):
            st.error("Processing failed")
        else:
            st.info(f"Status: {status.title()}")

        processing_info = display_data.get('processing_info', {})
        upload_info = display_data.get('upload_info', {})
        if processing_info.get('processed_at'):
            st.text(f"Processed: {processing_info['processed_at']}")
        if upload_info.get('uploaded_at'):
            st.text(f"Uploaded: {upload_info['uploaded_at']}")
        if processing_info.get('enhancement_method'):
            st.text(f"Enhancement: {processing_info['enhancement_method']}")

    if processing_info or api_sermon_data:
        with managed_expander("Advanced Information", expanded=False,
                         key=f"advanced_info_{sermon['id']}"):
            col1, col2 = st.columns(2)
            with col1:
                if processing_info:
                    for key, value in processing_info.items():
                        if key not in ['processed_at', 'enhancement_method'] and value:
                            display_key = key.replace('_', ' ').title()
                            if isinstance(value, dict | list):
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
        with managed_expander("Re-process Sermon", expanded=True,
                         key=f"reprocess_{sermon['id']}"):
            st.markdown("Select which processing steps to run:")
            rp_audio = st.checkbox("Audio enhancement", value=True, key=f"rp_audio_{sermon['id']}")
            rp_transcript = st.checkbox("Transcription", value=True, key=f"rp_trans_{sermon['id']}")
            rp_ai = st.checkbox(
                "AI description & hashtags", value=True, key=f"rp_ai_{sermon['id']}"
            )
            rp_dry_run = st.checkbox(
                "Dry run (no upload)", value=False, key=f"rp_dry_{sermon['id']}"
            )
            rp_backend = st.selectbox(
                "Transcription Backend",
                options=["whisper_local", "whisper_openai", "whisper_openrouter"],
                index=1,
                key=f"rp_backend_{sermon['id']}",
                help="Local Whisper (runs on your machine) or OpenAI/OpenRouter API"
            )
            rp_col1, rp_col2 = st.columns(2)
            with rp_col1:
                if st.button(
                    "Start Re-processing", type="primary", key=f"rp_start_{sermon['id']}"
                ):
                    try:
                        from job_queue import JobType, get_job_queue

                        from ui.database import SermonRepository
                        job_queue = get_job_queue()
                        repo = SermonRepository()
                        full_sermon = repo.get_sermon(sermon['id'])
                        file_paths = (full_sermon or {}).get('file_paths', {})
                        audio_path = (
                            file_paths.get('original_audio')
                            or file_paths.get('enhanced_audio')
                            or file_paths.get('audio')
                            or ''
                        )
                        job_id = job_queue.add_job(
                            job_type=JobType.BATCH_PROCESSING,
                            title=f"Re-process: {sermon.get('title', sermon['id'])}",
                            description=f"Re-processing sermon {sermon['id']}",
                            parameters={
                                'sermon_ids': [sermon['id']],
                                'config': st.session_state.get('config', {}),
                                'actions': {
                                    'enhance_audio': rp_audio,
                                    'transcribe': rp_transcript,
                                    'generate_description': rp_ai,
                                    'generate_hashtags': rp_ai,
                                },
                                'form_data': {
                                    'dry_run': rp_dry_run,
                                    'transcription_backend': rp_backend,
                                    'uploaded_file_path': audio_path,
                                }
                            },
                            priority=5
                        )
                        st.success(f"Re-process job created: {job_id[:8]}")
                        st.session_state.show_reprocess = None
                    except Exception as e:
                        st.error(f"Failed: {e}")
            with rp_col2:
                if st.button("Cancel", key=f"rp_cancel_{sermon['id']}"):
                    st.session_state.show_reprocess = None
                    st.rerun()

    # Transcript viewer/editor
    with managed_expander("Transcript", expanded=False,
                     key=f"transcript_expander_{sermon['id']}"):
        repo = None
        try:
            from ui.database import SermonRepository
            repo = SermonRepository()
        except Exception:
            repo = None
        transcript, timestamped = (
            _resolve_local_transcript(sermon, repo) if repo else ("", "")
        )
        if not transcript:
            # Remote fallback only: the local copy is authoritative for drafts.
            try:
                import sermon_updater
                with st.spinner("Fetching transcript from SermonAudio..."):
                    fetched = sermon_updater.get_sermon_transcript(sermon['id'])
                if fetched:
                    transcript = fetched
                    if repo:
                        repo.update_sermon(sermon['id'], {'transcript': transcript})
            except Exception:
                pass
        with st.form(f"transcript_form_{sermon['id']}"):
            edited_transcript = st.text_area("Edit transcript", value=transcript, height=200)
            save_transcript = st.form_submit_button("Save Transcript", type="primary")
        if save_transcript and edited_transcript != transcript:
            from ui.database import SermonRepository
            repo = SermonRepository()
            repo.update_sermon(sermon['id'], {'transcript': edited_transcript})
            _set_feedback("Transcript saved")
            st.session_state.selected_sermon = repo.get_sermon(sermon['id'])
            st.rerun()
        if timestamped:
            st.caption(
                f"Local timestamps available ({timestamped.count(chr(10)) + 1} segments)."
            )
            with managed_expander("Timestamped transcript", expanded=False,
                             key=f"timestamped_transcript_{sermon['id']}"):
                st.text(timestamped)

    # Notes
    with managed_expander("Notes", expanded=False):
        current_notes = sermon.get('notes', '') or ''
        with st.form(f"notes_form_{sermon['id']}"):
            new_notes = st.text_area("Sermon notes", value=current_notes, height=100)
            save_notes = st.form_submit_button("Save Notes", type="primary")
        if save_notes and new_notes != current_notes:
            _save_notes(sermon['id'], new_notes)
            _set_feedback("Notes saved")
            from ui.database import SermonRepository
            st.session_state.selected_sermon = SermonRepository().get_sermon(sermon['id'])
            st.rerun()

    if api_sermon_data:
        if st.button(
            "Refresh from SermonAudio", help="Fetch the latest data from SermonAudio API"
        ):
            try:
                from sermonaudio_api import SermonAudioAPI

                from ui.database import SermonRepository
                api_client = SermonAudioAPI()
                fresh_data = api_client.get_sermon_details(sermon_id, force_refresh=True)
                if fresh_data:
                    api = fresh_data.get('sermon', fresh_data)
                    speaker = api.get('speaker', {})
                    raw_updates = {
                        'title': api.get('fullTitle') or api.get('title'),
                        'subtitle': api.get('subtitle'),
                        'speaker': (
                            speaker.get('displayName')
                            if isinstance(speaker, dict)
                            else str(speaker) if speaker else None
                        ),
                        'event_type': api.get('eventType') or api.get('displayEventType'),
                        'recorded_date': api.get('displayEventDate') or api.get('preachDate'),
                        'bible_text': api.get('bibleText'),
                        'scripture_reference': api.get('bibleText'),
                        'series_title': (
                            api.get('series', {}).get('title')
                            if isinstance(api.get('series'), dict)
                            else api.get('seriesTitle')
                        ),
                        'church_name': (
                            api.get('broadcaster', {}).get('displayName')
                            if isinstance(api.get('broadcaster'), dict) else None
                        ),
                        'description': api.get('moreInfoText') or api.get('description'),
                    }
                    db_updates = {k: v for k, v in raw_updates.items() if v is not None}
                    repo = SermonRepository()
                    if db_updates and repo.update_sermon_metadata(sermon_id, db_updates):
                        _set_feedback("Sermon data refreshed and saved!")
                        st.session_state.selected_sermon = repo.get_sermon(sermon_id)
                        st.rerun()
                    else:
                        st.error("Failed to save refreshed data")
                else:
                    st.error("Failed to refresh data")
            except Exception as e:
                st.error(f"Error refreshing data: {e}")

def display_sermon_editor(sermon, api_client, repo):
    """Display sermon editor with API-backed dropdowns"""
    st.markdown("### Edit Sermon")

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

            parsed_date = _parse_date(sermon.get('recorded_date'))
            recorded_date = st.date_input(
                "Recorded Date",
                value=parsed_date.date() if parsed_date else datetime.now().date()
            )

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

            scripture_reference = st.text_input(
                "Scripture Reference", value=sermon.get('scripture_reference', '')
            )
            stored_event_type = sermon.get('event_type') or None
            if stored_event_type:
                event_key_suffix = re.sub(r"\W+", "_", stored_event_type).strip("_")
            else:
                event_key_suffix = "none"
            from ui.sermon_metadata import create_event_type_selectbox
            event_type = create_event_type_selectbox(
                "Event Type",
                key=f"edit_event_type_{sermon['id']}_{event_key_suffix or 'none'}",
                value=stored_event_type,
            )

        description = st.text_area("Description", value=sermon.get('description', ''), height=100)

        # Form buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            save = st.form_submit_button("Save", type="primary")
        with col2:
            cancel = st.form_submit_button("Cancel")

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
                    _set_feedback("Sermon updated successfully!")
                    st.session_state.editing_sermon = False
                    # Refresh the selected sermon data
                    st.session_state.selected_sermon = repo.get_sermon(sermon['id'])
                    st.rerun()
                else:
                    st.error("Failed to update sermon metadata")
            except Exception as e:
                st.error(f"Error updating sermon: {e}")

        if cancel:
            prefix = f"edit_event_type_{sermon['id']}_"
            try:
                stale_keys = [
                    key for key in list(st.session_state.keys())
                    if str(key).startswith(prefix)
                ]
            except Exception:
                stale_keys = []
            for key in stale_keys:
                st.session_state.pop(key, None)
            st.session_state.editing_sermon = False
            st.rerun()

if __name__ == "__main__":
    show_library()
