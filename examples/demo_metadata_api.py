#!/usr/bin/env python3
"""
Demo script to test the new SermonAudio API metadata functionality

This script demonstrates the new pastor, event type, and series retrieval
functionality that has been added to the SermonAudio Processor.

Usage:
    python demo_metadata_api.py

Requirements:
    - config.yaml with valid SermonAudio API configuration
    - Internet connection
"""

import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, '.')

def test_metadata_api():
    """Test the new metadata API functions"""
    print("🔄 Testing SermonAudio Metadata API Functions")
    print("=" * 50)
    
    try:
        # Import with minimal setup
        import yaml
        from dotenv import load_dotenv
        
        # Load environment
        load_dotenv()
        
        # Check for config file
        config_path = Path('config.yaml')
        if not config_path.exists():
            print("❌ Config file not found. Please create config.yaml with SermonAudio API credentials.")
            print("   See config.example.yaml for reference.")
            return False
            
        # Load config
        with open(config_path) as f:
            config = yaml.safe_load(f)
            
        sermon_audio_config = config.get('sermon_audio', {})
        if not sermon_audio_config.get('api_key'):
            print("❌ SermonAudio API key not found in config.yaml")
            print("   Please add your API key under sermon_audio.api_key")
            return False
            
        print("✅ Configuration loaded successfully")
        
        # Set up API key for sermon_updater
        os.environ['SERMON_AUDIO_API_KEY'] = sermon_audio_config['api_key']
        
        # Import our new functions
        from sermon_updater import get_broadcaster_pastors, get_broadcaster_event_types, get_broadcaster_series
        
        print("\n📋 Testing Pastor Retrieval...")
        pastors = get_broadcaster_pastors(limit=50)
        print(f"   Found {len(pastors)} pastors:")
        for i, pastor in enumerate(pastors[:5]):  # Show first 5
            print(f"   {i+1}. {pastor}")
        if len(pastors) > 5:
            print(f"   ... and {len(pastors) - 5} more")
            
        print("\n📅 Testing Event Type Retrieval...")
        events = get_broadcaster_event_types(limit=50)
        print(f"   Found {len(events)} event types:")
        for i, event in enumerate(events[:5]):  # Show first 5
            print(f"   {i+1}. {event}")
        if len(events) > 5:
            print(f"   ... and {len(events) - 5} more")
            
        print("\n📚 Testing Series Retrieval...")
        series = get_broadcaster_series(limit=50)
        print(f"   Found {len(series)} series:")
        for i, s in enumerate(series[:5]):  # Show first 5
            print(f"   {i+1}. {s}")
        if len(series) > 5:
            print(f"   ... and {len(series) - 5} more")
            
        print("\n✅ All API functions tested successfully!")
        print("\n🎯 Next Steps:")
        print("   1. Run the Streamlit UI: streamlit run ui/streamlit_app.py")
        print("   2. Navigate to New Sermon or Batch Update pages")
        print("   3. Use the 'Refresh Metadata' section to load this data into dropdowns")
        print("   4. Select pastors, events, and series from dynamic dropdowns")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Please install required dependencies: pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Error testing API: {e}")
        return False

if __name__ == "__main__":
    success = test_metadata_api()
    sys.exit(0 if success else 1)