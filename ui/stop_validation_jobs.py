#!/usr/bin/env python3
"""
Stop Validation Jobs - Emergency script to stop ongoing validation jobs

This script will:
1. Connect to the job queue database
2. Cancel any running validation jobs 
3. Clear validation job state to prevent further errors

Usage: python stop_validation_jobs.py
"""

import sqlite3
import sys
from pathlib import Path

def stop_validation_jobs():
    """Stop all validation jobs and clear state"""
    
    # Try to connect to jobs database
    ui_dir = Path(__file__).parent
    db_path = ui_dir / "jobs.db"
    
    if not db_path.exists():
        print("✅ No jobs database found - no active jobs to stop")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Get current validation jobs
        cursor.execute('''
            SELECT id, title, status FROM jobs 
            WHERE job_type = 'VALIDATION' AND status IN ('pending', 'running')
        ''')
        
        validation_jobs = cursor.fetchall()
        
        if not validation_jobs:
            print("✅ No active validation jobs found")
        else:
            print(f"🛑 Found {len(validation_jobs)} active validation jobs - stopping them...")
            
            for job_id, title, status in validation_jobs:
                print(f"   Stopping: {job_id[:8]} - {title} ({status})")
            
            # Cancel all validation jobs
            cursor.execute('''
                UPDATE jobs 
                SET status = 'cancelled', 
                    completed_at = datetime('now'),
                    result = 'Stopped by emergency script - configuration issue'
                WHERE job_type = 'VALIDATION' AND status IN ('pending', 'running')
            ''')
            
            affected_rows = cursor.rowcount
            conn.commit()
            
            print(f"✅ Stopped {affected_rows} validation jobs")
        
        # Show remaining jobs
        cursor.execute('SELECT COUNT(*) FROM jobs WHERE status IN ("pending", "running")')
        remaining_jobs = cursor.fetchone()[0]
        
        if remaining_jobs > 0:
            cursor.execute('''
                SELECT id, title, job_type, status FROM jobs 
                WHERE status IN ('pending', 'running')
            ''')
            active_jobs = cursor.fetchall()
            
            print(f"ℹ️  {remaining_jobs} other active jobs:")
            for job_id, title, job_type, status in active_jobs:
                print(f"   {job_id[:8]} - {title} ({job_type}, {status})")
        else:
            print("✅ No other active jobs")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error stopping validation jobs: {e}")

if __name__ == "__main__":
    print("🛑 Stopping validation jobs...")
    stop_validation_jobs()
    print("✅ Done!")
