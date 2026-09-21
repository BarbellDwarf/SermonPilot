"""
LLM Manager for handling multiple LLM providers with fallback support.
Supports OpenAI and Ollama providers with configurable primary and fallback options.
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

try:
    import openai
except Exception:
    openai = None  # OpenAI library not available, will be handled later
import requests

logger = logging.getLogger(__name__)


class LLMTimeoutError(TimeoutError):
    """Raised when an LLM call exceeds its wall-clock deadline."""

    def __init__(self, message: str, timeout: float | None = None):
        super().__init__(message)
        self.timeout = timeout


_DEFAULT_CALL_TIMEOUT_SECONDS = 120.0
_DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
_DEFAULT_TOTAL_BUDGET_SECONDS = 300.0


def _positive_float(value: Any, default: float) -> float:
    """Parse a positive timeout value, falling back to ``default``."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _call_with_deadline(fn, timeout: float, label: str):
    """Run ``fn`` on a daemon thread and fail once ``timeout`` elapses.

    Requests carry their own connect/read timeouts, but not every client
    honours them. This wall-clock bound is the backstop that keeps a hung
    provider call from wedging the pipeline. The worker is a daemon thread,
    so a still-blocked call cannot hold up interpreter shutdown.
    """
    if not timeout or timeout <= 0:
        return fn()
    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # re-raised on the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=_target, name=f"llm-call-{label}", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise LLMTimeoutError(f"{label} timed out after {timeout:.0f}s", timeout)
    if "error" in box:
        raise box["error"]
    return box.get("value")

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


def _drop_planning_edges(text: str) -> str:
    """Remove planning paragraphs from the start and end of a section."""
    planning_signals = (
        "the user wants",
        "the task:",
        "key points",
        "guidelines",
        "let me",
        "i need to",
        "i'll estimate",
        "draft:",
        "write ~",
        "check the character",
        "count words",
        "words:",
        "paragraph:",
    )
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    while paragraphs and any(
        signal in paragraphs[0].lower() for signal in planning_signals
    ):
        paragraphs.pop(0)
    while paragraphs and any(
        signal in paragraphs[-1].lower() for signal in planning_signals
    ):
        paragraphs.pop()
    return "\n\n".join(paragraphs).strip() if paragraphs else text.strip()


def extract_final_answer(text: str) -> str:
    """Extract the final answer when a model emits its planning alongside it.

    Some models (observed with glm-5.3-flash:cloud and thinking disabled) put
    "The user wants...", key points, and a "Draft:" section into the visible
    content. The last draft-style marker holds the real answer; planning
    paragraphs are then dropped from both edges of the result.
    """
    if not text:
        return text

    markers = (
        "draft:",
        "final answer:",
        "final description:",
        "final:",
        "description:",
        "answer:",
    )
    lowered = text.lower()
    best_index = -1
    best_marker = ""
    for marker in markers:
        index = lowered.rfind(marker)
        if index > best_index:
            best_index, best_marker = index, marker
    if best_index != -1:
        candidate = text[best_index + len(best_marker):]
        candidate = candidate.lstrip(" \t\r\n\"'“”")
        candidate = _drop_planning_edges(candidate)
        candidate = candidate.strip().strip("\"'“”").strip()
        if len(candidate) >= 120:
            return candidate

    return _drop_planning_edges(text)


