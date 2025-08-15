import requests
import yaml

SERMON_ID = "1212241923147168"
API_URL = f"https://api.sermonaudio.com/v2/node/sermons/{SERMON_ID}"

def get_api_key():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    return config["api_key"]

def main():
    api_key = get_api_key()
    headers = {"X-Api-Key": api_key}
    resp = requests.get(API_URL, headers=headers)
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print("Error response:", resp.text)
        return
    data = resp.json()
    transcript = data.get("transcript")
    if transcript:
        print("Transcript object:", transcript)
        download_url = transcript.get("downloadURL")
        if download_url:
            print("Transcript download URL:", download_url)
        else:
            print("Transcript object present, but no download URL.")
    else:
        print("No transcript available for this sermon.")

if __name__ == "__main__":
    main()
