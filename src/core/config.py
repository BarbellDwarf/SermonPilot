"""
Configuration Management Module

Extracted from sermon_updater.py to reduce complexity.
Handles configuration loading, validation, and environment variable overrides.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading and validation for SermonAudio Processor."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self._config = {}
        self._load_config()

    def _find_config_file(self) -> str:
        """Find configuration file in standard locations."""
        # Check environment variable first
        env_config = os.getenv('SA_UPDATER_CONFIG')
        if env_config and Path(env_config).exists():
            return env_config
            
        # Standard search paths
        search_paths = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path.home() / ".sermon-processor" / "config.yaml",
            Path("/etc/sermon-processor/config.yaml")
        ]

        for path in search_paths:
            if path.exists():
                return str(path)

        return "config.yaml"  # Default fallback

    def _load_config(self):
        """Load configuration from file and environment."""
        # Load from YAML file
        if Path(self.config_path).exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info(f"Configuration loaded from {self.config_path}")
            except (yaml.YAMLError, IOError) as e:
                logger.error(f"Failed to load config from {self.config_path}: {e}")
                self._config = {}
        else:
            logger.warning(f"Configuration file not found: {self.config_path}")
            self._config = {}

        # Override with environment variables
        self._override_from_env()
        
        # Apply legacy config migration if needed
        self._migrate_legacy_config()

    def _override_from_env(self):
        """Override configuration with environment variables."""
        env_mappings = {
            'SERMONAUDIO_API_KEY': ['api_key'],
            'SERMONAUDIO_BROADCASTER_ID': ['broadcaster_id'],
            'OPENAI_API_KEY': ['llm', 'primary', 'openai', 'api_key'],
            'OLLAMA_HOST': ['llm', 'primary', 'ollama', 'host'],
            'OLLAMA_MODEL': ['llm', 'primary', 'ollama', 'model'],
            'DEBUG': ['debug'],
            'VERBOSE': ['verbose'],
            'OUTPUT_DIRECTORY': ['output_directory'],
            'AUDIO_ENHANCEMENT_METHOD': ['audio_enhancement_method'],
        }

        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                # Convert boolean strings
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                self._set_nested_value(self._config, config_path, value)

    def _migrate_legacy_config(self):
        """Migrate legacy configuration format to new format."""
        # Check if already in new format
        if 'llm' in self._config:
            return

        # Migrate legacy LLM configuration
        llm_provider = self._config.get('llm_provider', 'ollama')
        
        new_llm_config = {
            'primary': {
                'provider': llm_provider
            },
            'fallback': {
                'enabled': True,
                'provider': 'openai' if llm_provider == 'ollama' else 'ollama'
            }
        }

        # Migrate Ollama settings
        if 'ollama_host' in self._config or 'ollama_model' in self._config:
            ollama_config = {}
            if 'ollama_host' in self._config:
                ollama_config['host'] = self._config['ollama_host']
            if 'ollama_model' in self._config:
                ollama_config['model'] = self._config['ollama_model']
            
            new_llm_config['primary']['ollama'] = ollama_config
            new_llm_config['fallback']['ollama'] = ollama_config.copy()

        # Migrate OpenAI settings
        if 'openai_api_key' in self._config or 'openai_model' in self._config:
            openai_config = {}
            if 'openai_api_key' in self._config:
                openai_config['api_key'] = self._config['openai_api_key']
            if 'openai_model' in self._config:
                openai_config['model'] = self._config['openai_model']
            
            new_llm_config['primary']['openai'] = openai_config
            new_llm_config['fallback']['openai'] = openai_config.copy()

        self._config['llm'] = new_llm_config
        logger.info("Legacy LLM configuration migrated to new format")

    def _set_nested_value(self, config: Dict, path: List[str], value: Any):
        """Set a value in nested dictionary structure."""
        current = config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def get(self, key_path: str, default=None):
        """Get configuration value using dot notation."""
        keys = key_path.split('.')
        value = self._config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value: Any):
        """Set configuration value using dot notation."""
        keys = key_path.split('.')
        self._set_nested_value(self._config, keys, value)

    def get_raw_config(self) -> Dict[str, Any]:
        """Get the raw configuration dictionary."""
        return self._config.copy()

    def save(self, path: Optional[str] = None):
        """Save current configuration to file."""
        save_path = path or self.config_path
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Configuration saved to {save_path}")
        except (IOError, yaml.YAMLError) as e:
            logger.error(f"Failed to save configuration to {save_path}: {e}")

    def validate_required_settings(self) -> List[str]:
        """Validate required configuration settings and return missing ones."""
        required_settings = [
            'api_key',
            'broadcaster_id'
        ]
        
        missing = []
        for setting in required_settings:
            if not self.get(setting):
                missing.append(setting)
        
        return missing

    def validate_llm_config(self) -> List[str]:
        """Validate LLM configuration and return issues."""
        issues = []
        
        llm_config = self.get('llm', {})
        if not llm_config:
            issues.append("No LLM configuration found")
            return issues
        
        primary = llm_config.get('primary', {})
        if not primary:
            issues.append("No primary LLM provider configured")
            return issues
        
        provider = primary.get('provider')
        if not provider:
            issues.append("No primary LLM provider specified")
        elif provider == 'ollama':
            if not primary.get('ollama', {}).get('host'):
                issues.append("Ollama host not configured")
            if not primary.get('ollama', {}).get('model'):
                issues.append("Ollama model not configured")
        elif provider == 'openai':
            if not primary.get('openai', {}).get('api_key'):
                issues.append("OpenAI API key not configured")
            if not primary.get('openai', {}).get('model'):
                issues.append("OpenAI model not configured")
        
        return issues

    def get_audio_settings(self) -> Dict[str, Any]:
        """Get audio processing settings with defaults."""
        return {
            'enhancement_method': self.get('audio_enhancement_method', 'deepfilternet'),
            'noise_reduction': self.get('audio_noise_reduction', True),
            'amplify': self.get('audio_amplify', True),
            'normalize': self.get('audio_normalize', True),
            'output_format': self.get('audio_output_format', 'mp3'),
            'quality': self.get('audio_quality', 'high'),
            'sample_rate': self.get('audio_sample_rate', 44100),
            'chunk_size': self.get('audio_chunk_size', 30),
        }

    def get_processing_settings(self) -> Dict[str, Any]:
        """Get processing settings with defaults."""
        return {
            'save_original_audio': self.get('save_original_audio', True),
            'save_transcript': self.get('save_transcript', False),
            'output_directory': self.get('output_directory', 'processed_sermons'),
            'max_concurrent_jobs': self.get('max_concurrent_jobs', 2),
            'debug': self.get('debug', False),
            'verbose': self.get('verbose', False),
        }

    def get_sermonaudio_settings(self) -> Dict[str, Any]:
        """Get SermonAudio API settings."""
        return {
            'api_key': self.get('api_key'),
            'broadcaster_id': self.get('broadcaster_id'),
            'base_url': self.get('sermonaudio_base_url', 'https://api.sermonaudio.com/v2'),
            'timeout': self.get('api_timeout', 30),
            'retry_attempts': self.get('api_retry_attempts', 3),
            'retry_delay': self.get('api_retry_delay', 1),
        }

    def __str__(self) -> str:
        """String representation of the configuration."""
        # Hide sensitive data
        safe_config = self._config.copy()
        
        def hide_sensitive(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    if any(sensitive in key.lower() for sensitive in ['key', 'password', 'token', 'secret']):
                        obj[key] = "***HIDDEN***"
                    else:
                        hide_sensitive(value, current_path)
        
        hide_sensitive(safe_config)
        return yaml.dump(safe_config, default_flow_style=False, sort_keys=False)