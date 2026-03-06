"""
Translation persistence in Supabase (article_translations table).
Server-side only: uses SUPABASE_SERVICE_KEY. Browser must NOT have service role key.
"""
import uuid
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from content_supabase import _headers, insert_content_item, REST_BASE

TRANSLATIONS_TABLE = "article_translations"


def get_or_create_content_item_id(parent_intercom_article_id: str) -> str:
    """
    Return content_item_id (uuid) for the given Intercom article id.
    Looks up intercom_content_items by external_id; if not found, inserts one and returns its id.
    """
    if not REST_BASE:
        raise ValueError("SUPABASE_URL must be set")
    pid = str(parent_intercom_article_id).strip()
    if not pid:
        raise ValueError("parent_intercom_article_id is required")
    url = f"{REST_BASE}/intercom_content_items"
    resp = requests.get(
        url,
        headers=_headers(),
        params={"select": "id", "external_id": f"eq.{pid}"},
        timeout=30,
    )
    if resp.ok and resp.text:
        rows = resp.json()
        if isinstance(rows, list) and len(rows) > 0:
            return str(rows[0]["id"])
    item_id = insert_content_item(intercom_article_id=pid)
    if item_id:
        return item_id
    resp2 = requests.get(
        url,
        headers=_headers(),
        params={"select": "id", "external_id": f"eq.{pid}"},
        timeout=30,
    )
    if resp2.ok and resp2.text:
        rows = resp2.json()
        if isinstance(rows, list) and len(rows) > 0:
            return str(rows[0]["id"])
    raise RuntimeError(f"Could not get or create content_item for intercom article {pid}")


def upsert_article_translation(
    parent_intercom_article_id: str,
    target_locale: str,
    translated_title: str,
    translated_body_html: str,
    status: str = "draft",
    source_locale: str = "en",
    engine: Optional[str] = None,
    model: Optional[str] = None,
    source_checksum: Optional[str] = None,
) -> Dict:
    """
    Upsert one row into article_translations (unique on parent_intercom_article_id, target_locale).
    Resolves content_item_id via get_or_create_content_item_id.
    Returns the saved row (with id, created_at, updated_at).
    """
    if not REST_BASE:
        raise ValueError("SUPABASE_URL must be set")
    content_item_id = get_or_create_content_item_id(parent_intercom_article_id)
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "content_item_id": content_item_id,
        "parent_intercom_article_id": str(parent_intercom_article_id),
        "source_locale": source_locale or "en",
        "target_locale": str(target_locale),
        "translated_title": translated_title or "",
        "translated_body_html": translated_body_html or "",
        "status": status if status in ("draft", "ready") else "draft",
        "engine": engine or "",
        "model": model or "",
        "source_checksum": source_checksum or "",
        "updated_at": now,
    }
    url = f"{REST_BASE}/{TRANSLATIONS_TABLE}"
    headers = dict(_headers())
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    resp = requests.post(url, json=row, headers=headers, timeout=30)
    if not resp.ok:
        # If 409 (duplicate), try PATCH to update existing
        if resp.status_code == 409:
            # Get existing translation ID
            get_url = f"{REST_BASE}/{TRANSLATIONS_TABLE}"
            get_resp = requests.get(
                get_url,
                headers=headers,
                params={
                    "parent_intercom_article_id": f"eq.{parent_intercom_article_id}",
                    "target_locale": f"eq.{target_locale}",
                    "select": "id"
                },
                timeout=30
            )
            if get_resp.ok and get_resp.text:
                existing = get_resp.json()
                if existing and len(existing) > 0:
                    trans_id = existing[0].get('id')
                    # Update using PATCH
                    patch_url = f"{REST_BASE}/{TRANSLATIONS_TABLE}?id=eq.{trans_id}"
                    patch_headers = dict(_headers())
                    patch_headers["Prefer"] = "return=representation"
                    patch_resp = requests.patch(patch_url, json=row, headers=patch_headers, timeout=30)
                    if patch_resp.ok:
                        try:
                            return patch_resp.json()[0] if isinstance(patch_resp.json(), list) else patch_resp.json()
                        except:
                            return row
        raise RuntimeError(f"Supabase article_translations: {resp.status_code} {resp.text[:500]}")
    try:
        out = resp.json()
    except Exception as e:
        raise RuntimeError(f"Supabase returned non-JSON: {resp.text[:200]}") from e
    if isinstance(out, list) and len(out) > 0:
        return out[0]
    return row


def list_article_translations() -> List[Dict]:
    """List all saved translations (for Saved Translations UI). Ordered by updated_at desc."""
    if not REST_BASE:
        return []
    try:
        url = f"{REST_BASE}/{TRANSLATIONS_TABLE}"
        headers = dict(_headers())
        headers.pop("Prefer", None)
        resp = requests.get(
            url,
            headers=headers,
            params={
                "select": "id,content_item_id,parent_intercom_article_id,source_locale,target_locale,translated_title,status,created_at,updated_at",
                "order": "updated_at.desc",
            },
            timeout=30,
        )
        if not resp.ok:
            return []
        data = resp.json() if resp.text else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_article_translation_by_id(translation_id: str) -> Optional[Dict]:
    """Fetch one translation by id (for viewing saved HTML)."""
    if not REST_BASE or not translation_id:
        return None
    try:
        url = f"{REST_BASE}/{TRANSLATIONS_TABLE}"
        headers = dict(_headers())
        headers.pop("Prefer", None)
        resp = requests.get(
            url,
            headers=headers,
            params={"select": "*", "id": f"eq.{translation_id}"},
            timeout=30,
        )
        if not resp.ok or not resp.text:
            return None
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None
    except Exception:
        return None
