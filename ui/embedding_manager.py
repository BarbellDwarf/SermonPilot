"""
Embedding Manager for handling multiple embedding providers with fallback support.
Supports OpenAI embeddings, Ollama embeddings, and various sentence-transformer models.
"""

import hashlib
import logging
import random
from typing import Any

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """Base class for embedding providers."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model_name = config.get("model", "unknown")
        self.dimensions = config.get("dimensions", 384)  # Default dimension

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for the given texts."""
        raise NotImplementedError

    def get_embedding_dimension(self) -> int:
        """Get the embedding dimension for this provider."""
        return self.dimensions

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name})"


class SentenceTransformerProvider(EmbeddingProvider):
    """Sentence Transformers embedding provider (local models)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.model_name = config.get("model", "all-MiniLM-L6-v2")
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the sentence transformer model."""
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.model_name)
            # Get actual dimensions from the model
            self.dimensions = self.model.get_sentence_embedding_dimension()
            logger.info(
                f"Loaded SentenceTransformer model: {self.model_name} (dim: {self.dimensions})"
            )
        except Exception as e:
            logger.error(
                f"Failed to load SentenceTransformer model {self.model_name}: {e}"
            )
            self.model = None
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using sentence transformers."""
        if self.model is None:
            raise RuntimeError("SentenceTransformer model not loaded")

        try:
            embeddings = self.model.encode(texts)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embeddings with SentenceTransformer: {e}")
            raise


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider (remote API)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.model_name = config.get("model", "text-embedding-3-small")
        self.base_url = config.get("base_url")  # Custom endpoint support
        self.client = None

        # Model dimensions mapping
        self.model_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

        self.dimensions = self.model_dimensions.get(self.model_name, 1536)
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize OpenAI client."""
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required for OpenAI embedding provider"
            )

        try:
            import openai

            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            self.client = openai.OpenAI(**client_kwargs)
            logger.info(
                f"Initialized OpenAI embedding client for model: {self.model_name}"
            )

        except ImportError:
            logger.error("OpenAI library not installed. Install with: pip install openai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using OpenAI API."""
        if self.client is None:
            raise RuntimeError("OpenAI client not initialized")

        try:
            response = self.client.embeddings.create(model=self.model_name, input=texts)
            embeddings = [embedding.embedding for embedding in response.data]
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings with OpenAI: {e}")
            raise


class XAIEmbeddingProvider(EmbeddingProvider):
    """xAI embedding provider (remote API)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.model_name = config.get("model", "text-embedding-3-small")
        self.base_url = config.get("base_url", "https://api.x.ai/v1")
        self.client = None

        # xAI model dimensions (similar to OpenAI)
        self.model_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
        }

        self.dimensions = self.model_dimensions.get(self.model_name, 1536)
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize xAI client."""
        if not self.api_key:
            raise ValueError("xAI API key is required for xAI embedding provider")

        try:
            import openai

            self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(
                f"Initialized xAI embedding client for model: {self.model_name}"
            )

        except ImportError:
            logger.error("OpenAI library not installed. Install with: pip install openai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize xAI client: {e}")
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using xAI API."""
        if self.client is None:
            raise RuntimeError("xAI client not initialized")

        try:
            response = self.client.embeddings.create(model=self.model_name, input=texts)
            embeddings = [embedding.embedding for embedding in response.data]
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings with xAI: {e}")
            raise


class HashEmbeddingProvider(EmbeddingProvider):
    """Fallback hash-based embedding provider for offline mode."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.dimensions = config.get("dimensions", 384)
        logger.info(
            f"Initialized hash-based embedding provider (dim: {self.dimensions})"
        )

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic hash-based embeddings."""
        embeddings: list[list[float]] = []
        for text in texts:
            # Create a deterministic but pseudo-random embedding based on text hash
            hash_value = hashlib.md5(text.encode()).hexdigest()
            random.seed(hash_value)
            # Create embedding vector with specified dimensions
            embedding = [random.random() - 0.5 for _ in range(self.dimensions)]
            embeddings.append(embedding)

        return embeddings


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider (local API)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host", "http://localhost:11434")
        self.model_name = config.get("model", "nomic-embed-text")
        self.auto_download = config.get("auto_download", False)
        self.client = None

        # Common Ollama embedding model dimensions
        self.model_dimensions = {
            "nomic-embed-text": 768,
            "mxbai-embed-large": 1024,
            "snowflake-arctic-embed:xs": 384,
            "snowflake-arctic-embed:s": 384,
            "snowflake-arctic-embed:m": 768,
            "snowflake-arctic-embed:l": 1024,
            "bge-large": 1024,
            "bge-base": 768,
            "bge-small": 384,
            "bge-m3": 1024,
            "bge-large-zh": 1024,
            "bge-large-en": 1024,
            "bge-large-zh-v1.5": 1024,
            "bge-large-en-v1.5": 1024,
            "all-minilm": 384,
            "paraphrase-multilingual": 384,
        }

        # Normalize model name for dimension lookup (strip any :tag like :latest)
        _dim_lookup_name = (
            self.model_name.split(":")[0]
            if isinstance(self.model_name, str)
            else self.model_name
        )
        self.dimensions = self.model_dimensions.get(_dim_lookup_name, 768)
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize Ollama client."""
        try:
            import os
            import ollama

            # Set environment variable for Ollama host
            os.environ["OLLAMA_HOST"] = self.host
            self.client = ollama

            # Check if model is available, download if auto_download is enabled
            self._ensure_model_available()

            logger.info(
                f"Initialized Ollama embedding client for model: {self.model_name}"
            )

        except ImportError:
            logger.error("Ollama library not installed. Install with: pip install ollama")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}")
            raise

    def _ensure_model_available(self) -> None:
        """Ensure the model is available, download if necessary."""
        if not self.client:
            return

        try:
            # Check if model exists
            models_list = self.client.list()
            items = models_list.get("models", []) if isinstance(models_list, dict) else []
            available_models: list[str] = []
            for m in items:
                try:
                    if isinstance(m, dict):
                        # Prefer 'model' (base name) but fall back to 'name' (tagged)
                        name = m.get("model") or m.get("name")
                    else:
                        # ollama library returns model objects with attribute 'model'
                        name = getattr(m, "model", None) or getattr(m, "name", None)
                    if name:
                        available_models.append(name)
                except Exception:
                    continue

            if self.model_name not in available_models:
                if self.auto_download:
                    logger.info(f"Model {self.model_name} not found. Downloading...")
                    self.client.pull(self.model_name)
                    logger.info(f"Successfully downloaded model: {self.model_name}")
                else:
                    logger.warning(
                        f"Model {self.model_name} not found and auto_download is disabled"
                    )
                    raise ValueError(
                        f"Model {self.model_name} not available and auto_download is disabled"
                    )
            else:
                logger.info(f"Model {self.model_name} is already available")

        except Exception as e:
            logger.error(f"Failed to check/download model {self.model_name}: {e}")
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Ollama API."""
        if self.client is None:
            raise RuntimeError("Ollama client not initialized")

        try:
            embeddings: list[list[float]] = []
            for text in texts:
                response = self.client.embed(model=self.model_name, input=text)
                
                # Handle different response formats
                if isinstance(response, dict):
                    if "embedding" in response and isinstance(response["embedding"], list):
                        embeddings.append(response["embedding"])  # single vector
                    elif (
                        "embeddings" in response
                        and isinstance(response["embeddings"], list)
                        and response["embeddings"]
                        and isinstance(response["embeddings"][0], list)
                    ):
                        # Might be [[...]] for one input; take the first
                        embeddings.append(response["embeddings"][0])
                    else:
                        raise ValueError(
                            f"Unexpected Ollama embed response keys: {list(response.keys())}"
                        )
                else:
                    # Handle modern Ollama response objects (EmbedResponse, etc.)
                    if hasattr(response, "embedding") and isinstance(response.embedding, list):
                        embeddings.append(response.embedding)
                    elif hasattr(response, "embeddings") and isinstance(response.embeddings, list):
                        if response.embeddings and isinstance(response.embeddings[0], list):
                            embeddings.append(response.embeddings[0])
                        else:
                            embeddings.append(response.embeddings)
                    else:
                        # Try to access as dict-like object
                        try:
                            if hasattr(response, '__getitem__'):
                                if "embedding" in response:
                                    embeddings.append(response["embedding"])
                                elif "embeddings" in response:
                                    embeddings.append(response["embeddings"][0] if response["embeddings"] else [])
                                else:
                                    raise ValueError(f"No embedding data found in response")
                            else:
                                raise ValueError(f"Unexpected response type from Ollama: {type(response)}")
                        except Exception as e:
                            logger.error(f"Failed to extract embedding from response: {e}")
                            logger.error(f"Response type: {type(response)}, attributes: {dir(response) if hasattr(response, '__dict__') else 'no __dict__'}")
                            raise ValueError(f"Cannot extract embedding from Ollama response: {type(response)}")

            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings with Ollama: {e}")
            raise


class AnthropicEmbeddingProvider(EmbeddingProvider):
    """Anthropic embedding provider (Claude)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.model_name = config.get("model", "claude-3-haiku-20240307")
        self.client = None

        # Model dimensions mapping
        self.model_dimensions = {
            "claude-3-haiku-20240307": 1536,
            "claude-3-sonnet-20240229": 1536,
            "claude-3-opus-20240229": 1536,
            "claude-3-5-sonnet-20240620": 1536,
        }

        self.dimensions = self.model_dimensions.get(self.model_name, 1536)
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize Anthropic client."""
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        try:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info(
                f"Initialized Anthropic embedding client for model: {self.model_name}"
            )

        except ImportError:
            logger.error(
                "Anthropic library not installed. Install with: pip install anthropic"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Anthropic API (placeholder strategy)."""
        if self.client is None:
            raise RuntimeError("Anthropic client not initialized")

        try:
            # Anthropic doesn't have a direct embedding API; use a deterministic fallback
            embeddings: list[list[float]] = []
            for text in texts:
                import hashlib as _hashlib

                hash_obj = _hashlib.md5(text.encode())
                hash_int = int(hash_obj.hexdigest(), 16)

                # Create deterministic embedding from hash
                embedding: list[float] = []
                for i in range(self.dimensions):
                    embedding.append(((hash_int >> (i % 32)) & 1) * 2 - 1)  # -1 or 1

                embeddings.append(embedding)

            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings with Anthropic: {e}")
            raise


