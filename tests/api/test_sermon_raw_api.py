import os

import requests

API_KEY = os.getenv('SERMONAUDIO_API_KEY')
SERMON_ID = '1212241923147168'

# Try the documented v2 API endpoint for a sermon
def get_sermon_raw(sermon_id):
    url = f'https://api.sermonaudio.com/v2/sermons/{sermon_id}'
    headers = {'Authorization': f'Bearer {API_KEY}'}
    r = requests.get(url, headers=headers)
    print(f"Status: {r.status_code}")
    print(r.json())

if __name__ == '__main__':
    get_sermon_raw(SERMON_ID)