def trim_to_sentence(text: str, limit: int) -> str:
    """Trim text to at most limit characters, preferring a sentence boundary.

    Whole sentences are kept while they fit. A single sentence longer than the
    limit is cut at a word boundary and closed with a period, so the result
    never ends mid-word or mid-thought without punctuation.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    import re as _re

    sentences = _re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for sentence in sentences:
        if not out:
            if len(sentence) > limit:
                cut = sentence[:limit]
                space = cut.rfind(" ")
                return (cut[:space].rstrip() + ".") if space > 0 else cut
            out = sentence
        elif len(out) + 1 + len(sentence) <= limit:
            out = out + " " + sentence
        else:
            break
    return out if out else text[:limit]


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
        self.host = config.get('host') or os.environ.get('OLLAMA_HOST') or 'http://localhost:11434'
        self.model = config.get('model', 'llama3')
        self.api_key = config.get('api_key', '')
        self.temperature = float(config.get('temperature', 0.7))
        self.max_tokens = int(config.get('max_tokens', 2048))
        self.num_ctx = int(config.get('num_ctx', 8192))
        self.timeout = _positive_float(
            config.get('timeout_seconds'), _DEFAULT_CALL_TIMEOUT_SECONDS
        )
        self.connect_timeout = _positive_float(
            config.get('connect_timeout_seconds'), _DEFAULT_CONNECT_TIMEOUT_SECONDS
        )

        try:
            import ollama
            self.ollama = ollama.Client(host=self.host, timeout=self.timeout)
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

    def _warn_if_truncated(self, response) -> None:
        if isinstance(response, dict):
            done_reason = response.get('done_reason')
        else:
            done_reason = getattr(response, 'done_reason', None)
        if done_reason == 'length':
            logger.warning(
                "Ollama response was truncated at the output token limit "
                "(max_tokens=%d). Raise the model's max_tokens or set "
                "llm.primary.ollama.think to false for non-reasoning tasks.",
                self.max_tokens,
            )

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send chat request to Ollama."""
        if not self.ollama:
            raise Exception("Ollama library not available") from None

        think = bool(self.config.get('think', False))
        try:
            call_kwargs = {
                'model': self.model,
                'messages': messages,
                'options': {
                    'temperature': self.temperature,
                    'num_ctx': self.num_ctx,
                    'num_predict': self.max_tokens,
                },
            }
            try:
                response = self.ollama.chat(think=think, **call_kwargs)
            except TypeError:
                response = self.ollama.chat(**call_kwargs)
            self._warn_if_truncated(response)
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
                "stream": False,
                "think": bool(self.config.get('think', False)),
                "options": {
                    "temperature": self.temperature,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.max_tokens,
                },
            }

            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                headers=self._headers(),
                timeout=(self.connect_timeout, self.timeout)
            )

            if response.status_code == 200:
                result = response.json()
                self._warn_if_truncated(result)
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
    """OpenAI-compatible LLM provider (supports xAI, Groq, OpenRouter, etc.)."""

    ENV_KEY = 'OPENAI_API_KEY'

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key') or os.getenv(self.ENV_KEY, '')
        self.model = config.get('model', 'gpt-3.5-turbo')
        self.base_url = config.get('base_url')
        self.temperature = float(config.get('temperature', 0.7))
        self.max_tokens = int(config.get('max_tokens', 2048))
        self.extra_headers = config.get('extra_headers') or None
        self.timeout = _positive_float(
            config.get('timeout_seconds'), _DEFAULT_CALL_TIMEOUT_SECONDS
        )

        if not self.api_key:
            raise ValueError(
                f"API key is required for OpenAI-compatible provider "
                f"(config api_key or {self.ENV_KEY})"
            )

        client_kwargs = {'api_key': self.api_key, 'timeout': self.timeout, 'max_retries': 0}
        if self.base_url:
            client_kwargs['base_url'] = self.base_url
        if self.extra_headers:
            client_kwargs['default_headers'] = self.extra_headers

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
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
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



class XAIProvider(OpenAIProvider):
    """xAI Grok LLM provider."""

    ENV_KEY = 'XAI_API_KEY'

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



