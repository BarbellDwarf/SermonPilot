"""
Test Configuration Manager Module

Tests for the extracted configuration management functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path
import yaml
import sys

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.config import ConfigManager


class TestConfigManager:
    """Test the configuration manager functionality."""
    
    def test_config_creation(self):
        """Test that config manager can be created."""
        config = ConfigManager()
        assert config is not None
    
    def test_config_with_temp_file(self):
        """Test config loading from temporary file."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {
                'api_key': 'test_key',
                'broadcaster_id': 'test_broadcaster',
                'debug': True,
                'audio_enhancement_method': 'deepfilternet'
            }
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            # Load config
            config = ConfigManager(temp_path)
            
            # Test basic get operations
            assert config.get('api_key') == 'test_key'
            assert config.get('broadcaster_id') == 'test_broadcaster'
            assert config.get('debug') is True
            assert config.get('audio_enhancement_method') == 'deepfilternet'
            assert config.get('nonexistent_key', 'default') == 'default'
            
        finally:
            # Clean up
            os.unlink(temp_path)
    
    def test_config_dot_notation(self):
        """Test dot notation for nested configuration."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {
                'llm': {
                    'primary': {
                        'provider': 'ollama',
                        'ollama': {
                            'host': 'localhost:11434',
                            'model': 'llama3'
                        }
                    }
                }
            }
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            config = ConfigManager(temp_path)
            
            # Test nested access
            assert config.get('llm.primary.provider') == 'ollama'
            assert config.get('llm.primary.ollama.host') == 'localhost:11434'
            assert config.get('llm.primary.ollama.model') == 'llama3'
            assert config.get('llm.nonexistent.key', 'default') == 'default'
            
        finally:
            os.unlink(temp_path)
    
    def test_environment_overrides(self):
        """Test environment variable overrides."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {
                'api_key': 'file_key',
                'debug': False
            }
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            # Set environment variables
            os.environ['SERMONAUDIO_API_KEY'] = 'env_key'
            os.environ['DEBUG'] = 'true'
            
            config = ConfigManager(temp_path)
            
            # Environment should override file
            assert config.get('api_key') == 'env_key'
            assert config.get('debug') is True
            
        finally:
            # Clean up
            os.unlink(temp_path)
            os.environ.pop('SERMONAUDIO_API_KEY', None)
            os.environ.pop('DEBUG', None)
    
    def test_legacy_migration(self):
        """Test legacy configuration migration."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            # Legacy config format
            legacy_config = {
                'llm_provider': 'ollama',
                'ollama_host': 'localhost:11434',
                'ollama_model': 'llama3',
                'openai_api_key': 'test_key',
                'openai_model': 'gpt-4'
            }
            yaml.dump(legacy_config, f)
            temp_path = f.name
        
        try:
            config = ConfigManager(temp_path)
            
            # Should be migrated to new format
            assert config.get('llm.primary.provider') == 'ollama'
            assert config.get('llm.primary.ollama.host') == 'localhost:11434'
            assert config.get('llm.primary.ollama.model') == 'llama3'
            assert config.get('llm.primary.openai.api_key') == 'test_key'
            assert config.get('llm.primary.openai.model') == 'gpt-4'
            
        finally:
            os.unlink(temp_path)
    
    def test_validation(self):
        """Test configuration validation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {
                'api_key': 'test_key',
                'broadcaster_id': 'test_broadcaster',
                'llm': {
                    'primary': {
                        'provider': 'ollama',
                        'ollama': {
                            'host': 'localhost:11434',
                            'model': 'llama3'
                        }
                    }
                }
            }
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            config = ConfigManager(temp_path)
            
            # Should pass required settings validation
            missing = config.validate_required_settings()
            assert len(missing) == 0
            
            # Should pass LLM validation
            issues = config.validate_llm_config()
            assert len(issues) == 0
            
        finally:
            os.unlink(temp_path)
    
    def test_settings_helpers(self):
        """Test settings helper methods."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {
                'api_key': 'test_key',
                'broadcaster_id': 'test_broadcaster',
                'audio_enhancement_method': 'resemble',
                'save_original_audio': False,
                'output_directory': '/custom/path'
            }
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            config = ConfigManager(temp_path)
            
            # Test audio settings
            audio_settings = config.get_audio_settings()
            assert audio_settings['enhancement_method'] == 'resemble'
            assert 'noise_reduction' in audio_settings
            
            # Test processing settings
            proc_settings = config.get_processing_settings()
            assert proc_settings['save_original_audio'] is False
            assert proc_settings['output_directory'] == '/custom/path'
            
            # Test sermonaudio settings
            sa_settings = config.get_sermonaudio_settings()
            assert sa_settings['api_key'] == 'test_key'
            assert sa_settings['broadcaster_id'] == 'test_broadcaster'
            
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    # Run basic tests
    print("Testing Configuration Manager...")
    
    # Test basic creation
    config = ConfigManager()
    print("✅ Config manager creation works")
    
    # Test with simple config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        test_config = {
            'api_key': 'test',
            'broadcaster_id': 'test',
            'debug': True
        }
        yaml.dump(test_config, f)
        temp_path = f.name
    
    try:
        config = ConfigManager(temp_path)
        assert config.get('api_key') == 'test'
        assert config.get('debug') is True
        print("✅ Config loading and access works")
        
        # Test validation
        missing = config.validate_required_settings()
        assert len(missing) == 0
        print("✅ Config validation works")
        
    finally:
        os.unlink(temp_path)
    
    print("All configuration manager tests passed!")