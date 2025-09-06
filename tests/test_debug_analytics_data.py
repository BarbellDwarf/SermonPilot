#!/usr/bin/env python3
"""
Debug test for analytics data retrieval
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_analytics_data_retrieval():
    """Test what's happening in get_real_content_data function."""
    
    print("=" * 60)
    print("DEBUGGING ANALYTICS DATA RETRIEVAL")
    print("=" * 60)
    
    try:
        # Import the analytics module and function
        from ui.ui_pages.analytics import get_real_content_data, get_validated_sermon_ids
        from ui.database import get_db
        
        print("✅ Successfully imported analytics functions")
        
        # Test database connection
        db = get_db()
        print("✅ Database connection established")
        
        # Test validated sermon IDs function directly
        print("\n🔍 Testing get_validated_sermon_ids function...")
        validated_ids = get_validated_sermon_ids(db)
        print(f"📊 Found {len(validated_ids)} validated sermon IDs")
        if validated_ids:
            print(f"Sample IDs: {validated_ids[:5]}")
        
        # Test processing status
        processing_data = db.get_processing_status()
        print(f"📊 Found {len(processing_data)} processing status records")
        
        # Test the full function
        print("\n🔍 Testing get_real_content_data function...")
        content_data = get_real_content_data()
        print(f"📊 Content data keys: {list(content_data.keys())}")
        print(f"📊 Speaker stats count: {len(content_data.get('speaker_stats', []))}")
        print(f"📊 Event types count: {len(content_data.get('event_types', []))}")
        print(f"📊 Quality trends count: {len(content_data.get('quality_trends', []))}")
        
        if content_data.get('speaker_stats'):
            print(f"📋 Sample speaker stats: {content_data['speaker_stats'][0]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_analytics_data_retrieval()
    exit_code = 0 if success else 1
    print(f'\nTest {"PASSED" if success else "FAILED"} - Exit code: {exit_code}')
    sys.exit(exit_code)
