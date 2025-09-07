#!/usr/bin/env python3
"""
Quick debug script to test the fetch_all functionality
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'ui'))

from sermonaudio_analytics import SermonAudioAnalytics
import yaml

# Load config
with open('config.yaml') as f:
    config = yaml.safe_load(f)

# Create analytics instance
analytics = SermonAudioAnalytics(
    api_key=config['api_key'],
    broadcaster_id=config['broadcaster_id']
)

print("🔍 Testing fetch_all functionality...")
print(f"📺 Broadcaster ID: {config['broadcaster_id']}")
print(f"🎯 Mock Mode: {analytics.mock_mode}")

print("\n🔧 Testing get_all_sermon_analytics with fetch_all=True...")
try:
    data = analytics.get_all_sermon_analytics(fetch_all=True)
    print(f"✅ Received {len(data)} sermons")
    if data:
        first_sermon = data[0]
        print(f"📝 First sermon title: {first_sermon.get('title', 'N/A')}")
        print(f"👤 First sermon speaker: {first_sermon.get('speaker', 'N/A')}")
        print(f"📥 First sermon downloads: {first_sermon.get('downloads', 'N/A')}")
        print(f"👁️ First sermon views: {first_sermon.get('views', 'N/A')}")
        
        # Check if it's mock data
        title = first_sermon.get('title', '')
        if any(word in title for word in ['Discovering', 'Embracing', 'Finding', 'Growing', 'The Gift', 'The Power', 'Understanding', 'Walking']):
            print("🚨 WARNING: This appears to be mock data!")
        else:
            print("✅ This appears to be real data!")
            
except Exception as e:
    print(f"❌ Error: {e}")

print("\n🔧 Testing get_all_sermon_analytics with fetch_all=False...")
try:
    data = analytics.get_all_sermon_analytics(fetch_all=False)
    print(f"✅ Received {len(data)} sermons")
    if data:
        first_sermon = data[0]
        print(f"📝 First sermon title: {first_sermon.get('title', 'N/A')}")
        print(f"👤 First sermon speaker: {first_sermon.get('speaker', 'N/A')}")
        print(f"📥 First sermon downloads: {first_sermon.get('downloads', 'N/A')}")
        print(f"👁️ First sermon views: {first_sermon.get('views', 'N/A')}")
        
        # Check if it's mock data
        title = first_sermon.get('title', '')
        if any(word in title for word in ['Discovering', 'Embracing', 'Finding', 'Growing', 'The Gift', 'The Power', 'Understanding', 'Walking']):
            print("🚨 WARNING: This appears to be mock data!")
        else:
            print("✅ This appears to be real data!")
            
except Exception as e:
    print(f"❌ Error: {e}")
