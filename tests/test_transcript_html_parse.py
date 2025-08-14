import requests
from bs4 import BeautifulSoup

SERMON_ID = '1212241923147168'
url = f'https://www.sermonaudio.com/secure/gettranscript.asp?SID={SERMON_ID}'

r = requests.get(url)
soup = BeautifulSoup(r.text, 'html.parser')

# Try to find transcript content in <pre>, <div>, or <textarea> tags
transcript = None
for tag in ['pre', 'textarea', 'div']:
    el = soup.find(tag)
    if el and el.text.strip():
        transcript = el.text.strip()
        break

if transcript:
    print("Transcript found:")
    print(transcript[:2000])  # Print first 2000 chars
else:
    print("No transcript found in HTML.")
