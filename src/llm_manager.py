"""
LLM Manager for handling multiple LLM providers with fallback support.
Supports OpenAI and Ollama providers with configurable primary and fallback options.
"""

import logging
import os
import sys
from typing import Any

import openai
import requests

logger = logging.getLogger(__name__)


class LLMProvider:
    """Base class for LLM providers."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat request and return the response content."""
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    """Ollama LLM provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.host = config.get('host', 'http://localhost:11434')
        self.model = config.get('model', 'llama3')

        os.environ["OLLAMA_HOST"] = self.host

        try:
            import ollama
            self.ollama = ollama
        except ImportError:
            logger.error("Ollama library not installed. Install with: pip install ollama")
            self.ollama = None

    def __str__(self) -> str:
        """String representation of the provider."""
        return f"OllamaProvider(model={self.model}, host={self.host})"

    def list_models(self) -> list[str]:
        """List available models from Ollama."""
        try:
            # Try using ollama library first
            if self.ollama:
                response = self.ollama.list()
                return [model['name'] for model in response.get('models', [])]
        except Exception:
            logger.debug("Ollama library failed for model listing, trying HTTP...")

        # Fallback to HTTP request
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            else:
                logger.error(f"Failed to list Ollama models: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Failed to connect to Ollama for model listing: {e}")
            return []

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send chat request to Ollama."""
        if not self.ollama:
            raise Exception("Ollama library not available") from None

        try:
            response = self.ollama.chat(model=self.model, messages=messages)
            return response['message']['content']
        except Exception as e:
            # Check if it's a model not found error from ollama library
            error_str = str(e).lower()
            if ("model" in error_str and
                ("not found" in error_str or "does not exist" in error_str)):
                available_models = self.list_models()
                if available_models:
                    print(f"\nError: Model '{self.model}' not found in Ollama.")
                    print(f"Available models: {', '.join(available_models)}")
                    sys.exit(1)
            
            logger.warning(f"Ollama library failed: {e}. Trying direct HTTP request...")

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False
            }

            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return result['message']['content']
            elif response.status_code == 404:
                # Check if it's a model not found error
                available_models = self.list_models()
                if available_models:
                    print(f"\nError: Model '{self.model}' not found in Ollama.")
                    print(f"Available models: {', '.join(available_models)}")
                    sys.exit(1)
                else:
                    # If we can't list models, it might be an endpoint issue
                    error_msg = (f"Ollama server appears to be down or unreachable: "
                                f"{response.status_code}")
                    raise Exception(error_msg) from None
            else:
                error_msg = f"Ollama HTTP request failed: {response.status_code} - {response.text}"
                raise Exception(error_msg) from e


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider (supports OpenAI, xAI, Anthropic, etc.)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.model = config.get('model', 'gpt-3.5-turbo')
        self.base_url = config.get('base_url')  # Custom endpoint for xAI, Anthropic, etc.

        if not self.api_key:
            raise ValueError("API key is required for OpenAI-compatible provider")

        client_kwargs = {'api_key': self.api_key}
        if self.base_url:
            client_kwargs['base_url'] = self.base_url

        self.client = openai.OpenAI(**client_kwargs)

    def __str__(self) -> str:
        """String representation of the provider."""
        if self.base_url:
            return f"OpenAIProvider(model={self.model}, base_url={self.base_url})"
        return f"OpenAIProvider(model={self.model})"

    def list_models(self) -> list[str]:
        """List available models from OpenAI-compatible API."""
        try:
            models = self.client.models.list()
            return [model.id for model in models.data]
        except Exception as e:
            logger.error(f"Failed to list OpenAI models: {e}")
            return []

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send chat request to OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
        except openai.NotFoundError as e:
            # Model not found error
            if "model" in str(e).lower():
                available_models = self.list_models()
                if available_models:
                    print(f"\nError: Model '{self.model}' not found.")
                    print(f"Available models: {', '.join(available_models)}")
                    sys.exit(1)
                else:
                    # If we can't list models, re-raise as general error for fallback
                    raise Exception("Unable to verify model availability") from e
            else:
                raise Exception(f"OpenAI API error: {e}") from e
        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            # Connection/timeout errors - let fallback handle
            raise Exception(f"OpenAI API connection error: {e}") from e
        except Exception as e:
            # Other errors
            raise Exception(f"OpenAI API error: {e}") from e


