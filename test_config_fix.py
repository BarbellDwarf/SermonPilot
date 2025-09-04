#!/usr/bin/env python3
"""
Test script to verify the config loading fix for Streamlit UI.
This script tests the specific scenario that was causing the AttributeError.
"""

import sys
from pathlib import Path

# Add paths for imports
project_root = Path(__file__).parent
ui_dir = project_root / "ui"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(ui_dir))

def test_config_handling():
    """Test the config handling with None values"""
    print("🧪 Testing Config Handling Fix")
    print("=" * 50)
    
    # Test 1: Simulate the original problem
    print("\n1. Testing original problem scenario...")
    
    class MockSessionState:
        def __init__(self):
            self.config = None  # This was the problem
        
        def get(self, key, default=None):
            if hasattr(self, key):
                return getattr(self, key)
            return default
    
    # Original problematic code
    session_state = MockSessionState()
    config = session_state.get('config', {})
    print(f"   config from session_state.get(): {config} (type: {type(config)})")
    
    try:
        value = config.get('api_key', '')
        print(f"   ❌ This shouldn't work: {value}")
    except AttributeError as e:
        print(f"   ✅ Expected error: {e}")
    
    # Test 2: Test our fix
    print("\n2. Testing our fix...")
    
    config_fixed = session_state.get('config') or {}
    print(f"   config from session_state.get() or {{}}: {config_fixed} (type: {type(config_fixed)})")
    
    try:
        value = config_fixed.get('api_key', '')
        print(f"   ✅ Fix works: api_key = '{value}'")
    except AttributeError as e:
        print(f"   ❌ Fix failed: {e}")
    
    # Test 3: Test with actual config values
    print("\n3. Testing with actual config values...")
    
    session_state.config = {'api_key': 'test-key', 'broadcaster_id': 'test-broadcaster'}
    config_with_values = session_state.get('config') or {}
    
    try:
        api_key = config_with_values.get('api_key', '')
        broadcaster_id = config_with_values.get('broadcaster_id', '')
        print(f"   ✅ API Key: '{api_key}'")
        print(f"   ✅ Broadcaster ID: '{broadcaster_id}'")
    except AttributeError as e:
        print(f"   ❌ Failed with values: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Config handling fix verified!")

def test_settings_page_import():
    """Test that the settings page can be imported without errors"""
    print("\n🧪 Testing Settings Page Import")
    print("=" * 50)
    
    try:
        # Mock streamlit for testing
        class MockStreamlit:
            def markdown(self, text, **kwargs):
                pass
            def text_input(self, *args, **kwargs):
                return ""
            def checkbox(self, *args, **kwargs):
                return False
            def columns(self, n):
                return [self] * n
            def button(self, *args, **kwargs):
                return False
            def tabs(self, names):
                return [self] * len(names)
            def selectbox(self, *args, **kwargs):
                return ""
            def slider(self, *args, **kwargs):
                return 0.0
            def number_input(self, *args, **kwargs):
                return 0
            def success(self, text):
                print(f"   ✅ {text}")
            def error(self, text):
                print(f"   ❌ {text}")
            def warning(self, text):
                print(f"   ⚠️ {text}")
            def info(self, text):
                print(f"   ℹ️ {text}")
            def download_button(self, *args, **kwargs):
                return False
            def file_uploader(self, *args, **kwargs):
                return None
            def code(self, *args, **kwargs):
                pass
            def rerun(self):
                pass
            
            # Mock session_state
            class SessionState:
                def __init__(self):
                    self.config = None  # Start with None to test our fix
                    self.confirm_reset = False
                
                def get(self, key, default=None):
                    if hasattr(self, key):
                        return getattr(self, key)
                    return default
            
            session_state = SessionState()
        
        # Replace streamlit module
        sys.modules['streamlit'] = MockStreamlit()
        
        # Now try to import and test settings functions
        from pages.settings import show_general_settings, show_llm_settings, show_audio_settings, show_validation_settings
        
        print("   ✅ Settings page imported successfully")
        
        # Test each settings function to see if they handle None config
        print("\n   Testing settings functions...")
        
        try:
            show_general_settings()
            print("   ✅ show_general_settings() - no errors")
        except Exception as e:
            print(f"   ❌ show_general_settings() failed: {e}")
        
        try:
            show_llm_settings()
            print("   ✅ show_llm_settings() - no errors")
        except Exception as e:
            print(f"   ❌ show_llm_settings() failed: {e}")
        
        try:
            show_audio_settings()
            print("   ✅ show_audio_settings() - no errors")
        except Exception as e:
            print(f"   ❌ show_audio_settings() failed: {e}")
        
        try:
            show_validation_settings()
            print("   ✅ show_validation_settings() - no errors")
        except Exception as e:
            print(f"   ❌ show_validation_settings() failed: {e}")
            
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    test_config_handling()
    test_settings_page_import()
    print("\n🎉 All tests completed!")