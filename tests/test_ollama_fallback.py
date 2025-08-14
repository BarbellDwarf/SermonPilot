import os

import requests
import yaml

# Load configuration FIRST to set environment variables
with open('config.yaml') as f:
    config = yaml.safe_load(f)

# Set OLLAMA_HOST BEFORE importing ollama
ollama_host = config.get('ollama_host')
if ollama_host:
    os.environ["OLLAMA_HOST"] = ollama_host
    print(f"Set OLLAMA_HOST to {ollama_host}")

# NOW import ollama after setting environment
import ollama


def ollama_chat_with_fallback(model, messages):
    """
    Try ollama library first, then fallback to direct HTTP request if it fails.
    """
    # Try the ollama library first
    try:
        print("Trying ollama library...")
        response = ollama.chat(model=model, messages=messages)
        print("Ollama library succeeded!")
        return response['message']['content']
    except Exception as e:
        print(f"Ollama library failed: {e}")
        print("Trying direct HTTP request...")

        # Fallback to direct HTTP request
        try:
            ollama_host = config.get('ollama_host', 'http://localhost:11434')
            payload = {
                "model": model,
                "messages": messages,
                "stream": False
            }

            response = requests.post(f"{ollama_host}/api/chat",
                                   json=payload,
                                   timeout=30)

            if response.status_code == 200:
                result = response.json()
                print("Direct HTTP request succeeded!")
                return result['message']['content']
            else:
                print(f"HTTP request failed with status {response.status_code}: {response.text}")
                raise Exception(f"HTTP request failed: {response.status_code}")
        except Exception as http_e:
            print(f"Direct HTTP request also failed: {http_e}")
            raise http_e

if __name__ == "__main__":
    print("Testing Ollama with fallback mechanism...")

    try:
        result = ollama_chat_with_fallback(
            model=config.get('ollama_model', 'llama3.1:8b'),
            messages=[{'role': 'user', 'content': 'Say hello in one sentence.'}]
        )
        print(f"Success! Response: {result}")
    except Exception as e:
        print(f"All methods failed: {e}")
