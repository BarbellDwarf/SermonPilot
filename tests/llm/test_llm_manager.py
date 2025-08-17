#!/usr/bin/env python3
"""
Test script for LLM Manager functionality.
This script tests the LLM configuration and switching functionality.
"""

import yaml
# Add src directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_manager import LLMManager, migrate_legacy_config

def test_llm_configuration():
    """Test the LLM configuration and provider switching."""
    
    # Load current configuration
    print("Loading configuration...")
    with open('config.yaml') as f:
        config = yaml.safe_load(f)
    
    # Migrate legacy config if needed
    print("Migrating legacy configuration if needed...")
    config = migrate_legacy_config(config)
    
    # Create LLM manager
    print("Creating LLM manager...")
    try:
        llm_manager = LLMManager(config)
        print("✅ LLM manager created successfully")
    except Exception as e:
        print(f"❌ Failed to create LLM manager: {e}")
        return False
    
    # Get provider information
    provider_info = llm_manager.get_provider_info()
    print("\n📊 Provider Information:")
    print(f"Primary provider: {provider_info.get('primary')}")
    print(f"Fallback provider: {provider_info.get('fallback')}")
    
    # Test a simple chat request
    print("\n🧪 Testing LLM functionality...")
    test_message = [{'role': 'user', 'content': 'Say "Hello, this is a test response!" and nothing else.'}]
    
    try:
        response = llm_manager.chat(test_message)
        print(f"✅ LLM response: {response}")
        return True
    except Exception as e:
        print(f"❌ LLM test failed: {e}")
        return False

def test_config_switching():
    """Test switching between different provider configurations."""
    
    print("\n🔄 Testing configuration switching...")
    
    # Test configuration with different primary providers
    test_configs = [
        {
            'llm': {
                'primary': {
                    'provider': 'ollama',
                    'ollama': {
                        'host': 'http://192.168.75.12:11434',
                        'model': 'llama3.1:8b'
                    }
                },
                'fallback': {
                    'enabled': True,
                    'provider': 'openai',
                    'openai': {
                        'api_key': 'sk-test-key',
                        'model': 'gpt-3.5-turbo'
                    }
                }
            }
        },
        {
            'llm': {
                'primary': {
                    'provider': 'openai',
                    'openai': {
                        'api_key': 'sk-test-key',
                        'model': 'gpt-4o'
                    }
                },
                'fallback': {
                    'enabled': True,
                    'provider': 'ollama',
                    'ollama': {
                        'host': 'http://192.168.75.12:11434',
                        'model': 'llama3.1:8b'
                    }
                }
            }
        }
    ]
    
    for i, test_config in enumerate(test_configs, 1):
        print(f"\n--- Test Configuration {i} ---")
        try:
            llm_manager = LLMManager(test_config)
            provider_info = llm_manager.get_provider_info()
            primary_type = provider_info.get('primary', {}).get('type', 'unknown')
            fallback_type = provider_info.get('fallback', {}).get('type', 'unknown')
            print(f"✅ Primary: {primary_type}, Fallback: {fallback_type}")
        except Exception as e:
            print(f"❌ Configuration {i} failed: {e}")

if __name__ == "__main__":
    print("🚀 LLM Manager Test Suite")
    print("=" * 50)
    
    # Test main functionality
    success = test_llm_configuration()
    
    # Test configuration switching
    test_config_switching()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ LLM Manager tests completed successfully!")
        print("\n💡 You can now switch between providers by editing config.yaml:")
        print("   - Change llm.primary.provider to 'ollama' or 'openai'")
        print("   - Change llm.fallback.provider to enable different fallback")
        print("   - Update the respective host/model/api_key settings as needed")
    else:
        print("❌ Some tests failed. Please check your configuration.")
