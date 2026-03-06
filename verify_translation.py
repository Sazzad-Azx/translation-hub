"""Verify the article and its French translation in Intercom"""
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

ARTICLE_ID = "13830625"

print("Verifying article in Intercom...")
resp = requests.get(f"https://api.intercom.io/articles/{ARTICLE_ID}", headers=HEADERS, timeout=30)

if resp.ok:
    data = resp.json()
    print(f"\nArticle found!")
    print(f"  ID: {data.get('id')}")
    print(f"  Title: {data.get('title')}")
    print(f"  State: {data.get('state')}")
    print(f"  URL: {data.get('url', 'N/A')}")
    
    # Check translated_content
    translated = data.get("translated_content", {})
    if translated:
        print(f"\n  Translations:")
        if isinstance(translated, dict):
            for locale, content in translated.items():
                if isinstance(content, dict) and content.get("title"):
                    print(f"    [{locale}] {content.get('title', 'N/A')[:80]}")
    else:
        print("\n  No translated_content field in response")
    
    # Print full response (truncated)
    print(f"\n  Full response (first 1000 chars):")
    print(f"  {json.dumps(data, indent=2)[:1000]}")
else:
    print(f"Error: {resp.status_code} - {resp.text[:300]}")
