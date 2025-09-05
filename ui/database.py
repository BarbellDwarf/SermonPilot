"""
Database utilities for SermonAudio Processor UI

Provides SQLite-based persistent storage for metadata caching,
processing status, and progress tracking to improve UI performance
and enable containerization.
"""

import sqlite3
import json
import logging
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class SermonDatabase:
    """SQLite database for sermon metadata and processing status"""
    
    def __init__(self, db_path: str = "sermon_processor.db"):
        """Initialize database connection"""
        self.db_path = Path(db_path)
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            # Metadata cache table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata_cache (
                    key TEXT PRIMARY KEY,
                    data TEXT,
                    last_updated TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            
            # Processing status table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processing_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sermon_id TEXT,
                    operation TEXT,
                    status TEXT,
                    progress REAL,
                    message TEXT,
                    started_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            # Validation results table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS validation_results (
                    sermon_id TEXT PRIMARY KEY,
                    is_valid BOOLEAN,
                    score REAL,
                    reason TEXT,
                    criteria_met TEXT,
                    criteria_failed TEXT,
                    validated_at TIMESTAMP
                )
            """)
            
            # Enhanced sermon records table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sermons (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    speaker TEXT,
                    recorded_date TEXT,
                    event_type TEXT,
                    bible_text TEXT,
                    duration REAL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # File paths table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sermon_files (
                    sermon_id TEXT,
                    file_type TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (sermon_id, file_type),
                    FOREIGN KEY (sermon_id) REFERENCES sermons(id)
                )
            """)
            
            # Processing information table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processing_info (
                    sermon_id TEXT PRIMARY KEY,
                    enhancement_method TEXT,
                    noise_reduction_applied BOOLEAN,
                    normalization_applied BOOLEAN,
                    qa_normalization_applied BOOLEAN,
                    qa_segments_count INTEGER DEFAULT 0,
                    processing_duration REAL,
                    quality_score REAL,
                    processing_logs TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sermon_id) REFERENCES sermons(id)
                )
            """)
            
            # Q&A segments table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS qa_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sermon_id TEXT,
                    start_time REAL,
                    end_time REAL,
                    segment_type TEXT,
                    confidence REAL,
                    audio_level_db REAL,
                    gain_applied REAL,
                    speaker_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sermon_id) REFERENCES sermons(id)
                )
            """)
            
            # Content table for full-text search
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sermon_content (
                    sermon_id TEXT PRIMARY KEY,
                    transcript_text TEXT,
                    description TEXT,
                    hashtags TEXT,
                    key_topics TEXT,
                    summary TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sermon_id) REFERENCES sermons(id)
                )
            """)
            
            # Create full-text search virtual table
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS sermon_search USING fts5(
                    sermon_id,
                    title,
                    speaker,
                    transcript_text,
                    description,
                    hashtags,
                    content='sermon_content'
                )
            """)
            
            # Upload information table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS upload_info (
                    sermon_id TEXT PRIMARY KEY,
                    sermonaudio_id TEXT,
                    upload_date TIMESTAMP,
                    upload_status TEXT,
                    upload_message TEXT,
                    FOREIGN KEY (sermon_id) REFERENCES sermons(id)
                )
            """)
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic cleanup"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def cache_metadata(self, key: str, data: List[str], expires_hours: int = 24):
        """Cache metadata with expiration"""
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_hours)
        
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO metadata_cache (key, data, last_updated, expires_at)
                VALUES (?, ?, ?, ?)
            """, (key, json.dumps(data), datetime.datetime.now(), expires_at))
            conn.commit()
    
    def get_cached_metadata(self, key: str) -> Optional[List[str]]:
        """Get cached metadata if not expired"""
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT data FROM metadata_cache 
                WHERE key = ? AND expires_at > ?
            """, (key, datetime.datetime.now())).fetchone()
            
            if row:
                return json.loads(row['data'])
            return None
    
    def update_processing_status(self, sermon_id: str, operation: str, 
                               status: str, progress: float = 0.0, 
                               message: str = ""):
        """Update processing status for a sermon"""
        now = datetime.datetime.now()
        
        with self.get_connection() as conn:
            # Check if record exists
            existing = conn.execute("""
                SELECT id FROM processing_status 
                WHERE sermon_id = ? AND operation = ?
                ORDER BY started_at DESC LIMIT 1
            """, (sermon_id, operation)).fetchone()
            
            if existing:
                # Update existing record
                conn.execute("""
                    UPDATE processing_status 
                    SET status = ?, progress = ?, message = ?, updated_at = ?,
                        completed_at = CASE WHEN ? IN ('completed', 'failed') THEN ? ELSE completed_at END
                    WHERE id = ?
                """, (status, progress, message, now, status, now, existing['id']))
            else:
                # Create new record
                conn.execute("""
                    INSERT INTO processing_status 
                    (sermon_id, operation, status, progress, message, started_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (sermon_id, operation, status, progress, message, now, now))
            
            conn.commit()
    
    def get_processing_status(self, sermon_id: str = None, operation: str = None) -> List[Dict]:
        """Get processing status records"""
        with self.get_connection() as conn:
            query = "SELECT * FROM processing_status"
            params = []
            
            conditions = []
            if sermon_id:
                conditions.append("sermon_id = ?")
                params.append(sermon_id)
            if operation:
                conditions.append("operation = ?")
                params.append(operation)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY started_at DESC"
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def save_validation_result(self, sermon_id: str, is_valid: bool, score: float,
                             reason: str, criteria_met: List[str], 
                             criteria_failed: List[str]):
        """Save validation result"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO validation_results
                (sermon_id, is_valid, score, reason, criteria_met, criteria_failed, validated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (sermon_id, is_valid, score, reason, 
                  json.dumps(criteria_met), json.dumps(criteria_failed),
                  datetime.datetime.now()))
            conn.commit()
    
    def get_validation_results(self, sermon_ids: List[str] = None) -> List[Dict]:
        """Get validation results"""
        with self.get_connection() as conn:
            if sermon_ids:
                placeholders = ",".join(["?" for _ in sermon_ids])
                query = f"SELECT * FROM validation_results WHERE sermon_id IN ({placeholders})"
                rows = conn.execute(query, sermon_ids).fetchall()
            else:
                rows = conn.execute("SELECT * FROM validation_results ORDER BY validated_at DESC").fetchall()
            
            results = []
            for row in rows:
                result = dict(row)
                result['criteria_met'] = json.loads(result['criteria_met'])
                result['criteria_failed'] = json.loads(result['criteria_failed'])
                results.append(result)
            
            return results
    
    def cleanup_old_records(self, days: int = 30):
        """Clean up old processing status and expired cache entries"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        
        with self.get_connection() as conn:
            # Clean old processing status
            conn.execute("DELETE FROM processing_status WHERE started_at < ?", (cutoff,))
            
            # Clean expired metadata cache
            conn.execute("DELETE FROM metadata_cache WHERE expires_at < ?", (datetime.datetime.now(),))
            
            conn.commit()
            logger.info("Cleaned up old database records")


