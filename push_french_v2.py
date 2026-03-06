"""Try multiple Intercom API approaches for adding French translation"""
import os
import requests
import json
from dotenv import load_dotenv
load_dotenv()

TOKEN = 'your_intercom_access_token_here'
ARTICLE_ID = "13830625"

os.environ['OPENAI_API_KEY'] = 'your_openai_api_key_here'
os.environ['OPENAI_MODEL'] = 'gpt-4o-mini'

from translator import GPTTranslator

# Translate
print("Translating article to French...")
translator = GPTTranslator()

# Get article
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

for version in ["Unstable", "2.14", "2.10", "2.6"]:
    h = dict(HEADERS)
    h["Intercom-Version"] = version
    resp = requests.get(f"https://api.intercom.io/articles/{ARTICLE_ID}", headers=h, timeout=30)
    if resp.ok:
        data = resp.json()
        tc = data.get("translated_content")
        keys = list(data.keys())
        print(f"\nAPI v{version}: translated_content={'yes' if tc else 'no'}, keys={[k for k in keys if 'translat' in k.lower()]}")
        if tc:
            print(f"  translated_content: {json.dumps(tc, indent=2, ensure_ascii=False)[:300]}")

article = resp.json()
translated = translator.translate_article(article, target_language='fr', source_language='en')

# Try approach: PUT with translated_content using different structures
print("\n" + "=" * 60)
print("Trying different translated_content structures...")
print("=" * 60)

structures = [
    # Structure 1: Simple locale dict
    {
        "title": article.get("title"),
        "author_id": article.get("author_id"),
        "translated_content": {
            "fr": {
                "title": translated["title"],
                "body": translated["body"],
                "state": "published"
            }
        }
    },
    # Structure 2: With type fields
    {
        "title": article.get("title"),
        "author_id": article.get("author_id"),
        "translated_content": {
            "type": "article_translated_content",
            "fr": {
                "type": "article_content",
                "title": translated["title"],
                "body": translated["body"],
                "state": "published",
                "author_id": article.get("author_id")
            }
        }
    },
    # Structure 3: Flat update with locale  
    {
        "title": translated["title"],
        "body": translated["body"],
        "author_id": article.get("author_id"),
        "locale": "fr",
        "state": "published"
    },
]

for i, update_data in enumerate(structures):
    for version in ["Unstable", "2.10"]:
        h = dict(HEADERS)
        h["Intercom-Version"] = version
        
        resp = requests.put(
            f"https://api.intercom.io/articles/{ARTICLE_ID}",
            headers=h,
            json=update_data,
            timeout=30
        )
        
        if resp.ok:
            result = resp.json()
            tc = result.get("translated_content")
            title = result.get("title", "")
            print(f"\nStructure {i+1} + v{version}: Status {resp.status_code}, title='{title[:50]}', translated_content={'yes' if tc else 'no'}")
            if tc and isinstance(tc, dict):
                print(f"  Languages: {[k for k in tc.keys() if k != 'type']}")
                if 'fr' in tc:
                    print(f"  FR title: {tc['fr'].get('title', 'N/A')[:80]}")
        else:
            print(f"\nStructure {i+1} + v{version}: Status {resp.status_code}, Error: {resp.text[:200]}")

# Final verification
print("\n" + "=" * 60)
print("Final verification")
print("=" * 60)

for version in ["Unstable", "2.10"]:
    h = dict(HEADERS)
    h["Intercom-Version"] = version
    resp = requests.get(f"https://api.intercom.io/articles/{ARTICLE_ID}", headers=h, timeout=30)
    if resp.ok:
        data = resp.json()
        tc = data.get("translated_content")
        title = data.get("title", "")
        url = data.get("url", "")
        print(f"\nv{version}: title='{title[:50]}', url={url}")
        print(f"  translated_content: {json.dumps(tc, indent=2, ensure_ascii=False)[:500] if tc else 'None'}")
