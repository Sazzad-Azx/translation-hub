"""
Supabase client for storing Intercom article mirror.
Uses Supabase REST API (requests) so no supabase package is required.
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

# Table name for mirrored articles
ARTICLES_TABLE = "intercom_articles"

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


def ensure_table_sql() -> str:
    """SQL to run in Supabase SQL Editor to create the articles table."""
    return (
        "-- Mirror of Intercom articles for dashboard and sync\n"
        "create table if not exists public.intercom_articles (\n"
        "  id uuid primary key default gen_random_uuid(),\n"
        "  intercom_id text not null unique,\n"
        "  title text not null,\n"
        "  description text,\n"
        "  body text,\n"
        "  collection_id text,\n"
        "  collection_name text,\n"
        "  state text,\n"
        "  synced_at timestamptz not null default now(),\n"
        "  created_at timestamptz not null default now(),\n"
        "  updated_at timestamptz not null default now()\n"
        ");\n"
        "create index if not exists idx_intercom_articles_intercom_id on public.intercom_articles(intercom_id);\n"
        "create index if not exists idx_intercom_articles_collection_name on public.intercom_articles(collection_name);"
    )


def article_from_intercom(article: Dict, collection_id: Optional[str] = None, collection_name: Optional[str] = None) -> Dict:
    """Build a row dict for intercom_articles from an Intercom article payload."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "intercom_id": str(article.get("id", "")),
        "title": article.get("title") or "",
        "description": article.get("description") or "",
        "body": article.get("body") or "",
        "collection_id": collection_id or "",
        "collection_name": collection_name or "",
        "state": article.get("state") or "",
        "synced_at": now,
        "updated_at": now,
    }


def upsert_articles(rows: List[Dict]) -> None:
    """Upsert article rows into intercom_articles (on conflict intercom_id update)."""
    if not rows or not REST_BASE:
        return
    url = f"{REST_BASE}/{ARTICLES_TABLE}"
    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    resp = requests.post(url, json=rows, headers=headers)
    resp.raise_for_status()


def list_articles(collection_name: Optional[str] = None) -> List[Dict]:
    """List articles from Supabase, optionally filtered by collection_name.
    Returns [] if the intercom_articles table does not exist (404)."""
    if not REST_BASE:
        raise ValueError("SUPABASE_URL must be set")
    url = f"{REST_BASE}/{ARTICLES_TABLE}"
    params = {"select": "*", "order": "title.asc"}
    if collection_name:
        params["collection_name"] = f"eq.{collection_name}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json() if resp.text else []
