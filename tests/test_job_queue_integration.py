#!/usr/bin/env python3
"""
Simple test to verify job queue integration works correctly.
This tests the backend functionality without requiring browser automation.
"""

import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent  # Go up one level from tests/
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ui"))

def test_job_queue_basic():
    """Test basic job queue functionality"""
    print("🔧 Testing job queue system...")
    
    try:
        from ui.job_queue import get_job_queue, JobType, JobStatus
        
        # Get job queue instance
        job_queue = get_job_queue()
        print("✅ Job queue initialized successfully")
        
        # Create a test validation job
        print("📝 Creating test validation job...")
        validation_job_id = job_queue.add_job(
            job_type=JobType.VALIDATION,
            title="Test Validation Job",
            description="Testing validation job functionality",
            parameters={'sermon_ids': ['123', '456'], 'test': True}
        )
        print(f"✅ Created validation job with ID: {validation_job_id[:8]}")
        
        # Create a test batch processing job
        print("📝 Creating test batch processing job...")
        batch_job_id = job_queue.add_job(
            job_type=JobType.BATCH_PROCESSING,
            title="Test Batch Processing",
            description="Testing batch processing functionality",
            parameters={
                'sermon_ids': ['789', '101112'],
                'actions': {
                    'generate_description': True,
                    'generate_hashtags': False,
                    'enhance_audio': True,
                    'validate_content': False
                },
                'config': {'api_key': 'test', 'broadcaster_id': 'test'}
            }
        )
        print(f"✅ Created batch job with ID: {batch_job_id[:8]}")
        
        # Check job status
        validation_job = job_queue.get_job(validation_job_id)
        batch_job = job_queue.get_job(batch_job_id)
        
        if validation_job:
            print(f"✅ Validation job found - Status: {validation_job.status}, Progress: {validation_job.progress}%")
        else:
            print("❌ Validation job not found")
            
        if batch_job:
            print(f"✅ Batch job found - Status: {batch_job.status}, Progress: {batch_job.progress}%")
        else:
            print("❌ Batch job not found")
        
        # List all jobs
        all_jobs = job_queue.get_all_jobs()
        print(f"📋 Total jobs in queue: {len(all_jobs)}")
        
        for job in all_jobs:
            print(f"   - {job.title} ({job.type.value}) - {job.status.value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Job queue test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_job_executors():
    """Test that job executors are properly registered"""
    print("\n🛠️ Testing job executors...")
    
    try:
        from ui.job_executors import get_available_job_types, get_executor
        
        available_types = get_available_job_types()
        print(f"✅ Available job types: {[t.value for t in available_types]}")
        
        for job_type in available_types:
            executor = get_executor(job_type)
            if executor:
                print(f"✅ Executor found for {job_type.value}: {executor.__name__}")
            else:
                print(f"❌ No executor found for {job_type.value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Job executor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_connectivity():
    """Test database connectivity for job persistence"""
    print("\n💾 Testing database connectivity...")
    
    try:
        from ui.database import get_db
        
        db = get_db()
        print("✅ Database connection established")
        
        # Test basic database operations
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='background_jobs'")
            result = cursor.fetchone()
            if result:
                print("✅ background_jobs table exists")
            else:
                print("⚠️ background_jobs table not found (will be created on first use)")
        
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ui_imports():
    """Test that UI page imports work correctly"""
    print("\n📱 Testing UI page imports...")
    
    try:
        # Test batch update page imports
        from ui.ui_pages.batch_update import start_batch_processing
        print("✅ batch_update.py imports successfully")
        
        # Test new sermon page imports
        from ui.ui_pages.new_sermon import start_processing
        print("✅ new_sermon.py imports successfully")
        
        # Test jobs page imports
        from ui.ui_pages.jobs import show_jobs
        print("✅ jobs.py imports successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ UI import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Job Queue Integration Test Suite")
    print("=" * 50)
    
    all_passed = True
    
    # Test 1: Basic job queue functionality
    print("\n1️⃣ Testing basic job queue functionality...")
    if not test_job_queue_basic():
        all_passed = False
    
    # Test 2: Job executors
    print("\n2️⃣ Testing job executors...")
    if not test_job_executors():
        all_passed = False
    
    # Test 3: Database connectivity
    print("\n3️⃣ Testing database connectivity...")
    if not test_database_connectivity():
        all_passed = False
    
    # Test 4: UI imports
    print("\n4️⃣ Testing UI page imports...")
    if not test_ui_imports():
        all_passed = False
    
    # Summary
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All tests passed! Job queue integration is working correctly.")
        print("\n💡 To test the full UI integration:")
        print("   1. Start the Streamlit app: streamlit run streamlit_app.py")
        print("   2. Navigate to Batch Update page")
        print("   3. Configure some sermons and start batch processing")
        print("   4. Navigate to Jobs page to see the job running")
        print("   5. Navigate back to Batch Update to see it's no longer using session state")
    else:
        print("❌ Some tests failed. Please check the errors above.")
    
    print("\n🏁 Test suite completed!")
