"""
Pull Service – fetches articles from Intercom and stores snapshots in Supabase pull_registry.

Table: pull_registry
Columns: id, intercom_id, title, description, state, url, source_updated_at,
         pulled_at, pull_status, pull_error, content_hash, body_html,
         author_id, collection_id, collection_name, created_at, updated_at
"""
import hashlib
import re
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

# Pattern matching translated article titles created by Push Approach 3
# e.g. "[FA] Some Title", "[ZH-CN] Some Title"
_LOCALE_PREFIX_RE = re.compile(r'^\[[A-Z]{2}(?:-[A-Z]{1,4})?\]\s+', re.IGNORECASE)

REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
TABLE = "pull_registry"

SETUP_SQL = """
CREATE TABLE IF NOT EXISTS public.pull_registry (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    intercom_id     text NOT NULL UNIQUE,
    title           text NOT NULL DEFAULT '',
    description     text DEFAULT '',
    state           text DEFAULT 'published',
    url             text DEFAULT '',
    source_updated_at timestamptz,
    pulled_at       timestamptz,
    pull_status     text DEFAULT NULL,
    pull_error      text DEFAULT '',
    content_hash    text DEFAULT '',
    body_html       text DEFAULT '',
    author_id       text DEFAULT '',
    collection_id   text DEFAULT '',
    collection_name text DEFAULT '',
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pull_registry_intercom_id ON pull_registry(intercom_id);
CREATE INDEX IF NOT EXISTS idx_pull_registry_pull_status ON pull_registry(pull_status);
""".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers(prefer: str = "") -> Dict[str, str]:
    if not SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_SERVICE_KEY must be set")
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _content_hash(body: str) -> str:
    """SHA-256 of article body for change detection."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def _ts_to_iso(ts) -> Optional[str]:
    """Convert Intercom unix timestamp (seconds) or ISO string to ISO-8601 string."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return str(ts)


