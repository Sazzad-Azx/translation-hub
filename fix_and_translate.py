"""
Fix: Restore English article and create a proper French translation on Intercom.
Since the workspace doesn't support translated_content, we'll use a direct approach.
"""
import os
import requests
import json
from dotenv import load_dotenv
load_dotenv()

TOKEN = 'your_intercom_access_token_here'
ARTICLE_ID = "13830625"

os.environ['INTERCOM_ACCESS_TOKEN'] = TOKEN
os.environ['OPENAI_API_KEY'] = 'your_openai_api_key_here'
os.environ['OPENAI_MODEL'] = 'gpt-4o-mini'

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Intercom-Version": "2.10"
}

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

# 1. Get original English content from Supabase
print("1. Getting original English content from Supabase...")
REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
sb_headers = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

items_resp = requests.get(
    f"{REST_BASE}/intercom_content_items",
    headers=sb_headers,
    params={"external_id": "eq.9037183", "select": "id"},
    timeout=30,
)
items = items_resp.json()
item_id = items[0]['id']

versions_resp = requests.get(
    f"{REST_BASE}/intercom_content_versions",
    headers=sb_headers,
    params={"content_item_id": f"eq.{item_id}", "locale": "eq.en", "select": "title,body_raw"},
    timeout=30,
)
versions = versions_resp.json()
en_title = versions[0]['title']
en_body = versions[0]['body_raw']
print(f"   English title: {en_title}")

# 2. Restore English content on article
print("\n2. Restoring English content on article...")
resp = requests.put(
    f"https://api.intercom.io/articles/{ARTICLE_ID}",
    headers=HEADERS,
    json={
        "title": en_title,
        "body": en_body,
        "author_id": 6821315,
        "state": "published"
    },
    timeout=30
)
print(f"   Status: {resp.status_code}")
if resp.ok:
    print(f"   English article restored: {resp.json().get('title', '')[:60]}")

# 3. Translate to French
print("\n3. Translating to French...")
from translator import GPTTranslator
translator = GPTTranslator()
article = {"title": en_title, "body": en_body, "description": ""}
translated = translator.translate_article(article, target_language='fr', source_language='en')
fr_title = translated['title']
fr_body = translated['body']
print(f"   French title: {fr_title}")

# 4. Create a separate French article in Intercom
print("\n4. Creating French article in Intercom...")
from intercom_client import IntercomClient
client = IntercomClient()

fr_article = client.create_article(
    title=f"[FR] {fr_title}",
    body=fr_body,
    description="",
    state="published"
)
fr_article_id = fr_article.get("id")
print(f"   Created French article ID: {fr_article_id}")
print(f"   URL: {fr_article.get('url', 'N/A')}")

# 5. Verify both articles
print("\n5. Verifying both articles in Intercom...")
resp_en = requests.get(f"https://api.intercom.io/articles/{ARTICLE_ID}", headers=HEADERS, timeout=30)
resp_fr = requests.get(f"https://api.intercom.io/articles/{fr_article_id}", headers=HEADERS, timeout=30)

if resp_en.ok:
    en_data = resp_en.json()
    print(f"\n   English article:")
    print(f"     ID: {en_data.get('id')}")
    print(f"     Title: {en_data.get('title')}")
    print(f"     State: {en_data.get('state')}")
    print(f"     URL: {en_data.get('url')}")

if resp_fr.ok:
    fr_data = resp_fr.json()
    print(f"\n   French article:")
    print(f"     ID: {fr_data.get('id')}")
    print(f"     Title: {fr_data.get('title')}")
    print(f"     State: {fr_data.get('state')}")
    print(f"     URL: {fr_data.get('url')}")

print("\n" + "=" * 60)
print("DONE! Both English and French articles are now on Intercom.")
print("=" * 60)

# List all articles in Intercom for confirmation
print("\nAll articles in Intercom workspace:")
resp_all = requests.get("https://api.intercom.io/articles", headers=HEADERS, params={"per_page": 50}, timeout=30)
if resp_all.ok:
    all_articles = resp_all.json().get("data", [])
    for a in all_articles:
        print(f"  [{a.get('state', '?')}] ID: {a.get('id')}, Title: {a.get('title', '')[:70]}")
