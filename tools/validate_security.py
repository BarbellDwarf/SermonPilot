#!/usr/bin/env python3
"""
Standalone security validation script
Validates security compliance without external dependencies
"""

import os
import re
import sys
import tempfile
from pathlib import Path


def test_config_example_uses_environment_variables():
    """Test that config.example.yaml uses environment variables."""
    config_file = Path(__file__).parent.parent / "config.example.yaml"
    if not config_file.exists():
        return False, "config.example.yaml not found"
    
    with open(config_file, 'r') as f:
        content = f.read()
    
    # Check that sensitive fields use environment variables
    sensitive_fields = ['api_key', 'broadcaster_id']
    violations = []
    
    for line_num, line in enumerate(content.splitlines(), 1):
        for field in sensitive_fields:
            if f'{field}:' in line and '${' not in line and not line.strip().startswith('#'):
                violations.append(f"Line {line_num}: {line.strip()}")
    
    if violations:
        return False, f"config.example.yaml contains hardcoded values:\n" + "\n".join(violations)
    
    return True, "All sensitive fields use environment variables"


def test_examples_config_security():
    """Test that examples_config.yaml has proper security warnings."""
    config_file = Path(__file__).parent.parent / "examples_config.yaml"
    if not config_file.exists():
        return False, "examples_config.yaml not found"
    
    with open(config_file, 'r') as f:
        content = f.read()
    
    # Check for security warning
    if "⚠️" not in content or "WARNING" not in content.upper():
        return False, "examples_config.yaml missing security warning"
    
    # Check that it uses environment variables
    if "${" not in content:
        return False, "examples_config.yaml not using environment variables"
    
    return True, "Examples config has proper security warnings and uses environment variables"


def test_env_example_exists():
    """Test that .env.example file exists and is comprehensive."""
    env_example = Path(__file__).parent.parent / ".env.example"
    if not env_example.exists():
        return False, ".env.example not found"
    
    with open(env_example, 'r') as f:
        content = f.read()
    
    # Check for required sections
    required_sections = [
        'SERMONAUDIO_API_KEY',
        'OPENAI_API_KEY',
        'XAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'GROQ_API_KEY'
    ]
    
    missing_sections = [section for section in required_sections if section not in content]
    
    if missing_sections:
        return False, f"Missing required environment variables in .env.example: {missing_sections}"
    
    return True, f".env.example contains all {len(required_sections)} required environment variables"


def test_security_tools_available():
    """Test that security tools are available."""
    tools_dir = Path(__file__).parent.parent / "tools"
    security_scanner = tools_dir / "security_scanner.py"
    
    if not security_scanner.exists():
        return False, "Security scanner not found"
    
    if not os.access(security_scanner, os.R_OK):
        return False, "Security scanner not readable"
    
    # Test that pre-commit hook exists
    precommit_hook = Path(__file__).parent.parent / ".githooks" / "pre-commit"
    if not precommit_hook.exists():
        return False, "Pre-commit hook not found"
    
    return True, "All security tools are available"


def test_test_fixtures_structure():
    """Test that test fixtures directory structure is proper."""
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures"
    
    if not fixtures_dir.exists():
        return False, "Test fixtures directory not found"
    
    required_subdirs = ['sample_audio', 'mock_configs', 'test_data']
    missing_dirs = [d for d in required_subdirs if not (fixtures_dir / d).exists()]
    
    if missing_dirs:
        return False, f"Missing fixture subdirectories: {missing_dirs}"
    
    # Check for README
    readme = fixtures_dir / "README.md"
    if not readme.exists():
        return False, "Test fixtures README.md not found"
    
    return True, f"Test fixtures structure complete with {len(required_subdirs)} subdirectories"


def main():
    """Run all security validation tests."""
    print("🔒 SermonAudio Processor - Security Validation")
    print("=" * 60)
    
    tests = [
        ("Environment Variables in Config", test_config_example_uses_environment_variables),
        ("Examples Config Security", test_examples_config_security),
        (".env.example Completeness", test_env_example_exists),
        ("Security Tools Available", test_security_tools_available),
        ("Test Fixtures Structure", test_test_fixtures_structure),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            success, message = test_func()
            if success:
                print(f"✅ {test_name}: {message}")
                passed += 1
            else:
                print(f"❌ {test_name}: {message}")
                failed += 1
        except Exception as e:
            print(f"💥 {test_name}: Error - {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Results: {passed} passed, {failed} failed")
    
    if failed > 0:
        print("\n🔧 Actions needed to fix failures:")
        print("1. Ensure all config files use environment variables")
        print("2. Add security warnings to example files")
        print("3. Complete .env.example with all required variables")
        print("4. Set up security tools and test structure")
        return 1
    else:
        print("\n🎉 All security validations passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())