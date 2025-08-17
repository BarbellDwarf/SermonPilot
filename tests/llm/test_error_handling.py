#!/usr/bin/env python3
"""Test script for LLM error handling with invalid models and endpoints."""

import yaml
# Add src directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_manager import LLMManager

def test_invalid_model():
    """Test with an invalid model name."""
    config = {
        'llm': {
            'primary': {
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://localhost:11434',
                    'model': 'nonexistent-model-12345'
                }
            },
            'fallback': {
                'enabled': True,
                'provider': 'openai',
                'openai': {
                    'api_key': 'test-key',
                    'model': 'nonexistent-openai-model'
                }
            }
        }
    }
    
    manager = LLMManager(config)
    
    try:
        response = manager.chat([
            {"role": "user", "content": "Hello, how are you?"}
        ])
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")

def test_invalid_endpoint():
    """Test with an invalid endpoint."""
    config = {
        'llm': {
            'primary': {
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://localhost:99999',  # Invalid port
                    'model': 'llama3'
                }
            },
            'fallback': {
                'enabled': True,
                'provider': 'openai',
                'openai': {
                    'api_key': 'test-key',
                    'model': 'gpt-3.5-turbo'
                }
            }
        }
    }
    
    manager = LLMManager(config)
    
    try:
        response = manager.chat([
            {"role": "user", "content": "Hello, how are you?"}
        ])
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Testing invalid model handling...")
    test_invalid_model()
    
    print("\nTesting invalid endpoint handling...")
    test_invalid_endpoint()
