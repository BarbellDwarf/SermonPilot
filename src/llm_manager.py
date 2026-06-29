"""
LLM Manager for handling multiple LLM providers with fallback support.
Supports OpenAI and Ollama providers with configurable primary and fallback options.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import openai
except Exception:
    openai = None  # OpenAI library not available, will be handled later
import requests

logger = logging.getLogger(__name__)

# Import database for cost tracking
try:
    # Try to import from the UI directory
    ui_dir = Path(__file__).parent.parent / "ui"
    if ui_dir.exists():
        sys.path.insert(0, str(ui_dir))
        from database import get_db
        DATABASE_AVAILABLE = True
    else:
        DATABASE_AVAILABLE = False
        logger.info("Database not available for cost tracking")
except ImportError:
    DATABASE_AVAILABLE = False
    logger.info("Database module not available for cost tracking")


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
        self.api_key = config.get('api_key', '')

        os.environ["OLLAMA_HOST"] = self.host

        try:
            import ollama
            self.ollama = ollama
        except ImportError:
            logger.error("Ollama library not installed. Install with: pip install ollama")
            self.ollama = None

    def __str__(self) -> str:
        return f"OllamaProvider(model={self.model}, host={self.host})"

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    def list_models(self) -> list[str]:
        """List available models from Ollama."""
        try:
            if self.ollama:
                response = self.ollama.list()
                models = response.get('models', [])
                names: list[str] = []
                for m in models:
                    try:
                        if isinstance(m, dict):
                            name = m.get('model') or m.get('name')
                        else:
                            name = getattr(m, 'model', None) or getattr(m, 'name', None)
                        if name:
                            names.append(name)
                    except Exception:
                        continue
                return names
        except Exception:
            logger.debug("Ollama library failed for model listing, trying HTTP...")

        try:
            response = requests.get(f"{self.host}/api/tags", headers=self._headers(), timeout=5)
            if response.status_code == 200:
                data = response.json()
                names: list[str] = []
                for m in data.get('models', []):
                    try:
                        names.append(m.get('model') or m.get('name'))
                    except Exception:
                        continue
                return [n for n in names if n]
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
                headers=self._headers(),
                timeout=30
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


class AnthropicProvider(OpenAIProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, config: dict[str, Any]):
        # Set default model if not specified
        if 'model' not in config:
            config['model'] = 'claude-3-5-sonnet-20241022'

        # Set Anthropic API base URL if not specified
        if 'base_url' not in config:
            config['base_url'] = 'https://api.anthropic.com/v1'

        super().__init__(config)

    def __str__(self) -> str:
        """String representation of the provider."""
        return f"AnthropicProvider(model={self.model})"


class XAIProvider(OpenAIProvider):
    """xAI Grok LLM provider."""

    def __init__(self, config: dict[str, Any]):
        # Set default model if not specified
        if 'model' not in config:
            config['model'] = 'grok-beta'

        # Set xAI API base URL if not specified
        if 'base_url' not in config:
            config['base_url'] = 'https://api.x.ai/v1'

        super().__init__(config)

    def __str__(self) -> str:
        """String representation of the provider."""
        return f"XAIProvider(model={self.model})"


class GoogleProvider(OpenAIProvider):
    """Google Gemini LLM provider."""

    def __init__(self, config: dict[str, Any]):
        # Set default model if not specified
        if 'model' not in config:
            config['model'] = 'gemini-1.5-flash'

        # Set Google AI API base URL if not specified
        if 'base_url' not in config:
            config['base_url'] = 'https://generativelanguage.googleapis.com/v1beta'

        super().__init__(config)

    def __str__(self) -> str:
        """String representation of the provider."""
        return f"GoogleProvider(model={self.model})"


class GroqProvider(OpenAIProvider):
    """Groq LLM provider."""

    def __init__(self, config: dict[str, Any]):
        # Set default model if not specified
        if 'model' not in config:
            config['model'] = 'llama-3.1-70b-versatile'

        # Set Groq API base URL if not specified
        if 'base_url' not in config:
            config['base_url'] = 'https://api.groq.com/openai/v1'

        super().__init__(config)

    def __str__(self) -> str:
        """String representation of the provider."""
        return f"GroqProvider(model={self.model})"


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter LLM provider."""

    def __init__(self, config: dict[str, Any]):
        if 'model' not in config:
            config['model'] = 'openai/gpt-4o-mini'

        if 'base_url' not in config:
            config['base_url'] = 'https://openrouter.ai/api/v1'

        super().__init__(config)

    def __str__(self) -> str:
        return f"OpenRouterProvider(model={self.model})"


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
            fallback_provider_config = fallback_config.get(fallback_provider_type, {})

            # Check if fallback provider has required configuration
            try:
                if fallback_provider_type in ['openai', 'anthropic', 'xai', 'google', 'groq', 'openrouter']:
                    # These providers require an API key
                    if not fallback_provider_config.get('api_key'):
                        logger.info(f"Fallback provider {fallback_provider_type} disabled: no API key configured")
                        self.fallback_provider = None
                    else:
                        self.fallback_provider = self._create_provider(
                            fallback_provider_type,
                            fallback_provider_config
                        )
                        logger.info(f"Fallback LLM provider initialized: {fallback_provider_type}")
                else:
                    # Ollama or other providers that may not require API keys
                    self.fallback_provider = self._create_provider(
                        fallback_provider_type,
                        fallback_provider_config
                    )
                    logger.info(f"Fallback LLM provider initialized: {fallback_provider_type}")
            except Exception as e:
                warning_msg = (
                    f"Failed to initialize fallback provider {fallback_provider_type}: {e}"
                )
                logger.info(warning_msg)  # Changed from warning to info to reduce noise
                self.fallback_provider = None

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
        elif provider_type == 'anthropic':
            return AnthropicProvider(provider_config)
        elif provider_type == 'xai':
            return XAIProvider(provider_config)
        elif provider_type == 'google':
            return GoogleProvider(provider_config)
        elif provider_type == 'groq':
            return GroqProvider(provider_config)
        elif provider_type == 'openrouter':
            return OpenRouterProvider(provider_config)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    def chat(
        self,
        messages: list[dict[str, str]],
        operation: str = "",
        sermon_id: str | None = None,
    ) -> str:
        """
        Send a chat request using primary provider with fallback support.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            operation: The operation being performed (e.g., 'description_generation')
            sermon_id: The sermon ID for cost tracking

        Returns:
            Response content string

        Raises:
            Exception: If both primary and fallback providers fail
        """
        start_time = time.time()
        
        if self.primary_provider:
            try:
                response = self.primary_provider.chat(messages)
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Log the successful API usage
                self._log_api_usage(
                    provider=self._get_provider_name(self.primary_provider),
                    model=self._get_provider_model(self.primary_provider),
                    messages=messages,
                    response=response,
                    duration_ms=duration_ms,
                    operation=operation,
                    sermon_id=sermon_id,
                    status="success"
                )
                
                logger.info(f"Primary provider succeeded: {type(self.primary_provider).__name__}")
                return response
            except Exception as e:
                logger.warning(f"Primary provider failed: {e}")
                
                # Log the failed API usage
                duration_ms = int((time.time() - start_time) * 1000)
                self._log_api_usage(
                    provider=self._get_provider_name(self.primary_provider),
                    model=self._get_provider_model(self.primary_provider),
                    messages=messages,
                    response="",
                    duration_ms=duration_ms,
                    operation=operation,
                    sermon_id=sermon_id,
                    status="error",
                    error_message=str(e)
                )

        start_time = time.time()  # Reset timer for fallback
        if self.fallback_provider:
            try:
                response = self.fallback_provider.chat(messages)
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Log the successful fallback API usage
                self._log_api_usage(
                    provider=self._get_provider_name(self.fallback_provider),
                    model=self._get_provider_model(self.fallback_provider),
                    messages=messages,
                    response=response,
                    duration_ms=duration_ms,
                    operation=operation,
                    sermon_id=sermon_id,
                    status="success"
                )
                
                logger.info(f"Fallback provider succeeded: {type(self.fallback_provider).__name__}")
                return response
            except Exception as e:
                logger.error(f"Fallback provider failed: {e}")
                
                # Log the failed fallback API usage
                duration_ms = int((time.time() - start_time) * 1000)
                self._log_api_usage(
                    provider=self._get_provider_name(self.fallback_provider),
                    model=self._get_provider_model(self.fallback_provider),
                    messages=messages,
                    response="",
                    duration_ms=duration_ms,
                    operation=operation,
                    sermon_id=sermon_id,
                    status="error",
                    error_message=str(e)
                )

        error_msg = (
            "All LLM providers failed. Please check your configuration and network connectivity."
        )
        raise Exception(error_msg)

    def _get_provider_name(self, provider) -> str:
        """Get the provider name for logging"""
        if hasattr(provider, 'config'):
            return provider.__class__.__name__.replace('Provider', '').lower()
        return 'unknown'

    def _get_provider_model(self, provider) -> str:
        """Get the model name for logging"""
        if hasattr(provider, 'model'):
            return provider.model
        elif hasattr(provider, 'config') and 'model' in provider.config:
            return provider.config['model']
        return 'unknown'

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token for English)"""
        return len(text) // 4

    def _estimate_cost(self, provider_name: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost based on provider and model"""
        # Simple cost estimation - in reality this would be more sophisticated
        cost_per_1k_tokens = {
            'openai': {
                'gpt-4o': 0.005,
                'gpt-4o-mini': 0.00015,
                'gpt-4': 0.03,
                'gpt-3.5-turbo': 0.002
            },
            'anthropic': {
                'claude-3-5-sonnet-20241022': 0.003,
                'claude-3-haiku-20240307': 0.00025
            },
            'xai': {
                'grok-beta': 0.005
            },
            'google': {
                'gemini-1.5-flash': 0.0001,
                'gemini-1.5-pro': 0.002
            },
            'groq': {
                'llama-3.1-8b-instant': 0.0001,
                'mixtral-8x7b-32768': 0.0002
            },
            'openrouter': {
                'openai/gpt-4o-mini': 0.00015,
                'openai/gpt-4o': 0.005,
                'anthropic/claude-3.5-sonnet': 0.003,
                'google/gemini-1.5-flash': 0.0001,
            },
            'ollama': {}  # Ollama is free for local models
        }
        
        if provider_name.lower() == 'ollama':
            return 0.0
            
        provider_costs = cost_per_1k_tokens.get(provider_name.lower(), {})
        cost_per_token = provider_costs.get(model.lower(), 0.001) / 1000  # Default to $0.001 per 1k tokens
        
        return (input_tokens + output_tokens) * cost_per_token

    def _log_api_usage(self, provider: str, model: str, messages: list, response: str,
                      duration_ms: int, operation: str, sermon_id: str | None = None,
                      status: str = "success", error_message: str | None = None):
        """Log API usage to database for cost tracking"""
        if not DATABASE_AVAILABLE:
            return
            
        try:
            # Calculate tokens
            input_text = " ".join([msg.get('content', '') for msg in messages])
            input_tokens = self._estimate_tokens(input_text)
            output_tokens = self._estimate_tokens(response)
            
            # Estimate cost
            cost = self._estimate_cost(provider, model, input_tokens, output_tokens)
            
            # Get database instance and log usage
            db = get_db()
            db.log_llm_api_usage(
                sermon_id=sermon_id,
                operation=operation,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                request_duration_ms=duration_ms,
                status=status,
                error_message=error_message,
                request_data=str(messages)[:1000] if messages else None,  # Truncate for storage
                response_data=response[:1000] if response else None  # Truncate for storage
            )
            
        except Exception as e:
            logger.debug(f"Failed to log API usage: {e}")  # Don't let logging errors break the main flow

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
            # Use the centralized chat method to ensure API usage logging
            messages = [{'role': 'user', 'content': validation_prompt}]
            
            # For validation calls, we'll directly call the validator provider but log the usage
            start_time = time.time()
            response = self.validator_provider.chat(messages)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API usage for validation
            self._log_api_usage(
                provider=self._get_provider_name(self.validator_provider),
                model=self._get_provider_model(self.validator_provider),
                messages=messages,
                response=response,
                duration_ms=duration_ms,
                operation="description_validation",
                sermon_id=None,  # Validation might not always have a sermon_id
                status="success"
            )

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
            
            # Try to log the failed validation attempt
            try:
                duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
                self._log_api_usage(
                    provider=self._get_provider_name(self.validator_provider),
                    model=self._get_provider_model(self.validator_provider),
                    messages=[{'role': 'user', 'content': validation_prompt}],
                    response="",
                    duration_ms=duration_ms,
                    operation="description_validation",
                    sermon_id=None,
                    status="error",
                    error_message=str(e)
                )
            except Exception as log_error:
                logger.debug(f"Failed to log validation error: {log_error}")
            
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
