"""List Intercom articles and show structure (parent/collection)."""
import os
import json
from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("INTERCOM_ACCESS_TOKEN", "your_intercom_access_token_here")

from intercom_client import IntercomClient
client = IntercomClient()
articles = client.get_articles()
print(f"Total articles (no filter): {len(articles)}")
for i, a in enumerate(articles[:5]):
    print(f"\n--- Article {i+1} ---")
    print(f"  id: {a.get('id')}")
    print(f"  title: {a.get('title')}")
    print(f"  parent_id: {a.get('parent_id')}")
    print(f"  parent_type: {a.get('parent_type')}")
    print(f"  parent_ids: {a.get('parent_ids')}")
    # Show all keys
    for k in sorted(a.keys()):
        if k not in ("body", "statistics"):
            v = a[k]
            if isinstance(v, (dict, list)) and len(str(v)) > 80:
                v = f"<{type(v).__name__} len={len(v)}>"
            print(f"  {k}: {v}")
