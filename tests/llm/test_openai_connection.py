
import openai
import yaml


def main():
    print("Starting OpenAI (Ollama endpoint) connection test...")
    # Load OpenAI-compatible endpoint from config.yaml if present
    openai_api_base = None
    config = {}
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        print("Loaded config.yaml successfully.")
        openai_api_base = config.get("openai_api_base")
    except Exception as e:
        print("Could not read config.yaml:", e)

    # Ollama's OpenAI endpoint does not require authentication
    openai.api_key = "sk-no-auth-required"
    if openai_api_base:
        openai.api_base = openai_api_base
        print(f"Set OpenAI API base to {openai_api_base}")
    else:
        print("No openai_api_base found in config.yaml. Please set it to your Ollama OpenAI endpoint, e.g. http://localhost:11434/v1")
        return

    try:
        print("Attempting to connect to Ollama OpenAI endpoint...")
        response = openai.ChatCompletion.create(
            model=config.get("openai_model", "llama3"),
            messages=[{"role": "user", "content": "Say hello."}]
        )
        print("Ollama OpenAI endpoint connection successful.")
        print("Response:", response['choices'][0]['message']['content'])
    except Exception as e:
        print("Failed to connect to Ollama OpenAI endpoint:", e)

if __name__ == "__main__":
    main()
