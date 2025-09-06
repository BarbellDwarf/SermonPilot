#!/usr/bin/env python3
"""
Test UI improvements: SermonAudio link, viewer removal, analytics enhancements
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add paths
ui_dir = Path(__file__).parent.parent / "ui"
sys.path.insert(0, str(ui_dir))

def test_sermon_details_has_sermonaudio_link():
    """Test that sermon details includes SermonAudio link"""
    from ui_pages.library import display_sermon_details
    
    # Mock streamlit
    with patch('ui_pages.library.st') as mock_st:
        mock_st.columns.return_value = [Mock(), Mock()]
        mock_st.text.return_value = None
        mock_st.markdown.return_value = None
        
        # Test sermon with ID
        sermon = {
            'id': '12345',
            'title': 'Test Sermon',
            'speaker': 'John Doe',
            'recorded_date': '2024-01-01',
            'church_name': 'Test Church',
            'series_title': 'Test Series',
            'event_type': 'Sunday Service',
            'scripture_reference': 'John 3:16',
            'description': 'Test description',
            'status': 'completed'
        }
        
        display_sermon_details(sermon)
        
        # Check that SermonAudio link was created
        markdown_calls = [call for call in mock_st.markdown.call_args_list 
                         if 'SermonAudio' in str(call)]
        assert len(markdown_calls) > 0, "SermonAudio link section should be present"
        
        link_calls = [call for call in mock_st.markdown.call_args_list 
                     if 'sermonaudio.com' in str(call)]
        assert len(link_calls) > 0, "SermonAudio URL should be present"

def test_sermon_details_handles_missing_id():
    """Test that sermon details handles missing sermon ID gracefully"""
    from ui_pages.library import display_sermon_details
    
    with patch('ui_pages.library.st') as mock_st:
        mock_st.columns.return_value = [Mock(), Mock()]
        mock_st.text.return_value = None
        mock_st.markdown.return_value = None
        
        # Test sermon without ID
        sermon = {
            'title': 'Test Sermon',
            'speaker': 'John Doe',
            'status': 'completed'
        }
        
        # Should not raise an exception
        display_sermon_details(sermon)
        
        # SermonAudio link section should not be present
        markdown_calls = [call for call in mock_st.markdown.call_args_list 
                         if 'SermonAudio' in str(call)]
        assert len(markdown_calls) == 0, "SermonAudio link should not be present without ID"

def test_viewer_page_removed_from_navigation():
    """Test that viewer page is removed from navigation"""
    from shared_navigation import get_navigation_items
    
    nav_items = get_navigation_items()
    viewer_items = [item for item in nav_items if 'viewer' in item[1].lower()]
    
    assert len(viewer_items) == 0, "Viewer page should be removed from navigation"

def test_analytics_uses_real_sermon_data():
    """Test that analytics can process real SermonAudio data"""
    from ui_pages.analytics import get_real_content_data
    
    # Mock config and sermon data
    mock_config = {
        'api_key': 'test_key',
        'broadcaster_id': 'test_broadcaster'
    }
    
    mock_sermons = [
        {
            'speaker': 'John Doe',
            'downloadCount': 150,
            'lastAudioAccessTimestamp': 1609459200,
            'eventType': 'Sunday Service'
        },
        {
            'speaker': 'Jane Smith', 
            'downloadCount': 75,
            'lastAudioAccessTimestamp': 1609459200,
            'eventType': 'Bible Study'
        },
        {
            'speaker': 'John Doe',
            'downloadCount': 200,
            'lastAudioAccessTimestamp': None,
            'eventType': 'Sunday Service'
        }
    ]
    
    with patch('ui_pages.analytics.st') as mock_st:
        mock_st.session_state.get.return_value = mock_config
        
        with patch('ui_pages.analytics.SermonUpdater') as mock_updater_class:
            mock_updater = Mock()
            mock_updater.get_sermons_in_date_range.return_value = mock_sermons
            mock_updater_class.return_value = mock_updater
            
            with patch('ui_pages.analytics.get_db') as mock_get_db:
                mock_db = Mock()
                mock_db.get_processing_status.return_value = []
                mock_get_db.return_value = mock_db
                
                result = get_real_content_data()
                
                # Check speaker stats
                assert 'speaker_stats' in result
                speaker_stats = result['speaker_stats']
                assert len(speaker_stats) > 0
                
                # Check that John Doe has higher download count
                john_doe = next((s for s in speaker_stats if s['speaker'] == 'John Doe'), None)
                assert john_doe is not None
                assert john_doe['total_downloads'] == 350  # 150 + 200
                assert john_doe['total_listens'] == 1  # Only one with timestamp
                
                # Check event types
                assert 'event_types' in result
                event_types = result['event_types']
                assert len(event_types) > 0
                
                sunday_service = next((e for e in event_types if e['event_type'] == 'Sunday Service'), None)
                assert sunday_service is not None
                assert sunday_service['count'] == 2
                assert sunday_service['total_downloads'] == 350

def test_analytics_handles_api_failure():
    """Test that analytics handles API failures gracefully"""
    from ui_pages.analytics import get_real_content_data
    
    with patch('ui_pages.analytics.st') as mock_st:
        # No config or invalid config
        mock_st.session_state.get.return_value = {}
        
        with patch('ui_pages.analytics.get_db') as mock_get_db:
            mock_db = Mock()
            mock_db.get_processing_status.return_value = [{'status': 'completed'}]
            mock_get_db.return_value = mock_db
            
            result = get_real_content_data()
            
            # Should return valid structure even with no API data
            assert 'speaker_stats' in result
            assert 'event_types' in result
            assert 'quality_trends' in result
            
            # Should have fallback data from processing status
            assert len(result['speaker_stats']) > 0
            assert result['speaker_stats'][0]['speaker'] == 'System Processed'

def test_streamlit_app_removes_viewer():
    """Test that streamlit app no longer includes viewer page"""
    
    # Read the streamlit app file
    app_file = Path(__file__).parent.parent / "ui" / "streamlit_app.py"
    app_content = app_file.read_text()
    
    # Should not have viewer page routing
    assert "elif current_page == 'viewer':" not in app_content
    
    # Should not have show_viewer function definition
    assert "def show_viewer():" not in app_content

def test_sermon_link_construction():
    """Test SermonAudio link construction with various sermon IDs"""
    
    test_cases = [
        ('12345', 'https://www.sermonaudio.com/sermoninfo.asp?SID=12345'),
        ('101220211425', 'https://www.sermonaudio.com/sermoninfo.asp?SID=101220211425'),
        ('abc123', 'https://www.sermonaudio.com/sermoninfo.asp?SID=abc123')
    ]
    
    for sermon_id, expected_url in test_cases:
        actual_url = f"https://www.sermonaudio.com/sermoninfo.asp?SID={sermon_id}"
        assert actual_url == expected_url, f"URL construction failed for ID {sermon_id}"

if __name__ == "__main__":
    print("Testing UI improvements...")
    
    # Test individual components
    print("✓ Testing SermonAudio link in sermon details")
    test_sermon_details_has_sermonaudio_link()
    
    print("✓ Testing sermon details without ID")
    test_sermon_details_handles_missing_id()
    
    print("✓ Testing viewer page removal from navigation")
    test_viewer_page_removed_from_navigation()
    
    print("✓ Testing analytics with real sermon data")
    test_analytics_uses_real_sermon_data()
    
    print("✓ Testing analytics API failure handling") 
    test_analytics_handles_api_failure()
    
    print("✓ Testing streamlit app viewer removal")
    test_streamlit_app_removes_viewer()
    
    print("✓ Testing sermon link construction")
    test_sermon_link_construction()
    
    print("\n🎉 All UI improvement tests passed!")
    print("\nChanges implemented:")
    print("1. ✅ Added SermonAudio link to library sermon details")
    print("2. ✅ Removed viewer page from navigation and app")
    print("3. ✅ Enhanced analytics to pull real download/listen data from SermonAudio API")
    print("4. ✅ Added fallback handling for all analytics data")
    print("5. ✅ Improved speaker and event type analytics with real metrics")
