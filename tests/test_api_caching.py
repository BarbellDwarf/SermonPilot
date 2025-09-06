#!/usr/bin/env python3
"""
Test API caching functionality
"""

import sys
from pathlib import Path
import json

# Add paths
project_root = Path(__file__).parent.parent
ui_dir = project_root / "ui"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

def test_api_caching():
    """Test that API data is properly cached"""
    
    print("🧪 Testing API Caching")
    
    try:
        from sermonaudio_api import SermonAudioAPI
        from sermon_importer import SermonImporter
        
        # Initialize components
        api = SermonAudioAPI()
        importer = SermonImporter()
        print("✅ Components initialized")
        
        if not api.is_configured():
            print("⚠️  SermonAudio API not configured - skipping test")
            return
            
        # Get a sermon to test with
        sermon_ids = importer.scan_processed_folder()
        if not sermon_ids:
            print("❌ No sermon folders found to test with")
            return
            
        test_sermon_id = sermon_ids[0]
        print(f"🧪 Testing with sermon {test_sermon_id}")
        
        # Test API data retrieval and caching
        print("🧪 Testing API data retrieval...")
        api_data = api.get_sermon_details(test_sermon_id)
        
        if api_data:
            print(f"✅ Retrieved API data:")
            print(f"   Title: {api_data.get('title', 'No title')}")
            print(f"   Speaker: {api_data.get('preacher', 'No speaker')}")
            print(f"   Date: {api_data.get('preachDate', 'No date')}")
            print(f"   Series: {api_data.get('seriesTitle', 'No series')}")
            
            # Check if data is cached
            cache_file = importer.processed_sermons_dir / test_sermon_id / f"{test_sermon_id}_api_data.json"
            if cache_file.exists():
                print("✅ API data is cached")
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                print(f"   Cached title: {cached_data.get('title', 'No title')}")
                
                # Verify data matches
                if cached_data.get('title') == api_data.get('title'):
                    print("✅ Cached data matches API data")
                else:
                    print("❌ Cached data does not match API data")
            else:
                print("❌ API data is not cached")
        else:
            print("❌ Failed to retrieve API data")
            
        # Test speakers and series
        print("🧪 Testing speakers and series...")
        speakers = api.get_speakers()
        series = api.get_series()
        
        print(f"✅ Found {len(speakers)} speakers")
        print(f"✅ Found {len(series)} series")
        
        if speakers:
            print(f"   Example speakers: {speakers[:3]}")
        if series:
            print(f"   Example series: {series[:3]}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_caching()
    print("\n✅ API caching testing complete!")
