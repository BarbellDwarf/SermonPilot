"""
Embedding Manager for handling multiple embedding providers with fallback support.
Supports OpenAI embeddings, Ollama embeddings, and various sentence-transformer models.
"""

import logging
import hashlib
import random
from typing import Any, List, Optional, Dict
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """Base class for embedding providers."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model_name = config.get('model', 'unknown')
        self.dimensions = config.get('dimensions', 384)  # Default dimension
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for the given texts."""
        raise NotImplementedError
    
    def get_embedding_dimension(self) -> int:
        """Get the embedding dimension for this provider."""
        return self.dimensions
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name})"


class SentenceTransformerProvider(EmbeddingProvider):
    """Sentence Transformers embedding provider (local models)."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_name = config.get('model', 'all-MiniLM-L6-v2')
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load the sentence transformer model."""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            
            # Get actual dimensions from the model
            self.dimensions = self.model.get_sentence_embedding_dimension()
            logger.info(f"Loaded SentenceTransformer model: {self.model_name} (dim: {self.dimensions})")
            
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model {self.model_name}: {e}")
            self.model = None
            raise
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
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
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.model_name = config.get('model', 'text-embedding-3-small')
        self.base_url = config.get('base_url')  # Custom endpoint support
        self.client = None
        
        # Model dimensions mapping
        self.model_dimensions = {
            'text-embedding-3-small': 1536,
            'text-embedding-3-large': 3072,
            'text-embedding-ada-002': 1536,
        }
        
        self.dimensions = self.model_dimensions.get(self.model_name, 1536)
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize OpenAI client."""
        if not self.api_key:
            raise ValueError("OpenAI API key is required for OpenAI embedding provider")
        
        try:
            import openai
            
            client_kwargs = {
                'api_key': self.api_key
            }
            
            if self.base_url:
                client_kwargs['base_url'] = self.base_url
            
            self.client = openai.OpenAI(**client_kwargs)
            logger.info(f"Initialized OpenAI embedding client for model: {self.model_name}")
            
        except ImportError:
            logger.error("OpenAI library not installed. Install with: pip install openai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API."""
        if self.client is None:
            raise RuntimeError("OpenAI client not initialized")
        
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=texts
            )
            
            embeddings = [embedding.embedding for embedding in response.data]
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings with OpenAI: {e}")
            raise


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider (local API)."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get('host', 'http://localhost:11434')
        self.model_name = config.get('model', 'nomic-embed-text')
        self.client = None
        
        # Common Ollama embedding model dimensions
        self.model_dimensions = {
            'nomic-embed-text': 768,
            'mxbai-embed-large': 1024,
            'snowflake-arctic-embed:xs': 384,
            'snowflake-arctic-embed:s': 384,
            'snowflake-arctic-embed:m': 768,
            'snowflake-arctic-embed:l': 1024,
        }
        
        self.dimensions = self.model_dimensions.get(self.model_name, 768)
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Ollama client."""
        try:
            import ollama
            import os
            
            # Set environment variable for Ollama host
            os.environ["OLLAMA_HOST"] = self.host
            self.client = ollama
            
            logger.info(f"Initialized Ollama embedding client for model: {self.model_name}")
            
        except ImportError:
            logger.error("Ollama library not installed. Install with: pip install ollama")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}")
            raise
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Ollama API."""
        if self.client is None:
            raise RuntimeError("Ollama client not initialized")
        
        try:
            embeddings = []
            for text in texts:
                response = self.client.embed(model=self.model_name, input=text)
                # The response structure may vary, handle different formats
                if hasattr(response, 'embedding'):
                    embeddings.append(response.embedding)
                elif isinstance(response, dict) and 'embedding' in response:
                    embeddings.append(response['embedding'])
                else:
                    raise ValueError(f"Unexpected response format from Ollama: {type(response)}")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings with Ollama: {e}")
            raise


class HashEmbeddingProvider(EmbeddingProvider):
    """Fallback hash-based embedding provider for offline mode."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.dimensions = config.get('dimensions', 384)
        logger.info(f"Initialized hash-based embedding provider (dim: {self.dimensions})")
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate deterministic hash-based embeddings."""
        embeddings = []
        for text in texts:
            # Create a deterministic but pseudo-random embedding based on text hash
            hash_value = hashlib.md5(text.encode()).hexdigest()
            random.seed(hash_value)
            # Create embedding vector with specified dimensions
            embedding = [random.random() - 0.5 for _ in range(self.dimensions)]
            embeddings.append(embedding)
        
        return embeddings


