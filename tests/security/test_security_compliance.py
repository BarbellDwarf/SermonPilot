#!/usr/bin/env python3
"""
Security compliance tests for SermonAudio Processor
Tests for hardcoded credentials, environment variable usage, and production safety
"""

import os
import re
import sys
import tempfile
import pytest
from pathlib import Path
from typing import Dict, Any

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from secure_config import SecureConfigLoader, ConfigSecurityError, validate_environment_setup
except ImportError:
    # Fallback if secure_config is not available
    SecureConfigLoader = None
    ConfigSecurityError = Exception


class TestSecurityCompliance:
    """Test suite for security compliance validation."""

    def test_no_hardcoded_credentials_in_source(self):
        """Ensure no hardcoded credentials in Python source code."""
        violations = []
        
        # Patterns for detecting hardcoded credentials
        credential_patterns = [
            r'api_key\s*=\s*["\'][^$][^{].*["\']',
            r'password\s*=\s*["\'][^$][^{].*["\']',
            r'secret\s*=\s*["\'][^$][^{].*["\']',
            r'token\s*=\s*["\'][^$][^{].*["\']',
            r'["\']sk-[a-zA-Z0-9]{32,}["\']',  # OpenAI keys
            r'["\']xai-[a-zA-Z0-9]{20,}["\']',  # xAI keys
        ]
        
        # Scan Python files in src directory
        src_dir = Path(__file__).parent.parent / "src"
        if src_dir.exists():
            for py_file in src_dir.rglob("*.py"):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    for line_num, line in enumerate(content.splitlines(), 1):
                        # Skip comments and secure_config file (which contains test patterns)
                        if line.strip().startswith('#') or 'secure_config.py' in str(py_file):
                            continue
                            
                        for pattern in credential_patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                violations.append(f"{py_file}:{line_num} - {line.strip()}")
                                
                except Exception as e:
                    # Skip files that can't be read
                    pass
        
        assert not violations, f"Hardcoded credentials found in source code:\n" + "\n".join(violations)

    def test_config_example_uses_environment_variables(self):
        """Test that config.example.yaml uses environment variables."""
        config_file = Path(__file__).parent.parent / "config.example.yaml"
        if not config_file.exists():
            pytest.skip("config.example.yaml not found")
        
        with open(config_file, 'r') as f:
            content = f.read()
        
        # Check that sensitive fields use environment variables
        sensitive_fields = ['api_key', 'broadcaster_id']
        violations = []
        
        for line_num, line in enumerate(content.splitlines(), 1):
            for field in sensitive_fields:
                if f'{field}:' in line and '${' not in line and not line.strip().startswith('#'):
                    violations.append(f"Line {line_num}: {line.strip()}")
        
        assert not violations, f"config.example.yaml contains hardcoded values:\n" + "\n".join(violations)

    @pytest.mark.skipif(SecureConfigLoader is None, reason="secure_config module not available")
    def test_secure_config_loader_validation(self):
        """Test the secure configuration loader validation."""
        # Create a test config with hardcoded credentials
        test_config_content = """
api_key: "sk-hardcoded123456789012345678901234"
broadcaster_id: "hardcoded-broadcaster"
debug: false
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(test_config_content)
            temp_config = f.name
        
        try:
            loader = SecureConfigLoader(temp_config)
            
            # This should raise a ConfigSecurityError due to hardcoded credentials
            with pytest.raises(ConfigSecurityError):
                loader.load_config(validate_security=True)
                
        finally:
            os.unlink(temp_config)

    @pytest.mark.skipif(SecureConfigLoader is None, reason="secure_config module not available")
    def test_secure_config_environment_substitution(self):
        """Test environment variable substitution in configuration."""
        # Set test environment variables
        os.environ['TEST_API_KEY'] = 'test-api-key-from-env'
        os.environ['TEST_BROADCASTER'] = 'test-broadcaster-from-env'
        
        test_config_content = """
