#!/usr/bin/env python3
"""
Test Force Re-import Functionality

Test the new force re-import feature that allows refreshing API data
and re-importing existing sermons.
"""

import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent.parent
ui_dir = project_root / "ui"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(ui_dir))

def test_force_reimport():
    """Test the force re-import functionality"""

    print("🧪 Testing Force Re-import Functionality")

    try:
        from database import SermonRepository
        from sermon_importer import SermonImporter

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

        # Check if sermon exists in database
        existing_sermon = repo.get_sermon(test_sermon_id)
        if existing_sermon:
            print(f"✅ Sermon exists in database: {existing_sermon.get('title', 'No title')}")
            original_title = existing_sermon.get('title', 'Unknown')
        else:
            print("ℹ️  Sermon not in database, importing first...")
            success = importer.import_sermon(test_sermon_id)
            if success:
                existing_sermon = repo.get_sermon(test_sermon_id)
                original_title = existing_sermon.get('title', 'Unknown')
                print(f"✅ Imported sermon: {original_title}")
            else:
                print("❌ Failed to import sermon for testing")
                return

        # Test delete functionality
        print("🧪 Testing delete sermon functionality...")
        delete_success = repo.delete_sermon(test_sermon_id)
        if delete_success:
            print("✅ Successfully deleted sermon")

            # Verify deletion
            deleted_check = repo.get_sermon(test_sermon_id)
            if deleted_check is None:
                print("✅ Confirmed sermon was deleted from database")
            else:
                print("❌ Sermon still exists after deletion")
        else:
            print("❌ Failed to delete sermon")

        # Test re-import with fresh API data
        print("🧪 Testing re-import with fresh API data...")
        success = importer.import_sermon(test_sermon_id, refresh_api_data=True)

        if success:
            # Get the re-imported sermon
            reimported_sermon = repo.get_sermon(test_sermon_id)
            new_title = reimported_sermon.get('title', 'Unknown')
            new_speaker = reimported_sermon.get('speaker', 'Unknown')

            print("✅ Re-imported sermon successfully:")
            print(f"   Title: {new_title}")
            print(f"   Speaker: {new_speaker}")
            print(f"   Date: {reimported_sermon.get('recorded_date', 'Unknown')}")

            # Check if we got fresh API data
            api_cache_file = importer.processed_sermons_dir / test_sermon_id / f"{test_sermon_id}_api_data.json"
            if api_cache_file.exists():
                print("✅ Fresh API data cached for future use")
            else:
                print("ℹ️  No API cache file (normal if API not configured)")

        else:
            print("❌ Failed to re-import sermon")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_force_reimport()
    print("\n✅ Force re-import testing complete!")
