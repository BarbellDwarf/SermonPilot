#!/usr/bin/env python3
"""Test script for LLM fallback functionality."""

from llm_manager import LLMManager

def test_valid_model():
    """Test with a valid model name to make sure normal operation works."""
    config = {
        'llm': {
            'primary': {
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://localhost:11434',
                    'model': 'llama3.1:8b'  # Using a model that exists
                }
            },
            'fallback': {
                'enabled': False  # Disable fallback for this test
            }
        }
    }
    
    manager = LLMManager(config)
    
    try:
        response = manager.chat([
            {"role": "user", "content": "What is 2+2? Answer with just the number."}
        ])
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_fallback():
    """Test fallback from invalid endpoint to valid one."""
    config = {
        'llm': {
            'primary': {
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://localhost:99999',  # Invalid port
                    'model': 'llama3.1:8b'
                }
            },
            'fallback': {
                'enabled': True,
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://localhost:11434',  # Valid endpoint
                    'model': 'llama3.1:8b'
                }
            }
        }
    }
    
    manager = LLMManager(config)
    
    try:
        response = manager.chat([
            {"role": "user", "content": "What is 3+3? Answer with just the number."}
        ])
        print(f"Response (from fallback): {response}")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("Testing valid model operation...")
    if test_valid_model():
        print("✓ Valid model test passed")
    else:
        print("✗ Valid model test failed")
    
    print("\nTesting fallback functionality...")
    if test_fallback():
        print("✓ Fallback test passed")
    else:
        print("✗ Fallback test failed")
