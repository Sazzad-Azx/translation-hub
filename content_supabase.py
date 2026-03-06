"""
Write Intercom article data to Supabase tables:
  intercom_content_items, intercom_content_versions, (sync_runs optional)
Uses same REST API as supabase_client.
"""
import uuid
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""


def _headers() -> Dict[str, str]:
    if not SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_SERVICE_KEY must be set")
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def insert_content_item(intercom_article_id: str, workspace: str = "default", project: str = "default") -> Optional[str]:
    """
    Insert one row into intercom_content_items. Returns the new row id (uuid), or None if already exists (409).
    """
    item_id = str(uuid.uuid4())
    row = {
        "id": item_id,
        "workspace": workspace,
        "project": project,
        "external_id": str(intercom_article_id),
        "external_type": "article",
    }
    url = f"{REST_BASE}/intercom_content_items"
    resp = requests.post(url, json=row, headers=_headers(), timeout=30)
    if resp.status_code == 409:
        return None
    if not resp.ok:
        raise RuntimeError(f"Supabase intercom_content_items: {resp.status_code} {resp.text}")
    resp.raise_for_status()
    return item_id


def insert_content_version(
    content_item_id: str,
    locale: str,
    title: str,
    body_raw: str,
    body_normalized: Optional[dict] = None,
) -> None:
    """Insert one row into intercom_content_versions."""
    row = {
        "id": str(uuid.uuid4()),
        "content_item_id": content_item_id,
        "locale": locale or "en",
        "title": title or "",
        "body_raw": body_raw or "",
        "body_normalized": body_normalized if body_normalized is not None else {},
    }
    url = f"{REST_BASE}/intercom_content_versions"
    resp = requests.post(url, json=row, headers=_headers(), timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Supabase intercom_content_versions: {resp.status_code} {resp.text}")
    resp.raise_for_status()


def list_articles_from_content() -> List[Dict]:
    """
    List articles stored in intercom_content_items + intercom_content_versions
    (back-office storage from fetch_and_dump_10_articles). Returns one row per
    article with intercom_id, title, collection_name (empty for content store).
    """
    if not REST_BASE:
        return []
    try:
        items_url = f"{REST_BASE}/intercom_content_items"
        items_resp = requests.get(
            items_url,
            headers=_headers(),
            params={"select": "id,external_id"},
            timeout=30,
        )
        if not items_resp.ok:
            return []
        items = items_resp.json() if items_resp.text else []
        if not items:
            return []
        versions_url = f"{REST_BASE}/intercom_content_versions"
        versions_resp = requests.get(
            versions_url,
            headers=_headers(),
            params={"select": "content_item_id,title,locale"},
            timeout=30,
        )
        if not versions_resp.ok:
            return []
        versions = versions_resp.json() if versions_resp.text else []
        # Map content_item_id -> best version (prefer en, else first)
        by_item: Dict[str, Dict] = {}
        for v in versions:
            cid = v.get("content_item_id")
            if not cid:
                continue
            if cid not in by_item or (v.get("locale") == "en"):
                by_item[cid] = v
        # Build list: one per item, with title from version
        result = []
        for it in items:
            item_id = it.get("id")
            external_id = it.get("external_id")
            if not external_id:
                continue
            ver = by_item.get(item_id) if item_id else None
            title = (ver.get("title") or "").strip() if ver else ""
            result.append({
                "intercom_id": str(external_id),
                "title": title or "Untitled",
                "collection_name": "",
            })
        return result
    except Exception:
        return []


def dump_articles_to_supabase(articles: List[Dict]) -> int:
    """
    For each Intercom article, insert one intercom_content_item and one
    intercom_content_versions (default locale). Skips articles already in DB (409).
    Returns count of articles newly dumped.
    """
    if not REST_BASE:
        raise ValueError("SUPABASE_URL must be set")
    count = 0
    for article in articles:
        intercom_id = str(article.get("id", ""))
        if not intercom_id:
            continue
        item_id = insert_content_item(intercom_article_id=intercom_id)
        if item_id is None:
            continue
        title = article.get("title") or ""
        body = article.get("body") or ""
        locale = "en"
        insert_content_version(content_item_id=item_id, locale=locale, title=title, body_raw=body)
        count += 1
    return count
