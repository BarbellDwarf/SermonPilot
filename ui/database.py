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