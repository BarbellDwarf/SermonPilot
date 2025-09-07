#!/usr/bin/env python3
"""
Test script to debug SermonAudio API integration
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml
from ui.sermonaudio_analytics import SermonAudioAnalytics

def test_sermonaudio_api():
    """Test the SermonAudio API integration"""
    
    # Load config
    print("📖 Loading configuration...")
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        api_key = config.get('api_key', '')
        broadcaster_id = config.get('broadcaster_id', '')
        
        print(f"✅ Config loaded: API key = {'✓' if api_key else '✗'}, Broadcaster ID = {broadcaster_id}")
        
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return
    
    # Initialize analytics
    print("\n🚀 Initializing SermonAudio Analytics...")
    analytics = SermonAudioAnalytics(api_key=api_key, broadcaster_id=broadcaster_id)
    
    if analytics.mock_mode:
        print("⚠️  Running in MOCK mode - credentials missing or invalid")
        return
    else:
        print("✅ Running in REAL mode - credentials configured")
    
    # Test API call
    print("\n📡 Making API call...")
    try:
        data = analytics.get_all_sermon_analytics()
        print(f"✅ API call successful! Received {len(data)} sermons")
        
        if data:
            # Show first sermon details
            first_sermon = data[0]
            print(f"\n📋 Sample sermon data:")
            print(f"  Title: {first_sermon.get('title', 'N/A')}")
            print(f"  Speaker: {first_sermon.get('speaker', 'N/A')}")
            print(f"  Views: {first_sermon.get('views', 0)}")
            print(f"  Downloads: {first_sermon.get('downloads', 0)}")
            print(f"  Date: {first_sermon.get('date', 'N/A')}")
            print(f"  Church: {first_sermon.get('church_name', 'N/A')}")
            
            # Show all available keys
            print(f"\n🔑 Available data fields: {list(first_sermon.keys())}")
            
            # Check for real vs mock data indicators
            if first_sermon.get('speaker') in ['Pastor John Smith', 'Dr. Sarah Johnson', 'Rev. Michael Brown']:
                print("⚠️  WARNING: This appears to be MOCK data, not real church data!")
            else:
                print("✅ This appears to be REAL data from your church!")
        
    except Exception as e:
        print(f"❌ API call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_sermonaudio_api()
