"""
Sync service: copy Intercom articles into Supabase (mirror).
"""
from typing import List, Dict, Optional

from intercom_client import IntercomClient
from supabase_client import (
    article_from_intercom,
    upsert_articles,
    list_articles as supabase_list_articles,
)
from config import INTERCOM_ACCESS_TOKEN


def sync_collection_from_intercom(
    collection_name: str,
    intercom_client: Optional[IntercomClient] = None,
) -> Dict:
    """
    Pull all articles from the given Intercom collection (by name, e.g. 'About FundedNext')
    and upsert them into Supabase. Returns summary.
    If the collection is not found, syncs all articles from Intercom instead (fallback).
    """
    client = intercom_client or IntercomClient()
    # Get collection by name: list collections and find matching name
    collections = client.get_collections()
    collection_id = None
    name_used = None
    for c in collections:
        name = (c.get("name") or "").strip()
        if name and collection_name.lower() in name.lower():
            collection_id = c.get("id")
            name_used = name
            break
    if collection_id:
        articles = client.get_articles(collection_id=collection_id)
    else:
        # Fallback: sync all articles when collection not found (e.g. no collections set up yet)
        articles = client.get_articles()
        name_used = collection_name + " (all articles; collection not found)"
    rows = [
        article_from_intercom(a, collection_id=str(collection_id) if collection_id else "", collection_name=name_used)
        for a in articles
    ]
    if not rows:
        return {
            "success": True,
            "collection_id": str(collection_id) if collection_id else None,
            "collection_name": name_used,
            "synced": 0,
            "articles": [],
            "note": "No articles to sync.",
        }
    upsert_articles(rows)
    return {
        "success": True,
        "collection_id": str(collection_id) if collection_id else None,
        "collection_name": name_used,
        "synced": len(rows),
        "articles": [{"intercom_id": r["intercom_id"], "title": r["title"]} for r in rows],
    }


def sync_by_collection_id(collection_id: str, collection_name: str, intercom_client: Optional[IntercomClient] = None) -> Dict:
    """Sync articles from Intercom by collection ID."""
    client = intercom_client or IntercomClient()
    articles = client.get_articles(collection_id=collection_id)
    rows = [
        article_from_intercom(a, collection_id=str(collection_id), collection_name=collection_name)
        for a in articles
    ]
    upsert_articles(rows)
    return {
        "success": True,
        "collection_id": str(collection_id),
        "collection_name": collection_name,
        "synced": len(rows),
        "articles": [{"intercom_id": r["intercom_id"], "title": r["title"]} for r in rows],
    }


def get_dashboard_articles(collection_name: Optional[str] = None) -> List[Dict]:
    """Return articles from Supabase for the dashboard."""
    return supabase_list_articles(collection_name=collection_name)