class LLMManager:
    """Manages LLM providers with primary and fallback support."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.primary_provider = None
        self.fallback_provider = None
        self.validator_provider = None

        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize primary and fallback providers based on config."""
        llm_config = self.config.get('llm', {})

        primary_config = llm_config.get('primary', {})
        primary_provider_type = primary_config.get('provider', 'ollama')

        try:
            self.primary_provider = self._create_provider(
                primary_provider_type,
                primary_config.get(primary_provider_type, {})
            )
            logger.info(f"Primary LLM provider initialized: {primary_provider_type}")
        except Exception as e:
            logger.error(f"Failed to initialize primary provider {primary_provider_type}: {e}")

        fallback_config = llm_config.get('fallback', {})
        if fallback_config.get('enabled', False):
            fallback_provider_type = fallback_config.get('provider', 'openai')

            try:
                self.fallback_provider = self._create_provider(
                    fallback_provider_type,
                    fallback_config.get(fallback_provider_type, {})
                )
                logger.info(f"Fallback LLM provider initialized: {fallback_provider_type}")
            except Exception as e:
                warning_msg = (
                    f"Failed to initialize fallback provider {fallback_provider_type}: {e}"
                )
                logger.warning(warning_msg)

        # Initialize validator provider (smaller model for validation)
        validator_config = llm_config.get('validator', {})
        if validator_config.get('enabled', False):
            validator_provider_type = validator_config.get('provider', 'ollama')

            try:
                self.validator_provider = self._create_provider(
                    validator_provider_type,
                    validator_config.get(validator_provider_type, {})
                )
                logger.info(f"Validator LLM provider initialized: {validator_provider_type}")
            except Exception as e:
                warning_msg = (
                    f"Failed to initialize validator provider {validator_provider_type}: {e}"
                )
                logger.warning(warning_msg)

    def _create_provider(self, provider_type: str, provider_config: dict[str, Any]) -> LLMProvider:
        """Create a provider instance based on type and config."""
        if provider_type == 'ollama':
            return OllamaProvider(provider_config)
        elif provider_type == 'openai':
            return OpenAIProvider(provider_config)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    def chat(self, messages: list[dict[str, str]]) -> str:
        """
        Send a chat request using primary provider with fallback support.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys

        Returns:
            Response content string

        Raises:
            Exception: If both primary and fallback providers fail
        """
        if self.primary_provider:
            try:
                response = self.primary_provider.chat(messages)
                logger.info(f"Primary provider succeeded: {type(self.primary_provider).__name__}")
                return response
            except Exception as e:
                logger.warning(f"Primary provider failed: {e}")

        if self.fallback_provider:
            try:
                response = self.fallback_provider.chat(messages)
                logger.info(f"Fallback provider succeeded: {type(self.fallback_provider).__name__}")
                return response
            except Exception as e:
                logger.error(f"Fallback provider failed: {e}")

        error_msg = (
            "All LLM providers failed. Please check your configuration and network connectivity."
        )
        raise Exception(error_msg)

    def validate_description(self, description: str, criteria: list[str]) -> tuple[bool, str]:
        """
        Validate a description using the validator model.
        
        Args:
            description: The description to validate
            criteria: List of validation criteria
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if not self.validator_provider:
            logger.warning("Validator provider not available, skipping validation")
            return True, "Validator not configured"
            
        criteria_text = "\n".join([f"- {criterion}" for criterion in criteria])
        
        validation_prompt = (
            "You are a description validator. Review the following sermon description and "
            "determine if it meets the quality criteria. Respond with only 'APPROVED' or "
            "'REJECTED' followed by a brief reason.\n\n"
            f"Criteria:\n{criteria_text}\n\n"
            f"Description to validate:\n{description}\n\n"
            "Response format: APPROVED/REJECTED - [brief reason]\n"
            "Response:"
        )
        
        try:
            response = self.validator_provider.chat([
                {'role': 'user', 'content': validation_prompt}
            ])
            
            response = response.strip()
            if response.upper().startswith('APPROVED'):
                reason = response.split('-', 1)[1].strip() if '-' in response else "Meets criteria"
                return True, reason
            elif response.upper().startswith('REJECTED'):
                reason = (response.split('-', 1)[1].strip() if '-' in response
                         else "Does not meet criteria")
                return False, reason
            else:
                # If response format is unexpected, assume rejected for safety
                return False, f"Unexpected validation response: {response}"
                
        except Exception as e:
            logger.warning(f"Description validation failed: {e}")
            return True, f"Validation error: {e}"  # Default to approved on error

    def get_provider_info(self) -> dict[str, Any]:
        """Get information about configured providers."""
        info = {
            'primary': None,
            'fallback': None,
            'validator': None
        }

        if self.primary_provider:
            provider_type = type(self.primary_provider).__name__.replace('Provider', '').lower()
            info['primary'] = {
                'type': provider_type,
                'model': getattr(self.primary_provider, 'model', 'unknown'),
                'available': True
            }

        if self.fallback_provider:
            provider_type = type(self.fallback_provider).__name__.replace('Provider', '').lower()
            info['fallback'] = {
                'type': provider_type,
                'model': getattr(self.fallback_provider, 'model', 'unknown'),
                'available': True
            }

        if self.validator_provider:
            provider_type = type(self.validator_provider).__name__.replace('Provider', '').lower()
            info['validator'] = {
                'type': provider_type,
                'model': getattr(self.validator_provider, 'model', 'unknown'),
                'available': True
            }

        return info


# Backward compatibility functions
def create_llm_manager(config: dict[str, Any]) -> LLMManager:
    """Create and return an LLM manager instance."""
    return LLMManager(config)


def migrate_legacy_config(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy configuration format to new format for backward compatibility."""
    if 'llm' in config:
        return config

    new_config = config.copy()

    llm_provider = config.get('llm_provider', 'ollama')

    new_config['llm'] = {
        'primary': {
            'provider': llm_provider
        },
        'fallback': {
            'enabled': True,
            'provider': 'openai' if llm_provider == 'ollama' else 'ollama'
        }
    }

    if 'ollama_host' in config or 'ollama_model' in config:
        ollama_config = {}
        if 'ollama_host' in config:
            ollama_config['host'] = config['ollama_host']
        if 'ollama_model' in config:
            ollama_config['model'] = config['ollama_model']

        new_config['llm']['primary']['ollama'] = ollama_config
        new_config['llm']['fallback']['ollama'] = ollama_config.copy()

    if 'openai_api_key' in config or 'openai_model' in config:
        openai_config = {}
        if 'openai_api_key' in config:
            openai_config['api_key'] = config['openai_api_key']
        if 'openai_model' in config:
            openai_config['model'] = config['openai_model']

        new_config['llm']['primary']['openai'] = openai_config
        new_config['llm']['fallback']['openai'] = openai_config.copy()

    logger.info("Legacy LLM configuration migrated to new format")
    return new_config
