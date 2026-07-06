#!/usr/bin/env python3
"""Migrate sermon directories from flat structure to nested speaker/series/title structure.

Old: processed_sermons/{sermon_id}/
New: processed_sermons/{speaker}/{series}/{title} - {series} - {speaker}/

Also renames files inside directories from {sermon_id}_* to standard names.
"""

import json
import logging
import os
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Add project to path
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


def migrate_sermon_dir(old_dir: Path, output_root: Path, dry_run: bool = False) -> bool:
    """Migrate a single sermon directory from flat to nested structure."""
    meta_path = old_dir / "metadata.json"
    if not meta_path.exists():
        logger.warning("No metadata.json in %s, skipping", old_dir)
        return False

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read metadata from %s: %s", old_dir, e)
        return False

    sermon_id = meta.get("sermonID") or meta.get("sermon_id") or old_dir.name
    speaker = meta.get("speaker", "Unknown")
    series = meta.get("series_title") or meta.get("series") or "No Series"
    title = meta.get("title", sermon_id)

    new_dir = get_sermon_dir(output_root, speaker, series, title, sermon_id)

    if new_dir == old_dir:
        logger.info("Already in correct structure: %s", old_dir)
        return False

    if new_dir.exists():
        logger.warning("Target directory already exists: %s", new_dir)
        return False

    if dry_run:
        logger.info("[DRY RUN] Would move: %s -> %s", old_dir, new_dir)
        return True

    new_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_dir), str(new_dir))
    logger.info("Moved: %s -> %s", old_dir, new_dir)

    # Rename files inside the new directory
    for old_name, new_name in FILE_RENAMES.items():
        old_file = new_dir / old_name
        new_file = new_dir / new_name
        if old_file.exists() and not new_file.exists():
            old_file.rename(new_file)
            logger.debug("  Renamed: %s -> %s", old_name, new_name)

    # Also rename any {sermon_id}_* files
    for f in list(new_dir.iterdir()):
        if f.is_file() and f.name.startswith(sermon_id + "_"):
            suffix = f.name[len(sermon_id) + 1:]
            target = new_dir / suffix
            if not target.exists():
                f.rename(target)
                logger.debug("  Renamed: %s -> %s", f.name, suffix)

    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate sermon directories to nested structure")
    parser.add_argument("--output-dir", default="processed_sermons",
                        help="Base output directory (default: processed_sermons)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    parser.add_argument("--sermon-id", help="Migrate only a specific sermon ID")
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    if not output_root.exists():
        logger.error("Output directory not found: %s", output_root)
        return 1

    migrated = 0
    skipped = 0

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
        for item in sorted(output_root.iterdir()):
            if item.is_dir() and item.name.isdigit():
                if migrate_sermon_dir(item, output_root, args.dry_run):
                    migrated += 1
                else:
                    skipped += 1

    logger.info("Migration complete: %d migrated, %d skipped", migrated, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
