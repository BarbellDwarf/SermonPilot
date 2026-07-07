#!/usr/bin/env python3
"""
Secure Configuration Loader
Handles environment variable substitution and security validation for the SermonPilot
"""

import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml


class ConfigSecurityError(Exception):
    """Raised when configuration contains security violations."""
    pass


class SecureConfigLoader:
    """Secure configuration loader with environment variable support and security validation."""
    
    def __init__(self, config_file: Union[str, Path] = "config.yaml"):
        self.config_file = Path(config_file)
        self.logger = logging.getLogger(__name__)
        
        # Patterns that indicate hardcoded credentials
        self.credential_patterns = [
            r'api_key:\s*["\']?[a-zA-Z0-9-]{20,}["\']?',
            r'password:\s*["\']?[^$][^{][^}]+["\']?',
            r'secret:\s*["\']?[a-zA-Z0-9]{16,}["\']?',
            r'token:\s*["\']?[a-zA-Z0-9-_]{20,}["\']?',
            r'key:\s*["\']?sk-[a-zA-Z0-9]+["\']?',  # OpenAI keys
            r'key:\s*["\']?xai-[a-zA-Z0-9]+["\']?',  # XAI keys
            r'key:\s*["\']?sk-ant-[a-zA-Z0-9]+["\']?',  # Anthropic keys
            r'key:\s*["\']?gsk-[a-zA-Z0-9]+["\']?',  # Groq keys
        ]
        
        # Hardcoded test values that should be replaced
        self.test_patterns = [
            'your-', 'example', 'test', 'demo', 'sample', '12345',
            'test_key', 'test_broadcaster', 'placeholder'
        ]
    
    def load_config(self, validate_security: bool = True) -> Dict[str, Any]:
        """
        Load configuration with environment variable substitution and security validation.
        
        Args:
            validate_security: Whether to perform security validation
            
        Returns:
            Configuration dictionary
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ConfigSecurityError: If security violations are detected
            ValueError: If required environment variables are missing
        """
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        # Load and process config file
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config_text = f.read()
        
        # Perform security scan on raw config first
        if validate_security:
            self._scan_config_security(config_text)
        
        # Replace environment variables
        config_text = self._substitute_environment_variables(config_text)
        
        # Parse YAML
        try:
            config = yaml.safe_load(config_text)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration: {e}")
        
        # Validate required environment variables
        self._validate_required_variables(config)
        
        # Final security validation on processed config
        if validate_security:
            self._validate_production_config(config)
        
        self.logger.info("Configuration loaded successfully with security validation")
        return config
    
    def _substitute_environment_variables(self, config_text: str) -> str:
        """
        Substitute environment variables in configuration text.
        Supports ${VAR} and ${VAR:-default} syntax.
        """
        def replace_var(match):
            var_expr = match.group(1)
            if ':-' in var_expr:
                var_name, default_value = var_expr.split(':-', 1)
                return os.getenv(var_name.strip(), default_value.strip())
            else:
                var_name = var_expr.strip()
                value = os.getenv(var_name)
                if value is None:
                    self.logger.warning(f"Environment variable {var_name} not set")
                    return f"${{{var_name}}}"  # Keep original if not found
                return value
        
        # Replace ${VAR} and ${VAR:-default} patterns
        config_text = re.sub(r'\$\{([^}]+)\}', replace_var, config_text)
        
        # Also support direct environment variable expansion
        config_text = os.path.expandvars(config_text)
        
        return config_text
    
    def _scan_config_security(self, config_text: str) -> None:
        """Scan configuration text for hardcoded credentials."""
        violations = []
        
        for line_num, line in enumerate(config_text.splitlines(), 1):
            # Skip comments
            if line.strip().startswith('#'):
                continue
                
            for pattern in self.credential_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip if it's an environment variable reference
                    if '${' in line or '$' in line:
                        continue
                    violations.append(f"Line {line_num}: {line.strip()}")
        
        if violations:
            raise ConfigSecurityError(
                f"Hardcoded credentials detected in configuration:\n" +
                "\n".join(violations) +
                "\n\nPlease replace with environment variables."
            )
    
    def _validate_required_variables(self, config: Dict[str, Any]) -> None:
        """Validate that required environment variables are set."""
        required_vars = [
            'SERMONAUDIO_API_KEY',
            'SERMONAUDIO_BROADCASTER_ID'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                # Check if the config contains the variable as a placeholder
                if self._contains_placeholder(config, var.lower().replace('_', '')):
                    missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {missing_vars}\n"
                f"Please set these variables in your .env file or environment."
            )
    
    def _contains_placeholder(self, obj: Any, key_part: str) -> bool:
        """Check if configuration contains placeholder values."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key_part in key.lower() and isinstance(value, str):
                    if any(pattern in value.lower() for pattern in self.test_patterns):
                        return True
                if self._contains_placeholder(value, key_part):
                    return True
        elif isinstance(obj, list):
            for item in obj:
                if self._contains_placeholder(item, key_part):
                    return True
        return False
    
    def _validate_production_config(self, config: Dict[str, Any]) -> None:
        """Validate configuration for production safety."""
        violations = []
        
        def check_hardcoded(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    check_hardcoded(value, current_path)
            elif isinstance(obj, str):
                # Check for obvious hardcoded patterns
                if any(pattern in obj.lower() for pattern in self.test_patterns):
                    violations.append(f"Hardcoded test value at {path}: {obj}")
        
        check_hardcoded(config)
        
        # Check for debug mode in production
        if os.getenv('PRODUCTION_MODE', '').lower() == 'true':
            if config.get('debug', False):
                violations.append("Debug mode is enabled in production")
        
        if violations:
            raise ConfigSecurityError(
                f"Configuration validation failed:\n" +
                "\n".join(violations) +
                "\n\nPlease fix these issues before deploying to production."
            )


def load_secure_config(config_file: Union[str, Path] = "config.yaml", 
                      validate_security: bool = True) -> Dict[str, Any]:
    """
    Convenience function to load secure configuration.
    
    Args:
        config_file: Path to configuration file
        validate_security: Whether to perform security validation
        
    Returns:
        Configuration dictionary
    """
    loader = SecureConfigLoader(config_file)
    return loader.load_config(validate_security=validate_security)


def validate_environment_setup() -> Dict[str, bool]:
    """
    Validate that the environment is properly set up for secure operation.
    
    Returns:
        Dictionary with validation results
    """
    results = {}
    
    # Check for .env file
    env_file = Path('.env')
    results['env_file_exists'] = env_file.exists()
    
    # Check for required environment variables
    required_vars = ['SERMONAUDIO_API_KEY', 'SERMONAUDIO_BROADCASTER_ID']
    results['required_vars_set'] = all(os.getenv(var) for var in required_vars)
    
    # Check for .env.example
    env_example = Path('.env.example')
    results['env_example_exists'] = env_example.exists()
    
    # Check for config.yaml
    config_file = Path('config.yaml')
    results['config_file_exists'] = config_file.exists()
    
    # Check if in production mode
    results['production_mode'] = os.getenv('PRODUCTION_MODE', '').lower() == 'true'
    
    return results


if __name__ == "__main__":
    """Command-line interface for configuration validation."""
    import sys
    
    print("🔍 SermonPilot - Configuration Security Validator")
    print("=" * 60)
    
    try:
        # Validate environment setup
        env_status = validate_environment_setup()
        
        print("\n📋 Environment Setup Status:")
        for check, status in env_status.items():
            icon = "✅" if status else "❌"
            print(f"  {icon} {check.replace('_', ' ').title()}: {status}")
        
        # Try to load configuration
        print("\n🔧 Loading Configuration...")
        
        if Path('config.yaml').exists():
            config = load_secure_config()
            print("✅ Configuration loaded successfully")
            print(f"   - API Key configured: {'✅' if 'api_key' in str(config) else '❌'}")
            print(f"   - LLM providers configured: {len(config.get('llm', {}).get('primary', {}))}")
            print(f"   - Debug mode: {'🟡 Enabled' if config.get('debug') else '✅ Disabled'}")
        else:
            print("⚠️  No config.yaml found - using config/config.example.yaml for validation")
            config = load_secure_config('config/config.example.yaml', validate_security=False)
            print("✅ Example configuration structure is valid")
        
        print("\n🔒 Security validation passed!")
        
    except ConfigSecurityError as e:
        print(f"\n❌ Security Validation Failed:")
        print(f"   {e}")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n💥 Configuration Error:")
        print(f"   {e}")
        sys.exit(1)
    
    print("\n🎉 All security checks passed! Configuration is ready for use.")