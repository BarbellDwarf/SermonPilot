
import os

import ollama
import yaml


def main():
    print("Starting Ollama connection test...")
    # Load ollama_host from config.yaml if present
    ollama_host = None
    config = {}
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        print("Loaded config.yaml successfully.")
        ollama_host = config.get("ollama_host")
    except Exception as e:
        print("Could not read config.yaml:", e)

    if ollama_host:
        os.environ["OLLAMA_HOST"] = ollama_host
        print(f"Set OLLAMA_HOST to {ollama_host}")
    else:
        print("No ollama_host found in config.yaml. Using default.")

    try:
        print("Attempting to connect to Ollama...")
        response = ollama.chat(
            model=config.get("ollama_model", "llama3"),
            messages=[{"role": "user", "content": "Say hello."}]
        )
        print("Ollama connection successful.")
        print("Response:", response['message']['content'])
    except Exception as e:
        print("Failed to connect to Ollama:", e)

if __name__ == "__main__":
    main()
