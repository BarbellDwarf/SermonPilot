#!/usr/bin/env python3
"""
Check the database for LLM API usage records and recent validation results
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

def check_database():
    # Connect to the database
    db_path = Path('sermon_processor.db')
    if not db_path.exists():
        print('Database file does not exist')
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if llm_api_usage table exists and get its schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='llm_api_usage'")
        schema = cursor.fetchone()
        if schema:
            print('LLM API Usage table schema:')
            print(schema[0])
            print()
            
            # Get row count
            cursor.execute('SELECT COUNT(*) FROM llm_api_usage')
            count = cursor.fetchone()[0]
            print(f'Total LLM API usage records: {count}')
            
            if count > 0:
                # Get recent records
                cursor.execute('SELECT * FROM llm_api_usage ORDER BY timestamp DESC LIMIT 10')
                records = cursor.fetchall()
                
                # Get column names
                cursor.execute('PRAGMA table_info(llm_api_usage)')
                columns = [col[1] for col in cursor.fetchall()]
                
                print('\nRecent LLM API usage records:')
                for record in records:
                    print(dict(zip(columns, record)))
            else:
                print('No LLM API usage records found')
        else:
            print('LLM API Usage table does not exist')

        # Check validation_results table for recent validation jobs
        print('\n' + '='*50)
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='validation_results'")
        validation_schema = cursor.fetchone()
        if validation_schema:
            print('Validation Results table schema:')
            print(validation_schema[0])
            print()
            
            # Get recent validation results
            cursor.execute("SELECT COUNT(*) FROM validation_results WHERE validated_at > datetime('now', '-1 hour')")
            recent_count = cursor.fetchone()[0]
            print(f'Validation results from last hour: {recent_count}')
            
            # Get all validation results to see what we have
            cursor.execute("SELECT COUNT(*) FROM validation_results")
            total_count = cursor.fetchone()[0]
            print(f'Total validation results: {total_count}')
            
            if total_count > 0:
                cursor.execute("SELECT sermon_id, is_valid, score, reason, validated_at FROM validation_results ORDER BY validated_at DESC LIMIT 10")
                records = cursor.fetchall()
                
                print('\nRecent validation results:')
                for record in records:
                    print(f'Sermon ID: {record[0]}, Valid: {record[1]}, Score: {record[2]}, Reason: {record[3]}, Time: {record[4]}')
        else:
            print('Validation Results table does not exist')

        # List all tables in the database
        print('\n' + '='*50)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print('All tables in database:')
        for table in tables:
            print(f'- {table[0]}')

    finally:
        conn.close()

if __name__ == '__main__':
    check_database()
