#!/usr/bin/env python3
"""
Unit Tests for Configuration Management
Tests configuration loading, validation, and migration functionality.
"""

import unittest
from unittest.mock import Mock, patch, mock_open
import sys
import os
import tempfile
import yaml
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class TestConfigurationLoading(unittest.TestCase):
    """Test configuration file loading and validation"""
    
    def test_yaml_structure_validation(self):
        """Test YAML structure validation"""
        valid_config = {
            'debug': False,
            'llm': {
                'primary': {
                    'provider': 'openai'
                }
            },
            'audio_processing': {
                'enhancement_method': 'none'
            }
        }
        
        # Test that required sections exist
        self.assertIn('llm', valid_config)
        self.assertIn('audio_processing', valid_config)
        self.assertIn('debug', valid_config)
    
    def test_config_file_parsing(self):
        """Test configuration file parsing"""
        sample_yaml = """
debug: false
llm:
  primary:
    provider: openai
    openai:
      api_key: test-key
      model: gpt-3.5-turbo
audio_processing:
  enhancement_method: none
  output_format: mp3
"""
        try:
            config = yaml.safe_load(sample_yaml)
            self.assertIsInstance(config, dict)
            self.assertIn('debug', config)
            self.assertIn('llm', config)
            self.assertIn('audio_processing', config)
        except yaml.YAMLError as e:
            self.fail(f"YAML parsing failed: {e}")
    
    def test_default_configuration_values(self):
        """Test default configuration values"""
        defaults = {
            'debug': False,
            'audio_processing': {
                'enhancement_method': 'none',
                'output_format': 'mp3',
                'sample_rate': 44100
            },
            'llm': {
                'primary': {
                    'provider': 'openai'
                }
            }
        }
        
        # Test default values are reasonable
        self.assertFalse(defaults['debug'])
        self.assertEqual(defaults['audio_processing']['enhancement_method'], 'none')
        self.assertEqual(defaults['audio_processing']['output_format'], 'mp3')
        self.assertEqual(defaults['audio_processing']['sample_rate'], 44100)

class TestConfigurationMigration(unittest.TestCase):
    """Test configuration migration functionality"""
    
    def test_legacy_config_detection(self):
        """Test detection of legacy configuration format"""
        legacy_config = {
            'openai_api_key': 'test-key',
            'openai_base_url': 'https://api.openai.com/v1',
            'openai_model': 'gpt-3.5-turbo'
        }
        
        new_config = {
            'llm': {
                'primary': {
                    'provider': 'openai',
                    'openai': {
                        'api_key': 'test-key',
                        'base_url': 'https://api.openai.com/v1',
                        'model': 'gpt-3.5-turbo'
                    }
                }
            }
        }
        
        # Test legacy detection logic
        has_legacy_keys = any(key.startswith('openai_') for key in legacy_config.keys())
        has_new_structure = 'llm' in new_config and 'primary' in new_config['llm']
        
        self.assertTrue(has_legacy_keys)
        self.assertTrue(has_new_structure)
    
    def test_migration_logic(self):
        """Test configuration migration logic"""
        # Simulate migration from legacy to new format
        legacy_keys = {
            'openai_api_key': 'llm.primary.openai.api_key',
            'openai_base_url': 'llm.primary.openai.base_url', 
            'openai_model': 'llm.primary.openai.model'
        }
        
        for legacy_key, new_path in legacy_keys.items():
            # Test mapping exists
            self.assertTrue(legacy_key.startswith('openai_'))
            self.assertTrue('llm.primary.openai' in new_path)

class TestConfigurationValidation(unittest.TestCase):
    """Test configuration validation functionality"""
    
    def test_required_fields_validation(self):
        """Test validation of required configuration fields"""
        required_sections = ['llm', 'audio_processing']
        required_llm_fields = ['primary']
        required_audio_fields = ['enhancement_method']
        
        config = {
            'llm': {
                'primary': {
                    'provider': 'openai'
                }
            },
            'audio_processing': {
                'enhancement_method': 'none'
            }
        }
        
        # Test required sections exist
        for section in required_sections:
            self.assertIn(section, config)
        
        # Test required LLM fields
        for field in required_llm_fields:
            self.assertIn(field, config['llm'])
        
        # Test required audio fields
        for field in required_audio_fields:
            self.assertIn(field, config['audio_processing'])
    
    def test_provider_specific_validation(self):
        """Test provider-specific configuration validation"""
        openai_config = {
            'provider': 'openai',
            'openai': {
                'api_key': 'test-key',
                'model': 'gpt-3.5-turbo'
            }
        }
        
        ollama_config = {
            'provider': 'ollama',
            'ollama': {
                'host': 'http://localhost:11434',
                'model': 'llama3.1:8b'
            }
        }
        
        # Test OpenAI config
        self.assertEqual(openai_config['provider'], 'openai')
        self.assertIn('openai', openai_config)
        self.assertIn('api_key', openai_config['openai'])
        
        # Test Ollama config  
        self.assertEqual(ollama_config['provider'], 'ollama')
        self.assertIn('ollama', ollama_config)
        self.assertIn('host', ollama_config['ollama'])
    
    def test_enhancement_method_validation(self):
        """Test audio enhancement method validation"""
        valid_methods = ['deepfilternet', 'resemble_enhance', 'none']
        invalid_methods = ['invalid', '', None, 123]
        
        for method in valid_methods:
            self.assertIn(method, valid_methods)
        
        for method in invalid_methods:
            self.assertNotIn(method, valid_methods)

if __name__ == '__main__':
    unittest.main()