#!/usr/bin/env python3
"""
Test Enhanced Sermon Import with API Integration

This script tests the enhanced sermon import functionality that now
fetches metadata from the SermonAudio API.
"""

import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent.parent
ui_dir = project_root / "ui"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

def test_api_integration():
    """Test the API integration for sermon import"""

    print("🧪 Testing Enhanced Sermon Import with API Integration")

    try:
        from sermon_importer import SermonImporter

        # Initialize importer
        importer = SermonImporter()
        print("✅ SermonImporter initialized")

        # Test scanning
        sermon_ids = importer.scan_processed_folder()
        print(f"📁 Found {len(sermon_ids)} sermon folders")

        if sermon_ids:
            # Test with first sermon
            test_sermon_id = sermon_ids[0]
            print(f"🧪 Testing API metadata extraction for sermon {test_sermon_id}")

            # Test the API metadata extraction
            api_data = importer._fetch_sermon_metadata_from_api(test_sermon_id)

            if api_data:
                print("✅ Successfully fetched API data:")
                print(f"   Title: {api_data.get('title', 'N/A')}")
                print(f"   Speaker: {api_data.get('speaker', 'N/A')}")
                print(f"   Event Type: {api_data.get('eventType', 'N/A')}")
                print(f"   Bible Text: {api_data.get('bibleText', 'N/A')}")
            else:
                print("⚠️  No API data retrieved (this may be normal if API not configured)")

            # Test metadata extraction
            print("🧪 Testing complete metadata extraction...")
            metadata = importer.extract_sermon_metadata(test_sermon_id)

            print("✅ Extracted metadata:")
            print(f"   ID: {metadata.get('id')}")
            print(f"   Title: {metadata.get('title')}")
            print(f"   Speaker: {metadata.get('speaker')}")
            print(f"   Date: {metadata.get('recorded_date')}")
            print(f"   Has Description: {'description' in metadata.get('content', {})}")
            print(f"   Has Hashtags: {'hashtags' in metadata.get('content', {})}")

        else:
            print("ℹ️  No sermon folders found to test with")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

def test_job_queue():
    """Test that job queue imports work"""

    print("\n🧪 Testing Job Queue Import")

    try:
        from job_queue import get_job_queue
        print("✅ Successfully imported job queue components")

        # Test initialization
        queue = get_job_queue()
        print("✅ Job queue initialized successfully")

        # Test getting jobs
        jobs = queue.get_all_jobs()
        print(f"📋 Found {len(jobs)} total jobs in queue")

        print("✅ Job queue system working correctly")

    except Exception as e:
        print(f"❌ Job queue test failed: {e}")

if __name__ == "__main__":
    test_api_integration()
    test_job_queue()
    print("\n✅ Testing complete!")