class CohereEmbeddingProvider(EmbeddingProvider):
    """Cohere embedding provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.model_name = config.get("model", "embed-english-v3.0")
        self.client = None

        # Model dimensions mapping
        self.model_dimensions = {
            "embed-english-v3.0": 1024,
            "embed-multilingual-v3.0": 1024,
            "embed-english-light-v3.0": 384,
            "embed-multilingual-light-v3.0": 384,
        }

        self.dimensions = self.model_dimensions.get(self.model_name, 1024)
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize Cohere client."""
        if not self.api_key:
            raise ValueError("Cohere API key is required")

        try:
            import cohere

            self.client = cohere.Client(api_key=self.api_key)
            logger.info(
                f"Initialized Cohere embedding client for model: {self.model_name}"
            )

        except ImportError:
            logger.error("Cohere library not installed. Install with: pip install cohere")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Cohere client: {e}")
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Cohere API."""
        if self.client is None:
            raise RuntimeError("Cohere client not initialized")

        try:
            response = self.client.embed(
                texts=texts, model=self.model_name, input_type="search_document"
            )
            return response.embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings with Cohere: {e}")
            raise


class VoyageAIEmbeddingProvider(EmbeddingProvider):
    """VoyageAI embedding provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.model_name = config.get("model", "voyage-2")
        self.client = None

        # Model dimensions mapping
        self.model_dimensions = {
            "voyage-large-2": 1536,
            "voyage-code-2": 1536,
            "voyage-2": 1024,
            "voyage-large-2-instruct": 1536,
        }

        self.dimensions = self.model_dimensions.get(self.model_name, 1024)
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize VoyageAI client."""
        if not self.api_key:
            raise ValueError("VoyageAI API key is required")

        try:
            import voyageai

            voyageai.api_key = self.api_key
            self.client = voyageai
            logger.info(
                f"Initialized VoyageAI embedding client for model: {self.model_name}"
            )

        except ImportError:
            logger.error(
                "VoyageAI library not installed. Install with: pip install voyageai"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to initialize VoyageAI client: {e}")
            raise

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using VoyageAI API."""
        if self.client is None:
            raise RuntimeError("VoyageAI client not initialized")

        try:
            result = self.client.embed(texts, model=self.model_name, input_type="document")
            return result.embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings with VoyageAI: {e}")
            raise


