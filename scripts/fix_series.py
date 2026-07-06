#!/usr/bin/env python3
"""Re-fetch series data for sermons that have 'No Series' in their metadata.json
and reorganize directories accordingly."""

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from sermon_updater import get_sermon_details
from src.sermon_paths import get_sermon_dir

root = Path("processed_sermons")
fixed = 0

for speaker_dir in sorted(root.iterdir()):
    if not speaker_dir.is_dir() or speaker_dir.name.startswith(("draft_", "dryrun")):
        continue
    for series_dir in sorted(speaker_dir.iterdir()):
        if not series_dir.is_dir():
            continue
        for sermon_dir in sorted(series_dir.iterdir()):
            if not sermon_dir.is_dir():
                continue
            meta_file = sermon_dir / "metadata.json"
            if not meta_file.exists():
                continue
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            sid = meta.get("sermonID") or meta.get("sermon_id", "")
            if not sid:
                continue
            current_series = meta.get("series_title") or ""
            if current_series:
                continue

            print(f"Fetching series for {sid} ({sermon_dir.name})...")
            data = get_sermon_details(sid)
            if not data:
                print(f"  No data for {sid}")
                continue

            series = (data.get("seriesTitle") or data.get("series_title") or
                      (data.get("series") or {}).get("title") or "")
            if not series:
                print(f"  No series for {sid}")
                continue

            meta["series_title"] = series
            meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            print(f"  Series: {series}")

            speaker = meta.get("speaker", "Unknown")
            title = meta.get("title", sid)
            new_dir = get_sermon_dir(root, speaker, series, title, sid)

            if new_dir == sermon_dir:
                print(f"  Already correct path")
                continue

            if new_dir.exists():
                print(f"  Target exists, merging")
                for item in sermon_dir.iterdir():
                    dest = new_dir / item.name
                    if not dest.exists():
                        shutil.move(str(item), str(dest))
                shutil.rmtree(str(sermon_dir))
            else:
                new_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(sermon_dir), str(new_dir))
                print(f"  Moved to {new_dir.name}")

            fixed += 1
            time.sleep(0.3)

# Clean up empty dirs
for speaker_dir in list(root.iterdir()):
    if not speaker_dir.is_dir():
        continue
    for series_dir in list(speaker_dir.iterdir()):
        if series_dir.is_dir() and not any(series_dir.iterdir()):
            series_dir.rmdir()
            print(f"Removed empty: {series_dir}")

print(f"\nFixed {fixed} sermons with series data")
