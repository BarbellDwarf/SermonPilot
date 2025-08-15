import requests


def main():
    try:
        resp = requests.get("http://localhost:11434")
        print("HTTP GET / response code:", resp.status_code)
        print("Response text (truncated):", resp.text[:200])
    except Exception as e:
        print("Failed to connect to Ollama HTTP endpoint:", e)

if __name__ == "__main__":
    main()
