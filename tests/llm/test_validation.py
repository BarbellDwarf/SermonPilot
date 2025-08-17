#!/usr/bin/env python3
"""Test script for the description validation functionality."""

import yaml
# Add src directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_manager import LLMManager

def test_validation():
    """Test the description validation system."""
    
    # Sample config with validator enabled
    config = {
        'llm': {
            'primary': {
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://192.168.75.12:11434',
                    'model': 'phi3:14b'
                }
            },
            'fallback': {
                'enabled': True,
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://192.168.75.12:11434',
                    'model': 'gemma3:12b'
                }
            },
            'validator': {
                'enabled': True,
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://192.168.75.12:11434',
                    'model': 'gemma2:2b'
                }
            }
        }
    }
    
    manager = LLMManager(config)
    
    # Test validation criteria
    criteria = [
        "Contains specific theological content or Bible references",
        "Mentions the speaker's main message or key points", 
        "Is written in a professional, engaging style",
        "Avoids generic Christian phrases without substance",
        "Has clear application or takeaway for listeners"
    ]
    
    # Test with a good description
    good_description = """
    Mark Hogan teaches from Romans 8:28 about God's sovereignty in all circumstances. 
    He explains how believers can trust that God works all things together for good 
    for those who love Him and are called according to His purpose. Hogan emphasizes 
    that this doesn't mean all things are good, but that God can use even difficult 
    circumstances to accomplish His purposes in our lives. The sermon challenges 
    listeners to surrender their worries to God and trust His perfect plan.
    """
    
    # Test with a poor description
    poor_description = """
    This was a great sermon about faith and hope. The pastor talked about God's love 
    and how we should trust Him. It was very encouraging and inspiring for everyone 
    who attended. We learned about being good Christians and following Jesus.
    """
    
    print("Testing description validation...")
    
    # Test good description
    is_valid, reason = manager.validate_description(good_description.strip(), criteria)
    print(f"\nGood description validation:")
    print(f"Valid: {is_valid}")
    print(f"Reason: {reason}")
    
    # Test poor description
    is_valid, reason = manager.validate_description(poor_description.strip(), criteria)
    print(f"\nPoor description validation:")
    print(f"Valid: {is_valid}")
    print(f"Reason: {reason}")
    
    # Test provider info
    provider_info = manager.get_provider_info()
    print(f"\nProvider information:")
    for key, info in provider_info.items():
        if info:
            print(f"  {key.title()}: {info['type']}/{info['model']}")

if __name__ == "__main__":
    test_validation()
