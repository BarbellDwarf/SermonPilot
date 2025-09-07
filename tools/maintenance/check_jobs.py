#!/usr/bin/env python3
"""
Check the background jobs for recent validation job details
"""

import sqlite3
from pathlib import Path

def check_jobs():
    # Connect to the database
    db_path = Path('sermon_processor.db')
    if not db_path.exists():
        print('Database file does not exist')
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check background_jobs table
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='background_jobs'")
        schema = cursor.fetchone()
        if schema:
            print('Background Jobs table schema:')
            print(schema[0])
            print()
            
            # Get recent jobs
            cursor.execute("SELECT COUNT(*) FROM background_jobs")
            total_count = cursor.fetchone()[0]
            print(f'Total background jobs: {total_count}')
            
            if total_count > 0:
                # Get column names
                cursor.execute('PRAGMA table_info(background_jobs)')
                columns = [col[1] for col in cursor.fetchall()]
                print(f'Columns: {columns}')
                
                # Get recent jobs
                cursor.execute("SELECT * FROM background_jobs ORDER BY id DESC LIMIT 5")
                records = cursor.fetchall()
                
                print('\nRecent background jobs:')
                for record in records:
                    job_data = dict(zip(columns, record, strict=True))
                    print(f"Job ID: {job_data.get('job_id', 'N/A')}")
                    print(f"  Type: {job_data.get('job_type', 'N/A')}")
                    print(f"  Status: {job_data.get('status', 'N/A')}")
                    print(f"  Progress: {job_data.get('progress', 'N/A')}")
                    print(f"  Created: {job_data.get('created_at', 'N/A')}")
                    print(f"  Started: {job_data.get('started_at', 'N/A')}")
                    print(f"  Completed: {job_data.get('completed_at', 'N/A')}")
                    print(f"  Result: {job_data.get('result', 'N/A')}")
                    if job_data.get('error_message'):
                        print(f"  Error: {job_data.get('error_message')}")
                    print()
        else:
            print('Background Jobs table does not exist')

    finally:
        conn.close()

if __name__ == '__main__':
    check_jobs()
