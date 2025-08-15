import requests

SERMON_ID = '1212241923147168'
url = f'https://www.sermonaudio.com/secure/gettranscript.asp?SID={SERMON_ID}'

r = requests.get(url)
print(f"Status: {r.status_code}")
print(r.text[:2000])  # Print first 2000 chars for inspection
