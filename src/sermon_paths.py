"""Centralized sermon path construction and discovery.

All sermon directory paths are built through this module so that
the directory structure can be changed in one place.

Current structure:
  processed_sermons/{speaker}/{series}/{title} - {series} - {speaker}/
    {Title} - {Series} - {Speaker} - {Date} - Original.mp3
    {Title} - {Series} - {Speaker} - {Date} - Processed.mp3
    transcript.txt, description.txt, hashtags.txt
    metadata.json, api_data.json, processing_info.json, qa_segments.json
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Internal file names (temp files, metadata, etc.)
FILENAMES = {
    "audio": "audio.mp3",
    "enhanced": "enhanced.mp3",
    "original": "original.mp3",
    "original_audio": "original.mp3",
    "original_video": "original.mp4",
    "temp": "temp.mp3",
    "transcript": "transcript.txt",
    "description": "description.txt",
    "hashtags": "hashtags.txt",
    "metadata": "metadata.json",
    "api_data": "api_data.json",
    "processing_info": "processing_info.json",
    "qa_segments": "qa_segments.json",
    "temp_video": "video_source.mp4",
    "enhanced_video": "video_enhanced.mp4",
}


def sanitize(name: str) -> str:
    """Sanitize a name for use as a filesystem component."""
    if not name:
        return "Unknown"
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name[:200]
    return name or "Unknown"


def build_output_filename(
    title: str | None,
    series: str | None,
    speaker: str | None,
    date: str | None,
    kind: str,
    ext: str,
) -> str:
    """Build a descriptive output filename.

    Format: {Title} - {Series} - {Speaker} - {Date} - {Kind}.{ext}

    kind is e.g. "Original" or "Processed".
    """
    parts = [
        sanitize(title or "Unknown"),
        sanitize(series or "No Series"),
        sanitize(speaker or "Unknown"),
        sanitize(date or "Unknown"),
        kind,
    ]
    return f"{' - '.join(parts)}.{ext.lstrip('.')}"


def get_sermon_dir(
    output_root: str | Path,
    speaker: str | None,
    series: str | None,
    title: str | None,
    sermon_id: str,
) -> Path:
    """Build the sermon directory path.

    Structure: {output_root}/{speaker}/{series}/{title} - {series} - {speaker}/
    """
    root = Path(output_root)
    safe_speaker = sanitize(speaker or "Unknown")
    safe_series = sanitize(series or "No Series")
    safe_title = sanitize(title or sermon_id)
    dir_name = f"{safe_title} - {safe_series} - {safe_speaker}"
    return root / safe_speaker / safe_series / dir_name


def get_file_path(sermon_dir: str | Path, file_type: str) -> Path:
    """Get the path for a specific file type within a sermon directory."""
    filename = FILENAMES.get(file_type)
    if not filename:
        raise ValueError(f"Unknown file type: {file_type}")
    return Path(sermon_dir) / filename


def read_metadata(sermon_dir: str | Path) -> dict[str, Any] | None:
    """Read metadata.json from a sermon directory."""
    meta_path = Path(sermon_dir) / FILENAMES["metadata"]
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read metadata from %s: %s", meta_path, e)
        return None


def discover_sermons(output_root: str | Path) -> list[Path]:
    """Discover all sermon directories under output_root.

    Walks the {speaker}/{series}/{dir_name} structure and returns
    paths to leaf directories that contain metadata.json.
    """
    root = Path(output_root)
    if not root.exists():
        return []

    sermons: list[Path] = []
    for speaker_dir in root.iterdir():
        if not speaker_dir.is_dir():
            continue
        for series_dir in speaker_dir.iterdir():
            if not series_dir.is_dir():
                continue
            for sermon_dir in series_dir.iterdir():
                if not sermon_dir.is_dir():
                    continue
                if (sermon_dir / FILENAMES["metadata"]).exists():
                    sermons.append(sermon_dir)
    return sermons


def find_sermon_dir(
    output_root: str | Path,
    sermon_id: str,
) -> Path | None:
    """Find a sermon directory by sermon_id.

    Searches the full {speaker}/{series}/{dir_name} tree for a
    directory whose metadata.json contains the given sermon_id.
    """
    root = Path(output_root)
    if not root.exists():
        return None

    for speaker_dir in root.iterdir():
        if not speaker_dir.is_dir():
            continue
        for series_dir in speaker_dir.iterdir():
            if not series_dir.is_dir():
                continue
            for sermon_dir in series_dir.iterdir():
                if not sermon_dir.is_dir():
                    continue
                meta = read_metadata(sermon_dir)
                if meta and meta.get("sermon_id") == sermon_id:
                    return sermon_dir
    return None
