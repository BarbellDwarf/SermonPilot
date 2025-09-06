"""
Sermon Importer - Scan processed_sermons folder and import missing sermons to database

This module provides functionality to scan the processed_sermons directory
and automatically import any sermons that exist as files but are missing 
from the database.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src and ui directories to path
ui_dir = Path(__file__).parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

from database import SermonRepository

logger = logging.getLogger(__name__)


class SermonImporter:
    """Import sermons from processed_sermons folder into database"""

    def __init__(self, processed_sermons_dir: str = "processed_sermons"):
        """Initialize with processed sermons directory"""
        self.processed_sermons_dir = Path(processed_sermons_dir)
        self.repo = SermonRepository()

    def scan_processed_folder(self) -> list[str]:
        """Scan processed_sermons folder and return list of sermon IDs"""
        if not self.processed_sermons_dir.exists():
            logger.warning(f"Processed sermons directory not found: {self.processed_sermons_dir}")
            return []

        sermon_ids = []
        for item in self.processed_sermons_dir.iterdir():
            if item.is_dir() and item.name.isdigit():
                sermon_ids.append(item.name)

        logger.info(f"Found {len(sermon_ids)} sermon directories")
        return sermon_ids

    def get_missing_sermons(self) -> list[str]:
        """Get list of sermon IDs that exist in files but not in database"""
        folder_sermon_ids = self.scan_processed_folder()
        missing_sermons = []

        for sermon_id in folder_sermon_ids:
            existing_sermon = self.repo.get_sermon(sermon_id)
            if not existing_sermon:
                missing_sermons.append(sermon_id)

        logger.info(f"Found {len(missing_sermons)} missing sermons in database")
        return missing_sermons

    def extract_sermon_metadata(self, sermon_id: str, refresh_api_data: bool = False) -> dict[str, Any]:
        """Extract metadata from sermon files in the processed folder"""
        sermon_dir = self.processed_sermons_dir / sermon_id

        if not sermon_dir.exists():
            raise FileNotFoundError(f"Sermon directory not found: {sermon_dir}")

        metadata = {
            'id': sermon_id,
            'title': f"Sermon {sermon_id}",  # Default title
            'speaker': "Unknown",  # Default speaker
            'recorded_date': datetime.now().strftime('%Y-%m-%d'),  # Default date
            'event_type': None,
            'bible_text': None,
            'duration': None,
            'status': 'processed',
            'file_paths': {},
            'content': {},
            'processing_info': {
                'qa_segments': [],
                'qa_segments_count': 0,
                'enhancement_method': 'unknown'
            }
        }

        # Find and process files in the sermon directory
        for file_path in sermon_dir.iterdir():
            if file_path.is_file():
                self._process_sermon_file(file_path, metadata)

        # Try to extract metadata from SermonAudio API data if available
        self._extract_api_metadata(sermon_id, metadata, refresh_api_data)

        return metadata

    def _process_sermon_file(self, file_path: Path, metadata: dict[str, Any]):
        """Process individual sermon file and extract relevant information"""
        file_name = file_path.name
        sermon_id = metadata['id']

        # Description file
        if file_name == f"{sermon_id}_description.txt":
            try:
                with open(file_path, encoding='utf-8') as f:
                    description = f.read().strip()
                    metadata['content']['description'] = description

                    # Try to extract title from first line of description
                    lines = description.split('\n')
                    if lines and len(lines[0]) < 100:  # Likely a title
                        metadata['title'] = lines[0].strip()
                        if len(lines) > 1:
                            metadata['content']['description'] = '\n'.join(lines[1:]).strip()

            except Exception as e:
                logger.warning(f"Could not read description file {file_path}: {e}")

        # Hashtags file
        elif file_name == f"{sermon_id}_hashtags.txt":
            try:
                with open(file_path, encoding='utf-8') as f:
                    hashtags = f.read().strip()
                    metadata['content']['hashtags'] = hashtags
            except Exception as e:
                logger.warning(f"Could not read hashtags file {file_path}: {e}")

        # Transcript file
        elif file_name == f"{sermon_id}_transcript.txt":
            try:
                with open(file_path, encoding='utf-8') as f:
                    transcript = f.read().strip()
                    metadata['content']['transcript_text'] = transcript
            except Exception as e:
                logger.warning(f"Could not read transcript file {file_path}: {e}")

        # Audio files
        elif file_name.endswith('.mp3'):
            if file_name.startswith('processed_'):
                metadata['file_paths']['processed_audio'] = str(file_path)
            elif file_name.startswith('original_'):
                metadata['file_paths']['original_audio'] = str(file_path)
            elif file_name.startswith(sermon_id):
                # Handle cases where original audio is named with just sermon_id
                metadata['file_paths']['original_audio'] = str(file_path)

            # Try to get audio duration
            try:
                metadata['duration'] = self._get_audio_duration(file_path)
            except Exception as e:
                logger.warning(f"Could not get duration for {file_path}: {e}")

        elif file_name.endswith('.wav'):
            if 'ai_upscaled' in file_name:
                metadata['file_paths']['enhanced_audio'] = str(file_path)
                metadata['processing_info']['enhancement_method'] = 'ai_upscaling'

        # Processing info files
        elif file_name == f"{sermon_id}_processing_info.json":
            try:
                with open(file_path, encoding='utf-8') as f:
                    processing_data = json.load(f)
                    metadata['processing_info'].update(processing_data)
            except Exception as e:
                logger.warning(f"Could not read processing info {file_path}: {e}")

        # Q&A segments file
        elif file_name == f"{sermon_id}_qa_segments.json":
            try:
                with open(file_path, encoding='utf-8') as f:
                    qa_segments = json.load(f)
                    metadata['processing_info']['qa_segments'] = qa_segments
                    metadata['processing_info']['qa_segments_count'] = len(qa_segments)
                    metadata['processing_info']['qa_normalization_applied'] = len(qa_segments) > 0
            except Exception as e:
                logger.warning(f"Could not read Q&A segments {file_path}: {e}")

    def _extract_api_metadata(self, sermon_id: str, metadata: dict[str, Any], refresh_api_data: bool = False):
        """Try to extract metadata from SermonAudio API data if available"""
        try:
            # First check if there's a cached API response
            api_cache_file = self.processed_sermons_dir / sermon_id / f"{sermon_id}_api_data.json"
            api_data = None

            # Clear cache if refresh requested
            if refresh_api_data and api_cache_file.exists():
                api_cache_file.unlink()
                logger.info(f"Cleared cached API data for sermon {sermon_id}")

            if api_cache_file.exists() and not refresh_api_data:
                with open(api_cache_file, encoding='utf-8') as f:
                    api_data = json.load(f)
                    logger.info(f"Using cached API data for sermon {sermon_id}")
            else:
                # Try to fetch live data from SermonAudio API
                logger.info(f"Fetching live API data for sermon {sermon_id}")
                from sermonaudio_api import SermonAudioAPI
                api_client = SermonAudioAPI()
                api_data = api_client.get_sermon_details(sermon_id, force_refresh=True)

                # Cache the API response for future use
                if api_data:
                    try:
                        api_cache_file.parent.mkdir(exist_ok=True)
                        with open(api_cache_file, 'w', encoding='utf-8') as f:
                            json.dump(api_data, f, indent=2, default=str)
                        logger.info(f"Cached API data for sermon {sermon_id}")
                    except Exception as cache_error:
                        logger.warning(f"Could not cache API data for {sermon_id}: {cache_error}")

            # Extract relevant fields from API data
            if api_data:
                if 'title' in api_data:
                    metadata['title'] = api_data['title']
                if 'fullTitle' in api_data:
                    metadata['title'] = api_data['fullTitle']  # Use full title if available

                # Handle speaker data (could be object or string)
                if 'speaker' in api_data:
                    speaker_data = api_data['speaker']
                    if isinstance(speaker_data, dict):
                        metadata['speaker'] = speaker_data.get('displayName', speaker_data.get('name', 'Unknown'))
                    else:
                        metadata['speaker'] = str(speaker_data)
                elif 'preacher' in api_data:
                    metadata['speaker'] = api_data['preacher']

                if 'eventType' in api_data:
                    metadata['event_type'] = api_data['eventType']
                if 'bibleText' in api_data:
                    metadata['bible_text'] = api_data['bibleText']
                if 'displayEventDate' in api_data:
                    metadata['recorded_date'] = api_data['displayEventDate']
                if 'preachDate' in api_data:
                    metadata['recorded_date'] = api_data['preachDate']
                if 'seriesTitle' in api_data:
                    metadata['series'] = api_data['seriesTitle']
                if 'description' in api_data and not metadata['content'].get('description'):
                    metadata['content']['description'] = api_data['description']
                if 'moreInfoText' in api_data and not metadata['content'].get('description'):
                    metadata['content']['description'] = api_data['moreInfoText']

                logger.info(f"Successfully extracted API metadata for sermon {sermon_id}: {metadata.get('title', 'No title')} by {metadata.get('speaker', 'Unknown')}")

        except Exception as e:
            logger.debug(f"Could not extract API metadata for {sermon_id}: {e}")

    def _fetch_sermon_metadata_from_api(self, sermon_id: str) -> dict[str, Any] | None:
        """Fetch sermon metadata directly from SermonAudio API"""
        try:
            # Try to get configuration for API access
            from pathlib import Path

            import yaml

            # Look for config.yaml in parent directory
            config_path = Path(__file__).parent.parent / "config.yaml"
            if not config_path.exists():
                logger.warning("config.yaml not found - cannot fetch API data")
                return None

            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)

            api_key = config.get('api_key')
            if not api_key:
                logger.warning("API key not found in config - cannot fetch API data")
                return None

            # Import sermon_updater functions to use existing API logic
            # Set the API key
            import sermonaudio

            import sermon_updater
            sermonaudio.set_api_key(api_key)

            # Fetch sermon details using the existing get_sermon_details function
            sermon_details = sermon_updater.get_sermon_details(sermon_id)

            if sermon_details:
                logger.info(f"Successfully fetched API data for sermon {sermon_id}")
                return sermon_details
            else:
                logger.warning(f"No API data found for sermon {sermon_id}")
                return None

        except Exception as e:
            logger.warning(f"Failed to fetch API data for sermon {sermon_id}: {e}")
            return None

    def _get_audio_duration(self, audio_path: Path) -> float | None:
        """Get duration of audio file in seconds"""
        try:
            # Try using mutagen if available
            try:
                from mutagen.mp3 import MP3
                from mutagen.wave import WAVE

                if audio_path.suffix.lower() == '.mp3':
                    audio = MP3(str(audio_path))
                    return audio.info.length
                elif audio_path.suffix.lower() == '.wav':
                    audio = WAVE(str(audio_path))
                    return audio.info.length
            except ImportError:
                pass

            # Fallback: estimate duration from file size (rough approximation)
            file_size = audio_path.stat().st_size
            if audio_path.suffix.lower() == '.mp3':
                # Rough estimate: 1 minute = ~1MB for typical sermon audio
                estimated_duration = file_size / (1024 * 1024) * 60
                return estimated_duration

        except Exception as e:
            logger.warning(f"Could not determine duration for {audio_path}: {e}")

        return None

    def import_sermon(self, sermon_id: str, refresh_api_data: bool = False) -> bool:
        """Import a single sermon into the database"""
        try:
            # Clear cached API data if refresh requested
            if refresh_api_data:
                api_cache_file = self.processed_sermons_dir / sermon_id / f"{sermon_id}_api_data.json"
                if api_cache_file.exists():
                    api_cache_file.unlink()
                    logger.info(f"Cleared cached API data for sermon {sermon_id}")

            metadata = self.extract_sermon_metadata(sermon_id, refresh_api_data)
            success = self.repo.save_sermon(metadata)

            if success:
                logger.info(f"Successfully imported sermon {sermon_id}")
            else:
                logger.error(f"Failed to import sermon {sermon_id}")

            return success

        except Exception as e:
            logger.error(f"Error importing sermon {sermon_id}: {e}")
            return False

    def import_missing_sermons(self) -> tuple[int, int, list[str]]:
        """
        Import all missing sermons from processed_sermons folder
        
        Returns:
            Tuple of (successful_imports, failed_imports, failed_sermon_ids)
        """
        missing_sermons = self.get_missing_sermons()

        if not missing_sermons:
            logger.info("No missing sermons found")
            return 0, 0, []

        successful_imports = 0
        failed_imports = 0
        failed_sermon_ids = []

        for sermon_id in missing_sermons:
            try:
                if self.import_sermon(sermon_id):
                    successful_imports += 1
                else:
                    failed_imports += 1
                    failed_sermon_ids.append(sermon_id)
            except Exception as e:
                logger.error(f"Failed to import sermon {sermon_id}: {e}")
                failed_imports += 1
                failed_sermon_ids.append(sermon_id)

        logger.info(f"Import complete: {successful_imports} successful, {failed_imports} failed")
        return successful_imports, failed_imports, failed_sermon_ids

    def get_import_status(self) -> dict[str, Any]:
        """Get status of sermons in folder vs database"""
        folder_sermons = self.scan_processed_folder()
        missing_sermons = self.get_missing_sermons()

        # Get sermons that are in database
        in_database = len(folder_sermons) - len(missing_sermons)

        return {
            'total_in_folder': len(folder_sermons),
            'in_database': in_database,
            'missing_from_database': len(missing_sermons),
            'missing_sermon_ids': missing_sermons[:10],  # First 10 for preview
            'folder_path': str(self.processed_sermons_dir)
        }


# Convenience functions for UI
def get_import_status() -> dict[str, Any]:
    """Get current import status"""
    importer = SermonImporter()
    return importer.get_import_status()


def import_missing_sermons() -> tuple[int, int, list[str]]:
    """Import all missing sermons"""
    importer = SermonImporter()
    return importer.import_missing_sermons()


def import_single_sermon(sermon_id: str) -> bool:
    """Import a single sermon by ID"""
    importer = SermonImporter()
    return importer.import_sermon(sermon_id)
