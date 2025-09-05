"""
Sermon Manager - Hybrid local/remote data management

Provides efficient sermon data retrieval by combining:
- SermonAudio API for comprehensive sermon listings
- Local filesystem scanning for processed files
- SQLite caching for performance optimization
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import os
import sys

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(parent_dir / "src"))

# Import sermonaudio only if available (optional for UI testing)
try:
    import sermonaudio
    sermonaudio_available = True
except ImportError:
    sermonaudio_available = False
    # Create mock sermonaudio module for testing
    class MockSermonAudio:
        @staticmethod
        def set_api_key(key):
            pass
    sermonaudio = MockSermonAudio()

from database import SermonRepository, get_db
import yaml

logger = logging.getLogger(__name__)

@dataclass
class AudioFiles:
    """Audio file information"""
    original: Optional[str] = None
    processed: Optional[str] = None
    original_url: Optional[str] = None
    duration: Optional[float] = None

@dataclass
class SermonData:
    """Comprehensive sermon data model"""
    id: str
    title: str
    date: datetime
    speaker: str
    description: str
    hashtags: List[str]
    local_available: bool
    remote_available: bool
    audio_files: AudioFiles
    transcript: Optional[str] = None
    event_type: Optional[str] = None
    bible_text: Optional[str] = None
    status: str = "unknown"
    processing_info: Dict[str, Any] = None
    qa_segments: List[Dict] = None

    def __post_init__(self):
        if self.processing_info is None:
            self.processing_info = {}
        if self.qa_segments is None:
            self.qa_segments = []

@dataclass 
class SermonDetails:
    """Detailed sermon information with all content"""
    sermon_data: SermonData
    content: Dict[str, Any]
    files: Dict[str, str]
    analytics: Optional[Dict[str, Any]] = None

class SermonManager:
    """Manages sermon data with hybrid local/remote retrieval"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with configuration"""
        self.config = config
        self.api_key = config.get('api_key')
        self.broadcaster_id = config.get('broadcaster_id')
        self.output_directory = Path(config.get('output_directory', 'processed_sermons'))
        self.cache_ttl = config.get('web_ui', {}).get('sermon_cache_ttl', 3600)  # 1 hour
        
        # Initialize SermonAudio API
        if self.api_key:
            sermonaudio.set_api_key(self.api_key)
        
        # Initialize repository
        self.repo = SermonRepository()
        
        # Cache for frequently accessed data
        self._sermon_list_cache = None
        self._cache_timestamp = None
    
    async def get_sermon_list(self, filters: Optional[Dict[str, Any]] = None) -> List[SermonData]:
        """Get list of all sermons with hybrid local/remote data"""
        try:
            # Check cache first
            if self._is_cache_valid():
                logger.debug("Using cached sermon list")
                return self._apply_filters(self._sermon_list_cache, filters)
            
            # Get remote sermon IDs
            remote_sermons = await self._fetch_remote_sermons(filters)
            
            # Scan local directory
            local_data = self.scan_local_sermons()
            
            # Merge data
            merged_sermons = self.merge_local_remote_data(remote_sermons, local_data)
            
            # Update cache
            self._sermon_list_cache = merged_sermons
            self._cache_timestamp = datetime.now()
            
            return self._apply_filters(merged_sermons, filters)
            
        except Exception as e:
            logger.error(f"Error getting sermon list: {e}")
            # Fallback to local data only
            local_data = self.scan_local_sermons()
            return list(local_data.values())
    
    async def get_sermon_details(self, sermon_id: str) -> Optional[SermonDetails]:
        """Get detailed information for a specific sermon"""
        try:
            # Check local first
            local_data = self._get_local_sermon_data(sermon_id)
            
            # Get remote data if needed
            remote_data = None
            if not local_data or not local_data.get('complete'):
                remote_data = await self._fetch_remote_sermon_details(sermon_id)
            
            # Merge and create detailed object
            sermon_data = self._merge_sermon_details(sermon_id, local_data, remote_data)
            
            if not sermon_data:
                return None
            
            # Get additional content
            content = self._get_sermon_content(sermon_id)
            files = self._get_sermon_files(sermon_id)
            
            return SermonDetails(
                sermon_data=sermon_data,
                content=content,
                files=files,
                analytics=None  # Will be populated by analytics manager
            )
            
        except Exception as e:
            logger.error(f"Error getting sermon details for {sermon_id}: {e}")
            return None
    
    def scan_local_sermons(self) -> Dict[str, SermonData]:
        """Scan local directory for processed sermon files"""
        local_sermons = {}
        
        if not self.output_directory.exists():
            return local_sermons
        
        for sermon_dir in self.output_directory.iterdir():
            if not sermon_dir.is_dir():
                continue
                
            sermon_id = sermon_dir.name
            
            # Get basic file information
            audio_files = AudioFiles()
            transcript_content = None
            
            # Check for audio files
            for audio_file in sermon_dir.glob("*.mp3"):
                if "original" in audio_file.name.lower():
                    audio_files.original = str(audio_file)
                elif "enhanced" in audio_file.name.lower() or "processed" in audio_file.name.lower():
                    audio_files.processed = str(audio_file)
                else:
                    # Default to processed if no specific naming
                    audio_files.processed = str(audio_file)
            
            # Check for transcript
            transcript_file = sermon_dir / "transcript.txt"
            if transcript_file.exists():
                try:
                    transcript_content = transcript_file.read_text(encoding='utf-8')
                except Exception as e:
                    logger.warning(f"Could not read transcript for {sermon_id}: {e}")
            
            # Get metadata from database
            db_sermon = self.repo.get_sermon(sermon_id)
            
            if db_sermon:
                # Create SermonData from database
                sermon_data = SermonData(
                    id=sermon_id,
                    title=db_sermon.get('title', f'Sermon {sermon_id}'),
                    date=datetime.fromisoformat(db_sermon.get('recorded_date', '1900-01-01')),
                    speaker=db_sermon.get('speaker', 'Unknown'),
                    description=db_sermon.get('description', ''),
                    hashtags=db_sermon.get('hashtags', []),
                    local_available=True,
                    remote_available=False,  # Will be updated during merge
                    audio_files=audio_files,
                    transcript=transcript_content,
                    event_type=db_sermon.get('event_type'),
                    bible_text=db_sermon.get('bible_text'),
                    status=db_sermon.get('status', 'processed'),
                    processing_info=db_sermon.get('processing_info', {}),
                    qa_segments=db_sermon.get('qa_segments', [])
                )
            else:
                # Create minimal SermonData for unknown local files
                sermon_data = SermonData(
                    id=sermon_id,
                    title=f'Local Sermon {sermon_id}',
                    date=datetime.fromtimestamp(sermon_dir.stat().st_mtime),
                    speaker='Unknown',
                    description='',
                    hashtags=[],
                    local_available=True,
                    remote_available=False,
                    audio_files=audio_files,
                    transcript=transcript_content,
                    status='local_only'
                )
            
            local_sermons[sermon_id] = sermon_data
        
        return local_sermons
    
    def merge_local_remote_data(self, remote_sermons: List[Dict], local_data: Dict[str, SermonData]) -> List[SermonData]:
        """Merge local and remote sermon data"""
        merged = {}
        
        # Start with local data
        for sermon_id, local_sermon in local_data.items():
            merged[sermon_id] = local_sermon
        
        # Add/update with remote data
        for remote_sermon in remote_sermons:
            sermon_id = str(remote_sermon.get('id', ''))
            if not sermon_id:
                continue
            
            # Parse date safely
            try:
                date_str = remote_sermon.get('preachDate', '')
                if date_str:
                    sermon_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    sermon_date = datetime.now()
            except (ValueError, TypeError):
                sermon_date = datetime.now()
            
            if sermon_id in merged:
                # Update existing local data with remote info
                local_sermon = merged[sermon_id]
                local_sermon.remote_available = True
                local_sermon.title = remote_sermon.get('fullTitle', local_sermon.title)
                local_sermon.speaker = remote_sermon.get('speaker', {}).get('displayName', local_sermon.speaker)
                local_sermon.date = sermon_date
                local_sermon.event_type = remote_sermon.get('eventType', local_sermon.event_type)
                local_sermon.bible_text = remote_sermon.get('bibleText', local_sermon.bible_text)
                
                # Update audio URL if available
                if remote_sermon.get('audioUrl'):
                    local_sermon.audio_files.original_url = remote_sermon['audioUrl']
            else:
                # Create new entry for remote-only sermon
                audio_files = AudioFiles(original_url=remote_sermon.get('audioUrl'))
                
                sermon_data = SermonData(
                    id=sermon_id,
                    title=remote_sermon.get('fullTitle', f'Sermon {sermon_id}'),
                    date=sermon_date,
                    speaker=remote_sermon.get('speaker', {}).get('displayName', 'Unknown'),
                    description=remote_sermon.get('shortDescription', ''),
                    hashtags=[],
                    local_available=False,
                    remote_available=True,
                    audio_files=audio_files,
                    event_type=remote_sermon.get('eventType'),
                    bible_text=remote_sermon.get('bibleText'),
                    status='remote_only'
                )
                
                merged[sermon_id] = sermon_data
        
        return list(merged.values())
    
    async def _fetch_remote_sermons(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Fetch sermon list from SermonAudio API"""
        if not self.api_key or not self.broadcaster_id:
            logger.warning("SermonAudio API credentials not configured")
            return []
        
        try:
            # Build API query parameters
            params = {
                'broadcasterId': self.broadcaster_id,
                'limit': filters.get('limit', 100) if filters else 100
            }
            
            # Add filters if provided
            if filters:
                if filters.get('event_type'):
                    params['eventType'] = filters['event_type']
                if filters.get('since_days'):
                    since_date = datetime.now() - timedelta(days=filters['since_days'])
                    params['startDate'] = since_date.strftime('%Y-%m-%d')
                if filters.get('search_keyword'):
                    params['keyword'] = filters['search_keyword']
            
            # Make API call (synchronous for now, can be made async)
            sermons = sermonaudio.get_sermons(**params)
            return sermons if sermons else []
            
        except Exception as e:
            logger.error(f"Error fetching remote sermons: {e}")
            return []
    
    async def _fetch_remote_sermon_details(self, sermon_id: str) -> Optional[Dict]:
        """Fetch detailed sermon info from SermonAudio API"""
        if not self.api_key:
            return None
        
        try:
            sermon = sermonaudio.get_sermon(sermon_id)
            return sermon
        except Exception as e:
            logger.error(f"Error fetching remote sermon details for {sermon_id}: {e}")
            return None
    
    def _get_local_sermon_data(self, sermon_id: str) -> Optional[Dict]:
        """Get local sermon data from database"""
        return self.repo.get_sermon(sermon_id)
    
    def _merge_sermon_details(self, sermon_id: str, local_data: Optional[Dict], remote_data: Optional[Dict]) -> Optional[SermonData]:
        """Merge local and remote sermon details"""
        if not local_data and not remote_data:
            return None
        
        # Use local data as base, supplement with remote
        base_data = local_data or {}
        remote_data = remote_data or {}
        
        # Parse date
        try:
            if base_data.get('recorded_date'):
                sermon_date = datetime.fromisoformat(base_data['recorded_date'])
            elif remote_data.get('preachDate'):
                sermon_date = datetime.fromisoformat(remote_data['preachDate'].replace('Z', '+00:00'))
            else:
                sermon_date = datetime.now()
        except (ValueError, TypeError):
            sermon_date = datetime.now()
        
        # Build audio files info
        audio_files = AudioFiles()
        
        # Local files
        sermon_dir = self.output_directory / sermon_id
        if sermon_dir.exists():
            for audio_file in sermon_dir.glob("*.mp3"):
                if "original" in audio_file.name.lower():
                    audio_files.original = str(audio_file)
                elif "enhanced" in audio_file.name.lower() or "processed" in audio_file.name.lower():
                    audio_files.processed = str(audio_file)
        
        # Remote URL
        if remote_data.get('audioUrl'):
            audio_files.original_url = remote_data['audioUrl']
        
        return SermonData(
            id=sermon_id,
            title=base_data.get('title') or remote_data.get('fullTitle', f'Sermon {sermon_id}'),
            date=sermon_date,
            speaker=base_data.get('speaker') or remote_data.get('speaker', {}).get('displayName', 'Unknown'),
            description=base_data.get('description') or remote_data.get('shortDescription', ''),
            hashtags=base_data.get('hashtags', []),
            local_available=bool(local_data),
            remote_available=bool(remote_data),
            audio_files=audio_files,
            transcript=base_data.get('transcript'),
            event_type=base_data.get('event_type') or remote_data.get('eventType'),
            bible_text=base_data.get('bible_text') or remote_data.get('bibleText'),
            status=base_data.get('status', 'unknown'),
            processing_info=base_data.get('processing_info', {}),
            qa_segments=base_data.get('qa_segments', [])
        )
    
    def _get_sermon_content(self, sermon_id: str) -> Dict[str, Any]:
        """Get sermon content (transcript, description, etc.)"""
        content = {
            'transcript_text': '',
            'description': '',
            'hashtags': [],
            'summary': ''
        }
        
        # Get from database
        sermon = self.repo.get_sermon(sermon_id)
        if sermon:
            content.update({
                'transcript_text': sermon.get('transcript', ''),
                'description': sermon.get('description', ''),
                'hashtags': sermon.get('hashtags', []),
                'summary': sermon.get('summary', '')
            })
        
        # Check for transcript file
        transcript_file = self.output_directory / sermon_id / "transcript.txt"
        if transcript_file.exists():
            try:
                content['transcript_text'] = transcript_file.read_text(encoding='utf-8')
            except Exception as e:
                logger.warning(f"Could not read transcript file for {sermon_id}: {e}")
        
        return content
    
    def _get_sermon_files(self, sermon_id: str) -> Dict[str, str]:
        """Get sermon file paths"""
        files = {}
        
        # Get from database
        file_records = self.repo.get_sermon_files(sermon_id)
        for record in file_records:
            files[record['file_type']] = record['file_path']
        
        # Scan directory
        sermon_dir = self.output_directory / sermon_id
        if sermon_dir.exists():
            for file_path in sermon_dir.iterdir():
                if file_path.is_file():
                    file_type = file_path.suffix.lower()
                    if file_type == '.mp3':
                        if 'original' in file_path.name.lower():
                            files['original_audio'] = str(file_path)
                        elif 'enhanced' in file_path.name.lower() or 'processed' in file_path.name.lower():
                            files['processed_audio'] = str(file_path)
                        else:
                            files['audio'] = str(file_path)
                    elif file_type == '.txt':
                        files['transcript'] = str(file_path)
                    elif file_type == '.json':
                        files['metadata'] = str(file_path)
        
        return files
    
    def _is_cache_valid(self) -> bool:
        """Check if sermon list cache is still valid"""
        if not self._sermon_list_cache or not self._cache_timestamp:
            return False
        
        age = (datetime.now() - self._cache_timestamp).total_seconds()
        return age < self.cache_ttl
    
    def _apply_filters(self, sermons: List[SermonData], filters: Optional[Dict[str, Any]]) -> List[SermonData]:
        """Apply filters to sermon list"""
        if not filters:
            return sermons
        
        filtered = sermons[:]
        
        # Filter by speaker
        if filters.get('speaker'):
            filtered = [s for s in filtered if filters['speaker'].lower() in s.speaker.lower()]
        
        # Filter by event type
        if filters.get('event_type'):
            filtered = [s for s in filtered if s.event_type and filters['event_type'].lower() in s.event_type.lower()]
        
        # Filter by date range
        if filters.get('start_date'):
            start_date = datetime.fromisoformat(filters['start_date'])
            filtered = [s for s in filtered if s.date >= start_date]
        
        if filters.get('end_date'):
            end_date = datetime.fromisoformat(filters['end_date'])
            filtered = [s for s in filtered if s.date <= end_date]
        
        # Filter by availability
        if filters.get('local_only'):
            filtered = [s for s in filtered if s.local_available]
        
        if filters.get('remote_only'):
            filtered = [s for s in filtered if s.remote_available]
        
        # Search in title/content
        if filters.get('search'):
            search_term = filters['search'].lower()
            filtered = [s for s in filtered if 
                       search_term in s.title.lower() or 
                       search_term in s.speaker.lower() or
                       search_term in s.description.lower()]
        
        return filtered

# Global instance
_sermon_manager = None

def get_sermon_manager(config: Optional[Dict[str, Any]] = None) -> SermonManager:
    """Get global sermon manager instance"""
    global _sermon_manager
    
    if _sermon_manager is None:
        if config is None:
            # Load default config
            try:
                with open('config.yaml', 'r') as f:
                    config = yaml.safe_load(f)
            except FileNotFoundError:
                config = {}
        
        _sermon_manager = SermonManager(config)
    
    return _sermon_manager