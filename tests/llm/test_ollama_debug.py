import ollama

print("Ollama module location:", ollama.__file__)
print("Ollama module version:", getattr(ollama, '__version__', 'unknown'))

try:
    print("Trying ollama.list()...")
    models = ollama.list()
    print("Models:", models)
except Exception as e:
    print("ollama.list() failed:", e)

try:
    print("Trying ollama.chat() with available model...")
    # Try with a model that is running, e.g. deepseek-r1:7b
    response = ollama.chat(
        model="deepseek-r1:7b",
        messages=[{"role": "user", "content": "Say hello."}]
    )
    print("Ollama chat response:", response['message']['content'])
except Exception as e:
    print("ollama.chat() failed:", e)
