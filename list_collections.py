"""List all Intercom help center collections (to find correct names)."""
import os
import json
from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("INTERCOM_ACCESS_TOKEN", "your_intercom_access_token_here")

from intercom_client import IntercomClient
client = IntercomClient()
# Get raw response to see structure
import requests
r = requests.get(
    "https://api.intercom.io/help_center/collections",
    headers=client.headers,
    params={"page": 1, "per_page": 50}
)
print("Status:", r.status_code)
data = r.json()
print("Keys:", list(data.keys()))
if "data" in data:
    print("Number of collections in data:", len(data["data"]))
    for c in data["data"][:15]:
        print(f"  id={c.get('id')}  name={repr(c.get('name'))}")
if "pages" in data:
    print("Pages:", data["pages"])
collections = client.get_collections()
print(f"\nget_collections() returned {len(collections)} collection(s):")
for c in collections[:15]:
    print(f"  id={c.get('id')}  name={repr(c.get('name'))}")
