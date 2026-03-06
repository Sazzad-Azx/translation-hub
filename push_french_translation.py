"""Directly push French translation to Intercom article 13830625"""
import os
import requests
import json
from dotenv import load_dotenv
load_dotenv()

os.environ['INTERCOM_ACCESS_TOKEN'] = 'your_intercom_access_token_here'
os.environ['OPENAI_API_KEY'] = 'your_openai_api_key_here'
os.environ['OPENAI_MODEL'] = 'gpt-4o-mini'

TOKEN = os.environ['INTERCOM_ACCESS_TOKEN']
ARTICLE_ID = "13830625"

# First, translate the article using GPT
from translator import GPTTranslator

# Get article content from Intercom
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Intercom-Version": "2.10"
}

print("1. Getting article from Intercom...")
resp = requests.get(f"https://api.intercom.io/articles/{ARTICLE_ID}", headers=HEADERS, timeout=30)
article = resp.json()
print(f"   Title: {article.get('title')}")
print(f"   Author ID: {article.get('author_id')}")

# Translate
print("\n2. Translating to French...")
translator = GPTTranslator()
translated = translator.translate_article(article, target_language='fr', source_language='en')
print(f"   French title: {translated['title']}")
print(f"   French body (first 200 chars): {translated['body'][:200]}")

# Push translation using PUT /articles/{id} with translated_content
print("\n3. Pushing French translation to Intercom...")

# Method 1: Using translated_content in the PUT body
update_data = {
    "author_id": article.get("author_id"),
    "translated_content": {
        "type": "article_translated_content",
        "fr": {
            "type": "article_content",
            "title": translated["title"],
            "description": translated.get("description", ""),
            "body": translated["body"],
            "author_id": article.get("author_id"),
            "state": "published"
        }
    }
}

print(f"   Sending PUT request...")
resp = requests.put(
    f"https://api.intercom.io/articles/{ARTICLE_ID}",
    headers=HEADERS,
    json=update_data,
    timeout=30
)
print(f"   Status: {resp.status_code}")
if resp.ok:
    result = resp.json()
    tc = result.get("translated_content")
    print(f"   Success!")
    if tc:
        print(f"   Translated content keys: {list(tc.keys()) if isinstance(tc, dict) else 'N/A'}")
        if isinstance(tc, dict) and 'fr' in tc:
            fr = tc['fr']
            print(f"   French title: {fr.get('title', 'N/A')[:80]}")
    print(f"\n   Article URL (EN): {result.get('url', 'N/A')}")
    # Try French URL
    en_url = result.get('url', '')
    if '/en/' in en_url:
        fr_url = en_url.replace('/en/', '/fr/')
        print(f"   Article URL (FR): {fr_url}")
else:
    print(f"   Error: {resp.text[:500]}")
    
    # Method 2: Try with Intercom-Version 2.14
    print("\n   Retrying with API version 2.14...")
    HEADERS14 = dict(HEADERS)
    HEADERS14["Intercom-Version"] = "2.14"
    
    resp2 = requests.put(
        f"https://api.intercom.io/articles/{ARTICLE_ID}",
        headers=HEADERS14,
        json=update_data,
        timeout=30
    )
    print(f"   Status: {resp2.status_code}")
    if resp2.ok:
        result2 = resp2.json()
        tc2 = result2.get("translated_content")
        print(f"   Success!")
        if tc2:
            print(f"   Translated content: {json.dumps(tc2, indent=2, ensure_ascii=False)[:500]}")
    else:
        print(f"   Error: {resp2.text[:500]}")

# Verify
print("\n4. Verifying...")
resp = requests.get(f"https://api.intercom.io/articles/{ARTICLE_ID}", headers=HEADERS, timeout=30)
data = resp.json()
tc = data.get("translated_content")
print(f"   translated_content present: {tc is not None}")
if tc and isinstance(tc, dict):
    print(f"   Languages: {[k for k in tc.keys() if k != 'type']}")
    if 'fr' in tc:
        print(f"   French title: {tc['fr'].get('title', 'N/A')[:80]}")
