import json

import requests
import yaml


def test_ollama_http():
    # Load config
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        ollama_host = config.get("ollama_host", "http://localhost:11434")
        print(f"Testing Ollama at: {ollama_host}")
    except Exception as e:
        print(f"Error loading config: {e}")
        ollama_host = "http://localhost:11434"

    # Test 1: Basic connectivity
    try:
        print("\n=== Test 1: Basic connectivity ===")
        response = requests.get(f"{ollama_host}/", timeout=5)
        print(f"GET {ollama_host}/ - Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Basic connectivity failed: {e}")
        return False

    # Test 2: List models
    try:
        print("\n=== Test 2: List models ===")
        response = requests.get(f"{ollama_host}/api/tags", timeout=10)
        print(f"GET {ollama_host}/api/tags - Status: {response.status_code}")
        if response.status_code == 200:
            models = response.json()
            print(f"Available models: {json.dumps(models, indent=2)}")
            return models.get('models', [])
        else:
            print(f"Failed to list models: {response.text}")
    except Exception as e:
        print(f"List models failed: {e}")

    return []

def test_ollama_chat(model_name):
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        ollama_host = config.get("ollama_host", "http://localhost:11434")
    except:
        ollama_host = "http://localhost:11434"

    print(f"\n=== Test 3: Chat with model {model_name} ===")
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Say hello in one word."}],
        "stream": False
    }

    try:
        response = requests.post(f"{ollama_host}/api/chat",
                               json=payload,
                               timeout=30)
        print(f"POST {ollama_host}/api/chat - Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Chat response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"Chat failed: {response.text}")
    except Exception as e:
        print(f"Chat request failed: {e}")

    return False

if __name__ == "__main__":
    print("Testing Ollama HTTP connection directly...")

    # Test basic connectivity and get models
    models = test_ollama_http()

    if models:
        # Try to chat with the first available model
        first_model = models[0]['name']
        print(f"\nTrying to chat with first available model: {first_model}")
        test_ollama_chat(first_model)

        # Also try with the configured model
        try:
            with open("config.yaml") as f:
                config = yaml.safe_load(f)
            configured_model = config.get("ollama_model", "llama3.1:8b")
            if any(m['name'] == configured_model for m in models):
                print(f"\nTrying to chat with configured model: {configured_model}")
                test_ollama_chat(configured_model)
            else:
                print(f"\nConfigured model '{configured_model}' not found in available models")
                print("Available models:")
                for model in models:
                    print(f"  - {model['name']}")
        except Exception as e:
            print(f"Error checking configured model: {e}")
    else:
        print("\nNo models available or connection failed")
