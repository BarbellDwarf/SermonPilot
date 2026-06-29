"""
Database utilities for SermonAudio Processor UI

Provides SQLite-based persistent storage for metadata caching,
processing status, and progress tracking to improve UI performance
and enable containerization.
"""

import datetime
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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

            # Add missing columns if they don't exist (migration)
            try:
                conn.execute("ALTER TABLE sermons ADD COLUMN series_title TEXT")
            except Exception:
                pass  # Column already exists
            
            try:
                conn.execute("ALTER TABLE sermons ADD COLUMN scripture_reference TEXT")
            except Exception:
                pass  # Column already exists
            
            try:
                conn.execute("ALTER TABLE sermons ADD COLUMN description TEXT")
            except Exception:
                pass  # Column already exists
            
            try:
                conn.execute("ALTER TABLE sermons ADD COLUMN church_name TEXT")
            except Exception:
                pass  # Column already exists

            try:
                conn.execute("ALTER TABLE sermons ADD COLUMN subtitle TEXT")
            except Exception:
                pass  # Column already exists

            try:
                conn.execute("ALTER TABLE sermons ADD COLUMN is_favorite INTEGER DEFAULT 0")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE sermons ADD COLUMN notes TEXT DEFAULT ''")
            except Exception:
                pass

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

            # Manual review queue table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS manual_review (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sermon_id TEXT NOT NULL,
                    reason TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP,
                    notes TEXT
                )
            """)

            # LLM API usage tracking table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sermon_id TEXT,
                    operation TEXT,
                    provider TEXT,
                    model TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    request_duration_ms INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'success',
                    error_message TEXT,
                    request_data TEXT,
                    response_data TEXT,
                    FOREIGN KEY (sermon_id) REFERENCES sermons(id)
                )
            """)

            # Create index for efficient querying
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_usage_timestamp
                ON llm_api_usage(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_usage_provider_model
                ON llm_api_usage(provider, model)
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

    def cache_metadata(self, key: str, data: list[str], expires_hours: int = 24):
        """Cache metadata with expiration"""
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_hours)

        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO metadata_cache (key, data, last_updated, expires_at)
                VALUES (?, ?, ?, ?)
            """, (key, json.dumps(data), datetime.datetime.now(), expires_at))
            conn.commit()

    def get_cached_metadata(self, key: str) -> list[str] | None:
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

    def get_processing_status(self, sermon_id: str = None, operation: str = None) -> list[dict]:
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
                             reason: str, criteria_met: list[str],
                             criteria_failed: list[str]):
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

    def get_validation_results(self, sermon_ids: list[str] = None) -> list[dict]:
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
                result['criteria_met'] = json.loads(result['criteria_met']) if result.get('criteria_met') else []
                result['criteria_failed'] = json.loads(result['criteria_failed']) if result.get('criteria_failed') else []
                results.append(result)

            return results

    def add_manual_review(self, sermon_id: str, reason: str = ""):
        """Add a sermon to the manual review queue"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO manual_review (sermon_id, reason, status, created_at)
                VALUES (?, ?, 'pending', ?)
            """, (sermon_id, reason, datetime.datetime.now()))
            conn.commit()

    def get_manual_reviews(self, status: str = None) -> list[dict]:
        """Get manual review queue entries"""
        with self.get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM manual_review WHERE status = ? ORDER BY created_at DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM manual_review ORDER BY created_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]

    def update_manual_review_status(self, review_id: int, status: str, notes: str = ""):
        """Update a manual review entry status"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE manual_review
                SET status = ?, reviewed_at = ?, notes = ?
                WHERE id = ?
            """, (status, datetime.datetime.now(), notes, review_id))
            conn.commit()

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

    def log_llm_api_usage(self, sermon_id: str = None, operation: str = "",
                          provider: str = "", model: str = "",
                          input_tokens: int = 0, output_tokens: int = 0,
                          cost_usd: float = 0.0, request_duration_ms: int = 0,
                          status: str = "success", error_message: str = None,
                          request_data: str = None, response_data: str = None):
        """Log LLM API usage for cost tracking and analytics"""
        total_tokens = input_tokens + output_tokens
        
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO llm_api_usage (
                    sermon_id, operation, provider, model,
                    input_tokens, output_tokens, total_tokens, cost_usd,
                    request_duration_ms, status, error_message,
                    request_data, response_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sermon_id, operation, provider, model,
                input_tokens, output_tokens, total_tokens, cost_usd,
                request_duration_ms, status, error_message,
                request_data, response_data
            ))
            conn.commit()

    def get_llm_usage_summary(self, days: int = 30):
        """Get LLM usage summary for the specified number of days"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        
        with self.get_connection() as conn:
            # Total usage stats
            summary = conn.execute("""
                SELECT 
                    COUNT(*) as total_calls,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(total_tokens) as total_tokens,
                    SUM(cost_usd) as total_cost,
                    AVG(cost_usd) as avg_cost_per_call,
                    AVG(request_duration_ms) as avg_duration_ms,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_calls,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as failed_calls
                FROM llm_api_usage 
                WHERE timestamp >= ?
            """, (cutoff,)).fetchone()
            
            # Provider breakdown
            providers = conn.execute("""
                SELECT 
                    provider,
                    COUNT(*) as calls,
                    SUM(total_tokens) as tokens,
                    SUM(cost_usd) as cost
                FROM llm_api_usage 
                WHERE timestamp >= ?
                GROUP BY provider
                ORDER BY cost DESC
            """, (cutoff,)).fetchall()
            
            # Model breakdown
            models = conn.execute("""
                SELECT 
                    provider,
                    model,
                    COUNT(*) as calls,
                    SUM(total_tokens) as tokens,
                    SUM(cost_usd) as cost,
                    AVG(request_duration_ms) as avg_duration_ms
                FROM llm_api_usage 
                WHERE timestamp >= ?
                GROUP BY provider, model
                ORDER BY cost DESC
            """, (cutoff,)).fetchall()
            
            # Daily cost trends
            daily_costs = conn.execute("""
                SELECT 
                    DATE(timestamp) as date,
                    COUNT(*) as calls,
                    SUM(total_tokens) as tokens,
                    SUM(cost_usd) as daily_cost
                FROM llm_api_usage 
                WHERE timestamp >= ?
                GROUP BY DATE(timestamp)
                ORDER BY date ASC
            """, (cutoff,)).fetchall()
            
            return {
                'summary': dict(summary) if summary else {},
                'providers': [dict(row) for row in providers],
                'models': [dict(row) for row in models],
                'daily_costs': [dict(row) for row in daily_costs]
            }

    def get_llm_usage_by_operation(self, days: int = 30):
        """Get LLM usage breakdown by operation type"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        
        with self.get_connection() as conn:
            operations = conn.execute("""
                SELECT 
                    operation,
                    COUNT(*) as calls,
                    SUM(total_tokens) as tokens,
                    SUM(cost_usd) as cost,
                    AVG(request_duration_ms) as avg_duration_ms
                FROM llm_api_usage 
                WHERE timestamp >= ?
                GROUP BY operation
                ORDER BY cost DESC
            """, (cutoff,)).fetchall()
            
            return [dict(row) for row in operations]


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

    def save_sermon(self, sermon_data: dict[str, Any]) -> bool:
        """
        Save a complete sermon record with all associated data.
        
        Args:
            sermon_data: Dictionary containing sermon information
            
        Returns:
            Success status
        """
        try:
            with self.db.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO sermons 
                    (id, title, subtitle, speaker, recorded_date, event_type, bible_text, series_title, scripture_reference, description, duration, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sermon_data.get('id'),
                    sermon_data.get('title'),
                    sermon_data.get('subtitle'),
                    sermon_data.get('speaker'),
                    sermon_data.get('recorded_date'),
                    sermon_data.get('event_type'),
                    sermon_data.get('bible_text'),
                    sermon_data.get('series_title'),
                    sermon_data.get('scripture_reference'),
                    sermon_data.get('description'),
                    sermon_data.get('duration'),
                    sermon_data.get('status', 'processed'),
                    datetime.datetime.now()
                ))

                # Save file paths
                file_paths = sermon_data.get('file_paths', {})
                if isinstance(file_paths, dict):
                    for file_type, file_path in file_paths.items():
                        if not file_path:
                            continue
                        if not isinstance(file_path, (str, Path)):
                            continue
                        file_size = 0
                        try:
                            p = Path(str(file_path))
                            if p.exists():
                                file_size = p.stat().st_size
                        except (TypeError, OSError, ValueError):
                            file_size = 0

                        conn.execute("""
                            INSERT OR REPLACE INTO sermon_files 
                            (sermon_id, file_type, file_path, file_size)
                            VALUES (?, ?, ?, ?)
                        """, (sermon_data.get('id'), file_type, str(file_path), file_size))

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

    def get_sermon(self, sermon_id: str) -> dict[str, Any] | None:
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
            processing_info = None
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

    def delete_sermon(self, sermon_id: str) -> bool:
        """Delete a sermon and all associated data"""
        try:
            with self.db.get_connection() as conn:
                # Delete from all related tables
                conn.execute("DELETE FROM qa_segments WHERE sermon_id = ?", (sermon_id,))
                conn.execute("DELETE FROM sermon_content WHERE sermon_id = ?", (sermon_id,))
                conn.execute("DELETE FROM processing_info WHERE sermon_id = ?", (sermon_id,))
                conn.execute("DELETE FROM sermon_files WHERE sermon_id = ?", (sermon_id,))
                conn.execute("DELETE FROM upload_info WHERE sermon_id = ?", (sermon_id,))
                conn.execute("DELETE FROM processing_status WHERE sermon_id = ?", (sermon_id,))
                conn.execute("DELETE FROM sermon_search WHERE sermon_id = ?", (sermon_id,))

                # Delete main sermon record
                conn.execute("DELETE FROM sermons WHERE id = ?", (sermon_id,))

                conn.commit()
                logger.info(f"Successfully deleted sermon {sermon_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete sermon {sermon_id}: {e}")
            return False

    def update_sermon_metadata(self, sermon_id: str, metadata: dict[str, Any]) -> bool:
        """Update sermon metadata in the database (partial update -- only specified fields)"""
        try:
            with self.db.get_connection() as conn:
                sermon_cols = ('title', 'subtitle', 'speaker', 'event_type', 'recorded_date',
                               'bible_text', 'series_title', 'description', 'scripture_reference',
                               'church_name', 'is_favorite', 'notes')
                set_parts = []
                params = []
                for col in sermon_cols:
                    if col in metadata:
                        set_parts.append(f"{col} = ?")
                        params.append(metadata[col])
                if set_parts:
                    set_parts.append("updated_at = ?")
                    params.append(datetime.datetime.now())
                    params.append(sermon_id)
                    conn.execute(f"""
                        UPDATE sermons SET {', '.join(set_parts)} WHERE id = ?
                    """, params)

                if 'description' in metadata:
                    conn.execute("""
                        UPDATE sermon_content SET description = ? WHERE sermon_id = ?
                    """, (metadata['description'], sermon_id))

                fts_cols = {'title', 'speaker', 'description', 'hashtags', 'transcript_text'}
                cols_in_update = fts_cols & metadata.keys()
                if cols_in_update:
                    existing = conn.execute(
                        "SELECT s.title, s.speaker, sc.transcript_text, COALESCE(sc.description, s.description) AS description, sc.hashtags "
                        "FROM sermons s "
                        "LEFT JOIN sermon_content sc ON s.id = sc.sermon_id "
                        "WHERE s.id = ?",
                        (sermon_id,)
                    ).fetchone()
                    fts_title = metadata.get('title') or (existing[0] if existing else '')
                    fts_speaker = metadata.get('speaker') or (existing[1] if existing else '')
                    fts_transcript = metadata.get('transcript_text') or (existing[2] if existing else '')
                    fts_description = metadata.get('description') or (existing[3] if existing else '')
                    fts_hashtags = metadata.get('hashtags') or (existing[4] if existing else '')
                    conn.execute("DELETE FROM sermon_search WHERE sermon_id = ?", (sermon_id,))
                    conn.execute("""
                        INSERT INTO sermon_search
                        (sermon_id, title, speaker, transcript_text, description, hashtags)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (sermon_id, fts_title, fts_speaker, fts_transcript, fts_description, fts_hashtags))

                conn.commit()
                logger.info(f"Successfully updated metadata for sermon {sermon_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to update sermon {sermon_id}: {e}")
            return False

    def get_all_sermons(self, filters: dict[str, Any] | None = None,
                       limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        """Get all sermons with optional filtering"""
        with self.db.get_connection() as conn:
            query = """
                SELECT s.id, s.title, s.subtitle, s.speaker, s.recorded_date, s.event_type,
                       s.bible_text, s.duration, s.status, s.created_at, s.updated_at,
                       s.series_title, s.scripture_reference, s.church_name,
                       s.is_favorite, s.notes,
                       pi.qa_segments_count,
                       pi.qa_normalization_applied,
                       pi.enhancement_method,
                       ui.upload_status,
                       sc.transcript_text AS transcript,
                       sc.description,
                       sc.hashtags,
                       sc.key_topics,
                       sc.summary
                FROM sermons s
                LEFT JOIN processing_info pi ON s.id = pi.sermon_id
                LEFT JOIN upload_info ui ON s.id = ui.sermon_id
                LEFT JOIN sermon_content sc ON s.id = sc.sermon_id
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

                if filters.get('is_favorite'):
                    query += " AND s.is_favorite = 1"

                if filters.get('status'):
                    query += " AND s.status = ?"
                    params.append(filters['status'])

            query += " ORDER BY s.recorded_date DESC, s.created_at DESC"

            if limit:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def search_sermons(self, query_text: str, limit: int = 50) -> list[dict[str, Any]]:
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

    def update_sermon(self, sermon_id: str, updates: dict[str, Any]) -> bool:
        """Update specific fields of an existing sermon"""
        try:
            with self.db.get_connection() as conn:
                # Build dynamic update query
                set_clauses = []
                params = []

                # Main sermon table fields
                sermon_fields = ['title', 'speaker', 'recorded_date', 'event_type', 'bible_text', 'duration', 'status']

                for field in sermon_fields:
                    if field in updates:
                        set_clauses.append(f"{field} = ?")
                        params.append(updates[field])

                if set_clauses:
                    set_clauses.append("updated_at = ?")
                    params.append(datetime.datetime.now())
                    params.append(sermon_id)

                    query = f"UPDATE sermons SET {', '.join(set_clauses)} WHERE id = ?"
                    conn.execute(query, params)

                # Update content table if content fields are provided
                content_fields = ['transcript', 'description', 'hashtags']
                content_updates = {k: v for k, v in updates.items() if k in content_fields}

                if content_updates:
                    # Check if content record exists
                    existing = conn.execute("SELECT sermon_id FROM sermon_content WHERE sermon_id = ?", (sermon_id,)).fetchone()

                    if existing:
                        # Update existing content
                        content_set_clauses = []
                        content_params = []

                        for field, value in content_updates.items():
                            if field == 'transcript':
                                content_set_clauses.append("transcript_text = ?")
                            else:
                                content_set_clauses.append(f"{field} = ?")
                            content_params.append(value)

                        if content_set_clauses:
                            content_set_clauses.append("updated_at = ?")
                            content_params.append(datetime.datetime.now())
                            content_params.append(sermon_id)

                            content_query = f"UPDATE sermon_content SET {', '.join(content_set_clauses)} WHERE sermon_id = ?"
                            conn.execute(content_query, content_params)
                    else:
                        # Create new content record
                        transcript_text = content_updates.get('transcript', '')
                        description = content_updates.get('description', '')
                        hashtags = content_updates.get('hashtags', '')

                        conn.execute("""
                            INSERT INTO sermon_content 
                            (sermon_id, transcript_text, description, hashtags)
                            VALUES (?, ?, ?, ?)
                        """, (sermon_id, transcript_text, description, hashtags))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to update sermon {sermon_id}: {e}")
            return False

    def get_processing_stats(self) -> dict[str, Any]:
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
