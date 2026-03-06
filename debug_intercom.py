"""Debug Intercom API to find the article"""
import os
import requests
import json
from dotenv import load_dotenv
load_dotenv()

os.environ['INTERCOM_ACCESS_TOKEN'] = 'your_intercom_access_token_here'

TOKEN = os.environ['INTERCOM_ACCESS_TOKEN']
BASE = "https://api.intercom.io"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Intercom-Version": "2.14"
}

def api_get(endpoint, params=None):
    r = requests.get(f"{BASE}{endpoint}", headers=HEADERS, params=params, timeout=30)
    return r

print("=" * 60)
print("STEP 1: List articles from /articles endpoint")
print("=" * 60)

resp = api_get("/articles", {"page": 1, "per_page": 50})
print(f"Status: {resp.status_code}")
if resp.ok:
    data = resp.json()
    articles = data.get("data", [])
    total = data.get("total_count", "?")
    pages = data.get("pages", {})
    print(f"Total articles: {total}")
    print(f"Articles in this page: {len(articles)}")
    print(f"Pages info: {json.dumps(pages, indent=2)}")
    
    target = "can i reset my monthly competition"
    print(f"\nSearching for: '{target}'")
    for a in articles:
        title = a.get("title", "")
        print(f"  ID: {a.get('id')}, Title: {title[:80]}, State: {a.get('state', '?')}")
        if target in title.lower():
            print(f"  >>> MATCH FOUND! ID = {a.get('id')}")
    
    # Check more pages
    page = 2
    while pages.get("next"):
        print(f"\nFetching page {page}...")
        resp = api_get("/articles", {"page": page, "per_page": 50})
        if not resp.ok:
            break
        data = resp.json()
        articles = data.get("data", [])
        pages = data.get("pages", {})
        print(f"Articles in page {page}: {len(articles)}")
        for a in articles:
            title = a.get("title", "")
            print(f"  ID: {a.get('id')}, Title: {title[:80]}, State: {a.get('state', '?')}")
            if target in title.lower():
                print(f"  >>> MATCH FOUND! ID = {a.get('id')}")
        page += 1
        if page > 20:
            break
else:
    print(f"Error: {resp.text[:300]}")

print("\n" + "=" * 60)
print("STEP 2: Try search endpoint")
print("=" * 60)

resp = api_get("/articles/search", {"phrase": "Competition account breached", "state": "published"})
print(f"Status: {resp.status_code}")
if resp.ok:
    data = resp.json()
    articles = (data.get("data") or {}).get("articles") or data.get("data", [])
    print(f"Results: {len(articles) if isinstance(articles, list) else 'N/A'}")
    if isinstance(articles, list):
        for a in articles:
            print(f"  ID: {a.get('id')}, Title: {a.get('title', '')[:80]}")
else:
    print(f"Error: {resp.text[:300]}")

print("\n" + "=" * 60)
print("STEP 3: List Help Centers")
print("=" * 60)

resp = api_get("/help_center/help_centers")
print(f"Status: {resp.status_code}")
if resp.ok:
    data = resp.json()
    centers = data.get("data", [])
    print(f"Help centers: {len(centers)}")
    for hc in centers:
        print(f"  ID: {hc.get('id')}, Name: {hc.get('display_name') or hc.get('name', '?')}")
else:
    print(f"Error: {resp.text[:300]}")

print("\n" + "=" * 60)
print("STEP 4: List Collections")
print("=" * 60)

resp = api_get("/help_center/collections", {"per_page": 50})
print(f"Status: {resp.status_code}")
if resp.ok:
    data = resp.json()
    collections = data.get("data", [])
    print(f"Collections: {len(collections)}")
    for c in collections:
        print(f"  ID: {c.get('id')}, Name: {c.get('name', '?')}")
else:
    print(f"Error: {resp.text[:300]}")

print("\n" + "=" * 60)
print("STEP 5: Try different API versions")
print("=" * 60)

for version in ["2.10", "2.11", "Unstable"]:
    headers_v = dict(HEADERS)
    headers_v["Intercom-Version"] = version
    resp = requests.get(f"{BASE}/articles", headers=headers_v, params={"page": 1, "per_page": 5}, timeout=30)
    print(f"Version {version}: Status={resp.status_code}, Articles={len(resp.json().get('data', []))}" if resp.ok else f"Version {version}: Error {resp.status_code}")
