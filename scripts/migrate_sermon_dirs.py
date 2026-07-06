#!/usr/bin/env python3
"""Migrate sermon directories from flat structure to nested speaker/series/title structure.

Old: processed_sermons/{sermon_id}/
New: processed_sermons/{speaker}/{series}/{title} - {series} - {speaker}/

For directories without metadata.json, fetches data from the SermonAudio API.
"""

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sermon_paths import FILENAMES, get_sermon_dir, sanitize

FILE_RENAMES = {
    "transcript.txt": FILENAMES["transcript"],
    "description.txt": FILENAMES["description"],
    "hashtags.txt": FILENAMES["hashtags"],
    "metadata.json": FILENAMES["metadata"],
    "api_data.json": FILENAMES["api_data"],
    "processing_info.json": FILENAMES["processing_info"],
    "qa_segments.json": FILENAMES["qa_segments"],
    "audio.mp3": FILENAMES["audio"],
    "enhanced.mp3": FILENAMES["enhanced"],
    "original.mp3": FILENAMES["original"],
    "temp.mp3": FILENAMES["temp"],
}


def fetch_sermon_metadata(sermon_id: str) -> dict | None:
    """Fetch sermon metadata from SermonAudio API."""
    try:
        from dotenv import load_dotenv
        load_dotenv()

        from sermon_updater import get_sermon_details
        data = get_sermon_details(sermon_id)
        if not data:
            return None

        speaker = "Unknown"
        if data.get("speaker"):
            s = data["speaker"]
            speaker = (s.get("full_name") or s.get("display_name") or
                       s.get("displayName") or str(s))

        series = data.get("seriesTitle") or data.get("series_title") or ""

        title = (data.get("display_title") or data.get("displayTitle") or
                 data.get("title") or sermon_id)

        return {
            "sermonID": sermon_id,
            "sermon_id": sermon_id,
            "title": title,
            "speaker": speaker,
            "series_title": series,
            "recorded_date": data.get("preachDate", ""),
            "event_type": str(data.get("event_type") or data.get("eventType", "")),
            "bible_text": data.get("bibleText", ""),
        }
    except Exception as e:
        logger.warning("API fetch failed for %s: %s", sermon_id, e)
        return None


def migrate_sermon_dir(old_dir: Path, output_root: Path, dry_run: bool = False) -> bool:
    """Migrate a single sermon directory from flat to nested structure."""
    meta_path = old_dir / "metadata.json"
    meta = None

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read metadata from %s: %s", old_dir, e)

    sermon_id = old_dir.name

    if not meta:
        logger.info("Fetching API data for %s...", sermon_id)
        meta = fetch_sermon_metadata(sermon_id)
        if not meta:
            logger.warning("No data available for %s, skipping", sermon_id)
            return False
        if not dry_run:
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            logger.info("Saved metadata.json for %s", sermon_id)

    speaker = meta.get("speaker", "Unknown")
    series = meta.get("series_title") or meta.get("series") or "No Series"
    title = meta.get("title", sermon_id)

    new_dir = get_sermon_dir(output_root, speaker, series, title, sermon_id)

    if new_dir == old_dir:
        logger.info("Already in correct structure: %s", old_dir)
        return False

    if new_dir.exists():
        logger.warning("Target already exists: %s, merging contents", new_dir)
        if not dry_run:
            for item in old_dir.iterdir():
                dest = new_dir / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            shutil.rmtree(str(old_dir))
        return True

    if dry_run:
        logger.info("[DRY RUN] Would move: %s -> %s", old_dir, new_dir)
        return True

    new_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_dir), str(new_dir))
    logger.info("Moved: %s -> %s", old_dir, new_dir)

    for old_name, new_name in FILE_RENAMES.items():
        old_file = new_dir / old_name
        new_file = new_dir / new_name
        if old_file.exists() and not new_file.exists():
            old_file.rename(new_file)

    for f in list(new_dir.iterdir()):
        if f.is_file() and f.name.startswith(sermon_id + "_"):
            suffix = f.name[len(sermon_id) + 1:]
            target = new_dir / suffix
            if not target.exists():
                f.rename(target)

    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate sermon directories to nested structure")
    parser.add_argument("--output-dir", default="processed_sermons",
                        help="Base output directory (default: processed_sermons)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    parser.add_argument("--sermon-id", help="Migrate only a specific sermon ID")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between API calls in seconds (default: 0.5)")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    if not output_root.exists():
        logger.error("Output directory not found: %s", output_root)
        return 1

    migrated = 0
    skipped = 0
    api_calls = 0

    if args.sermon_id:
        old_dir = output_root / args.sermon_id
        if old_dir.exists() and old_dir.is_dir():
            if migrate_sermon_dir(old_dir, output_root, args.dry_run):
                migrated += 1
            else:
                skipped += 1
        else:
            logger.error("Sermon directory not found: %s", old_dir)
            return 1
    else:
        items = sorted(output_root.iterdir())
        total = len([i for i in items if i.is_dir() and i.name.isdigit()])
        for idx, item in enumerate(items):
            if not item.is_dir() or not item.name.isdigit():
                continue
            has_meta = (item / "metadata.json").exists()
            if not has_meta:
                api_calls += 1
                if api_calls > 1 and api_calls % 10 == 0:
                    logger.info("Rate limit pause after %d API calls...", api_calls)
                    time.sleep(2)
                else:
                    time.sleep(args.delay)
            if migrate_sermon_dir(item, output_root, args.dry_run):
                migrated += 1
            else:
                skipped += 1
            if (idx + 1) % 50 == 0:
                logger.info("Progress: %d/%d processed (%d migrated, %d skipped, %d API calls)",
                           idx + 1, total, migrated, skipped, api_calls)

    logger.info("Migration complete: %d migrated, %d skipped (%d API calls)",
               migrated, skipped, api_calls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