class GroqProvider(OpenAIProvider):
    """Groq LLM provider."""

    ENV_KEY = 'GROQ_API_KEY'

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
        self.fallback_providers: list[LLMProvider] = []
        self.validator_provider = None
        self.operation_providers: dict[str, LLMProvider] = {}

        llm_config = config.get('llm', {}) if isinstance(config, dict) else {}
        self.call_timeout_seconds = _positive_float(
            llm_config.get('timeout_seconds'), _DEFAULT_CALL_TIMEOUT_SECONDS
        )
        self.connect_timeout_seconds = _positive_float(
            llm_config.get('connect_timeout_seconds'), _DEFAULT_CONNECT_TIMEOUT_SECONDS
        )
        self.total_budget_seconds = _positive_float(
            llm_config.get('total_budget_seconds'), _DEFAULT_TOTAL_BUDGET_SECONDS
        )

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
        self.fallback_providers: list[LLMProvider] = []
        if fallback_config.get('enabled', False):
            provider_types = list(fallback_config.get('providers', []))
            single = fallback_config.get('provider')
            if single and single not in provider_types:
                provider_types.insert(0, single)
            for fallback_provider_type in provider_types:
                fallback_provider_config = fallback_config.get(fallback_provider_type, {})
                try:
                    provider = self._create_provider(
                        fallback_provider_type,
                        fallback_provider_config
                    )
                    self.fallback_providers.append(provider)
                    logger.info(f"Fallback LLM provider initialized: {fallback_provider_type}")
                except Exception as e:
                    logger.info(f"Skipping fallback {fallback_provider_type}: {e}")
        else:
            logger.info("Fallback providers disabled in config")

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

        for operation_name, operation_config in llm_config.get('operations', {}).items():
            if not isinstance(operation_config, dict):
                continue
            override_provider = operation_config.get('provider')
            if not override_provider or 'model' not in operation_config:
                continue
            provider_config = {
                key: self._resolve_env_placeholders(value)
                for key, value in operation_config.items()
                if key != 'provider'
            }
            try:
                self.operation_providers[operation_name] = self._create_provider(
                    override_provider, provider_config.get(override_provider, provider_config)
                )
                logger.info(
                    f"Operation '{operation_name}' pinned to provider "
                    f"{self._get_provider_name(self.operation_providers[operation_name])}"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize operation provider for {operation_name}: {e}")

    @staticmethod
    def _resolve_env_placeholders(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: LLMManager._resolve_env_placeholders(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [LLMManager._resolve_env_placeholders(item) for item in value]
        if isinstance(value, str):
            if value.startswith('${') and value.endswith('}'):
                return os.getenv(value[2:-1], value) or value
            if value.startswith('$'):
                return os.getenv(value[1:], value) or value
        return value

    def _create_provider(self, provider_type: str, provider_config: dict[str, Any]) -> LLMProvider:
        """Create a provider instance based on type and config."""
        if provider_type == 'ollama':
            return OllamaProvider(provider_config)
        elif provider_type == 'openai':
            return OpenAIProvider(provider_config)
        elif provider_type == 'xai':
            return XAIProvider(provider_config)
        elif provider_type == 'groq':
            return GroqProvider(provider_config)
        elif provider_type == 'openrouter':
            return OpenRouterProvider(provider_config)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    def _describe_provider(self, provider) -> str:
        """Provider identity for logs and progress lines."""
        name = self._get_provider_name(provider)
        model = self._get_provider_model(provider)
        host = getattr(provider, 'host', None) or getattr(provider, 'base_url', None)
        if host:
            return f"{name}(model={model}, host={host})"
        return f"{name}(model={model})"

    def _run_provider_call(
        self,
        provider: LLMProvider,
        messages: list[dict[str, str]],
        operation: str,
        sermon_id: str | None,
        deadline: float,
    ) -> str:
        """Call one provider with a bounded wall-clock timeout and full logging."""
        label = self._describe_provider(provider)
        remaining = deadline - time.time()
        if remaining <= 0:
            raise LLMTimeoutError(
                f"LLM total budget of {self.total_budget_seconds:.0f}s exhausted "
                f"before calling {label}",
                self.total_budget_seconds,
            )
        call_timeout = min(self.call_timeout_seconds, remaining)
        logger.info(
            "LLM call starting: operation=%s provider=%s timeout=%.0fs",
            operation or "chat",
            label,
            call_timeout,
        )
        started = time.time()
        try:
            response = _call_with_deadline(
                lambda: provider.chat(messages), call_timeout, label
            )
        except LLMTimeoutError:
            duration_ms = int((time.time() - started) * 1000)
            logger.error(
                "LLM call timed out: operation=%s provider=%s after %.2fs",
                operation or "chat",
                label,
                duration_ms / 1000,
            )
            self._log_api_usage(
                provider=self._get_provider_name(provider),
                model=self._get_provider_model(provider),
                messages=messages,
                response="",
                duration_ms=duration_ms,
                operation=operation,
                sermon_id=sermon_id,
                status="error",
                error_message=f"timeout after {call_timeout:.0f}s",
            )
            raise
        except Exception as e:
            duration_ms = int((time.time() - started) * 1000)
            logger.warning(
                "LLM call failed: operation=%s provider=%s after %.2fs: %s",
                operation or "chat",
                label,
                duration_ms / 1000,
                e,
            )
            self._log_api_usage(
                provider=self._get_provider_name(provider),
                model=self._get_provider_model(provider),
                messages=messages,
                response="",
                duration_ms=duration_ms,
                operation=operation,
                sermon_id=sermon_id,
                status="error",
                error_message=str(e),
            )
            raise

        duration_ms = int((time.time() - started) * 1000)
        logger.info(
            "LLM call finished: operation=%s provider=%s duration=%.2fs chars=%d",
            operation or "chat",
            label,
            duration_ms / 1000,
            len(response or ""),
        )
        self._log_api_usage(
            provider=self._get_provider_name(provider),
            model=self._get_provider_model(provider),
            messages=messages,
            response=response,
            duration_ms=duration_ms,
            operation=operation,
            sermon_id=sermon_id,
            status="success",
        )
        return response

    def chat(
        self,
        messages: list[dict[str, str]],
        operation: str = "",
        sermon_id: str | None = None,
    ) -> str:
        """
        Send a chat request using primary provider with fallback support.

        Every provider call is bounded by ``llm.timeout_seconds`` (default 120)
        and the whole primary/fallback sequence by ``llm.total_budget_seconds``
        (default 300), so a hung or slow provider can never wedge the caller.
        Each call logs the provider, model, host, and duration.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            operation: The operation being performed (e.g., 'description_generation')
            sermon_id: The sermon ID for cost tracking

        Returns:
            Response content string

        Raises:
            LLMTimeoutError: If every attempt exceeded its deadline.
            Exception: If both primary and fallback providers fail.
        """
        start_time = time.time()
        deadline = start_time + self.total_budget_seconds
        timed_out = False

        operation_provider = self.operation_providers.get(operation) if operation else None
        if operation_provider:
            try:
                response = self._run_provider_call(
                    operation_provider, messages, operation, sermon_id, deadline
                )
                logger.info(
                    "Operation provider succeeded for %s: %s",
                    operation,
                    type(operation_provider).__name__,
                )
                return response
            except LLMTimeoutError as e:
                timed_out = True
                logger.warning("Operation provider for %s timed out: %s", operation, e)
            except Exception as e:
                logger.warning("Operation provider for %s failed: %s", operation, e)

        if self.primary_provider:
            try:
                response = self._run_provider_call(
                    self.primary_provider, messages, operation, sermon_id, deadline
                )
                logger.info(
                    "Primary provider succeeded: %s", type(self.primary_provider).__name__
                )
                return response
            except LLMTimeoutError as e:
                timed_out = True
                logger.warning("Primary provider timed out: %s", e)
            except Exception as e:
                logger.warning("Primary provider failed: %s", e)

        for fallback in self.fallback_providers:
            if time.time() >= deadline:
                logger.warning(
                    "LLM total budget of %.0fs exhausted before fallback %s",
                    self.total_budget_seconds,
                    type(fallback).__name__,
                )
                break
            try:
                response = self._run_provider_call(
                    fallback, messages, operation, sermon_id, deadline
                )
                logger.info("Fallback provider succeeded: %s", type(fallback).__name__)
                return response
            except LLMTimeoutError as e:
                timed_out = True
                logger.warning("Fallback provider timed out: %s", e)
            except Exception as e:
                logger.error("Fallback provider %s failed: %s", type(fallback).__name__, e)

        if timed_out:
            raise LLMTimeoutError(
                f"All LLM providers timed out (total budget "
                f"{self.total_budget_seconds:.0f}s)",
                self.total_budget_seconds,
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

    @staticmethod
    def _unknown_model_cost(model: str, total_tokens: int) -> float:
        logger.debug(f"No cost table entry for model '{model}'; tracking usage without cost")
        return 0.0

    def _estimate_cost(
        self, provider_name: str, model: str, input_tokens: int, output_tokens: int
    ) -> float:
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
        cost_per_token = (
            provider_costs.get(model.lower())
            or self._unknown_model_cost(model, input_tokens + output_tokens)
        ) / 1000

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
            logger.debug(
                f"Failed to log API usage: {e}"  # Don't let logging errors break the main flow
            )

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
            logger.info(
                "LLM call starting: operation=description_validation provider=%s timeout=%.0fs",
                self._describe_provider(self.validator_provider),
                self.call_timeout_seconds,
            )
            response = _call_with_deadline(
                lambda: self.validator_provider.chat(messages),
                self.call_timeout_seconds,
                self._describe_provider(self.validator_provider),
            )
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
            logger.info(
                "LLM call finished: operation=description_validation provider=%s "
                "duration=%.2fs chars=%d",
                self._describe_provider(self.validator_provider),
                duration_ms / 1000,
                len(response or ""),
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
                duration_ms = (
                    int((time.time() - start_time) * 1000)
                    if 'start_time' in locals() else 0
                )
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

        if self.fallback_providers:
            info['fallback'] = [
                {
                    'type': type(fb).__name__.replace('Provider', '').lower(),
                    'model': getattr(fb, 'model', 'unknown'),
                    'available': True,
                }
                for fb in self.fallback_providers
            ]

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
