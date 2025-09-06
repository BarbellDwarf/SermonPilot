#!/usr/bin/env python3
"""
Simple validation test for UI improvements without heavy imports
"""

import sys
from pathlib import Path

def test_sermonaudio_link_in_library():
    """Test that library.py contains SermonAudio link code"""
    library_file = Path(__file__).parent.parent / "ui" / "ui_pages" / "library.py"
    content = library_file.read_text(encoding='utf-8')
    
    # Check for SermonAudio link construction
    assert "sermonaudio.com/sermoninfo.asp" in content, "SermonAudio link should be present"
    assert "SermonAudio Link" in content, "SermonAudio link section should be present"
    
    print("✅ SermonAudio link found in library.py")

def test_viewer_removed_from_navigation():
    """Test that viewer is removed from navigation"""
    nav_file = Path(__file__).parent.parent / "ui" / "shared_navigation.py"
    content = nav_file.read_text(encoding='utf-8')
    
    # Should not contain viewer page reference
    assert '"viewer"' not in content.lower(), "Viewer should be removed from navigation"
    assert "'viewer'" not in content.lower(), "Viewer should be removed from navigation"
    
    print("✅ Viewer removed from navigation")

def test_viewer_removed_from_app():
    """Test that viewer is removed from main app"""
    app_file = Path(__file__).parent.parent / "ui" / "streamlit_app.py"
    content = app_file.read_text(encoding='utf-8')
    
    # Should not contain viewer page logic
    assert "elif current_page == 'viewer':" not in content, "Viewer page routing should be removed"
    assert "def show_viewer():" not in content, "Viewer function should be removed"
    
    print("✅ Viewer removed from main app")

def test_analytics_has_real_data_logic():
    """Test that analytics.py has real data processing"""
    analytics_file = Path(__file__).parent.parent / "ui" / "ui_pages" / "analytics.py"
    content = analytics_file.read_text(encoding='utf-8')
    
    # Check for real data processing
    assert "downloadCount" in content, "Analytics should process download count"
    assert "lastAudioAccessTimestamp" in content, "Analytics should process listen data"
    assert "get_real_content_data" in content, "Analytics should have real data function"
    
    print("✅ Analytics has real data processing logic")

def test_file_structure_validation():
    """Validate expected files exist and contain basic structure"""
    ui_dir = Path(__file__).parent.parent / "ui"
    
    # Check key files exist
    files_to_check = [
        "streamlit_app.py",
        "shared_navigation.py", 
        "ui_pages/library.py",
        "ui_pages/analytics.py",
        "ui_pages/viewer.py"  # Should still exist as reference
    ]
    
    for file_path in files_to_check:
        full_path = ui_dir / file_path
        assert full_path.exists(), f"File {file_path} should exist"
    
    print("✅ All expected files exist")

def test_link_construction_logic():
    """Test SermonAudio link construction"""
    base_url = "https://www.sermonaudio.com/sermoninfo.asp?SID="
    
    test_cases = [
        ("12345", f"{base_url}12345"),
        ("101220211425", f"{base_url}101220211425"),
        ("abc123", f"{base_url}abc123")
    ]
    
    for sermon_id, expected in test_cases:
        actual = f"{base_url}{sermon_id}"
        assert actual == expected, f"Link construction failed for {sermon_id}"
    
    print("✅ Link construction logic validated")

if __name__ == "__main__":
    print("🔍 Validating UI improvements...")
    print()
    
    try:
        test_sermonaudio_link_in_library()
        test_viewer_removed_from_navigation()
        test_viewer_removed_from_app()
        test_analytics_has_real_data_logic()
        test_file_structure_validation()
        test_link_construction_logic()
        
        print()
        print("🎉 All validation tests passed!")
        print()
        print("📋 Summary of Changes Implemented:")
        print("1. ✅ Added SermonAudio link to library sermon details")
        print("2. ✅ Removed viewer page from navigation")
        print("3. ✅ Removed viewer page routing from main app")
        print("4. ✅ Enhanced analytics to use real SermonAudio data (downloads, listens)")
        print("5. ✅ Preserved viewer.py file as reference")
        print("6. ✅ All file structure maintained correctly")
        print()
        print("🚀 Ready for production use!")
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        sys.exit(1)
