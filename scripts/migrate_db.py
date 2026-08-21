"""Repair an existing SermonPilot database.

Rebuilds the sermon_search FTS table with the standalone schema, dedupes FTS
rows, removes orphaned child rows, and guards NULL recorded_date values.

Usage:
    python scripts/migrate_db.py [db_path]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

EXPECTED_FTS_COLS = [
    'sermon_id', 'title', 'speaker', 'transcript_text', 'description',
    'hashtags', 'key_topics', 'summary',
]

CHILD_TABLES = (
    'sermon_files', 'processing_info', 'qa_segments', 'sermon_content',
    'upload_info', 'validation_results', 'manual_review', 'llm_api_usage',
    'processing_status',
)

# Must match the indexes created by SermonDatabase.init_database()
INDEX_STATEMENTS = (
    ("idx_llm_usage_timestamp", "llm_api_usage(timestamp)"),
    ("idx_llm_usage_provider_model", "llm_api_usage(provider, model)"),
    ("idx_llm_usage_sermon_id", "llm_api_usage(sermon_id)"),
    ("idx_qa_segments_sermon_id", "qa_segments(sermon_id)"),
    ("idx_processing_status_sermon_operation",
     "processing_status(sermon_id, operation)"),
    ("idx_processing_status_started_at", "processing_status(started_at)"),
    ("idx_sermons_status", "sermons(status)"),
    ("idx_sermons_recorded_date", "sermons(recorded_date)"),
)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def enable_wal(conn: sqlite3.Connection) -> None:
    """Switch the database to write-ahead logging (persistent per file)."""
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    print(f"Journal mode: {mode}")


def ensure_indexes(conn: sqlite3.Connection) -> None:
    """Create any missing query indexes."""
    created = 0
    for name, columns in INDEX_STATEMENTS:
        cursor = conn.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON {columns}"
        )
        created += max(cursor.rowcount, 0)
    conn.commit()
    print(f"Indexes ensured ({created} created)")


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Drop and recreate sermon_search, then repopulate from sermons."""
    conn.execute("DROP TABLE IF EXISTS sermon_search")
    conn.execute("""
        CREATE VIRTUAL TABLE sermon_search USING fts5(
            sermon_id,
            title,
            speaker,
            transcript_text,
            description,
            hashtags,
            key_topics,
            summary
        )
    """)
    conn.execute("""
        INSERT INTO sermon_search
            (sermon_id, title, speaker, transcript_text, description, hashtags,
             key_topics, summary)
        SELECT s.id, s.title, s.speaker, sc.transcript_text, sc.description,
               sc.hashtags, sc.key_topics, sc.summary
        FROM sermons s
        LEFT JOIN sermon_content sc ON s.id = sc.sermon_id
    """)
    conn.commit()


def dedupe_fts(conn: sqlite3.Connection) -> None:
    """Remove duplicate FTS rows, keeping the oldest row per sermon_id."""
    conn.execute("""
        DELETE FROM sermon_search
        WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM sermon_search GROUP BY sermon_id
        )
    """)
    conn.commit()


def remove_orphans(conn: sqlite3.Connection, tables: set[str]) -> None:
    """Delete child rows whose sermon no longer exists."""
    for table in CHILD_TABLES:
        if table not in tables:
            continue
        conn.execute(f"""
            DELETE FROM {table}
            WHERE sermon_id IS NOT NULL
              AND sermon_id NOT IN (SELECT id FROM sermons)
        """)
    conn.commit()


def guard_null_dates(conn: sqlite3.Connection) -> None:
    """Replace NULL recorded_date values with a safe default."""
    conn.execute(
        "UPDATE sermons SET recorded_date = '1900-01-01' WHERE recorded_date IS NULL"
    )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair a SermonPilot database")
    parser.add_argument(
        'db_path', nargs='?', default='sermon_processor.db',
        help='Path to the SQLite database (default: sermon_processor.db)',
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    conn = _connect(db_path)
    try:
        tables = {
            row['name'] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if 'sermons' not in tables:
            print("No sermons table found; nothing to repair")
            return 0

        fts_cols = [
            row['name'] for row in conn.execute("PRAGMA table_info(sermon_search)")
        ]
        if fts_cols != EXPECTED_FTS_COLS:
            print("Rebuilding sermon_search (broken or missing FTS table)")
            rebuild_fts(conn)
        else:
            print("sermon_search already uses the standalone schema")

        dedupe_fts(conn)
        remove_orphans(conn, tables)
        guard_null_dates(conn)
        ensure_indexes(conn)
        enable_wal(conn)
        print("Database repair complete")
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
