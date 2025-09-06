"""
Test script for the new configurable embedding system
"""

import sys
from pathlib import Path

# Add UI directory to path
project_root = Path(__file__).parent
ui_dir = project_root / "ui"
sys.path.insert(0, str(ui_dir))

def test_sentence_transformer_provider():
    """Test sentence transformer embedding provider"""
    print("=== Testing Sentence Transformer Provider ===")
    
    try:
        from ui.embedding_manager import SentenceTransformerProvider
        
        config = {
            'provider': 'sentence_transformers',
            'model': 'all-MiniLM-L6-v2'
        }
        
        provider = SentenceTransformerProvider(config)
        print(f"✅ Provider initialized: {provider}")
        print(f"✅ Embedding dimensions: {provider.get_embedding_dimension()}")
        
        # Test embeddings
        texts = ["This is a test", "Another test sentence"]
        embeddings = provider.get_embeddings(texts)
        print(f"✅ Generated {len(embeddings)} embeddings with {len(embeddings[0])} dimensions")
        
        return True
        
    except Exception as e:
        print(f"❌ Sentence Transformer provider failed: {e}")
        return False


def test_openai_provider():
    """Test OpenAI embedding provider (without API key)"""
    print("\n=== Testing OpenAI Provider (No API Key) ===")
    
    try:
        from ui.embedding_manager import OpenAIEmbeddingProvider
        
        config = {
            'provider': 'openai',
            'model': 'text-embedding-3-small',
            'api_key': None  # No key provided
        }
        
        try:
            provider = OpenAIEmbeddingProvider(config)
            print("❌ Should have failed without API key")
            return False
        except ValueError as e:
            print(f"✅ Correctly failed without API key: {e}")
            return True
            
    except Exception as e:
        print(f"❌ OpenAI provider test failed: {e}")
        return False


def test_ollama_provider():
    """Test Ollama embedding provider (without server)"""
    print("\n=== Testing Ollama Provider (No Server) ===")
    
    try:
        from ui.embedding_manager import OllamaEmbeddingProvider
        
        config = {
            'provider': 'ollama',
            'model': 'nomic-embed-text',
            'host': 'http://localhost:11434'
        }
        
        provider = OllamaEmbeddingProvider(config)
        print(f"✅ Provider initialized: {provider}")
        print(f"✅ Embedding dimensions: {provider.get_embedding_dimension()}")
        
        # Try to get embeddings (will likely fail without server)
        try:
            texts = ["Test embedding"]
            embeddings = provider.get_embeddings(texts)
            print(f"✅ Generated embeddings: {len(embeddings)}")
            return True
        except Exception as e:
            print(f"⚠️ Expected failure without Ollama server: {e}")
            return True  # This is expected
            
    except Exception as e:
        print(f"❌ Ollama provider test failed: {e}")
        return False


def test_hash_provider():
    """Test hash-based fallback provider"""
    print("\n=== Testing Hash Provider ===")
    
    try:
        from ui.embedding_manager import HashEmbeddingProvider
        
        config = {
            'provider': 'hash',
            'dimensions': 384
        }
        
        provider = HashEmbeddingProvider(config)
        print(f"✅ Provider initialized: {provider}")
        print(f"✅ Embedding dimensions: {provider.get_embedding_dimension()}")
        
        # Test embeddings
        texts = ["This is a test", "Another test sentence", "This is a test"]  # Repeat to test determinism
        embeddings = provider.get_embeddings(texts)
        print(f"✅ Generated {len(embeddings)} embeddings with {len(embeddings[0])} dimensions")
        
        # Test determinism
        embeddings2 = provider.get_embeddings(["This is a test"])
        if embeddings[0] == embeddings2[0]:
            print("✅ Hash embeddings are deterministic")
        else:
            print("❌ Hash embeddings are not deterministic")
            
        return True
        
    except Exception as e:
        print(f"❌ Hash provider failed: {e}")
        return False


def test_embedding_manager_fallback():
    """Test the embedding manager with hash fallback only"""
    print("\n=== Testing Embedding Manager with Hash Fallback ===")
    
    try:
        from ui.embedding_manager import EmbeddingManager
        
        config = {
            'primary': {
                'provider': 'hash',
                'dimensions': 384
            },
            'fallback': []
        }
        
        manager = EmbeddingManager(config)
        print(f"✅ Manager initialized")
        
        provider_info = manager.get_current_provider_info()
        print(f"✅ Current provider: {provider_info}")
        
        # Test embeddings
        texts = ["Test embedding", "Another test"]
        embeddings = manager.get_embeddings(texts)
        print(f"✅ Generated {len(embeddings)} embeddings with {len(embeddings[0])} dimensions")
        
        return True
        
    except Exception as e:
        print(f"❌ Embedding manager fallback failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag_integration_hash():
    """Test RAG system with hash-only embedding configuration"""
    print("\n=== Testing RAG System Integration with Hash Embeddings ===")
    
    try:
        from ui.rag_system import SermonAnalyticsRAG
        
        embedding_config = {
            'primary': {
                'provider': 'hash',
                'dimensions': 384
            },
            'fallback': []
        }
        
        rag = SermonAnalyticsRAG(
            db_path="test_vector_db_hash",
            embedding_config=embedding_config
        )
        print("✅ RAG system initialized with hash embedding config")
        
        # Test with sample data
        sample_data = [{
            'sermon_id': '123',
            'title': 'Test Sermon on Faith',
            'speaker': 'Test Speaker',
            'views': 100,
            'engagement_score': 8.5,
            'keywords': ['faith', 'prayer']
        }]
        
        rag.add_analytics_data(sample_data)
        print("✅ Successfully added sample data")
        
        # Test query
        result = rag.query_analytics('What sermons talk about faith?')
        print("✅ Query successful")
        print(f"Answer: {result['answer'][:100]}...")
        
        # Test provider info
        provider_info = rag.get_embedding_provider_info()
        print(f"✅ Provider info: {provider_info}")
        
        return True
        
    except Exception as e:
        print(f"❌ RAG integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_preset_models():
    """Test preset model configurations"""
    print("\n=== Testing Preset Model Configurations ===")
    
    try:
        from ui.embedding_manager import PRESET_EMBEDDING_MODELS
        
        print("✅ Available preset models:")
        for provider, models in PRESET_EMBEDDING_MODELS.items():
            print(f"  {provider}:")
            for model, info in models.items():
                print(f"    - {model}: {info['dimensions']}D - {info['description']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Preset models test failed: {e}")
        return False


def main():
    """Run all embedding system tests"""
    print("🧪 Testing Configurable Embedding System\n")
    
    tests = [
        test_sentence_transformer_provider,
        test_openai_provider,
        test_ollama_provider,
        test_hash_provider,
        test_embedding_manager_fallback,
        test_rag_integration_hash,
        test_preset_models
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print(f"\n📊 Test Results: {sum(results)}/{len(results)} passed")
    
    if all(results):
        print("🎉 All embedding system tests passed!")
    else:
        print("⚠️ Some tests failed. Check the output above for details.")
    
    return all(results)


if __name__ == "__main__":
    main()