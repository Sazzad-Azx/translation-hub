"""Debug Intercom API - try different regions and approaches"""
import os
import requests
import json
from dotenv import load_dotenv
load_dotenv()

TOKEN = 'your_intercom_access_token_here'

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Intercom-Version": "2.10"
}

# Try different Intercom API regions
print("=" * 60)
print("Testing different Intercom API regions")
print("=" * 60)

for base in ["https://api.intercom.io", "https://api.eu.intercom.io", "https://api.au.intercom.io"]:
    try:
        resp = requests.get(f"{base}/articles", headers=HEADERS, params={"page": 1, "per_page": 50}, timeout=10)
        if resp.ok:
            data = resp.json()
            articles = data.get("data", [])
            total = data.get("total_count", len(articles))
            print(f"{base}: {total} articles")
            for a in articles[:5]:
                print(f"  ID: {a.get('id')}, Title: {a.get('title', '')[:60]}")
        else:
            print(f"{base}: Error {resp.status_code} - {resp.text[:100]}")
    except Exception as e:
        print(f"{base}: Exception - {str(e)[:100]}")

# Try to get article 9037183 from each region
print("\n" + "=" * 60)
print("Trying to access article 9037183 from each region")
print("=" * 60)

for base in ["https://api.intercom.io", "https://api.eu.intercom.io", "https://api.au.intercom.io"]:
    try:
        resp = requests.get(f"{base}/articles/9037183", headers=HEADERS, timeout=10)
        print(f"{base}/articles/9037183: Status {resp.status_code}")
        if resp.ok:
            data = resp.json()
            print(f"  Title: {data.get('title', '?')}")
            print(f"  State: {data.get('state', '?')}")
    except Exception as e:
        print(f"{base}: Exception - {str(e)[:100]}")

# Try to list ALL articles across all states  
print("\n" + "=" * 60)
print("Listing all articles (all states)")
print("=" * 60)

for state in ["published", "draft", "all"]:
    try:
        resp = requests.get("https://api.intercom.io/articles/search", 
                          headers=HEADERS, 
                          params={"state": state, "per_page": 50}, 
                          timeout=10)
        if resp.ok:
            data = resp.json()
            articles_data = data.get("data", {})
            if isinstance(articles_data, dict):
                articles = articles_data.get("articles", [])
            else:
                articles = articles_data
            print(f"State '{state}': {len(articles)} articles")
        else:
            print(f"State '{state}': Error {resp.status_code}")
    except Exception as e:
        print(f"State '{state}': Exception - {str(e)[:100]}")

# Check if there's a way to use /me endpoint
print("\n" + "=" * 60)
print("Checking /me endpoint for workspace info")
print("=" * 60)

try:
    resp = requests.get("https://api.intercom.io/me", headers=HEADERS, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        print(f"App ID: {data.get('app', {}).get('id_code', '?')}")
        print(f"Name: {data.get('name', '?')}")
        print(f"Type: {data.get('type', '?')}")
        print(json.dumps(data, indent=2)[:500])
except Exception as e:
    print(f"Exception: {str(e)[:200]}")
