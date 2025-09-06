"""
SermonAudio API Client - Fetch speakers, series, and sermon metadata

Provides comprehensive API integration for:
- Fetching broadcaster metadata (speakers, series)
- Caching API responses for performance
- Providing dropdown data for UI forms
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

# Add src directory to path
ui_dir = Path(__file__).parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

logger = logging.getLogger(__name__)


class SermonAudioAPI:
    """SermonAudio API client with caching"""

    def __init__(self):
        """Initialize API client"""
        self.api_key = None
        self.cache_dir = Path("api_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self._load_config()

    def _load_config(self):
        """Load API configuration"""
        try:
            config_path = Path(__file__).parent.parent / "config.yaml"
            if config_path.exists():
                with open(config_path, encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                self.api_key = config.get('api_key')
                if self.api_key:
                    import sermonaudio
                    sermonaudio.set_api_key(self.api_key)
                    logger.info("SermonAudio API key loaded successfully")
                else:
                    logger.warning("No API key found in config.yaml")
            else:
                logger.warning("config.yaml not found")
        except Exception as e:
            logger.error(f"Error loading config: {e}")

    def _get_cache_file(self, cache_key: str) -> Path:
        """Get cache file path for a given key"""
        return self.cache_dir / f"{cache_key}.json"

    def _is_cache_valid(self, cache_file: Path, max_age_hours: int = 24) -> bool:
        """Check if cache file is valid and not expired"""
        if not cache_file.exists():
            return False
        
        try:
            file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            return file_age < timedelta(hours=max_age_hours)
        except Exception:
            return False

    def _load_from_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Load data from cache if valid"""
        cache_file = self._get_cache_file(cache_key)
        if self._is_cache_valid(cache_file):
            try:
                with open(cache_file, encoding='utf-8') as f:
                    data = json.load(f)
                    logger.debug(f"Loaded {cache_key} from cache")
                    return data
            except Exception as e:
                logger.warning(f"Error reading cache file {cache_file}: {e}")
        return None

    def _save_to_cache(self, cache_key: str, data: dict[str, Any]):
        """Save data to cache"""
        cache_file = self._get_cache_file(cache_key)
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            logger.debug(f"Saved {cache_key} to cache")
        except Exception as e:
            logger.warning(f"Error saving to cache file {cache_file}: {e}")

    def get_speakers(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Get list of speakers from API with caching"""
        cache_key = "speakers"
        
        if not force_refresh:
            cached_data = self._load_from_cache(cache_key)
            if cached_data:
                return cached_data.get('speakers', [])

        speakers = []
        if not self.api_key:
            logger.warning("No API key available for fetching speakers")
            return speakers

        try:
            import sermon_updater
            
            # Fetch speakers/pastors from API
            logger.info("Fetching speakers from SermonAudio API...")
            api_speakers = sermon_updater.get_broadcaster_pastors()
            
            if api_speakers:
                for speaker_name in api_speakers:
                    speakers.append({
                        'id': speaker_name,
                        'name': speaker_name,
                        'displayName': speaker_name
                    })
                
                # Cache the results
                cache_data = {
                    'speakers': speakers,
                    'fetched_at': datetime.now().isoformat()
                }
                self._save_to_cache(cache_key, cache_data)
                logger.info(f"Fetched and cached {len(speakers)} speakers")
            
        except Exception as e:
            logger.error(f"Error fetching speakers from API: {e}")

        return speakers

    def get_series(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Get list of series from API with caching"""
        cache_key = "series"
        
        if not force_refresh:
            cached_data = self._load_from_cache(cache_key)
            if cached_data:
                return cached_data.get('series', [])

        series = []
        if not self.api_key:
            logger.warning("No API key available for fetching series")
            return series

        try:
            import sermon_updater
            
            # Fetch series from API
            logger.info("Fetching series from SermonAudio API...")
            api_series = sermon_updater.get_broadcaster_series()
            
            if api_series:
                for series_name in api_series:
                    series.append({
                        'id': series_name,
                        'name': series_name,
                        'description': '',
                        'sermonCount': 0
                    })
                
                # Cache the results
                cache_data = {
                    'series': series,
                    'fetched_at': datetime.now().isoformat()
                }
                self._save_to_cache(cache_key, cache_data)
                logger.info(f"Fetched and cached {len(series)} series")
            
        except Exception as e:
            logger.error(f"Error fetching series from API: {e}")

        return series

    def get_sermon_details(self, sermon_id: str, force_refresh: bool = False) -> dict[str, Any] | None:
        """Get sermon details from API with caching"""
        cache_key = f"sermon_{sermon_id}"
        
        if not force_refresh:
            cached_data = self._load_from_cache(cache_key)
            if cached_data:
                return cached_data.get('sermon', None)

        if not self.api_key:
            logger.warning(f"No API key available for fetching sermon {sermon_id}")
            return None

        try:
            import sermon_updater
            
            # Fetch sermon details using existing function
            logger.info(f"Fetching sermon {sermon_id} from SermonAudio API...")
            sermon_details = sermon_updater.get_sermon_details(sermon_id)
            
            if sermon_details:
                # Cache the results
                cache_data = {
                    'sermon': sermon_details,
                    'fetched_at': datetime.now().isoformat()
                }
                self._save_to_cache(cache_key, cache_data)
                logger.info(f"Fetched and cached sermon {sermon_id}")
                return sermon_details
            
        except Exception as e:
            logger.error(f"Error fetching sermon {sermon_id} from API: {e}")

        return None

    def clear_cache(self):
        """Clear all cached API data"""
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared all API cache")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

    def is_configured(self) -> bool:
        """Check if API is properly configured"""
        return bool(self.api_key)
