"""
SermonAudio Analytics Data Provider

Fetches and processes sermon analytics data from SermonAudio API.
Falls back to mock data when API is unavailable.
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SermonAudioAnalytics:
    """Provider for SermonAudio analytics data"""
    
    def __init__(self, api_key: str = None, broadcaster_id: str = None):
        self.api_key = api_key
        self.broadcaster_id = broadcaster_id
        self.mock_mode = not (api_key and broadcaster_id)
        
        if self.mock_mode:
            logger.info("SermonAudio analytics running in mock mode (no API credentials)")
        else:
            logger.info(f"SermonAudio analytics configured for broadcaster: {broadcaster_id}")
    
    def get_all_sermon_analytics(self, date_range=None, fetch_all=False) -> List[Dict[str, Any]]:
        """Get comprehensive sermon analytics data
        
        Args:
            date_range: Tuple of (start_date, end_date) as strings in YYYY-MM-DD format
            fetch_all: If True, fetch all available sermons (ignores pageSize limit)
        """
        if self.mock_mode:
            return self._generate_mock_data()
        else:
            try:
                return self._fetch_real_data(date_range=date_range, fetch_all=fetch_all)
            except Exception as e:
                logger.warning(f"Failed to fetch real data, falling back to mock: {e}")
                return self._generate_mock_data()
    
    def _parse_sermon_data(self, sermon):
        """Parse individual sermon data from API response"""
        try:
            # Handle speaker data
            speaker_data = sermon.get('speaker', {})
            if isinstance(speaker_data, dict):
                speaker_name = speaker_data.get('displayName', 'Unknown Speaker')
            else:
                speaker_name = str(speaker_data) if speaker_data else 'Unknown Speaker'
            
            # Handle broadcaster data
            broadcaster_data = sermon.get('broadcaster', {})
            if isinstance(broadcaster_data, dict):
                church_name = broadcaster_data.get('displayName', 'Unknown Church')
            else:
                church_name = str(broadcaster_data) if broadcaster_data else 'Unknown Church'
            
            # Try to get view data from available fields
            # SermonAudio API v2 doesn't provide play counts in detailedStats for regular access
            # We use lastAudioAccessTimestamp as an indicator of recent activity
            views = 0  # No direct view count available
            last_audio_access = sermon.get('lastAudioAccessTimestamp')
            last_video_access = sermon.get('lastVideoAccessTimestamp')
            
            # If we have recent access timestamps, we can note the sermon has been accessed
            # but we can't get actual play counts from the API
            has_recent_activity = bool(last_audio_access or last_video_access)
            
            return {
                'sermon_id': sermon.get('sermonID', ''),
                'title': sermon.get('fullTitle') or sermon.get('displayTitle', 'Untitled'),
                'speaker': speaker_name,
                'date': sermon.get('preachDate', ''),
                'series': (sermon.get('series', {}).get('title') if isinstance(sermon.get('series'), dict) else sermon.get('seriesTitle')) or sermon.get('subtitle', ''),
                'topic': sermon.get('bibleText', ''),
                'bible_text': sermon.get('bibleText', ''),
                'views': views,  # API limitation: view counts not available
                'downloads': sermon.get('downloadCount', 0),
                'video_downloads': sermon.get('videoDownloadCount', 0),
                'duration_minutes': (sermon.get('audioDurationSeconds', 0) // 60) if sermon.get('audioDurationSeconds') else 0,
                'file_size_mb': 0,  # Not available in API response
                'language': sermon.get('languageCode', 'en'),
                'sermon_url': f"https://www.sermonaudio.com/sermon/{sermon.get('sermonID', '')}",
                'created_date': sermon.get('preachDate', ''),
                'last_modified': sermon.get('preachDate', ''),
                'subtitle': sermon.get('subtitle', ''),
                'denomination': '',  # Not directly available
                'church_name': church_name,
                'church_city': '',  # Not available in lite broadcaster data
                'church_state': '',  # Not available in lite broadcaster data
                'is_video': sermon.get('hasVideo', False),
                'is_audio': sermon.get('hasAudio', False),
                'quality_rating': 0,  # Not available
                'keywords': '',  # Not available in this response
                'event_type': sermon.get('eventType', ''),
                'comment_count': sermon.get('commentCount', 0),
                'likes': 0,  # Not available
                'last_audio_access': last_audio_access,
                'last_video_access': last_video_access,
                'has_recent_activity': has_recent_activity
            }
        except Exception as e:
            print(f"Error parsing sermon data: {e}")
            return None
    
    def _fetch_real_data(self, date_range=None, fetch_all=False):
        """Fetch real sermon data from the SermonAudio API.
        
        Args:
            date_range: Tuple of (start_date, end_date) as strings in YYYY-MM-DD format
            fetch_all: If True, fetch all available sermons (ignores pageSize limit)
        """
        if not self.api_key or not self.broadcaster_id:
            raise ValueError("API key and broadcaster ID are required for real data")
        
        # Make API call to SermonAudio API v2
        url = "https://api.sermonaudio.com/v2/node/sermons"
        headers = {'X-Api-Key': self.api_key, 'Content-Type': 'application/json'}
        
        # Base parameters
        params = {
            'broadcasterID': self.broadcaster_id,
            'page': 1
        }
        
        # Add date range if specified
        if date_range and len(date_range) == 2:
            start_date, end_date = date_range
            if start_date:
                params['preachDateStart'] = start_date
            if end_date:
                params['preachDateEnd'] = end_date
        
        # Set page size based on fetch_all flag
        if fetch_all:
            params['pageSize'] = 100  # Use smaller page size for pagination
        else:
            params['pageSize'] = 100  # Default for analytics view
        
        all_sermons = []
        max_pages = 1 if not fetch_all else 50  # Limit to prevent runaway requests
        
        try:
            for page in range(1, max_pages + 1):
                params['page'] = page
                
                logger.info(f"Fetching page {page} with params: {params}")
                response = requests.get(url, params=params, headers=headers, timeout=60)
                response.raise_for_status()
                data = response.json()
                sermons = data.get('results', [])
                
                if not sermons:  # No more sermons to fetch
                    break
                
                # Parse sermon data
                for sermon in sermons:
                    parsed_sermon = self._parse_sermon_data(sermon)
                    if parsed_sermon:
                        all_sermons.append(parsed_sermon)
                
                # If we got fewer sermons than page size, we're done
                if len(sermons) < params['pageSize']:
                    break
                
                # For single page requests, stop after first page
                if not fetch_all:
                    break
            
            logger.info(f"Successfully fetched {len(all_sermons)} sermons")
            return all_sermons
            
        except Exception as e:
            logger.error(f"Failed to fetch real sermon data: {e}")
            raise
    
    def _generate_mock_data(self) -> List[Dict[str, Any]]:
        """Fallback: return empty list when API is unavailable."""
        return []
    
    def get_speaker_stats(self) -> List[Dict[str, Any]]:
        """Get aggregated statistics by speaker"""
        all_sermons = self.get_all_sermon_analytics()
        speaker_stats = {}
        
        for sermon in all_sermons:
            speaker = sermon["speaker"]
            if speaker not in speaker_stats:
                speaker_stats[speaker] = {
                    "speaker": speaker,
                    "sermon_count": 0,
                    "total_views": 0,
                    "total_listens": 0,
                    "total_downloads": 0,
                    "total_engagement": 0.0,
                    "avg_completion": 0.0
                }
            
            stats = speaker_stats[speaker]
            stats["sermon_count"] += 1
            stats["total_views"] += sermon["views"]
            stats["total_listens"] += sermon["listens"]
            stats["total_downloads"] += sermon["downloads"]
            stats["total_engagement"] += sermon["engagement_score"]
            stats["avg_completion"] += sermon["watch_time_avg"]
        
        # Calculate averages
        for speaker, stats in speaker_stats.items():
            count = stats["sermon_count"]
            stats["avg_views"] = stats["total_views"] / count
            stats["avg_listens"] = stats["total_listens"] / count
            stats["avg_downloads"] = stats["total_downloads"] / count
            stats["avg_engagement"] = stats["total_engagement"] / count
            stats["avg_completion"] = stats["avg_completion"] / count
        
        # Sort by total views
        return sorted(speaker_stats.values(), key=lambda x: x["total_views"], reverse=True)
    
    def get_series_stats(self) -> List[Dict[str, Any]]:
        """Get aggregated statistics by series"""
        all_sermons = self.get_all_sermon_analytics()
        series_stats = {}
        
        for sermon in all_sermons:
            series = sermon["series"]
            if series not in series_stats:
                series_stats[series] = {
                    "series": series,
                    "sermon_count": 0,
                    "total_views": 0,
                    "total_listens": 0,
                    "avg_engagement": 0.0
                }
            
            stats = series_stats[series]
            stats["sermon_count"] += 1
            stats["total_views"] += sermon["views"]
            stats["total_listens"] += sermon["listens"]
            stats["avg_engagement"] += sermon["engagement_score"]
        
        # Calculate averages
        for series, stats in series_stats.items():
            count = stats["sermon_count"]
            stats["avg_views"] = stats["total_views"] / count
            stats["avg_listens"] = stats["total_listens"] / count
            stats["avg_engagement"] = stats["avg_engagement"] / count
        
        return sorted(series_stats.values(), key=lambda x: x["avg_engagement"], reverse=True)
    
    def get_trending_topics(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get trending topics from recent sermons"""
        all_sermons = self.get_all_sermon_analytics()
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_sermons = [
            s for s in all_sermons 
            if datetime.strptime(s["date_preached"], "%Y-%m-%d") > cutoff_date
        ]
        
        topic_stats = {}
        for sermon in recent_sermons:
            for keyword in sermon["keywords"]:
                if keyword not in topic_stats:
                    topic_stats[keyword] = {
                        "topic": keyword,
                        "sermon_count": 0,
                        "total_views": 0,
                        "total_engagement": 0.0
                    }
                
                stats = topic_stats[keyword]
                stats["sermon_count"] += 1
                stats["total_views"] += sermon["views"]
                stats["total_engagement"] += sermon["engagement_score"]
        
        # Calculate averages and sort by engagement
        trending = []
        for topic, stats in topic_stats.items():
            count = stats["sermon_count"]
            if count > 0:
                trending.append({
                    "topic": topic.title(),
                    "sermon_count": count,
                    "total_views": stats["total_views"],
                    "avg_views": stats["total_views"] / count,
                    "avg_engagement": stats["total_engagement"] / count
                })
        
        return sorted(trending, key=lambda x: x["avg_engagement"], reverse=True)[:10]

