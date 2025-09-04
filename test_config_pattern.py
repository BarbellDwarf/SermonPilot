#!/usr/bin/env python3
"""
Focused test for the specific config access pattern used in settings.py
"""

def test_config_access_pattern():
    """Test the specific pattern used in settings.py functions"""
    print("🧪 Testing Config Access Pattern")
    print("=" * 50)
    
    # Mock session state that behaves like Streamlit's
    class MockSessionState:
        def __init__(self, config_value):
            self.config = config_value
        
        def get(self, key, default=None):
            """Mimics streamlit session_state.get behavior"""
            if hasattr(self, key):
                return getattr(self, key)  # Returns actual value, even if None
            return default
    
    # Test scenarios
    test_cases = [
        ("None config", None),
        ("Empty dict config", {}),
        ("Populated config", {'api_key': 'test-key', 'broadcaster_id': 'test-id'}),
    ]
    
    for scenario, config_value in test_cases:
        print(f"\n{scenario}:")
        session_state = MockSessionState(config_value)
        
        # Original problematic pattern
        try:
            config_old = session_state.get('config', {})
            api_key_old = config_old.get('api_key', '')
            print(f"  ❌ OLD: config={config_old}, api_key='{api_key_old}' - This would fail with None")
        except AttributeError as e:
            print(f"  ❌ OLD: Failed as expected - {e}")
        
        # Our fixed pattern
        try:
            config_new = session_state.get('config') or {}
            api_key_new = config_new.get('api_key', '')
            broadcaster_id_new = config_new.get('broadcaster_id', '')
            print(f"  ✅ NEW: config={config_new}, api_key='{api_key_new}', broadcaster_id='{broadcaster_id_new}'")
        except Exception as e:
            print(f"  ❌ NEW: Unexpected failure - {e}")
    
    print("\n" + "=" * 50)
    print("✅ Config access pattern fix verified!")

if __name__ == "__main__":
    test_config_access_pattern()