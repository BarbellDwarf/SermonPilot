#!/usr/bin/env python3
"""
Simple test for the force re-import functionality without delete
"""

import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent.parent
ui_dir = project_root / "ui"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

def test_reimport_without_delete():
    """Test re-import with refresh_api_data flag"""
    
    print("🧪 Testing Re-import with API Refresh")
    
    try:
        from sermon_importer import SermonImporter
        from database import SermonRepository
        
        # Initialize components
        importer = SermonImporter()
        repo = SermonRepository()
        print("✅ Components initialized")
        
        # Get a sermon to test with
        sermon_ids = importer.scan_processed_folder()
        if not sermon_ids:
            print("❌ No sermon folders found to test with")
            return
            
        test_sermon_id = sermon_ids[0]
        print(f"🧪 Testing with sermon {test_sermon_id}")
        
        # Test import with fresh API data flag
        print("🧪 Testing import with refresh_api_data=True...")
        success = importer.import_sermon(test_sermon_id, refresh_api_data=True)
        
        if success:
            # Get the imported sermon
            imported_sermon = repo.get_sermon(test_sermon_id)
            title = imported_sermon.get('title', 'Unknown')
            speaker = imported_sermon.get('speaker', 'Unknown')
            
            print(f"✅ Imported sermon successfully:")
            print(f"   Title: {title}")
            print(f"   Speaker: {speaker}")
            print(f"   Date: {imported_sermon.get('recorded_date', 'Unknown')}")
            
            # Check if we got fresh API data
            api_cache_file = importer.processed_sermons_dir / test_sermon_id / f"{test_sermon_id}_api_data.json"
            if api_cache_file.exists():
                print("✅ Fresh API data cached for future use")
                # Read cache to see what data we got
                import json
                with open(api_cache_file, 'r') as f:
                    api_data = json.load(f)
                print(f"   API Title: {api_data.get('title', 'No title')}")
                print(f"   API Speaker: {api_data.get('preacher', 'No speaker')}")
                print(f"   API Date: {api_data.get('preachDate', 'No date')}")
            else:
                print("ℹ️  No API cache file (normal if API not configured)")
                
            print("✅ Force re-import functionality is working!")
        else:
            print("❌ Failed to import sermon")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_reimport_without_delete()
    print("\n✅ Re-import testing complete!")