class EmbeddingManager:
    """Manages multiple embedding providers with fallback support."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.primary_provider = None
        self.fallback_providers = []
        self.current_provider = None
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize embedding providers based on configuration."""
        try:
            # Initialize primary provider
            primary_config = self.config.get('primary', {})
            if primary_config:
                self.primary_provider = self._create_provider(primary_config)
                self.current_provider = self.primary_provider
                logger.info(f"Primary embedding provider: {self.primary_provider}")
            
            # Initialize fallback providers
            fallback_configs = self.config.get('fallback', [])
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
                'provider': 'hash',
                'dimensions': self.primary_provider.get_embedding_dimension() if self.primary_provider else 384
            }
            hash_provider = self._create_provider(hash_config)
            self.fallback_providers.append(hash_provider)
            
            if not self.primary_provider and not self.fallback_providers:
                raise RuntimeError("No embedding providers could be initialized")
                
        except Exception as e:
            logger.error(f"Failed to initialize embedding manager: {e}")
            raise
    
    def _create_provider(self, config: Dict[str, Any]) -> EmbeddingProvider:
        """Create an embedding provider based on configuration."""
        provider_type = config.get('provider', '').lower()
        
        if provider_type == 'sentence_transformers' or provider_type == 'local':
            return SentenceTransformerProvider(config)
        elif provider_type == 'openai':
            return OpenAIEmbeddingProvider(config)
        elif provider_type == 'ollama':
            return OllamaEmbeddingProvider(config)
        elif provider_type == 'hash':
            return HashEmbeddingProvider(config)
        else:
            raise ValueError(f"Unknown embedding provider type: {provider_type}")
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings with automatic fallback on failure."""
        if not texts:
            return []
        
        # Try primary provider first
        if self.current_provider:
            try:
                embeddings = self.current_provider.get_embeddings(texts)
                logger.debug(f"Generated {len(embeddings)} embeddings using {self.current_provider}")
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
        elif self.primary_provider:
            return self.primary_provider.get_embedding_dimension()
        else:
            return 384  # Default dimension
    
    def get_current_provider_info(self) -> Dict[str, Any]:
        """Get information about the currently active provider."""
        if self.current_provider:
            return {
                'provider': self.current_provider.__class__.__name__,
                'model': self.current_provider.model_name,
                'dimensions': self.current_provider.get_embedding_dimension()
            }
        else:
            return {'provider': 'None', 'model': 'None', 'dimensions': 0}


def create_embedding_manager(config: Dict[str, Any]) -> EmbeddingManager:
    """Factory function to create an embedding manager from configuration."""
    return EmbeddingManager(config)


# Common embedding model configurations for easy reference
PRESET_EMBEDDING_MODELS = {
    'sentence_transformers': {
        'all-MiniLM-L6-v2': {'dimensions': 384, 'description': 'Fast, good quality (default)'},
        'all-mpnet-base-v2': {'dimensions': 768, 'description': 'Higher quality, slower'},
        'all-distilroberta-v1': {'dimensions': 768, 'description': 'Good balance of speed/quality'},
        'paraphrase-multilingual-MiniLM-L12-v2': {'dimensions': 384, 'description': 'Multilingual support'},
    },
    'openai': {
        'text-embedding-3-small': {'dimensions': 1536, 'description': 'Fast, cost-effective'},
        'text-embedding-3-large': {'dimensions': 3072, 'description': 'Highest quality'},
        'text-embedding-ada-002': {'dimensions': 1536, 'description': 'Legacy model'},
    },
    'ollama': {
        'nomic-embed-text': {'dimensions': 768, 'description': 'General purpose embedding'},
        'mxbai-embed-large': {'dimensions': 1024, 'description': 'High-quality embedding'},
        'snowflake-arctic-embed:s': {'dimensions': 384, 'description': 'Small, fast model'},
        'snowflake-arctic-embed:m': {'dimensions': 768, 'description': 'Medium model'},
        'snowflake-arctic-embed:l': {'dimensions': 1024, 'description': 'Large, high-quality model'},
    }
}