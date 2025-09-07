#!/usr/bin/env python3
"""Check database schema"""

import sys
import sqlite3
from pathlib import Path

# Add ui to path
ui_dir = Path(__file__).parent / "ui"
sys.path.insert(0, str(ui_dir))

from database import get_db

def main():
    db = get_db()
    with db.get_connection() as conn:
        # Get table schema
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for table in tables:
            print(f'\n=== Table: {table[0]} ===')
            schema = conn.execute(f'PRAGMA table_info({table[0]})').fetchall()
            for col in schema:
                null_str = "NOT NULL" if col[3] else "NULL"
                print(f'{col[1]} {col[2]} ({null_str})')

if __name__ == "__main__":
    main()