# Global database instance
_db = None

def get_db() -> SermonDatabase:
    """Get global database instance"""
    global _db
    if _db is None:
        # Store database in data directory if it exists, otherwise current directory
        data_dir = Path("data")
        if data_dir.exists():
            db_path = data_dir / "sermon_processor.db"
        else:
            db_path = Path("sermon_processor.db")
        
        _db = SermonDatabase(str(db_path))
    return _db


class SermonRepository:
    """Repository for managing sermon records with Q&A information"""
    
    def __init__(self, db: SermonDatabase = None):
        """Initialize repository with database connection"""
        self.db = db or get_db()
    
    def save_sermon(self, sermon_data: Dict[str, Any]) -> bool:
        """
        Save a complete sermon record with all associated data.
        
        Args:
            sermon_data: Dictionary containing sermon information
            
        Returns:
            Success status
        """
        try:
            with self.db.get_connection() as conn:
                # Save main sermon record
                conn.execute("""
                    INSERT OR REPLACE INTO sermons 
                    (id, title, speaker, recorded_date, event_type, bible_text, duration, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sermon_data.get('id'),
                    sermon_data.get('title'),
                    sermon_data.get('speaker'),
                    sermon_data.get('recorded_date'),
                    sermon_data.get('event_type'),
                    sermon_data.get('bible_text'),
                    sermon_data.get('duration'),
                    sermon_data.get('status', 'processed'),
                    datetime.datetime.now()
                ))
                
                # Save file paths
                file_paths = sermon_data.get('file_paths', {})
                for file_type, file_path in file_paths.items():
                    if file_path:
                        file_size = 0
                        if Path(file_path).exists():
                            file_size = Path(file_path).stat().st_size
                        
                        conn.execute("""
                            INSERT OR REPLACE INTO sermon_files 
                            (sermon_id, file_type, file_path, file_size)
                            VALUES (?, ?, ?, ?)
                        """, (sermon_data.get('id'), file_type, file_path, file_size))
                
                # Save processing information
                processing_info = sermon_data.get('processing_info', {})
                if processing_info:
                    conn.execute("""
                        INSERT OR REPLACE INTO processing_info 
                        (sermon_id, enhancement_method, noise_reduction_applied, 
                         normalization_applied, qa_normalization_applied, qa_segments_count,
                         processing_duration, quality_score, processing_logs)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sermon_data.get('id'),
                        processing_info.get('enhancement_method'),
                        processing_info.get('noise_reduction_applied'),
                        processing_info.get('normalization_applied'),
                        processing_info.get('qa_normalization_applied'),
                        processing_info.get('qa_segments_count', 0),
                        processing_info.get('processing_duration'),
                        processing_info.get('quality_score'),
                        json.dumps(processing_info.get('processing_logs', {}))
                    ))
                
                # Save Q&A segments
                qa_segments = processing_info.get('qa_segments', [])
                if qa_segments:
                    # Clear existing segments for this sermon
                    conn.execute("DELETE FROM qa_segments WHERE sermon_id = ?", (sermon_data.get('id'),))
                    
                    # Insert new segments
                    for segment in qa_segments:
                        conn.execute("""
                            INSERT INTO qa_segments 
                            (sermon_id, start_time, end_time, segment_type, confidence, 
                             audio_level_db, gain_applied, speaker_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sermon_data.get('id'),
                            segment.get('start_time'),
                            segment.get('end_time'),
                            segment.get('segment_type'),
                            segment.get('confidence'),
                            segment.get('audio_level_db'),
                            segment.get('gain_applied'),
                            segment.get('speaker_id')
                        ))
                
                # Save content for full-text search
                content = sermon_data.get('content', {})
                if content:
                    conn.execute("""
                        INSERT OR REPLACE INTO sermon_content 
                        (sermon_id, transcript_text, description, hashtags, key_topics, summary)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        sermon_data.get('id'),
                        content.get('transcript_text'),
                        content.get('description'),
                        content.get('hashtags'),
                        json.dumps(content.get('key_topics', [])),
                        content.get('summary')
                    ))
                    
                    # Update full-text search index
                    conn.execute("""
                        INSERT OR REPLACE INTO sermon_search 
                        (sermon_id, title, speaker, transcript_text, description, hashtags)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        sermon_data.get('id'),
                        sermon_data.get('title'),
                        sermon_data.get('speaker'),
                        content.get('transcript_text'),
                        content.get('description'),
                        content.get('hashtags')
                    ))
                
                # Save upload information
                upload_info = sermon_data.get('upload_info', {})
                if upload_info:
                    conn.execute("""
                        INSERT OR REPLACE INTO upload_info 
                        (sermon_id, sermonaudio_id, upload_date, upload_status, upload_message)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        sermon_data.get('id'),
                        upload_info.get('sermonaudio_id'),
                        upload_info.get('upload_date'),
                        upload_info.get('upload_status'),
                        upload_info.get('upload_message')
                    ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to save sermon {sermon_data.get('id')}: {e}")
            return False
    
    def get_sermon(self, sermon_id: str) -> Optional[Dict[str, Any]]:
        """Get a complete sermon record by ID"""
        with self.db.get_connection() as conn:
            # Get main sermon data
            sermon_row = conn.execute("""
                SELECT * FROM sermons WHERE id = ?
            """, (sermon_id,)).fetchone()
            
            if not sermon_row:
                return None
            
            sermon = dict(sermon_row)
            
            # Get file paths
            file_rows = conn.execute("""
                SELECT file_type, file_path FROM sermon_files WHERE sermon_id = ?
            """, (sermon_id,)).fetchall()
            sermon['file_paths'] = {row['file_type']: row['file_path'] for row in file_rows}
            
            # Get processing info
            proc_row = conn.execute("""
                SELECT * FROM processing_info WHERE sermon_id = ?
            """, (sermon_id,)).fetchone()
            if proc_row:
                processing_info = dict(proc_row)
                processing_info['processing_logs'] = json.loads(processing_info.get('processing_logs') or '{}')
                sermon['processing_info'] = processing_info
            
            # Get Q&A segments
            segment_rows = conn.execute("""
                SELECT * FROM qa_segments WHERE sermon_id = ? ORDER BY start_time
            """, (sermon_id,)).fetchall()
            qa_segments = [dict(row) for row in segment_rows]
            if processing_info:
                sermon['processing_info']['qa_segments'] = qa_segments
            
            # Get content
            content_row = conn.execute("""
                SELECT * FROM sermon_content WHERE sermon_id = ?
            """, (sermon_id,)).fetchone()
            if content_row:
                content = dict(content_row)
                content['key_topics'] = json.loads(content.get('key_topics') or '[]')
                sermon['content'] = content
            
            # Get upload info
            upload_row = conn.execute("""
                SELECT * FROM upload_info WHERE sermon_id = ?
            """, (sermon_id,)).fetchone()
            if upload_row:
                sermon['upload_info'] = dict(upload_row)
            
            return sermon
    
    def get_all_sermons(self, filters: Optional[Dict[str, Any]] = None, 
                       limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all sermons with optional filtering"""
        with self.db.get_connection() as conn:
            query = """
                SELECT s.*, 
                       pi.qa_segments_count,
                       pi.qa_normalization_applied,
                       pi.enhancement_method,
                       ui.upload_status
                FROM sermons s
                LEFT JOIN processing_info pi ON s.id = pi.sermon_id
                LEFT JOIN upload_info ui ON s.id = ui.sermon_id
                WHERE 1=1
            """
            params = []
            
            # Apply filters
            if filters:
                if filters.get('speaker'):
                    query += " AND s.speaker LIKE ?"
                    params.append(f"%{filters['speaker']}%")
                
                if filters.get('event_type'):
                    query += " AND s.event_type = ?"
                    params.append(filters['event_type'])
                
                if filters.get('date_from'):
                    query += " AND s.recorded_date >= ?"
                    params.append(filters['date_from'])
                
                if filters.get('date_to'):
                    query += " AND s.recorded_date <= ?"
                    params.append(filters['date_to'])
                
                if filters.get('has_qa_segments'):
                    query += " AND pi.qa_segments_count > 0"
                
                if filters.get('status'):
                    query += " AND s.status = ?"
                    params.append(filters['status'])
            
            query += " ORDER BY s.recorded_date DESC, s.created_at DESC"
            
            if limit:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def search_sermons(self, query_text: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Full-text search across sermon content"""
        with self.db.get_connection() as conn:
            # Try FTS search first, fall back to LIKE search if FTS fails
            try:
                search_results = conn.execute("""
                    SELECT sermon_id, 
                           title,
                           speaker,
                           snippet(sermon_search, 2, '<mark>', '</mark>', '...', 32) as snippet,
                           rank
                    FROM sermon_search 
                    WHERE sermon_search MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query_text, limit)).fetchall()
            except Exception:
                # Fallback to simple LIKE search if FTS fails
                search_results = conn.execute("""
                    SELECT sc.sermon_id,
                           s.title,
                           s.speaker,
                           '' as snippet,
                           1 as rank
                    FROM sermon_content sc
                    JOIN sermons s ON sc.sermon_id = s.id
                    WHERE sc.transcript_text LIKE ? 
                       OR sc.description LIKE ?
                       OR s.title LIKE ?
                       OR s.speaker LIKE ?
                    LIMIT ?
                """, (f'%{query_text}%', f'%{query_text}%', f'%{query_text}%', f'%{query_text}%', limit)).fetchall()
            
            # Get full sermon data for results
            sermon_ids = [row['sermon_id'] for row in search_results]
            if not sermon_ids:
                return []
            
            placeholders = ",".join(["?" for _ in sermon_ids])
            sermons = conn.execute(f"""
                SELECT s.*, pi.qa_segments_count 
                FROM sermons s
                LEFT JOIN processing_info pi ON s.id = pi.sermon_id
                WHERE s.id IN ({placeholders})
            """, sermon_ids).fetchall()
            
            # Combine search results with sermon data
            sermon_dict = {s['id']: dict(s) for s in sermons}
            results = []
            
            for search_row in search_results:
                sermon_id = search_row['sermon_id']
                if sermon_id in sermon_dict:
                    sermon = sermon_dict[sermon_id]
                    sermon['search_snippet'] = search_row['snippet']
                    sermon['search_rank'] = search_row['rank']
                    results.append(sermon)
            
            return results
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get overall processing statistics"""
        with self.db.get_connection() as conn:
            # Basic counts
            total_sermons = conn.execute("SELECT COUNT(*) FROM sermons").fetchone()[0]
            
            qa_sermons = conn.execute("""
                SELECT COUNT(*) FROM processing_info WHERE qa_segments_count > 0
            """).fetchone()[0]
            
            total_qa_segments = conn.execute("SELECT COUNT(*) FROM qa_segments").fetchone()[0]
            
            # Average processing metrics
            avg_stats = conn.execute("""
                SELECT 
                    AVG(qa_segments_count) as avg_qa_segments,
                    AVG(processing_duration) as avg_processing_time,
                    AVG(quality_score) as avg_quality_score
                FROM processing_info
                WHERE processing_duration IS NOT NULL
            """).fetchone()
            
            # Total duration
            total_duration = conn.execute("""
                SELECT SUM(duration) FROM sermons WHERE duration IS NOT NULL
            """).fetchone()[0] or 0
            
            return {
                'total_sermons': total_sermons,
                'qa_sermons': qa_sermons,
                'total_qa_segments': total_qa_segments,
                'total_duration_hours': total_duration / 3600.0,
                'avg_qa_segments_per_sermon': avg_stats['avg_qa_segments'] or 0,
                'avg_processing_time': avg_stats['avg_processing_time'] or 0,
                'avg_quality_score': avg_stats['avg_quality_score'] or 0
            }