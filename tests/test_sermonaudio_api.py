#!/usr/bin/env python3
"""
Test script to debug SermonAudio API integration
"""

import sys
import os
# Add parent directory to path to import ui modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from ui.sermonaudio_analytics import SermonAudioAnalytics

def test_sermonaudio_api():
    """Test the SermonAudio API integration"""
    
    # Load config
    print("📖 Loading configuration...")
    try:
        with open('../config.yaml') as f:
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
        # Let's also test the raw API call to see what's happening
        import requests
        
        # Test the raw API first
        print("🔍 Testing raw API call...")
        base_url = 'https://api.sermonaudio.com/v2/'
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        params = {
            'broadcasterID': broadcaster_id,
            'pageSize': 100,
            'lite': 'false',
            'cache': 'true',
            'sortBy': 'newest',
            'requireAudio': 'false'
        }
        
        response = requests.get(
            f"{base_url}node/sermons",
            headers=headers,
            params=params,
            timeout=30
        )
        
        print(f"📊 Raw API Response:")
        print(f"  Status Code: {response.status_code}")
        print(f"  URL: {response.url}")
        
        if response.status_code == 200:
            raw_data = response.json()
            print(f"  Response Keys: {list(raw_data.keys())}")
            print(f"  Total Count: {raw_data.get('totalCount', 'Not found')}")
            
            # Check both 'sermons' and 'results' fields
            sermons_data = raw_data.get('results', raw_data.get('sermons', []))
            print(f"  Sermons Length: {len(sermons_data)}")
            
            if sermons_data:
                first_sermon = sermons_data[0]
                print(f"  First Sermon Keys: {list(first_sermon.keys())}")
                print("\n🔍 RAW FIRST SERMON DATA:")
                import json
                sermon_json = json.dumps(first_sermon, indent=2)
                if len(sermon_json) > 1500:
                    print(sermon_json[:1500] + "...")
                else:
                    print(sermon_json)
                
                # Show specific fields we're interested in
                print("\n🎯 KEY FIELDS:")
                print(f"  fullTitle: {first_sermon.get('fullTitle')}")
                print(f"  displayTitle: {first_sermon.get('displayTitle')}")
                print(f"  downloadCount: {first_sermon.get('downloadCount')}")
                print(f"  detailedStats: {first_sermon.get('detailedStats')}")
                print(f"  speaker: {first_sermon.get('speaker')}")
                print(f"  eventType: {first_sermon.get('eventType')}")
                print(f"  broadcaster: {first_sermon.get('broadcaster', {}).get('displayName', 'N/A')}")
        else:
            print(f"  Error Response: {response.text[:200]}")
        
        # Test individual sermon call for detailed stats
        print("\n🔍 Testing individual sermon call for detailed stats...")
        if sermons_data:
            sermon_id = sermons_data[0].get('sermonID')
            if sermon_id:
                individual_url = f"https://api.sermonaudio.com/v2/node/sermons/{sermon_id}"
                individual_headers = {
                    'X-Api-Key': api_key,
                    'Accept': 'application/json'
                }
                individual_params = {
                    'lite': 'false'
                }
                
                individual_response = requests.get(individual_url, headers=individual_headers, params=individual_params)
                print(f"📊 Individual Sermon API Response:")
                print(f"  Status Code: {individual_response.status_code}")
                print(f"  URL: {individual_response.url}")
                
                if individual_response.status_code == 200:
                    individual_data = individual_response.json()
                    detailed_stats = individual_data.get('detailedStats')
                    print(f"  detailedStats: {detailed_stats}")
                    
                    if detailed_stats:
                        print(f"  📈 Detailed Stats Found:")
                        for key, value in detailed_stats.items():
                            print(f"    {key}: {value}")
                    else:
                        print("  ⚠️ detailedStats is None even for individual sermon call")
                        # Let's check if there are any other stats fields
                        stats_fields = ['downloadCount', 'videoDownloadCount', 'commentCount', 'lastAudioAccessTimestamp']
                        for field in stats_fields:
                            value = individual_data.get(field)
                            print(f"    {field}: {value}")
                else:
                    print(f"  Error: {individual_response.text[:200]}")
        
        # Now test through our analytics class
        print("\n🎯 Testing through analytics class...")
        data = analytics.get_all_sermon_analytics()
        print(f"✅ API call successful! Received {len(data)} sermons")
        
        if data:
            # Show first sermon details
            first_sermon = data[0]
            print("\n📋 Sample sermon data:")
            print(f"  Title: {first_sermon.get('title', 'N/A')}")
            print(f"  Speaker: {first_sermon.get('speaker', 'N/A')}")
            print(f"  Views: {first_sermon.get('views', 0)}")
            print(f"  Downloads: {first_sermon.get('downloads', 0)}")
            print(f"  Date: {first_sermon.get('date', 'N/A')}")
            print(f"  Church: {first_sermon.get('church_name', 'N/A')}")
            print(f"  Event Type: {first_sermon.get('event_type', 'N/A')}")
            print(f"  Bible Text: {first_sermon.get('bible_text', 'N/A')}")
            
            # Show all available keys
            print(f"\n🔑 Available data fields: {list(first_sermon.keys())}")
            
            # Check for real vs mock data indicators
            mock_speakers = ['Pastor John Smith', 'Dr. Sarah Johnson', 'Rev. Michael Brown']
            if first_sermon.get('speaker') in mock_speakers:
                print("⚠️  WARNING: This appears to be MOCK data, not real church data!")
            else:
                print("✅ This appears to be REAL data from your church!")
        else:
            print("⚠️  No sermons returned. This could mean:")
            print("   1. No sermons are uploaded for this broadcaster")
            print("   2. The broadcaster ID is incorrect")
            print("   3. The sermons are private or restricted")
            print("   4. There's an API permission issue")
        
    except Exception as e:
        print(f"❌ API call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_sermonaudio_api()

import yaml
from ui.sermonaudio_analytics import SermonAudioAnalytics

def test_sermonaudio_api():
    """Test the SermonAudio API integration"""
    
    # Load config
    print("📖 Loading configuration...")
    try:
        with open('../config.yaml') as f:
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
        # Let's also test the raw API call to see what's happening
        import requests
        
        # Test the raw API first
        print("🔍 Testing raw API call...")
        base_url = 'https://api.sermonaudio.com/v2/'
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        params = {
            'broadcasterID': broadcaster_id,
            'pageSize': 100,
            'lite': 'false',
            'cache': 'true',
            'sortBy': 'newest',
            'requireAudio': 'false'
        }
        
        response = requests.get(
            f"{base_url}node/sermons",
            headers=headers,
            params=params,
            timeout=30
        )
        
        print(f"📊 Raw API Response:")
        print(f"  Status Code: {response.status_code}")
        print(f"  URL: {response.url}")
        
        if response.status_code == 200:
            raw_data = response.json()
            print(f"  Response Keys: {list(raw_data.keys())}")
            print(f"  Total Count: {raw_data.get('totalCount', 'Not found')}")
            
            # Check both 'sermons' and 'results' fields
            sermons_data = raw_data.get('results', raw_data.get('sermons', []))
            print(f"  Sermons Length: {len(sermons_data)}")
            
            if sermons_data:
                first_sermon = sermons_data[0]
                print(f"  First Sermon Keys: {list(first_sermon.keys())}")
                print(f"\n🔍 RAW FIRST SERMON DATA:")
                import json
                print(json.dumps(first_sermon, indent=2)[:1000] + "..." if len(json.dumps(first_sermon)) > 1000 else json.dumps(first_sermon, indent=2))
        else:
            print(f"  Error Response: {response.text[:200]}")
        
        # Now test through our analytics class
        print(f"\n🎯 Testing through analytics class...")
        data = analytics.get_all_sermon_analytics()
        print(f"✅ API call successful! Received {len(data)} sermons")
        
        if data:
            # Show first sermon details
            first_sermon = data[0]
            print("\n📋 Sample sermon data:")
            print(f"  Title: {first_sermon.get('title', 'N/A')}")
            print(f"  Speaker: {first_sermon.get('speaker', 'N/A')}")
            print(f"  Views: {first_sermon.get('views', 0)}")
            print(f"  Downloads: {first_sermon.get('downloads', 0)}")
            print(f"  Date: {first_sermon.get('date', 'N/A')}")
            print(f"  Church: {first_sermon.get('church_name', 'N/A')}")
            
            # Show all available keys
            print(f"\n🔑 Available data fields: {list(first_sermon.keys())}")
            
            # Check for real vs mock data indicators
            mock_speakers = ['Pastor John Smith', 'Dr. Sarah Johnson', 'Rev. Michael Brown']
            if first_sermon.get('speaker') in mock_speakers:
                print("⚠️  WARNING: This appears to be MOCK data, not real church data!")
            else:
                print("✅ This appears to be REAL data from your church!")
        else:
            print("⚠️  No sermons returned. This could mean:")
            print("   1. No sermons are uploaded for this broadcaster")
            print("   2. The broadcaster ID is incorrect")
            print("   3. The sermons are private or restricted")
            print("   4. There's an API permission issue")
        
    except Exception as e:
        print(f"❌ API call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_sermonaudio_api()
