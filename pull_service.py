"""
Pull Service – fetches articles from Intercom and stores snapshots in Supabase pull_registry.

Table: pull_registry
Columns: id, intercom_id, title, description, state, url, source_updated_at,
         pulled_at, pull_status, pull_error, content_hash, body_html,
         author_id, collection_id, collection_name, created_at, updated_at
"""
import hashlib
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

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

    # If needs_update filter is active, keep only articles with that status
    # and recalculate total (since DB-level filter was approximate)
    if needs_update_filter:
        articles = [a for a in articles if a["needs_pull"] == "updated_in_source"]
        # For accurate pagination with this filter we need the real total;
        # fetch all matching rows' count by scanning (only id + timestamps)
        all_params: Dict = {
            "select": "pulled_at,source_updated_at,pull_status",
            "pulled_at": "not.is.null",
        }
        if search:
            all_params["title"] = f"ilike.*{search}*"
        all_resp = requests.get(f"{REST_BASE}/{TABLE}", headers=headers, params=all_params, timeout=20)
        if all_resp.ok and all_resp.text:
            all_rows = all_resp.json()
            if isinstance(all_rows, list):
                total = sum(1 for r in all_rows if _compute_needs_pull(r) == "updated_in_source")
    elif up_to_date_filter:
        # Filter for articles that are up to date (pulled, not failed, not needs_update)
        articles = [a for a in articles if a["needs_pull"] == "up_to_date"]
        # Recalculate total for accurate pagination
        all_params: Dict = {
            "select": "pulled_at,source_updated_at,pull_status",
            "pulled_at": "not.is.null",
            "pull_status": "neq.failed",
        }
        if search:
            all_params["title"] = f"ilike.*{search}*"
        all_resp = requests.get(f"{REST_BASE}/{TABLE}", headers=headers, params=all_params, timeout=20)
        if all_resp.ok and all_resp.text:
            all_rows = all_resp.json()
            if isinstance(all_rows, list):
                total = sum(1 for r in all_rows if _compute_needs_pull(r) == "up_to_date")

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
    Returns { synced: int, total: int }
    """
    # Fetch collection names for mapping parent_id → name
    collection_map: Dict[str, str] = {}
    try:
        collections = intercom_client.get_collections()
        for c in collections:
            cid = str(c.get("id", ""))
            cname = c.get("name", "") or ""
            if cid and cname:
                collection_map[cid] = cname
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
    for a in articles:
        iid = str(a.get("id", ""))
        if not iid:
            continue
        title = (a.get("title") or "").strip() or "Untitled"
        description = a.get("description") or ""
        state = a.get("state") or "published"
        url = a.get("url") or ""
        source_updated = _ts_to_iso(a.get("updated_at"))
        author_id = str(a.get("author_id") or "")
        # parent_id is the collection_id in many Intercom responses
        collection_id = str(a.get("parent_id") or a.get("collection_id") or "")
        collection_name = collection_map.get(collection_id, "")

        existing = get_pull_article(iid)
        now = datetime.now(timezone.utc).isoformat()

        row = {
            "intercom_id": iid,
            "title": title,
            "description": description,
            "state": state,
            "url": url,
            "source_updated_at": source_updated,
            "author_id": author_id,
            "collection_id": collection_id,
            "collection_name": collection_name,
            "updated_at": now,
        }

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

    return {"synced": synced, "total": len(articles)}


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

            now = datetime.now(timezone.utc).isoformat()
            row = {
                "intercom_id": iid,
                "title": title,
                "description": description,
                "state": state,
                "url": url,
                "source_updated_at": source_updated,
                "pulled_at": now,
                "pull_status": "success",
                "pull_error": "",
                "content_hash": c_hash,
                "body_html": body,
                "author_id": author_id,
                "collection_id": collection_id,
                "updated_at": now,
            }

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
# Stats for dashboard
# ---------------------------------------------------------------------------

def get_pull_stats() -> Dict:
    """Return aggregate stats for the pull registry."""
    if not REST_BASE:
        return {"total": 0, "pulled": 0, "never_pulled": 0, "failed": 0, "up_to_date": 0, "needs_update": 0}
    headers = _headers()
    headers.pop("Prefer", None)
    try:
        resp = requests.get(
            f"{REST_BASE}/{TABLE}",
            headers=headers,
            params={"select": "pull_status,pulled_at,source_updated_at"},
            timeout=15,
        )
        if not resp.ok:
            return {"total": 0}
        rows = resp.json() if resp.text else []
        if not isinstance(rows, list):
            return {"total": 0}

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