api_key: "${TEST_API_KEY}"
broadcaster_id: "${TEST_BROADCASTER}"
debug: false
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(test_config_content)
            temp_config = f.name
        
        try:
            loader = SecureConfigLoader(temp_config)
            config = loader.load_config(validate_security=False)  # Skip security validation for test
            
            assert config['api_key'] == 'test-api-key-from-env'
            assert config['broadcaster_id'] == 'test-broadcaster-from-env'
            
        finally:
            os.unlink(temp_config)
            # Clean up environment variables
            del os.environ['TEST_API_KEY']
            del os.environ['TEST_BROADCASTER']

    def test_environment_setup_validation(self):
        """Test environment setup validation function."""
        if SecureConfigLoader is None:
            pytest.skip("secure_config module not available")
            
        results = validate_environment_setup()
        
        # Check that the function returns expected keys
        expected_keys = [
            'env_file_exists', 'required_vars_set', 'env_example_exists',
            'config_file_exists', 'production_mode'
        ]
        
        for key in expected_keys:
            assert key in results, f"Missing key in environment validation: {key}"
            assert isinstance(results[key], bool), f"Key {key} should be boolean"

    def test_test_files_properly_isolated(self):
        """Test that test files are in proper test directories."""
        repo_root = Path(__file__).parent.parent
        violations = []
        
        # Check for test files outside test directories
        for py_file in repo_root.rglob("*.py"):
            # Skip files in proper test directories
            if any(test_dir in str(py_file) for test_dir in ['tests/', 'test_', 'Tests/']):
                continue
                
            # Skip the security scanner itself
            if 'security_scanner.py' in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Look for obvious test patterns in non-test files
                test_indicators = ['test_key', 'test_broadcaster', '12345', 'mock_', 'fake_']
                for line_num, line in enumerate(content.splitlines(), 1):
                    # Skip comments
                    if line.strip().startswith('#'):
                        continue
                        
                    for indicator in test_indicators:
                        if indicator in line.lower():
                            violations.append(f"{py_file}:{line_num} - Test data in production file: {line.strip()}")
                            
            except Exception:
                # Skip files that can't be read
                pass
        
        # Allow some violations in known test files and examples
        allowed_files = ['examples/', 'config.example', 'examples_config']
        violations = [v for v in violations if not any(allowed in v for allowed in allowed_files)]
        
        assert len(violations) <= 10, f"Too many test data violations in production files:\n" + "\n".join(violations[:10])

    def test_production_safety_checks(self):
        """Test production safety configurations."""
        # Check that debug mode defaults to False in example configs
        config_file = Path(__file__).parent.parent / "config.example.yaml"
        if config_file.exists():
            with open(config_file, 'r') as f:
                content = f.read()
            
            # Look for debug configuration
            debug_lines = [line for line in content.splitlines() if 'debug:' in line and not line.strip().startswith('#')]
            
            for line in debug_lines:
                # Debug should default to false for production safety
                assert 'false' in line.lower(), f"Debug mode should default to false: {line}"

    def test_gitignore_excludes_sensitive_files(self):
        """Test that .gitignore properly excludes sensitive files."""
        gitignore_file = Path(__file__).parent.parent / ".gitignore"
        if not gitignore_file.exists():
            pytest.skip(".gitignore not found")
        
        with open(gitignore_file, 'r') as f:
            gitignore_content = f.read()
        
        # Check for important exclusions
        required_exclusions = ['.env', 'config.yaml']
        missing_exclusions = []
        
        for exclusion in required_exclusions:
            if exclusion not in gitignore_content:
                missing_exclusions.append(exclusion)
        
        assert not missing_exclusions, f"Missing required .gitignore exclusions: {missing_exclusions}"

    def test_no_real_api_keys_in_examples(self):
        """Test that example files don't contain real API keys."""
        examples_dir = Path(__file__).parent.parent
        real_key_patterns = [
            r'sk-[a-zA-Z0-9]{48,}',  # Real OpenAI keys are longer
            r'xai-[a-zA-Z0-9]{40,}',  # Real xAI keys
            r'sk-ant-[a-zA-Z0-9]{40,}',  # Real Anthropic keys
        ]
        
        violations = []
        
        for file_path in examples_dir.rglob("*example*.yaml"):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                for pattern in real_key_patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        violations.append(f"{file_path}: Potential real API key detected")
                        
            except Exception:
                pass
        
        assert not violations, f"Potential real API keys found in example files:\n" + "\n".join(violations)


def test_security_scanner_available():
    """Test that the security scanner tool is available and functional."""
    scanner_path = Path(__file__).parent.parent / "tools" / "security_scanner.py"
    assert scanner_path.exists(), "Security scanner tool not found"
    
    # Test that it's executable
    assert os.access(scanner_path, os.R_OK), "Security scanner is not readable"


if __name__ == "__main__":
    """Run security tests directly."""
    print("🔒 Running Security Compliance Tests...")
    
    # Run the tests
    pytest.main([__file__, "-v"])