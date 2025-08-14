
import datetime
import os

import requests
import yaml

BASE_URL = 'https://api.sermonaudio.com/v2/'

def get_api_key():
	key = os.getenv('SERMONAUDIO_API_KEY')
	if key:
		print("API key loaded from environment variable.")
		return key
	try:
		with open('config.yaml') as f:
			config = yaml.safe_load(f)
			api_key = config.get('api_key')
			print(f"API key loaded from config.yaml: {api_key}")
			return api_key
	except Exception as e:
		print(f"Error loading API key from config.yaml: {e}")
		return None

def get_broadcaster_id():
	bid = os.getenv('SERMONAUDIO_BROADCASTER_ID')
	if bid:
		print("Broadcaster ID loaded from environment variable.")
		return bid
	try:
		with open('config.yaml') as f:
			config = yaml.safe_load(f)
			broadcaster_id = config.get('broadcaster_id')
			print(f"Broadcaster ID loaded from config.yaml: {broadcaster_id}")
			return broadcaster_id
	except Exception as e:
		print(f"Error loading broadcaster ID from config.yaml: {e}")
		return None

def get_headers():
	api_key = get_api_key()
	if not api_key:
		raise Exception('API key not found')
	return {
		'X-Api-Key': api_key,
		'Content-Type': 'application/json',
	}

def create_test_sermon(title, speaker, date):
	url = BASE_URL + 'node/sermons'
	headers = get_headers()
	broadcaster_id = get_broadcaster_id()
	keywords = 'zechariah,old testament,prophecy,test'
	payload = {
		'broadcasterID': broadcaster_id,
		'displayTitle': title[:30],
		'fullTitle': title[:85],
		'speakerName': speaker,
		'preachDate': date,
		'acceptCopyright': True,
		'bibleText': 'Zechariah',
		'moreInfoText': 'This is a test description for Zechariah sermon.',
		'keywords': keywords,
		'eventType': 'Sunday Service',
		'languageCode': 'en',
	}
	resp = requests.post(url, headers=headers, json=payload)
	print(f"Create sermon status: {resp.status_code}")
	print(resp.text)
	if resp.status_code == 201:
		data = resp.json()
		print('Sermon created:', data)
		return data.get('sermonID') or data.get('sermon_id')
	else:
		print('Failed to create sermon:', resp.text)
		return None

def update_sermon(sermon_id, description, hashtags):
	url = BASE_URL + f'node/sermons/{sermon_id}'
	headers = get_headers()
	keywords = ','.join(hashtags)
	payload = {
		'moreInfoText': description,
		'bibleText': 'Zechariah',
		'keywords': keywords
	}
	resp = requests.patch(url, headers=headers, json=payload)
	print(f"Update sermon status: {resp.status_code}")
	print(resp.text)
	return resp.status_code in [200, 204]

def upload_audio(sermon_id, audio_path):
	print(f"Uploading audio for sermon {sermon_id} from {audio_path}")
	url = BASE_URL + 'media'
	headers = get_headers()
	payload = {
		'uploadType': 'original-audio',
		'sermonID': sermon_id
	}
	resp = requests.post(url, headers=headers, json=payload)
	print(f"Audio upload initiation status: {resp.status_code}")
	print(resp.text)
	if resp.status_code == 201:
		data = resp.json()
		upload_url = data.get('uploadURL')
		if upload_url:
			print(f"Direct upload URL: {upload_url}")
			try:
				# Read the audio file and upload directly to the provided URL
				with open(audio_path, 'rb') as audio_file:
					upload_resp = requests.post(upload_url, data=audio_file, headers={'Content-Type': 'audio/mpeg'})
					print(f"Direct upload status: {upload_resp.status_code}")
					if upload_resp.status_code in [200, 201, 204]:
						print("File uploaded successfully via direct HTTP upload.")
					else:
						print(f"Upload failed with status {upload_resp.status_code}: {upload_resp.text}")
			except Exception as e:
				print(f"Error uploading file via HTTP: {e}")
		else:
			print("No upload URL returned.")
	else:
		print("Failed to initiate audio upload.")

def main():
	today = datetime.date.today().isoformat()
	title = "Zechariah - Mark Hogan"
	speaker = "Mark Hogan"
	description = "Expository sermon on Zechariah. Covers prophecy and relevance for today."
	hashtags = ["zechariah", "prophecy", "old testament", "mark hogan"]
	audio_path = "tests/2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3"
	sermon_id = create_test_sermon(title, speaker, today)
	if not sermon_id:
		print("Sermon creation failed.")
		return
	updated = update_sermon(sermon_id, description, hashtags)
	if updated:
		print("Sermon updated successfully.")
	else:
		print("Sermon update failed.")
	upload_audio(sermon_id, audio_path)

if __name__ == "__main__":
	main()