class EmbeddingManager:
    """Manages multiple embedding providers with fallback support."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.primary_provider: EmbeddingProvider | None = None
        self.fallback_providers: list[EmbeddingProvider] = []
        self.current_provider: EmbeddingProvider | None = None
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize embedding providers based on configuration."""
        try:
            # Initialize primary provider
            primary_config = self.config.get("primary", {})
            if primary_config:
                self.primary_provider = self._create_provider(primary_config)
                self.current_provider = self.primary_provider
                logger.info(f"Primary embedding provider: {self.primary_provider}")

            # Initialize fallback providers
            fallback_configs = self.config.get("fallback", [])
            if not isinstance(fallback_configs, list):
                fallback_configs = [fallback_configs] if fallback_configs else []

            for fallback_config in fallback_configs:
                try:
                    provider = self._create_provider(fallback_config)
                    self.fallback_providers.append(provider)
                    logger.info(f"Fallback embedding provider: {provider}")
                except Exception as e:
                    logger.warning(f"Failed to initialize fallback provider: {e}")

            # Add hash fallback as final option
            hash_config = {
                "provider": "hash",
                "dimensions": self.primary_provider.get_embedding_dimension()
                if self.primary_provider
                else 384,
            }
            hash_provider = self._create_provider(hash_config)
            self.fallback_providers.append(hash_provider)

            if not self.primary_provider and not self.fallback_providers:
                raise RuntimeError("No embedding providers could be initialized")

        except Exception as e:
            logger.error(f"Failed to initialize embedding manager: {e}")
            raise

    def _create_provider(self, config: dict[str, Any]) -> EmbeddingProvider:
        """Create an embedding provider based on configuration."""
        provider_type = config.get("provider", "").lower()

        # Extract provider-specific config if it exists as a nested dict
        provider_config = config.get(provider_type, config)
        # Make sure the provider type is included in the config
        if isinstance(provider_config, dict):
            provider_config = {**provider_config, "provider": provider_type}
        else:
            provider_config = config

        if provider_type in ("sentence_transformers", "local"):
            return SentenceTransformerProvider(provider_config)
        if provider_type == "openai":
            return OpenAIEmbeddingProvider(provider_config)
        if provider_type == "xai":
            return XAIEmbeddingProvider(provider_config)
        if provider_type == "anthropic":
            return AnthropicEmbeddingProvider(provider_config)
        if provider_type == "cohere":
            return CohereEmbeddingProvider(provider_config)
        if provider_type == "voyageai":
            return VoyageAIEmbeddingProvider(provider_config)
        if provider_type == "ollama":
            return OllamaEmbeddingProvider(provider_config)
        if provider_type == "hash":
            return HashEmbeddingProvider(provider_config)

        raise ValueError(f"Unknown embedding provider type: {provider_type}")

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings with automatic fallback on failure."""
        if not texts:
            return []

        # Try primary provider first
        if self.current_provider:
            try:
                embeddings = self.current_provider.get_embeddings(texts)
                logger.debug(
                    f"Generated {len(embeddings)} embeddings using {self.current_provider}"
                )
                return embeddings
            except Exception as e:
                logger.warning(f"Primary provider {self.current_provider} failed: {e}")
                self.current_provider = None

        # Try fallback providers
        for provider in self.fallback_providers:
            try:
                embeddings = provider.get_embeddings(texts)
                logger.info(f"Using fallback provider: {provider}")
                self.current_provider = provider
                return embeddings
            except Exception as e:
                logger.warning(f"Fallback provider {provider} failed: {e}")
                continue

        raise RuntimeError("All embedding providers failed")

    def get_embedding_dimension(self) -> int:
        """Get the embedding dimension of the current provider."""
        if self.current_provider:
            return self.current_provider.get_embedding_dimension()
        if self.primary_provider:
            return self.primary_provider.get_embedding_dimension()
        return 384  # Default dimension

    def get_current_provider_info(self) -> dict[str, Any]:
        """Get information about the currently active provider."""
        if self.current_provider:
            return {
                "provider": self.current_provider.__class__.__name__,
                "model": self.current_provider.model_name,
                "dimensions": self.current_provider.get_embedding_dimension(),
            }
        return {"provider": "None", "model": "None", "dimensions": 0}


def create_embedding_manager(config: dict[str, Any]) -> EmbeddingManager:
    """Factory function to create an embedding manager from configuration."""
    return EmbeddingManager(config)


# Common embedding model configurations for easy reference
PRESET_EMBEDDING_MODELS = {
    "sentence_transformers": {
        "all-MiniLM-L6-v2": {
            "dimensions": 384,
            "description": "Fast, good quality (default)",
        },
        "all-mpnet-base-v2": {
            "dimensions": 768,
            "description": "Higher quality, slower",
        },
        "all-distilroberta-v1": {
            "dimensions": 768,
            "description": "Good balance of speed/quality",
        },
        "paraphrase-multilingual-MiniLM-L12-v2": {
            "dimensions": 384,
            "description": "Multilingual support",
        },
    },
    "openai": {
        "text-embedding-3-small": {
            "dimensions": 1536,
            "description": "Fast, cost-effective",
        },
        "text-embedding-3-large": {
            "dimensions": 3072,
            "description": "Highest quality",
        },
        "text-embedding-ada-002": {
            "dimensions": 1536,
            "description": "Legacy model",
        },
    },
    "xai": {
        "text-embedding-3-small": {
            "dimensions": 1536,
            "description": "Fast, cost-effective",
        },
        "text-embedding-3-large": {
            "dimensions": 3072,
            "description": "Highest quality",
        },
    },
    "anthropic": {
        "claude-3-haiku-20240307": {
            "dimensions": 1536,
            "description": "Fast, efficient model",
        },
        "claude-3-sonnet-20240229": {
            "dimensions": 1536,
            "description": "Balanced performance",
        },
        "claude-3-opus-20240229": {
            "dimensions": 1536,
            "description": "Highest quality",
        },
        "claude-3-5-sonnet-20240620": {
            "dimensions": 1536,
            "description": "Latest high-performance model",
        },
    },
    "cohere": {
        "embed-english-v3.0": {
            "dimensions": 1024,
            "description": "English embeddings v3",
        },
        "embed-multilingual-v3.0": {
            "dimensions": 1024,
            "description": "Multilingual v3",
        },
        "embed-english-light-v3.0": {
            "dimensions": 384,
            "description": "Light English model",
        },
        "embed-multilingual-light-v3.0": {
            "dimensions": 384,
            "description": "Light multilingual",
        },
    },
    "voyageai": {
        "voyage-large-2": {
            "dimensions": 1536,
            "description": "Large, high-quality model",
        },
        "voyage-code-2": {
            "dimensions": 1536,
            "description": "Code-specialized embeddings",
        },
        "voyage-2": {
            "dimensions": 1024,
            "description": "Balanced performance",
        },
        "voyage-large-2-instruct": {
            "dimensions": 1536,
            "description": "Instruction-tuned model",
        },
    },
    "ollama": {
        "nomic-embed-text": {
            "dimensions": 768,
            "description": "General purpose embedding",
        },
        "mxbai-embed-large": {
            "dimensions": 1024,
            "description": "High-quality embedding",
        },
        "snowflake-arctic-embed:s": {
            "dimensions": 384,
            "description": "Small, fast model",
        },
        "snowflake-arctic-embed:m": {
            "dimensions": 768,
            "description": "Medium model",
        },
        "snowflake-arctic-embed:l": {
            "dimensions": 1024,
            "description": "Large, high-quality",
        },
    },
}