def table_exists() -> bool:
    """Check whether pull_registry table exists in Supabase."""
    if not REST_BASE:
        return False
    try:
        resp = requests.get(
            f"{REST_BASE}/{TABLE}?select=id&limit=1",
            headers=_headers(),
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_pull_articles(
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    status_filter: str = "",
) -> Dict:
    """
    Return paginated list from pull_registry with computed 'needs_pull' status.
    Returns: { articles: [...], total: int, page: int, page_size: int }
    """
    if not REST_BASE:
        return {"articles": [], "total": 0, "page": page, "page_size": page_size}

    headers = _headers()
    headers.pop("Prefer", None)
    # Build query params
    params: Dict = {
        "select": "id,intercom_id,title,description,state,url,source_updated_at,pulled_at,pull_status,pull_error,content_hash,collection_name,created_at,updated_at",
        "order": "title.asc",
    }

    # Search by title (case-insensitive ilike)
    if search:
        params["title"] = f"ilike.*{search}*"

    # Status filter
    needs_update_filter = False
    up_to_date_filter = False
    if status_filter == "never_pulled":
        params["pulled_at"] = "is.null"
    elif status_filter == "failed":
        params["pull_status"] = "eq.failed"
    elif status_filter == "pulling":
        params["pull_status"] = "eq.pulling"
    elif status_filter == "needs_update":
        # PostgREST can't compare two columns directly, so we fetch
        # all articles that HAVE been pulled and filter in Python.
        params["pulled_at"] = "not.is.null"
        needs_update_filter = True
    elif status_filter == "up_to_date":
        # Filter for articles that are pulled and up to date (not failed, not needs_update)
        params["pulled_at"] = "not.is.null"
        params["pull_status"] = "neq.failed"
        up_to_date_filter = True

    # For needs_update and up_to_date filters, we must fetch ALL matching rows
    # and paginate in Python, because the DB can't compare two columns directly.
    if needs_update_filter or up_to_date_filter:
        target_status = "updated_in_source" if needs_update_filter else "up_to_date"
        # Fetch all pulled articles (paginated in chunks of 1000)
        all_articles = []
        fetch_offset = 0
        while True:
            fetch_params = dict(params)
            fetch_params["offset"] = str(fetch_offset)
            fetch_params["limit"] = "1000"
            resp = requests.get(f"{REST_BASE}/{TABLE}", headers=headers, params=fetch_params, timeout=20)
            if not resp.ok:
                break
            batch = resp.json() if resp.text else []
            if not isinstance(batch, list) or not batch:
                break
            all_articles.extend(batch)
            if len(batch) < 1000:
                break
            fetch_offset += 1000

        # Compute status and filter
        for a in all_articles:
            a["needs_pull"] = _compute_needs_pull(a)
        filtered = [a for a in all_articles if a["needs_pull"] == target_status]
        total = len(filtered)

        # Paginate in Python
        offset = (page - 1) * page_size
        articles = filtered[offset:offset + page_size]
    else:
        # Standard DB-level pagination for other filters
        # Get total count first
        count_headers = dict(headers)
        count_headers["Prefer"] = "count=exact"
        count_headers["Range-Unit"] = "items"
        count_headers["Range"] = "0-0"
        count_resp = requests.get(f"{REST_BASE}/{TABLE}", headers=count_headers, params=params, timeout=15)
        total = 0
        if count_resp.ok:
            content_range = count_resp.headers.get("Content-Range", "")
            if "/" in content_range:
                try:
                    total = int(content_range.split("/")[1])
                except (ValueError, IndexError):
                    total = 0

        # Fetch page
        offset = (page - 1) * page_size
        params["offset"] = str(offset)
        params["limit"] = str(page_size)

        resp = requests.get(f"{REST_BASE}/{TABLE}", headers=headers, params=params, timeout=15)
        if not resp.ok:
            return {"articles": [], "total": 0, "page": page, "page_size": page_size, "error": resp.text[:200]}

        articles = resp.json() if resp.text else []
        if not isinstance(articles, list):
            articles = []

        # Compute needs_pull status for each article
        for a in articles:
            a["needs_pull"] = _compute_needs_pull(a)

    return {
        "articles": articles,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _compute_needs_pull(article: Dict) -> str:
    """
    Compute pull status badge:
      'up_to_date'         – Pulled On is newer than Source Updated OR hash matches
      'updated_in_source'  – Source Updated is newer than Pulled On
      'never_pulled'       – Pulled On is null
      'failed'             – last pull_status = failed
      'pulling'            – currently pulling
    """
    pull_status = article.get("pull_status")
    pulled_at = article.get("pulled_at")
    source_updated = article.get("source_updated_at")

    if pull_status == "pulling":
        return "pulling"
    if pull_status == "failed":
        return "failed"
    if not pulled_at:
        return "never_pulled"
    if source_updated and pulled_at:
        try:
            src_dt = datetime.fromisoformat(source_updated.replace("Z", "+00:00"))
            pull_dt = datetime.fromisoformat(pulled_at.replace("Z", "+00:00"))
            if src_dt > pull_dt:
                return "updated_in_source"
        except Exception:
            pass
    return "up_to_date"


def get_pull_article(intercom_id: str) -> Optional[Dict]:
    """Get one row from pull_registry by intercom_id."""
    if not REST_BASE:
        return None
    headers = _headers()
    headers.pop("Prefer", None)
    resp = requests.get(
        f"{REST_BASE}/{TABLE}",
        headers=headers,
        params={"intercom_id": f"eq.{intercom_id}", "select": "*"},
        timeout=10,
    )
    if resp.ok and resp.text:
        rows = resp.json()
        if isinstance(rows, list) and len(rows) > 0:
            return rows[0]
    return None


# ---------------------------------------------------------------------------
# Sync source list (populate pull_registry from Intercom without pulling body)
# ---------------------------------------------------------------------------

def sync_source_list(intercom_client) -> Dict:
    """
    Fetch the article listing from Intercom and upsert into pull_registry
    (title, state, source_updated_at, url). Does NOT fetch the full body.
    Also resolves collection names from Intercom Help Center.
    Only syncs articles that belong to a Help Center collection.
    Returns { synced: int, total: int }
    """
    # Fetch collection names for mapping parent_id → name
    collection_map: Dict[str, str] = {}
    # Build set of collection IDs that belong to any Help Center
    help_center_collection_ids: set = set()
    try:
        collections = intercom_client.get_collections()
        for c in collections:
            cid = str(c.get("id", ""))
            cname = c.get("name", "") or ""
            if cid and cname:
                collection_map[cid] = cname
            # Only include collections that belong to a help center
            if cid and c.get("help_center_id"):
                help_center_collection_ids.add(cid)
    except Exception:
        pass  # Non-critical – articles still sync without collection names

    articles = []
    page = 1
    per_page = 50
    while True:
        resp = intercom_client._make_request("GET", "/articles", params={"page": page, "per_page": per_page})
        data = resp.json()
        batch = data.get("data", [])
        articles.extend(batch)
        if not data.get("pages", {}).get("next"):
            break
        page += 1

    synced = 0
    skipped_locale = 0
    skipped_no_helpcenter = 0
    for a in articles:
        iid = str(a.get("id", ""))
        if not iid:
            continue
        title = (a.get("title") or "").strip() or "Untitled"

        # Skip translated articles created by Push Approach 3 (e.g. "[FA] Title")
        if _LOCALE_PREFIX_RE.match(title):
            skipped_locale += 1
            continue

        # Skip articles not belonging to any Help Center collection
        article_collection_id = str(a.get("parent_id") or a.get("collection_id") or "")
        if help_center_collection_ids and article_collection_id not in help_center_collection_ids:
            skipped_no_helpcenter += 1
            continue

        description = a.get("description") or ""
        state = a.get("state") or "published"
        url = a.get("url") or ""
        source_updated = _ts_to_iso(a.get("updated_at"))
        author_id = str(a.get("author_id") or "")
        collection_id = article_collection_id
        collection_name = collection_map.get(collection_id, "")

        existing = get_pull_article(iid)
        now = datetime.now(timezone.utc).isoformat()

        row = {
            "intercom_id": iid,
            "title": title,
            "description": description,
            "state": state,
            "url": url,
            "author_id": author_id,
            "collection_id": collection_id,
            "collection_name": collection_name,
            "updated_at": now,
        }
        # Only set source_updated_at for new articles.
        # For existing articles, source_updated_at is only updated during
        # full pull when content_hash actually changes — prevents push-triggered
        # Intercom timestamp bumps from marking articles as outdated.
        if not existing:
            row["source_updated_at"] = source_updated

        if existing:
            # Update
            headers = _headers("return=minimal")
            requests.patch(
                f"{REST_BASE}/{TABLE}?intercom_id=eq.{iid}",
                json=row,
                headers=headers,
                timeout=15,
            )
        else:
            # Insert
            row["created_at"] = now
            headers = _headers("return=minimal")
            resp = requests.post(f"{REST_BASE}/{TABLE}", json=row, headers=headers, timeout=15)
            if resp.status_code == 409:
                # Already exists (race condition), just update
                requests.patch(
                    f"{REST_BASE}/{TABLE}?intercom_id=eq.{iid}",
                    json=row,
                    headers=headers,
                    timeout=15,
                )
        synced += 1

    # Clean up any existing [LOCALE] rows already in pull_registry
    _cleanup_locale_articles()

    # Remove articles from pull_registry that are not in any Help Center collection
    if help_center_collection_ids:
        _cleanup_non_helpcenter_articles(help_center_collection_ids)

    # Save last sync timestamp
    _save_last_sync_time()

    return {"synced": synced, "total": len(articles), "skipped_locale": skipped_locale, "skipped_no_helpcenter": skipped_no_helpcenter}


def _save_last_sync_time():
    """Store last sync source time in automation_settings."""
    if not REST_BASE:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        headers = _headers("return=minimal")
        # Try update first
        r = requests.patch(
            f"{REST_BASE}/automation_settings?key=eq.last_sync_source",
            headers=headers,
            json={"value": now, "updated_at": now},
            timeout=15,
        )
        if r.status_code == 404 or (r.ok and r.text == '[]'):
            # Insert
            headers2 = _headers("return=minimal")
            requests.post(
                f"{REST_BASE}/automation_settings",
                headers=headers2,
                json={"key": "last_sync_source", "value": now, "updated_at": now},
                timeout=15,
            )
    except Exception:
        pass


def get_last_sync_time() -> str:
    """Read last sync source time from automation_settings. Returns ISO string or empty."""
    if not REST_BASE:
        return ""
    try:
        headers = _headers()
        headers.pop("Prefer", None)
        r = requests.get(
            f"{REST_BASE}/automation_settings",
            headers=headers,
            params={"select": "value", "key": "eq.last_sync_source"},
            timeout=15,
        )
        if r.ok:
            rows = r.json()
            if rows:
                return rows[0].get("value", "")
    except Exception:
        pass
    return ""


def _cleanup_locale_articles():
    """Remove [LOCALE] translated article rows from pull_registry."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        # Fetch titles that match the locale prefix pattern
        headers = _headers()
        resp = requests.get(
            f"{REST_BASE}/{TABLE}",
            headers=headers,
            params={"select": "intercom_id,title", "limit": "5000"},
            timeout=30,
        )
        if resp.status_code != 200:
            return
        rows = resp.json()
        to_delete = [r["intercom_id"] for r in rows
                     if _LOCALE_PREFIX_RE.match((r.get("title") or ""))]
        if not to_delete:
            return
        # Delete in batches
        del_headers = _headers("return=minimal")
        for i in range(0, len(to_delete), 50):
            batch = to_delete[i:i+50]
            ids_csv = ",".join(f'"{iid}"' for iid in batch)
            requests.delete(
                f"{REST_BASE}/{TABLE}?intercom_id=in.({ids_csv})",
                headers=del_headers,
                timeout=15,
            )
        print(f"    [INFO] Cleaned up {len(to_delete)} [LOCALE] articles from pull_registry")
    except Exception as e:
        print(f"    [WARN] Locale cleanup failed: {e}")


def _cleanup_non_helpcenter_articles(valid_collection_ids: set):
    """Remove articles from pull_registry whose collection_id is not in any Help Center."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        headers = _headers()
        # Fetch all collection_id values from pull_registry
        all_rows = []
        offset = 0
        while True:
            resp = requests.get(
                f"{REST_BASE}/{TABLE}",
                headers=headers,
                params={"select": "intercom_id,collection_id", "limit": "1000", "offset": str(offset)},
                timeout=30,
            )
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

        to_delete = [r["intercom_id"] for r in all_rows
                     if str(r.get("collection_id") or "") not in valid_collection_ids]
        if not to_delete:
            return
        del_headers = _headers("return=minimal")
        # Delete translations from article_translations first
        trans_deleted = 0
        for i in range(0, len(to_delete), 50):
            batch = to_delete[i:i + 50]
            ids_csv = ",".join(f'"{iid}"' for iid in batch)
            requests.delete(
                f"{REST_BASE}/article_translations?parent_intercom_article_id=in.({ids_csv})",
                headers=del_headers,
                timeout=15,
            )
            trans_deleted += len(batch)
        # Delete from pull_registry
        for i in range(0, len(to_delete), 50):
            batch = to_delete[i:i + 50]
            ids_csv = ",".join(f'"{iid}"' for iid in batch)
            requests.delete(
                f"{REST_BASE}/{TABLE}?intercom_id=in.({ids_csv})",
                headers=del_headers,
                timeout=15,
            )
        print(f"    [INFO] Cleaned up {len(to_delete)} non-Help-Center articles from pull_registry + their translations")
    except Exception as e:
        print(f"    [WARN] Non-Help-Center cleanup failed: {e}")


# ---------------------------------------------------------------------------
# Pull individual articles (fetch full body + store)
# ---------------------------------------------------------------------------

def pull_articles(intercom_ids: List[str], intercom_client) -> List[Dict]:
    """
    Pull full content for specified articles from Intercom and save to pull_registry.
    Returns a list of result dicts: { intercom_id, status, error? }
    """
    results = []

    for iid in intercom_ids:
        iid = str(iid).strip()
        if not iid:
            continue

        # Mark as pulling
        _set_pull_status(iid, "pulling")

        try:
            # Fetch full article from Intercom
            article = intercom_client.get_article(iid)
            title = (article.get("title") or "").strip() or "Untitled"
            body = article.get("body") or ""
            description = article.get("description") or ""
            state = article.get("state") or "published"
            url = article.get("url") or ""
            source_updated = _ts_to_iso(article.get("updated_at"))
            author_id = str(article.get("author_id") or "")
            collection_id = str(article.get("parent_id") or article.get("collection_id") or "")
            c_hash = _content_hash(body)

            # Only update source_updated_at if the content actually changed
            # This prevents push-triggered Intercom timestamp bumps from
            # showing articles as "recently updated source"
            existing = get_pull_article(iid)
            old_hash = existing.get("content_hash", "") if existing else ""
            content_changed = (old_hash != c_hash)

            now = datetime.now(timezone.utc).isoformat()
            row = {
                "intercom_id": iid,
                "title": title,
                "description": description,
                "state": state,
                "url": url,
                "pulled_at": now,
                "pull_status": "success",
                "pull_error": "",
                "content_hash": c_hash,
                "body_html": body,
                "author_id": author_id,
                "collection_id": collection_id,
                "updated_at": now,
            }
            # Only update source_updated_at when content genuinely changed
            if content_changed or not existing:
                row["source_updated_at"] = source_updated

            _upsert_pull_row(iid, row)

            # Also store in intercom_content_items/versions for the rest of the app
            _store_to_content_tables(iid, title, body)

            results.append({"intercom_id": iid, "title": title, "status": "success"})
            safe_title = title.encode("ascii", "replace").decode("ascii")
            print(f"  [PULL OK] {safe_title} (ID: {iid})")

        except Exception as e:
            error_msg = str(e)
            _set_pull_status(iid, "failed", error_msg)
            results.append({"intercom_id": iid, "status": "failed", "error": error_msg})
            safe_err = error_msg.encode("ascii", "replace").decode("ascii")
            print(f"  [PULL FAIL] ID: {iid} - {safe_err}")

    return results


def _set_pull_status(intercom_id: str, status: str, error: str = ""):
    """Quick update of pull_status and pull_error."""
    if not REST_BASE:
        return
    now = datetime.now(timezone.utc).isoformat()
    row = {"pull_status": status, "pull_error": error, "updated_at": now}
    headers = _headers("return=minimal")
    requests.patch(
        f"{REST_BASE}/{TABLE}?intercom_id=eq.{intercom_id}",
        json=row,
        headers=headers,
        timeout=10,
    )


def _upsert_pull_row(intercom_id: str, row: Dict):
    """Insert or update pull_registry row by intercom_id."""
    existing = get_pull_article(intercom_id)
    if existing:
        headers = _headers("return=minimal")
        requests.patch(
            f"{REST_BASE}/{TABLE}?intercom_id=eq.{intercom_id}",
            json=row,
            headers=headers,
            timeout=15,
        )
    else:
        row["created_at"] = datetime.now(timezone.utc).isoformat()
        headers = _headers("return=minimal")
        resp = requests.post(f"{REST_BASE}/{TABLE}", json=row, headers=headers, timeout=15)
        if resp.status_code == 409:
            requests.patch(
                f"{REST_BASE}/{TABLE}?intercom_id=eq.{intercom_id}",
                json=row,
                headers=headers,
                timeout=15,
            )


def _store_to_content_tables(intercom_id: str, title: str, body: str):
    """Also write to intercom_content_items/versions for use by Translate/Push."""
    try:
        from content_supabase import insert_content_item, insert_content_version
        item_id = insert_content_item(intercom_article_id=intercom_id)
        if item_id:
            insert_content_version(content_item_id=item_id, locale="en", title=title, body_raw=body)
    except Exception:
        pass  # non-critical – pull_registry is the source of truth here


# ---------------------------------------------------------------------------
# Get articles needing pull (for automation)
# ---------------------------------------------------------------------------

def get_articles_needing_pull() -> List[str]:
    """
    Return a list of intercom_ids for articles that are 'never_pulled' or 'updated_in_source'.
    Used by the automation service to auto-pull pending articles.
    """
    if not REST_BASE:
        return []
    headers = _headers()
    headers.pop("Prefer", None)
    try:
        all_rows: list = []
        offset = 0
        batch_size = 1000
        while True:
            resp = requests.get(
                f"{REST_BASE}/{TABLE}",
                headers=headers,
                params={
                    "select": "intercom_id,pull_status,pulled_at,source_updated_at",
                    "limit": str(batch_size),
                    "offset": str(offset),
                },
                timeout=20,
            )
            if not resp.ok:
                break
            batch = resp.json() if resp.text else []
            if not isinstance(batch, list) or len(batch) == 0:
                break
            all_rows.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size

        ids = []
        for r in all_rows:
            status = _compute_needs_pull(r)
            if status in ("never_pulled", "updated_in_source"):
                ids.append(r["intercom_id"])
        return ids
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Stats for dashboard
# ---------------------------------------------------------------------------

def get_pull_stats() -> Dict:
    """Return aggregate stats for the pull registry."""
    if not REST_BASE:
        return {"total": 0, "pulled": 0, "never_pulled": 0, "failed": 0, "up_to_date": 0, "needs_update": 0}
    headers = _headers()
    headers.pop("Prefer", None)
    try:
        rows: list = []
        offset = 0
        batch_size = 1000
        while True:
            resp = requests.get(
                f"{REST_BASE}/{TABLE}",
                headers=headers,
                params={
                    "select": "pull_status,pulled_at,source_updated_at",
                    "limit": str(batch_size),
                    "offset": str(offset),
                },
                timeout=15,
            )
            if not resp.ok:
                return {"total": 0}
            batch = resp.json() if resp.text else []
            if not isinstance(batch, list) or len(batch) == 0:
                break
            rows.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size

        total = len(rows)
        pulled = sum(1 for r in rows if r.get("pulled_at"))
        never = sum(1 for r in rows if not r.get("pulled_at"))
        failed = sum(1 for r in rows if r.get("pull_status") == "failed")
        up_to_date = 0
        needs_update = 0
        for r in rows:
            status = _compute_needs_pull(r)
            if status == "up_to_date":
                up_to_date += 1
            elif status == "updated_in_source":
                needs_update += 1

        return {
            "total": total,
            "pulled": pulled,
            "never_pulled": never,
            "failed": failed,
            "up_to_date": up_to_date,
            "needs_update": needs_update,
        }
    except Exception:
        return {"total": 0}
