"""
Create the article in Intercom (if not present) and translate it to French.
"""
import os
import sys
import requests
from dotenv import load_dotenv
load_dotenv()

os.environ['INTERCOM_ACCESS_TOKEN'] = 'your_intercom_access_token_here'
os.environ['OPENAI_API_KEY'] = 'your_openai_api_key_here'
os.environ['OPENAI_MODEL'] = 'gpt-4o-mini'

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from workflow import TranslationWorkflow

def get_article_from_supabase(target_title):
    """Get article content from Supabase content tables"""
    REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    
    # Check content_items + versions
    items_url = f"{REST_BASE}/intercom_content_items"
    items_resp = requests.get(items_url, headers=headers, params={"select": "id,external_id"}, timeout=30)
    if not items_resp.ok:
        print(f"Failed to query Supabase: {items_resp.status_code}")
        return None
    
    items = items_resp.json() if items_resp.text else []
    versions_url = f"{REST_BASE}/intercom_content_versions"
    
    for item in items:
        item_id = item.get('id')
        versions_resp = requests.get(
            versions_url,
            headers=headers,
            params={"content_item_id": f"eq.{item_id}", "select": "title,body_raw,locale"},
            timeout=30,
        )
        if versions_resp.ok:
            versions = versions_resp.json() if versions_resp.text else []
            for v in versions:
                if v.get('locale') == 'en' and target_title.lower() in (v.get('title') or '').lower():
                    return {
                        'id': item.get('external_id'),
                        'title': v.get('title', ''),
                        'description': '',
                        'body': v.get('body_raw', ''),
                    }
    return None


def main():
    target = "Can I reset my monthly Competition account after it is breached?"
    
    print("=" * 60)
    print("Translate Article to French & Update Intercom")
    print("=" * 60)
    
    # 1. Get article from Supabase
    print(f"\n1. Fetching article from Supabase...")
    article = get_article_from_supabase(target)
    if not article:
        print("   Article not found in Supabase!")
        return 1
    
    print(f"   Found: {article['title']}")
    print(f"   Original Intercom ID: {article['id']}")
    print(f"   Body length: {len(article.get('body', ''))} chars")
    
    # 2. Run the workflow
    print(f"\n2. Running translation workflow...")
    workflow = TranslationWorkflow()
    result = workflow.process_article(article, languages=['fr'])
    
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"Article: {result['article_title']}")
    print(f"Translations: {result['translations']}")
    if result['errors']:
        print(f"Errors: {result['errors']}")
        return 1
    
    print("\nDone! The article has been created in Intercom and translated to French.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
