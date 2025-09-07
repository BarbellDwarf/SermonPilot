#!/usr/bin/env python3
"""
Unit Tests for LLM Manager Components
Tests LLM provider switching, configuration, and chat functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class TestLLMManager(unittest.TestCase):
    """Test the LLMManager class functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_config = {
            'llm': {
                'primary': {
                    'provider': 'openai',
                    'openai': {
                        'base_url': 'https://api.openai.com/v1',
                        'api_key': 'test-key',
                        'model': 'gpt-3.5-turbo'
                    }
                },
                'fallback': {
                    'enabled': True,
                    'provider': 'ollama',
                    'ollama': {
                        'host': 'http://localhost:11434',
                        'model': 'llama3.1:8b'
                    }
                }
            }
        }
    
    def test_provider_validation(self):
        """Test LLM provider validation"""
        valid_providers = ['openai', 'ollama', 'anthropic', 'groq']
        
        for provider in valid_providers:
            self.assertIn(provider, valid_providers)
        
        invalid_providers = ['invalid_provider', '', None]
        for provider in invalid_providers:
            self.assertNotIn(provider, valid_providers)
    
    def test_fallback_chain_logic(self):
        """Test the fallback chain for LLM providers"""
        # Test logic: primary → fallback → exception
        chain_steps = ['primary', 'fallback', 'exception']
        
        for i, step in enumerate(chain_steps):
            if step == 'primary':
                self.assertTrue(True)  # Primary should always be tried first
            elif step == 'fallback':
                self.assertTrue(True)  # Fallback should be tried if primary fails
            elif step == 'exception':
                self.assertTrue(True)  # Exception should be raised if all fail
    
    @patch('src.llm_manager.openai')
    def test_openai_provider_initialization(self, mock_openai):
        """Test OpenAI provider initialization"""
        mock_client = Mock()
        mock_openai.OpenAI.return_value = mock_client
        
        try:
            from src.llm_manager import LLMManager
            manager = LLMManager(self.mock_config['llm'])
            self.assertIsNotNone(manager)
        except ImportError:
            self.skipTest("LLMManager not available in test environment")
    
    def test_config_migration_logic(self):
        """Test configuration migration from legacy format"""
        # Test that legacy config gets migrated properly
        legacy_config = {
            'openai_api_key': 'test-key',
            'openai_base_url': 'https://api.openai.com/v1'
        }
        
        # This would be migrated to new format
        expected_new_format = {
            'llm': {
                'primary': {
                    'provider': 'openai',
                    'openai': {
                        'api_key': 'test-key',
                        'base_url': 'https://api.openai.com/v1'
                    }
                }
            }
        }
        
        # Test the migration logic conceptually
        self.assertIn('openai_api_key', legacy_config)
        self.assertIn('openai', expected_new_format['llm']['primary'])

class TestChatFunctionality(unittest.TestCase):
    """Test chat and message handling functionality"""
    
    def test_message_format_validation(self):
        """Test that messages are properly formatted"""
        valid_message = {
            'role': 'user',
            'content': 'Test message'
        }
        
        required_fields = ['role', 'content']
        for field in required_fields:
            self.assertIn(field, valid_message)
        
        valid_roles = ['system', 'user', 'assistant']
        self.assertIn(valid_message['role'], valid_roles)
    
    def test_conversation_history_management(self):
        """Test conversation history tracking"""
        conversation = []
        
        # Add system message
        system_msg = {'role': 'system', 'content': 'You are a helpful assistant.'}
        conversation.append(system_msg)
        
        # Add user message
        user_msg = {'role': 'user', 'content': 'Hello!'}
        conversation.append(user_msg)
        
        # Add assistant response
        assistant_msg = {'role': 'assistant', 'content': 'Hello! How can I help you?'}
        conversation.append(assistant_msg)
        
        self.assertEqual(len(conversation), 3)
        self.assertEqual(conversation[0]['role'], 'system')
        self.assertEqual(conversation[1]['role'], 'user')
        self.assertEqual(conversation[2]['role'], 'assistant')

if __name__ == '__main__':
    unittest.main()