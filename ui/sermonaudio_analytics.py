"""
SermonAudio Analytics Data Provider

Fetches and processes sermon analytics data from SermonAudio API.
Falls back to mock data when API is unavailable.
"""

import logging
import random
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
    
    def get_all_sermon_analytics(self) -> List[Dict[str, Any]]:
        """Get comprehensive sermon analytics data"""
        if self.mock_mode:
            return self._generate_mock_data()
        else:
            try:
                return self._fetch_real_data()
            except Exception as e:
                logger.warning(f"Failed to fetch real data, falling back to mock: {e}")
                return self._generate_mock_data()
    
    def _fetch_real_data(self) -> List[Dict[str, Any]]:
        """Fetch real data from SermonAudio API"""
        # TODO: Implement real SermonAudio API integration
        # This would require the sermonaudio package and proper API calls
        logger.info("Real SermonAudio API integration not yet implemented")
        return self._generate_mock_data()
    
    def _generate_mock_data(self) -> List[Dict[str, Any]]:
        """Generate realistic mock data for development and testing"""
        speakers = [
            "Pastor John Smith", "Dr. Sarah Johnson", "Rev. Michael Brown",
            "Pastor David Wilson", "Dr. Emily Davis", "Rev. Robert Miller",
            "Pastor Lisa Anderson", "Dr. James Taylor", "Rev. Mary Thomas"
        ]
        
        event_types = [
            "Sunday Morning Service", "Sunday Evening Service", 
            "Wednesday Bible Study", "Special Event", "Conference",
            "Funeral Service", "Wedding Service", "Youth Service"
        ]
        
        series_names = [
            "Foundations of Faith", "Walking with Jesus", "Psalms Study",
            "Gospel of John", "Kingdom Living", "Spiritual Disciplines",
            "Christmas Series", "Easter Messages", "Summer Revival"
        ]
        
        topics = [
            ["prayer", "faith", "worship"], ["love", "grace", "salvation"],
            ["hope", "forgiveness", "redemption"], ["wisdom", "guidance", "trust"],
            ["service", "discipleship", "evangelism"], ["joy", "peace", "contentment"],
            ["courage", "strength", "perseverance"], ["family", "relationships", "community"],
            ["stewardship", "generosity", "blessing"], ["healing", "restoration", "renewal"]
        ]
        
        sermons = []
        base_date = datetime.now() - timedelta(days=365)
        
        for i in range(100):  # Generate 100 mock sermons
            # Create realistic dates
            preached_date = base_date + timedelta(days=random.randint(0, 365))
            uploaded_date = preached_date + timedelta(days=random.randint(0, 7))
            
            # Select random attributes
            speaker = random.choice(speakers)
            event_type = random.choice(event_types)
            series = random.choice(series_names)
            topic_set = random.choice(topics)
            
            # Generate realistic metrics
            base_views = random.randint(50, 2000)
            listen_rate = random.uniform(0.6, 0.9)  # 60-90% of views become listens
            download_rate = random.uniform(0.1, 0.3)  # 10-30% of listens become downloads
            
            views = base_views
            listens = int(views * listen_rate)
            downloads = int(listens * download_rate)
            
            # Engagement score based on completion rate and interaction
            completion_rate = random.uniform(0.4, 0.95)
            engagement_factors = [
                completion_rate,
                min(downloads / max(listens, 1), 1.0),  # Download rate
                random.uniform(0.7, 1.0)  # Base engagement
            ]
            engagement_score = sum(engagement_factors) / len(engagement_factors) * 10
            
            # Duration in minutes
            duration = random.randint(25, 75)
            
            sermon = {
                "sermon_id": f"mock_{i+1:03d}",
                "title": self._generate_sermon_title(topic_set),
                "speaker": speaker,
                "series": series,
                "event_type": event_type,
                "date_preached": preached_date.strftime("%Y-%m-%d"),
                "date_uploaded": uploaded_date.strftime("%Y-%m-%d"),
                "views": views,
                "listens": listens,
                "downloads": downloads,
                "duration_minutes": duration,
                "watch_time_total": int(listens * duration * completion_rate),
                "watch_time_avg": completion_rate,
                "engagement_score": round(engagement_score, 2),
                "keywords": topic_set,
                "bible_text": self._generate_bible_reference(),
                "description": f"A sermon about {', '.join(topic_set)} delivered during {event_type.lower()}.",
                "metadata": {
                    "quality_score": random.uniform(7.0, 9.5),
                    "processing_date": uploaded_date.strftime("%Y-%m-%d"),
                    "audio_enhanced": random.choice([True, False]),
                    "transcript_available": random.choice([True, False])
                }
            }
            
            sermons.append(sermon)
        
        # Sort by upload date (most recent first)
        sermons.sort(key=lambda x: x["date_uploaded"], reverse=True)
        
        logger.info(f"Generated {len(sermons)} mock sermon analytics records")
        return sermons
    
    def _generate_sermon_title(self, topics: List[str]) -> str:
        """Generate realistic sermon titles based on topics"""
        title_patterns = [
            "The Power of {topic}",
            "Walking in {topic}",
            "Understanding {topic}",
            "Living with {topic}",
            "Finding {topic}",
            "Growing in {topic}",
            "The Gift of {topic}",
            "Embracing {topic}",
            "Discovering {topic}",
            "The Heart of {topic}"
        ]
        
        pattern = random.choice(title_patterns)
        topic = random.choice(topics).title()
        return pattern.format(topic=topic)
    
    def _generate_bible_reference(self) -> str:
        """Generate realistic Bible references"""
        books = [
            "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
            "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians",
            "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus",
            "Philemon", "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John",
            "3 John", "Jude", "Revelation", "Genesis", "Exodus", "Psalms", "Proverbs",
            "Isaiah", "Jeremiah", "Ezekiel", "Daniel"
        ]
        
        book = random.choice(books)
        chapter = random.randint(1, 30)
        
        if random.choice([True, False]):
            # Single verse
            verse = random.randint(1, 35)
            return f"{book} {chapter}:{verse}"
        else:
            # Verse range
            start_verse = random.randint(1, 25)
            end_verse = start_verse + random.randint(1, 10)
            return f"{book} {chapter}:{start_verse}-{end_verse}"
    
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

