#!/usr/bin/env python3
"""
Debug Auto Validation - Find what's triggering automatic validation

This script will help identify what component is automatically triggering
validation errors during startup.
"""

import os
import sys
from pathlib import Path

# Add paths like the UI does
ui_dir = Path(__file__).parent
project_root = ui_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

def test_imports():
    """Test importing UI components to see which one triggers validation"""
    
    print("🔍 Testing imports to find auto-validation trigger...")
    
    # Test basic imports first
    try:
        print("📦 Testing basic imports...")
        import yaml
        print("   ✅ yaml imported")
        
        import sqlite3
        print("   ✅ sqlite3 imported")
        
        from database import SermonRepository
        print("   ✅ database imported")
        
    except Exception as e:
        print(f"   ❌ Basic import failed: {e}")
        return
    
    # Test sermon importer
    try:
        print("📦 Testing sermon_importer...")
        from sermon_importer import get_import_status
        print("   ✅ sermon_importer imported successfully")
        
        # This might trigger the scan
        print("   🔍 Calling get_import_status()...")
        status = get_import_status()
        print(f"   ✅ Import status: {status.get('total_in_folder', 0)} sermons in folder")
        
    except Exception as e:
        print(f"   ❌ sermon_importer failed: {e}")
    
    # Test job queue
    try:
        print("📦 Testing job_queue...")
        from job_queue import get_job_queue
        queue = get_job_queue()
        print("   ✅ job_queue imported and initialized")
        
        jobs = queue.get_jobs()
        print(f"   ℹ️  Found {len(jobs)} total jobs in queue")
        
        active_jobs = [j for j in jobs if j.status.name in ['PENDING', 'RUNNING']]
        print(f"   ℹ️  Found {len(active_jobs)} active jobs")
        
        for job in active_jobs:
            print(f"      - {job.id[:8]}: {job.title} ({job.job_type.name}, {job.status.name})")
        
    except Exception as e:
        print(f"   ❌ job_queue failed: {e}")
    
    # Test ui_processor
    try:
        print("📦 Testing ui_processor...")
        from ui_processor import get_processor
        processor = get_processor()
        print("   ✅ ui_processor imported and initialized")
        
    except Exception as e:
        print(f"   ❌ ui_processor failed: {e}")
    
    print("🔍 Import testing complete!")

if __name__ == "__main__":
    test_imports()
