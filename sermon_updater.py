"""SermonAudio Updater & Processor

Core capabilities:
* List sermons with comprehensive filtering (all public API query params exposed).
* Process sermons: download audio, enhance, summarize, hashtag, update metadata, upload audio.
* Multi‑year support: ``--year`` (single) or ``--years`` (comma/range list).

Examples:
    python sermon_updater.py --sermon-id 1234567890123
    python sermon_updater.py --since-days 14 --event-type "Sunday - AM" --require-audio --limit 5
    python sermon_updater.py --search-keyword grace --language-code eng --dry-run --list-only
    python sermon_updater.py --date-range 2024-01-01 2024-01-31 --auto-yes
    python sermon_updater.py --years 2022-2023,2025 --limit 10 --list-only

Config: defaults to ``config.yaml`` (override with ``--config`` or SA_UPDATER_CONFIG env var).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
import traceback
import warnings
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass
from typing import Any
from collections.abc import Iterable
from io import StringIO

import requests
import sermonaudio
import yaml
from dotenv import load_dotenv
from sermonaudio.node.requests import Node

# Suppress ML library import noise
with redirect_stdout(StringIO()), redirect_stderr(StringIO()), warnings.catch_warnings():
    warnings.simplefilter("ignore")
    os.environ["PYTHONWARNINGS"] = "ignore"
    # Suppress torchaudio warning specifically
    os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "1"
    # Pre-configure DF logging before import
    import logging
    logging.getLogger("df").setLevel(logging.CRITICAL)
    logging.getLogger("df").disabled = True
    from audio_processing import process_sermon_audio
    from llm_manager import LLMManager, migrate_legacy_config

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

def setup_logging(verbose: bool = False):
    """Configure logging levels based on verbose flag."""
    level = logging.DEBUG if verbose else logging.ERROR
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s' if verbose else '%(message)s',
        force=True
    )

    # Set third-party loggers to ERROR unless in verbose mode
    if not verbose:
        for logger_name in [
            'requests', 'urllib3', 'audio_processing', 'llm_manager',
            'transformers', 'torch', 'torchaudio', 'deepspeed', 'df',
            'resemble_enhance', 'deepfilternet', 'DeepFilterNet'
        ]:
            logging.getLogger(logger_name).setLevel(logging.ERROR)
        
        # Specifically suppress DF logger which is very verbose
        df_logger = logging.getLogger("df")
        df_logger.setLevel(logging.CRITICAL)
        df_logger.disabled = True
def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return migrate_legacy_config(cfg)


CONFIG_PATH = os.environ.get("SA_UPDATER_CONFIG", "config.yaml")
if not os.path.exists(CONFIG_PATH):
    print(f"[FATAL] Config file not found: {CONFIG_PATH}")
    sys.exit(1)

config = load_config(CONFIG_PATH)
llm_manager = LLMManager(config)

SERMON_AUDIO_API_KEY = config['api_key']
SERMON_AUDIO_BROADCASTER_ID = config['broadcaster_id']
sermonaudio.set_api_key(SERMON_AUDIO_API_KEY)

DRY_RUN = config.get('dry_run', False)
DEBUG = config.get('debug', False)

AUDIO_PARAMS = {
    'noise_reduction': config.get('audio_noise_reduction', True),
    'amplify': config.get('audio_amplify', True),
    'normalize': config.get('audio_normalize', True),
    'gain_db': config.get('audio_gain_db', 1.0),
    'target_level_db': config.get('audio_target_level_db', -22.0),
    'use_audacity': config.get('use_audacity', False),
    'enhancement_method': config.get('audio_enhancement_method', 'resemble_enhance')
}

BASE_URL = 'https://api.sermonaudio.com/v2/'


def console_print(message: str, level: str = "info"):
    """Print messages to console with appropriate formatting.
    
    Args:
        message: Message to print
        level: Message level (info, warning, error, success)
    """
    if level == "error":
        print(f"❌ {message}")
    elif level == "warning":
        print(f"⚠️  {message}")
    elif level == "success":
        print(f"✅ {message}")
    else:
        print(f"ℹ️  {message}")


def get_api_headers() -> dict[str, str]:
    return {'X-Api-Key': SERMON_AUDIO_API_KEY, 'Content-Type': 'application/json'}


def update_sermon_metadata(sermon_id: str, description: str, hashtags: str | list[str]) -> bool:
    url = BASE_URL + f'node/sermons/{sermon_id}'
    headers = get_api_headers()
    keywords = hashtags if isinstance(hashtags, str) else ','.join(hashtags)
    payload = {'moreInfoText': description, 'keywords': keywords}
    resp = requests.patch(url, headers=headers, json=payload, timeout=60)
    logger.debug("Update sermon status: %d", resp.status_code)
    if resp.status_code not in (200, 204):
        logger.error("Update error: %s", resp.text[:200])
    return resp.status_code in (200, 204)


def upload_audio_file(sermon_id: str, audio_path: str) -> bool:
    logger.debug("Uploading audio for sermon %s from %s", sermon_id, audio_path)
    url = BASE_URL + 'media'
    headers = get_api_headers()
    payload = {'uploadType': 'original-audio', 'sermonID': sermon_id}
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    logger.debug("Audio upload initiation status: %d", resp.status_code)
    if resp.status_code != 201:
        logger.error("Failed to initiate audio upload: %s", resp.text[:200])
        return False
    data = resp.json()
    upload_url = data.get('uploadURL')
    if not upload_url:
        logger.error("No upload URL returned.")
        return False
    try:
        with open(audio_path, 'rb') as fh:
            up = requests.post(
                upload_url,
                data=fh,
                headers={'Content-Type': 'audio/mpeg'},
                timeout=600,
            )
        logger.debug("Direct upload status: %d", up.status_code)
        return up.status_code in (200, 201, 204)
    except Exception as e:  # pragma: no cover
        logger.error("Error uploading file: %s", e)
        return False


def download_file(url: str, local_path: str):
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def generate_summary(
    transcript: str,
    event_type: str | None = None,
    speaker_name: str | None = None,
) -> str:
    def is_class_event(et):
        class_types = [
            'Sunday School', 'Midweek Service', 'Bible Study', 'Teaching', 'Class',
            'Devotional', 'Conference', 'Camp Meeting', 'Children', 'Youth', 'Question & Answer'
        ]
        et_str = str(et or '')
        return any(c.lower() in et_str.lower() for c in class_types)

    if is_class_event(event_type):
        role_desc = 'Bible class summarization assistant'
        body_desc = 'Sunday School, Midweek, or class/lecture event'
        person_label = speaker_name or 'the instructor'
    else:
        role_desc = 'sermon summarization assistant'
        body_desc = 'sermon'
        person_label = speaker_name or 'the preacher'

    prompt = (
        f"You are a {role_desc}. Read the following {body_desc} transcript and write a single, "
        f"concise description of {person_label}'s main message and application. Focus on what "
        f"they wanted the audience to understand, believe, or do. Avoid generic statements; "
        f"emphasize unique focus.\n\nTranscript:\n{transcript}\n\nGuidelines:\n"
        f"- One paragraph (150-300 words).\n- Use the speaker's name.\n"
        f"- No intro/closing words.\n- No markdown or bullets.\n"
        f"- Do not prefix with 'Summary:'.\n- If incomplete, infer likely main message."
    )
    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating summary using %s LLM...", primary_provider)
        response = llm_manager.chat([{'role': 'user', 'content': prompt}])
        logger.debug("Summary generated (%d chars)", len(response))
        return response
    except Exception as e:  # pragma: no cover
        logger.error("LLM summary generation failed: %s", e)
        return "Summary generation failed"


def verify_hashtags(initial_hashtags: str, original_text: str) -> str:
    """
    Verify and clean hashtags through a second LLM pass.
    This ensures the output strictly follows hashtag format and removes any comments.
    """
    verification_prompt = (
        "You are a hashtag validator. Your job is to extract ONLY valid hashtags from the input below. "
        "Rules:\n"
        "1. Output ONLY hashtags (words starting with #)\n"
        "2. Remove any comments, explanations, or non-hashtag text\n"
        "3. Keep hashtags space-separated\n"
        "4. Maximum 150 characters total\n"
        "5. If you see obvious formatting issues, fix them\n"
        "6. If no valid hashtags found, generate 3-5 relevant ones for the sermon topic\n\n"
        f"Original sermon topic context: {original_text[:200]}...\n\n"
        f"Hashtag input to verify:\n{initial_hashtags}\n\n"
        "Valid hashtags only:"
    )
    
    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Verifying hashtags using %s LLM...", primary_provider)
        response = llm_manager.chat([{'role': 'user', 'content': verification_prompt}])
        
        # Extract only hashtags from the response
        import re
        hashtag_pattern = r'#\w+'
        hashtags = re.findall(hashtag_pattern, response)
        
        if hashtags:
            verified_hashtags = ' '.join(hashtags)
            # Ensure length limit
            if len(verified_hashtags) > 150:
                # Truncate at word boundary
                truncated = verified_hashtags[:150]
                last_space = truncated.rfind(' ')
                if last_space > 0:
                    verified_hashtags = truncated[:last_space]
                else:
                    verified_hashtags = truncated
            
            logger.debug("Verified hashtags: %s", verified_hashtags)
            return verified_hashtags
        else:
            logger.warning("No valid hashtags found in verification, using fallback")
            return "#faith #hope #worship #christian #jesus"
            
    except Exception as e:
        logger.error("Hashtag verification failed: %s", e)
        # Return cleaned version of original hashtags as fallback
        import re
        hashtag_pattern = r'#\w+'
        fallback_hashtags = re.findall(hashtag_pattern, initial_hashtags)
        if fallback_hashtags:
            return ' '.join(fallback_hashtags)[:150]
        else:
            return "#faith #hope #worship #christian #jesus"


def generate_hashtags(text: str) -> str:
    prompt = (
        "Generate 5-10 highly relevant, search-friendly hashtags (<=150 chars total) for this "
        "sermon. Combine multi-word phrases (#ChristianLiving). Avoid duplicates & generic "
        "(#sermon #church) unless uniquely relevant. Output ONLY space-delimited hashtags.\n\n"
        f"Text:\n{text}\n\nHashtags:"
    )
    try:
        provider_info = llm_manager.get_provider_info()
        primary_provider = provider_info.get('primary', {}).get('type', 'unknown')
        logger.debug("Generating hashtags using %s LLM...", primary_provider)
        
        # First pass: Generate hashtags
        response = llm_manager.chat([{'role': 'user', 'content': prompt}])
        logger.debug("Initial hashtag response: %s", response)
        
        # Second pass: Verify and clean hashtags (if enabled in config)
        if config.get('hashtag_verification', True):
            verified_hashtags = verify_hashtags(response, text)
            logger.debug("Final verified hashtags: %s", verified_hashtags)
            return verified_hashtags
        else:
            # Original processing method for backward compatibility
            hashtags = ' '.join(response.replace(',', ' ').split())
            if len(hashtags) > 150:
                hashtags = hashtags[:150]
            logger.debug("Generated hashtags (no verification): %s", hashtags)
            return hashtags
            
    except Exception as e:  # pragma: no cover
        logger.error("LLM hashtag generation failed: %s", e)
        return "#faith #hope #worship #christian #jesus"
    except Exception as e:  # pragma: no cover
        logger.error("LLM hashtag generation failed: %s", e)
        return "#faith #hope #worship #christian #jesus"


def process_single_sermon(sermon_id: str, no_upload: bool = False, verbose: bool = False):
    logger.debug(f"Processing sermon_id={sermon_id}")
    details = Node.get_sermon(sermon_id)
    speaker_name = None
    if hasattr(details, 'speaker') and details.speaker:
        speaker_name = (
            getattr(details.speaker, 'full_name', None)
            or getattr(details.speaker, 'display_name', None)
            or getattr(details.speaker, 'displayName', None)
            or str(details.speaker)
        )
    sermon_name = (
        getattr(details, 'display_title', None)
        or getattr(details, 'displayTitle', '<No Title>')
    )
    event_type = getattr(details, 'event_type', None) or getattr(details, 'eventType', None)
    logger.info("Processing: %s (%s) event=%s", sermon_name, sermon_id, event_type)

    base_dir = os.path.abspath(os.path.dirname(__file__))
    processed_root = os.path.join(base_dir, "processed_sermons")
    os.makedirs(processed_root, exist_ok=True)
    sermon_dir = os.path.join(processed_root, sermon_id)
    os.makedirs(sermon_dir, exist_ok=True)
    input_audio = os.path.join(sermon_dir, f"temp_{sermon_id}.mp3")
    output_audio = os.path.join(sermon_dir, f"processed_{sermon_id}.mp3")

    # Gather potential audio URLs
    audio_url = None
    candidates: list[str] = []
    if hasattr(details, 'media') and details.media and hasattr(details.media, 'audio'):
        for audio_obj in details.media.audio:
            for key in ('downloadURL', 'download_url', 'streamURL', 'url'):
                if hasattr(audio_obj, key) and getattr(audio_obj, key):
                    candidates.append(getattr(audio_obj, key))
    if hasattr(details, 'audio_url') and details.audio_url:
        candidates.append(details.audio_url)
    for c in candidates:
        logger.debug("Trying audio URL: %s", c)
        try:
            download_file(c, input_audio)
            audio_url = c
            logger.debug("Audio download succeeded")
            break
        except Exception as e:
            logger.debug("Failed: %s", e)
    if not audio_url:
        logger.warning("No audio available; skipping sermon %s", sermon_id)
        return

    # Process audio
    try:
        processing_success = process_sermon_audio(
            input_audio,
            output_audio,
            skip_on_error=True,
            verbose=verbose,
            **AUDIO_PARAMS
        )
        if not processing_success:
            logger.warning("Audio processing issues; continuing with original audio")
    except Exception as e:
        logger.error("Audio processing failed: %s", e)
        return

    # Pull transcript
    transcript = ""
    try:
        api_url = f"{BASE_URL}node/sermons/{sermon_id}"
        resp = requests.get(api_url, headers={'X-Api-Key': SERMON_AUDIO_API_KEY}, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            t_obj = data.get('transcript')
            if t_obj and t_obj.get('downloadURL'):
                t_resp = requests.get(t_obj['downloadURL'], timeout=60)
                if t_resp.status_code == 200:
                    transcript = t_resp.text
                    logger.debug("Transcript retrieved")
    except Exception as e:  # pragma: no cover
        logger.error("Transcript retrieval error: %s", e)
    if not transcript:
        logger.warning("No transcript; skipping summary + hashtags.")
        return

    summary = generate_summary(transcript, event_type=event_type, speaker_name=speaker_name)
    hashtags = generate_hashtags(transcript)

    # Save local copies
    try:
        with open(
            os.path.join(sermon_dir, f"{sermon_id}_description.txt"),
            'w',
            encoding='utf-8',
        ) as fh:
            fh.write(summary)
        with open(
            os.path.join(sermon_dir, f"{sermon_id}_hashtags.txt"),
            'w',
            encoding='utf-8',
        ) as fh:
            fh.write(hashtags)
    except Exception as e:  # pragma: no cover
        logger.error("Failed writing local files: %s", e)

    if DRY_RUN or no_upload:
        logger.info("Dry-run / no-upload: skipping metadata+audio update")
        return

    try:
        if update_sermon_metadata(sermon_id, summary, hashtags):
            logger.debug("Metadata updated")
    except Exception as e:  # pragma: no cover
        logger.error("Metadata update error: %s", e)
    try:
        if upload_audio_file(sermon_id, output_audio):
            logger.debug("Audio uploaded")
    except Exception as e:  # pragma: no cover
        logger.error("Audio upload error: %s", e)
    try:
        if os.path.exists(input_audio):
            os.remove(input_audio)
    except Exception:  # pragma: no cover
        pass

    logger.info("Sermon %s complete", sermon_id)


def get_sermons_in_date_range(start_date, end_date):
    """Legacy helper. Prefer cli_main() with --date-range for new code."""
    try:
        start_dt = dt.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = dt.datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        logger.error("Invalid date format; expected YYYY-MM-DD")
        return []
    params = {
        'broadcasterID': SERMON_AUDIO_BROADCASTER_ID,
        'preachedAfterTimestamp': int(start_dt.timestamp()),
        'preachedBeforeTimestamp': int(end_dt.timestamp()),
        'pageSize': 100,
        'page': 1,
        'cache': 'true',
        'lite': 'true'
    }
    headers = get_api_headers()
    url = f"{BASE_URL}node/sermons"
    all_sermons = []
    while True:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=60)
            if r.status_code != 200:
                break
            data = r.json()
            results = data.get('results', [])
            for s in results:
                speaker_info = s.get('speaker') or {}
                all_sermons.append({
                    'sermonID': s.get('sermonID'),
                    'displayTitle': s.get('displayTitle'),
                    'preachDate': s.get('preachDate'),
                    'speakerName': speaker_info.get('displayName'),
                    'eventType': s.get('eventType')
                })
            if not data.get('next'):
                break
            params['page'] += 1
        except Exception:
            break
    all_sermons.sort(key=lambda x: x['preachDate'] or '1900-01-01')
    return all_sermons


def get_sermons_in_year(year):
    return get_sermons_in_date_range(f"{year}-01-01", f"{year}-12-31")


def process_year(year, no_upload=False):
    """Legacy bulk processor. Prefer cli_main() with --year for new code."""
    sermons = get_sermons_in_year(year)
    if not sermons:
        logger.warning("No sermons found for year")
        return
    if input(f"Process all {len(sermons)} sermons from {year}? (y/N): ").lower() != 'y':
        return
    for s in sermons:
        process_single_sermon(s['sermonID'], no_upload=no_upload)


def process_date_range(start_date, end_date, no_upload=False):
    sermons = get_sermons_in_date_range(start_date, end_date)
    if not sermons:
        logger.warning("No sermons found in date range")
        return
    if input(f"Process all {len(sermons)} sermons? (y/N): ").lower() != 'y':
        return
    for s in sermons:
        process_single_sermon(s['sermonID'], no_upload=no_upload)


@dataclass
class SermonLite:
    sermonID: str
    displayTitle: str
    preachDate: str | None
    speakerName: str | None
    eventType: str | None


SERMON_FILTER_ARG_MAP = {
    # Maps CLI flag -> (API param, type, help text)
    # type: int/str -> value passed directly; 'flag' -> 'true'; 'negflag' -> 'false'
    'page': ('page', int, 'Result page (default 1)'),
    'page_size': ('pageSize', int, 'Page size (max 100)'),
    'exact_ref_match': ('exactRefMatch', 'flag', 'Exact Bible ref match'),
    'chapter': ('chapter', int, 'First/only chapter'),
    'chapter_end': ('chapterEnd', int, 'Last chapter inclusive'),
    'verse': ('verse', int, 'First/only verse'),
    'verse_end': ('verseEnd', int, 'Last verse inclusive'),
    'featured': ('featured', 'flag', 'Featured sermons only'),
    'search_keyword': ('searchKeyword', str, 'Full-text search'),
    'include_transcripts': ('includeTranscripts', 'flag', 'Search transcripts (needs cache=true)'),
    'language_code': ('languageCode', str, 'ISO 639 language code'),
    'require_audio': ('requireAudio', 'flag', 'Require audio'),
    'require_video': ('requireVideo', 'flag', 'Require video'),
    'require_pdf': ('requirePDF', 'flag', 'Require PDF'),
    'no_media': ('noMedia', 'flag', 'Only sermons with no media'),
    'series': ('series', str, 'Filter by series (needs broadcaster)'),
    'denomination': ('denomination', str, 'Broadcaster denomination'),
    'vacant_pulpit': ('vacantPulpit', 'flag', 'Vacant pulpit'),
    'state': ('state', str, 'Broadcaster state/region'),
    'country': ('country', str, 'ISO3 country'),
    'speaker_name': ('speakerName', str, 'Speaker name'),
    'speaker_id': ('speakerID', int, 'Speaker ID'),
    'staff_pick': ('staffPick', 'flag', 'Staff pick'),
    'listener_recommended': ('listenerRecommended', 'flag', 'Listener recommended'),
    # 'year' reserved for core shortcut; expose preached-year for filtering
    'preached_year': ('year', int, 'Year preached (filter)'),
    'month': ('month', int, 'Month (1-12)'),
    'day': ('day', int, 'Day (1-31)'),
    'audio_min_duration': ('audioMinDurationSeconds', int, 'Minimum audio duration (s)'),
    'audio_max_duration': ('audioMaxDurationSeconds', int, 'Maximum audio duration (s)'),
    'lite': ('lite', 'flag', 'Lite sermons'),
    'lite_broadcaster': ('liteBroadcaster', 'flag', 'Lite broadcaster'),
    'cache': ('cache', 'flag', 'Enable API cache'),
    'preached_after': ('preachedAfterTimestamp', int, 'Preached after UNIX timestamp'),
    'preached_before': ('preachedBeforeTimestamp', int, 'Preached before UNIX timestamp'),
    'collection_id': ('collectionID', int, 'Collection ID'),
    'include_drafts': ('includeDrafts', 'flag', 'Include drafts'),
    'include_scheduled': ('includeScheduled', 'flag', 'Include scheduled'),
    'exclude_published': ('includePublished', 'negflag', 'Exclude published'),
    'book': ('book', str, 'OSIS book'),
    'sermon_ids': ('sermonIDs', str, 'Comma-separated sermon IDs'),
    'event_type': ('eventType', str, 'Event type description'),
    'broadcaster_id': ('broadcasterID', str, 'Override broadcaster ID'),
    'sort_by': ('sortBy', str, 'Sort field')
}


def build_sermon_query_params(args: argparse.Namespace) -> dict[str, Any]:
    """Map parsed argparse namespace -> API query parameter dict.

    Handles:
    * Boolean flags (flag / negflag) -> 'true' / 'false'
    * Date range ( --date-range ) -> preachedAfterTimestamp / preachedBeforeTimestamp
    * since-days shortcut -> preachedAfterTimestamp
    * limit does not override explicit pageSize already set
    """
    params: dict[str, Any] = {}
    for cli_name, (api_name, kind, _help) in SERMON_FILTER_ARG_MAP.items():
        if not hasattr(args, cli_name):
            continue
        value = getattr(args, cli_name)
        if value in (None, False):
            continue
        if kind == 'flag':
            params[api_name] = 'true'
        elif kind == 'negflag':
            params[api_name] = 'false'
        else:
            params[api_name] = value

    if getattr(args, 'date_range', None):
        start, end = args.date_range
        try:
            s_dt = dt.datetime.strptime(start, '%Y-%m-%d')
            e_dt = dt.datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            params['preachedAfterTimestamp'] = int(s_dt.timestamp())
            params['preachedBeforeTimestamp'] = int(e_dt.timestamp())
        except Exception as e:  # pragma: no cover
            logger.warning("Invalid --date-range: %s", e)

    if getattr(args, 'since_days', None):
        after = dt.datetime.utcnow() - dt.timedelta(days=args.since_days)
        params.setdefault('preachedAfterTimestamp', int(after.timestamp()))

    if getattr(args, 'limit', None):
        params.setdefault('pageSize', args.limit)
    return params


def fetch_sermons(params: dict[str, Any], max_results: int | None = None) -> list[SermonLite]:
    """Iterate paginated sermon list endpoint accumulating results.

    Stops early if max_results reached or API error encountered.
    """
    url = f"{BASE_URL}node/sermons"
    headers = get_api_headers()
    sermons: list[SermonLite] = []
    page = int(params.get('page', 1))
    params = params.copy()
    params.setdefault('page', page)
    params.setdefault('pageSize', 50)
    while True:
        params['page'] = page
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code != 200:
            logger.error("Sermons query failed (%d): %s", resp.status_code, resp.text[:160])
            break
        data = resp.json()
        results = data.get('results', [])
        for r in results:
            speaker_info = r.get('speaker') or {}
            sermons.append(
                SermonLite(
                    sermonID=r.get('sermonID'),
                    displayTitle=r.get('displayTitle'),
                    preachDate=r.get('preachDate'),
                    speakerName=speaker_info.get('displayName'),
                    eventType=r.get('eventType'),
                )
            )
            if max_results and len(sermons) >= max_results:
                return sermons
        if not data.get('next'):
            break
        page += 1
    return sermons


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Process or list SermonAudio sermons with rich filtering.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    core = p.add_argument_group('Core Actions')
    core.add_argument('--sermon-id', help='Process a single sermon ID')
    core.add_argument('--list-only', action='store_true', help='Only list results (no processing)')
    core.add_argument('--limit', type=int, help='Max sermons to list/process (caps pageSize)')
    core.add_argument('--since-days', dest='since_days', type=int, help='Preached after N days ago')
    core.add_argument(
        '--date-range',
        nargs=2,
        metavar=('START', 'END'),
        help='Date range YYYY-MM-DD YYYY-MM-DD',
    )
    core.add_argument('--year', type=int, help='Process entire year (short-cut)')
    core.add_argument(
        '--years',
        help='Multiple years: 2021,2023 or 2020-2022 (comma/range; combines)'
    )
    core.add_argument('--auto-yes', action='store_true', help='Skip confirmation prompts')
    core.add_argument('--no-upload', action='store_true', help='Skip metadata & audio upload')
    core.add_argument(
        '--dry-run',
        action='store_true',
        help='Skip remote updates (implies --no-upload)',
    )
    core.add_argument('--config', default=CONFIG_PATH, help='Alternate config file')
    core.add_argument('-v', '--verbose', action='store_true', help='Verbose debug output')

    filt = p.add_argument_group('Sermon Filters (map to API query params)')
    for cli_name, (_api, kind, help_txt) in SERMON_FILTER_ARG_MAP.items():
        arg = f"--{cli_name.replace('_', '-')}"
        if kind in ('flag', 'negflag'):
            filt.add_argument(arg, action='store_true', help=help_txt)
        else:
            numeric_names = {
                'page','page_size','chapter','chapter_end','verse','verse_end','year','month','day',
                'speaker_id','collection_id','audio_min_duration','audio_max_duration',
                'preached_after','preached_before'
            }
            typ = (
                int
                if (
                    kind is int
                    or 'duration' in cli_name
                    or cli_name in numeric_names
                )
                else str
            )
            filt.add_argument(arg, type=typ, help=help_txt)
    return p


def confirm(prompt: str, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    return input(f"{prompt} [y/N]: ").strip().lower() == 'y'


def cli_main(argv: Iterable[str] | None = None):  # orchestration
    """CLI entry point.

    1. Parse args
    2. Optional config reload
    3. Single-sermon path OR build query params and list
    4. Optional batch processing with confirmation unless --auto-yes
    """
    global config, llm_manager, DRY_RUN, DEBUG
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Set up logging based on verbose flag
    setup_logging(args.verbose)

    if args.config and args.config != CONFIG_PATH:
        if not os.path.exists(args.config):
            parser.error(f"Config not found: {args.config}")
        config = load_config(args.config)
        llm_manager = LLMManager(config)
        # update dependent flags
        DRY_RUN = config.get('dry_run', DRY_RUN)
        DEBUG = config.get('debug', DEBUG)

    if args.verbose:
        DEBUG = True
    if args.dry_run:
        DRY_RUN = True

    if args.sermon_id:
        if not confirm(f"Process sermon {args.sermon_id}?", args.auto_yes):
            console_print("Cancelled")
            return
        console_print(f"Processing sermon {args.sermon_id}...")
        process_single_sermon(args.sermon_id, no_upload=args.no_upload or args.dry_run)
        return

    # Year shortcut -> preached_year (pure filter) so --limit & other filters apply
    if args.year:
        if not hasattr(args, 'preached_year') or args.preached_year in (None, 0):
            args.preached_year = args.year
        logger.debug(f"Using --year {args.year} as preached_year filter (respects --limit)")

    # Multi-year support: --years accepts comma separated and/or single range (e.g. 2020-2022)
    multi_years: list[int] = []
    if getattr(args, 'years', None):
        parts = [p.strip() for p in args.years.split(',') if p.strip()]
        for p in parts:
            if '-' in p:
                try:
                    a, b = p.split('-', 1)
                    start_y = int(a)
                    end_y = int(b)
                    if start_y > end_y:
                        start_y, end_y = end_y, start_y
                    multi_years.extend(range(start_y, end_y + 1))
                except ValueError:
                    logger.warning("Invalid year range: %s", p)
            else:
                try:
                    multi_years.append(int(p))
                except ValueError:
                    print(f"[WARN] Invalid year: {p}")
        # Deduplicate & sort
        multi_years = sorted(set(multi_years))
        if multi_years:
            logger.debug(f"Multi-year filter parsed: {multi_years}")
            # Remove single-year preached_year if present to avoid conflict
            if hasattr(args, 'preached_year'):
                args.preached_year = None

    params = build_sermon_query_params(args)
    params.setdefault('broadcasterID', SERMON_AUDIO_BROADCASTER_ID)

    if not any(k in params for k in ('preachedAfterTimestamp', 'preachedBeforeTimestamp', 'year')):
        after = dt.datetime.utcnow() - dt.timedelta(days=30)
        params['preachedAfterTimestamp'] = int(after.timestamp())
        params.setdefault('cache', 'true')

    # If multi-year list requested, perform separate queries per year and merge.
    if multi_years:
        combined: list[SermonLite] = []
        for y in multi_years:
            y_params = params.copy()
            y_params['year'] = y
            logger.debug(f"Fetching year {y} with params: {y_params}")
            batch = fetch_sermons(y_params, max_results=None)
            combined.extend(batch)
            if args.limit and len(combined) >= args.limit:
                combined = combined[:args.limit]
                break
        sermons = combined
    else:
        sermons = fetch_sermons(params, max_results=args.limit)
    if not sermons:
        print('No sermons matched filters.')
        return

    print(f"Matched {len(sermons)} sermons:")
    for s in sermons:
        print(
            f"  {s.preachDate} | {s.sermonID} | {s.displayTitle} | "
            f"{s.speakerName or '-'} | {s.eventType or '-'}"
        )

    if args.list_only:
        return

    if not confirm(f"Process {len(sermons)} sermons?", args.auto_yes):
        console_print('Cancelled')
        return

    # Show processing summary
    console_print(f"🎯 Processing {len(sermons)} sermons...")
    if args.dry_run:
        console_print("🔍 DRY RUN MODE - No changes will be made", "warning")
    if args.no_upload:
        console_print("📁 NO UPLOAD MODE - Audio will not be uploaded", "warning")

    success = 0
    errors = 0

    # Process each sermon with individual progress updates
    for idx, s in enumerate(sermons, 1):
        if not args.verbose:
            console_print(f"[{idx}/{len(sermons)}] Processing: {s.displayTitle}")
        try:
            process_single_sermon(
                s.sermonID,
                no_upload=args.no_upload or args.dry_run,
                verbose=args.verbose
            )
            success += 1
            if not args.verbose:
                console_print(f"[{idx}/{len(sermons)}] ✅ Completed: {s.displayTitle}", "success")
        except Exception as e:  # pragma: no cover
            errors += 1
            error_msg = f"[{idx}/{len(sermons)}] ❌ Error: {s.displayTitle} - {e}"
            if args.verbose:
                console_print(error_msg, "error")
                traceback.print_exc()
            else:
                console_print(error_msg, "error")
        time.sleep(1)

    # Final summary
    if success > 0:
        console_print(f"✅ Completed successfully: {success} sermons", "success")
    if errors > 0:
        console_print(f"❌ Errors encountered: {errors} sermons", "error")
    else:
        console_print("🎉 All sermons processed without errors!", "success")


if __name__ == '__main__':  # pragma: no cover
    try:
        cli_main()
    except Exception as top_e:  # noqa: BLE001
        console_print(f"Fatal error: {top_e}", "error")
        traceback.print_exc()
        sys.exit(1)
