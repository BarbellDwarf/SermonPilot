#!/usr/bin/env python3
"""
Test script to verify debug functionality works correctly.
"""
import yaml

# Load config and test debug functionality
with open('config.yaml') as f:
    config = yaml.safe_load(f)

DEBUG = config.get('debug', False)

def debug_print(message):
    """Print debug message only if debug mode is enabled."""
    if DEBUG:
        print(f"[DEBUG] {message}")

# Test the debug functionality
print("Testing debug functionality...")
print(f"Debug mode enabled: {DEBUG}")

debug_print("This is a debug message that should only show when debug=true")
print("This is a regular message that always shows")

debug_print("Another debug message")
print("Another regular message")

# Simulate changing debug mode
print("\nTesting with debug enabled:")
DEBUG = True
debug_print("This debug message should now show")
print("Regular message still shows")

print("\nTesting with debug disabled:")
DEBUG = False
debug_print("This debug message should NOT show")
print("Regular message still shows")

print("\nDebug functionality test complete!")
