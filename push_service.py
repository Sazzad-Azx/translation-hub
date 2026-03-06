"""
Push Service – Deployment Control Panel backend.

Lists articles scoped to a selected target language with push readiness status.
Orchestrates pushing translated content to Intercom via the IntercomClient.

Push statuses per article × language:
  READY         – translation exists, is up-to-date, ready to push
  LIVE          – already pushed and up-to-date
  OUTDATED      – pushed but source/translation updated since last push
  MISSING       – no translation for this language
  FAILED        – last push attempt failed
  PENDING       – push in progress right now
  NEEDS_RETRANSLATION – source updated after translation was created
"""

import threading
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, TARGET_LANGUAGES

REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
PULL_TABLE = "pull_registry"
TRANSLATIONS_TABLE = "article_translations"

# In-memory tracking of active push jobs
_active_pushes: Dict[str, str] = {}  # "intercom_id:locale" → "PENDING"
_push_lock = threading.Lock()

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


def _parse_ts(val) -> Optional[datetime]:
    if not val:
        return None
    try:
        if isinstance(val, datetime):
            return val
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except Exception:
        return None


def _relative_time(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = int((now - dt).total_seconds())
    except Exception:
        return ""
    if secs < 0:
        return "just now"
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    days = secs // 86400
    if days < 30:
        return f"{days}d ago"
    return f"{days // 30}mo ago"


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_pulled_articles(search: str = "") -> List[Dict]:
    """Fetch all pulled articles (have body_html)."""
    if not REST_BASE:
        return []
    headers = _headers()
    headers.pop("Prefer", None)
    params: Dict = {
        "select": "id,intercom_id,title,state,url,source_updated_at,pulled_at,pull_status,content_hash,collection_name,body_html",
        "pulled_at": "not.is.null",
        "order": "title.asc",
        "limit": "5000",
    }
    if search:
        params["title"] = f"ilike.*{search}*"
    try:
        resp = requests.get(f"{REST_BASE}/{PULL_TABLE}", headers=headers, params=params, timeout=20)
        if not resp.ok:
            return []
        rows = resp.json() if resp.text else []
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _fetch_translations_for_locale(locale: str) -> Dict[str, Dict]:
    """Fetch all translations for a given locale, keyed by parent_intercom_article_id."""
    if not REST_BASE:
        return {}
    headers = _headers()
    headers.pop("Prefer", None)
    # Try with pushed_at/push_error columns first, fall back without
    select_cols = "id,parent_intercom_article_id,target_locale,translated_title,translated_body_html,status,updated_at,source_checksum,engine,model,pushed_at,push_error"
    try:
        resp = requests.get(
            f"{REST_BASE}/{TRANSLATIONS_TABLE}",
            headers=headers,
            params={
                "select": select_cols,
                "target_locale": f"eq.{locale}",
                "limit": "5000",
            },
            timeout=20,
        )
        if resp.status_code == 400:
            # Columns might not exist yet, try without them
            select_cols = "id,parent_intercom_article_id,target_locale,translated_title,translated_body_html,status,updated_at,source_checksum,engine,model"
            resp = requests.get(
                f"{REST_BASE}/{TRANSLATIONS_TABLE}",
                headers=headers,
                params={
                    "select": select_cols,
                    "target_locale": f"eq.{locale}",
                    "limit": "5000",
                },
                timeout=20,
            )
        if not resp.ok:
            return {}
        rows = resp.json() if resp.text else []
        if not isinstance(rows, list):
            return {}
        result: Dict[str, Dict] = {}
        for r in rows:
            pid = r.get("parent_intercom_article_id", "")
            if pid:
                result[pid] = r
        return result
    except Exception:
        return {}


def _fetch_translation_full(intercom_id: str, locale: str) -> Optional[Dict]:
    """Fetch full translation row including body for preview."""
    if not REST_BASE:
        return None
    headers = _headers()
    headers.pop("Prefer", None)
    # Try with all columns, fall back to basic columns
    select_cols = "id,parent_intercom_article_id,target_locale,translated_title,translated_body_html,status,updated_at,source_checksum,engine,model,pushed_at,push_error,created_at"
    try:
        resp = requests.get(
            f"{REST_BASE}/{TRANSLATIONS_TABLE}",
            headers=headers,
            params={
                "select": select_cols,
                "parent_intercom_article_id": f"eq.{intercom_id}",
                "target_locale": f"eq.{locale}",
            },
            timeout=15,
        )
        if resp.status_code == 400:
            # Columns might not exist, try without pushed_at/push_error
            select_cols = "id,parent_intercom_article_id,target_locale,translated_title,translated_body_html,status,updated_at,source_checksum,engine,model,created_at"
            resp = requests.get(
                f"{REST_BASE}/{TRANSLATIONS_TABLE}",
                headers=headers,
                params={
                    "select": select_cols,
                    "parent_intercom_article_id": f"eq.{intercom_id}",
                    "target_locale": f"eq.{locale}",
                },
                timeout=15,
            )
        if not resp.ok or not resp.text:
            return None
        rows = resp.json()
        if isinstance(rows, list) and len(rows) > 0:
            return rows[0]
        return None
    except Exception:
        return None


def _fetch_article_source(intercom_id: str) -> Optional[Dict]:
    """Fetch source article body from pull_registry."""
    if not REST_BASE:
        return None
    headers = _headers()
    headers.pop("Prefer", None)
    try:
        resp = requests.get(
            f"{REST_BASE}/{PULL_TABLE}",
            headers=headers,
            params={
                "select": "id,intercom_id,title,state,url,source_updated_at,pulled_at,body_html,collection_name",
                "intercom_id": f"eq.{intercom_id}",
            },
            timeout=15,
        )
        if not resp.ok or not resp.text:
            return None
        rows = resp.json()
        if isinstance(rows, list) and len(rows) > 0:
            return rows[0]
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------

def _compute_push_status(article: Dict, translation: Optional[Dict], locale: str) -> Tuple[str, str]:
    """
    Compute push status for one article × one locale.
    Returns: (status, reason)
    """
    iid = article.get("intercom_id", "")
    job_key = f"{iid}:{locale}"

    # Check active pushes
    with _push_lock:
        if job_key in _active_pushes:
            return "PENDING", "Push in progress..."

    pulled_at = _parse_ts(article.get("pulled_at"))
    source_updated = _parse_ts(article.get("source_updated_at"))

    # No translation exists
    if not translation:
        return "MISSING", "No translation exists for this language"

    has_content = bool(translation.get("translated_title") or translation.get("translated_body_html"))
    if not has_content:
        return "MISSING", "Translation has no content"

    trans_updated = _parse_ts(translation.get("updated_at"))
    pushed_at = _parse_ts(translation.get("pushed_at"))
    push_error = translation.get("push_error") or ""

    # Check if source updated after translation
    if source_updated and trans_updated and source_updated > trans_updated:
        return "NEEDS_RETRANSLATION", "Source updated after translation was created"

    # Check if last push failed
    if push_error and not pushed_at:
        return "FAILED", f"Last push failed: {push_error[:100]}"

    # Already pushed
    if pushed_at:
        # Check if translation updated after push
        if trans_updated and trans_updated > pushed_at:
            return "OUTDATED", "Translation updated since last push"
        # Check if source updated after push
        if source_updated and source_updated > pushed_at:
            return "OUTDATED", "Source updated since last push"
        return "LIVE", "Already published and up-to-date"

    # Translation exists, not pushed yet
    return "READY", "Translation ready to publish"


# ---------------------------------------------------------------------------
# Main list endpoint
# ---------------------------------------------------------------------------

def list_push_articles(
    locale: str = "",
    search: str = "",
    status_filter: str = "",
    page: int = 1,
    page_size: int = 25,
) -> Dict:
    """
    List articles for push deployment.
    If locale is provided, enrich with translation status for that language.
    If no locale, return basic article info with status 'NO_LANG'.
    Returns: { articles, total, page, page_size, counts }
    """
    articles = _fetch_pulled_articles(search)
    translations = _fetch_translations_for_locale(locale) if locale else {}

    # Build enriched list
    enriched = []
    for a in articles:
        iid = a.get("intercom_id", "")
        t = translations.get(iid) if locale else None

        if locale:
            push_status, reason = _compute_push_status(a, t, locale)
        else:
            push_status = "NO_LANG"
            reason = "Select a target language"

        enriched.append({
            "intercom_id": iid,
            "title": a.get("title", "Untitled"),
            "type": "Article",
            "state": a.get("state", ""),
            "collection_name": a.get("collection_name", ""),
            "url": a.get("url", ""),
            "push_status": push_status,
            "reason": reason,
            "source_updated_at": a.get("source_updated_at"),
            "pulled_at": a.get("pulled_at"),
            "translated_at": t.get("updated_at") if t else None,
            "pushed_at": t.get("pushed_at") if t else None,
            "translation_id": t.get("id") if t else None,
            "source_updated_relative": _relative_time(_parse_ts(a.get("source_updated_at"))),
            "translated_relative": _relative_time(_parse_ts(t.get("updated_at"))) if t else "",
            "pushed_relative": _relative_time(_parse_ts(t.get("pushed_at"))) if t else "",
        })

    # Compute counts (only meaningful when locale is set)
    counts = {
        "total": len(enriched),
        "ready": sum(1 for x in enriched if x["push_status"] == "READY"),
        "live": sum(1 for x in enriched if x["push_status"] == "LIVE"),
        "outdated": sum(1 for x in enriched if x["push_status"] == "OUTDATED"),
        "missing": sum(1 for x in enriched if x["push_status"] == "MISSING"),
        "failed": sum(1 for x in enriched if x["push_status"] == "FAILED"),
        "needs_retranslation": sum(1 for x in enriched if x["push_status"] == "NEEDS_RETRANSLATION"),
        "pending": sum(1 for x in enriched if x["push_status"] == "PENDING"),
    }

    # Apply status filter
    if status_filter and status_filter != "ALL":
        enriched = [x for x in enriched if x["push_status"] == status_filter]

    total = len(enriched)

    # Pagination
    start = (page - 1) * page_size
    end = start + page_size
    page_items = enriched[start:end]

    return {
        "articles": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Multi-locale list endpoint
# ---------------------------------------------------------------------------

def list_push_articles_multi(
    locales: List[str],
    search: str = "",
    page: int = 1,
    page_size: int = 25,
) -> Dict:
    """
    List articles with push status for multiple locales simultaneously.
    Returns a matrix: each article row contains status per locale.
    """
    articles = _fetch_pulled_articles(search)

    # Fetch translations for all requested locales in parallel
    import concurrent.futures
    trans_by_locale: Dict[str, Dict] = {}

    def _fetch_for_locale(loc):
        return loc, _fetch_translations_for_locale(loc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(locales), 6)) as ex:
        futures = [ex.submit(_fetch_for_locale, loc) for loc in locales]
        for f in concurrent.futures.as_completed(futures):
            try:
                loc, data = f.result()
                trans_by_locale[loc] = data
            except Exception:
                pass

    # Ensure every locale key exists
    for loc in locales:
        if loc not in trans_by_locale:
            trans_by_locale[loc] = {}

    enriched = []
    for a in articles:
        iid = a.get("intercom_id", "")
        locale_data: Dict[str, Dict] = {}
        for loc in locales:
            t = trans_by_locale[loc].get(iid)
            status, reason = _compute_push_status(a, t, loc)
            locale_data[loc] = {
                "status": status,
                "reason": reason,
                "pushed_relative": _relative_time(_parse_ts(t.get("pushed_at"))) if t else "",
                "translated_relative": _relative_time(_parse_ts(t.get("updated_at"))) if t else "",
            }

        enriched.append({
            "intercom_id": iid,
            "title": a.get("title", "Untitled"),
            "state": a.get("state", ""),
            "collection_name": a.get("collection_name", ""),
            "source_updated_relative": _relative_time(_parse_ts(a.get("source_updated_at"))),
            "locale_data": locale_data,
        })

    total = len(enriched)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "articles": enriched[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

def get_push_preview(intercom_id: str, locale: str) -> Optional[Dict]:
    """
    Get preview data for push drawer.
    Returns source article + translation side by side.
    """
    source = _fetch_article_source(intercom_id)
    if not source:
        return None

    translation = _fetch_translation_full(intercom_id, locale)
    push_status, reason = _compute_push_status(source, translation, locale)

    source_updated = _parse_ts(source.get("source_updated_at"))
    pulled_at = _parse_ts(source.get("pulled_at"))
    trans_updated = _parse_ts(translation.get("updated_at")) if translation else None
    pushed_at = _parse_ts(translation.get("pushed_at")) if translation else None

    # Diff indicator
    is_outdated = False
    if source_updated and trans_updated and source_updated > trans_updated:
        is_outdated = True

    return {
        "intercom_id": intercom_id,
        "locale": locale,
        "push_status": push_status,
        "reason": reason,
        "source": {
            "title": source.get("title", ""),
            "body_html": source.get("body_html", ""),
            "state": source.get("state", ""),
            "url": source.get("url", ""),
            "collection_name": source.get("collection_name", ""),
            "source_updated_at": source.get("source_updated_at"),
            "pulled_at": source.get("pulled_at"),
            "source_updated_relative": _relative_time(source_updated),
            "pulled_relative": _relative_time(pulled_at),
        },
        "translation": {
            "id": translation.get("id") if translation else None,
            "title": translation.get("translated_title", "") if translation else "",
            "body_html": translation.get("translated_body_html", "") if translation else "",
            "status": translation.get("status", "") if translation else "",
            "engine": translation.get("engine", "") if translation else "",
            "model": translation.get("model", "") if translation else "",
            "updated_at": translation.get("updated_at") if translation else None,
            "translated_relative": _relative_time(trans_updated),
            "pushed_at": translation.get("pushed_at") if translation else None,
            "pushed_relative": _relative_time(pushed_at),
        },
        "is_outdated": is_outdated,
    }


# ---------------------------------------------------------------------------
# Push execution
# ---------------------------------------------------------------------------

def push_single(intercom_id: str, locale: str, intercom_client) -> Dict:
    """
    Push one translation to Intercom.
    Returns: { success, intercom_id, locale, message, pushed_at }
    """
    job_key = f"{intercom_id}:{locale}"

    with _push_lock:
        _active_pushes[job_key] = "PENDING"

    try:
        # Fetch translation
        translation = _fetch_translation_full(intercom_id, locale)
        if not translation:
            return {"success": False, "intercom_id": intercom_id, "locale": locale,
                    "message": "No translation found"}

        title = translation.get("translated_title", "")
        body = translation.get("translated_body_html", "")
        if not title and not body:
            return {"success": False, "intercom_id": intercom_id, "locale": locale,
                    "message": "Translation has no content"}

        # Push to Intercom
        result = intercom_client.create_or_update_translation(
            article_id=intercom_id,
            locale=locale,
            title=title,
            body=body,
        )

        # Update pushed_at in Supabase
        now = datetime.now(timezone.utc).isoformat()
        _update_translation_push_status(
            intercom_id, locale, pushed_at=now, push_error=""
        )

        return {
            "success": True,
            "intercom_id": intercom_id,
            "locale": locale,
            "message": "Successfully pushed to Intercom",
            "pushed_at": now,
        }

    except Exception as e:
        # Record failure
        error_msg = str(e)[:500]
        _update_translation_push_status(
            intercom_id, locale, pushed_at=None, push_error=error_msg
        )
        return {
            "success": False,
            "intercom_id": intercom_id,
            "locale": locale,
            "message": f"Push failed: {error_msg}",
        }
    finally:
        with _push_lock:
            _active_pushes.pop(job_key, None)


def _update_translation_push_status(
    intercom_id: str, locale: str,
    pushed_at: Optional[str] = None, push_error: str = ""
):
    """Update pushed_at and push_error on article_translations."""
    if not REST_BASE:
        return
    headers = _headers()
    headers.pop("Prefer", None)

    # Find the translation row
    try:
        resp = requests.get(
            f"{REST_BASE}/{TRANSLATIONS_TABLE}",
            headers=headers,
            params={
                "select": "id",
                "parent_intercom_article_id": f"eq.{intercom_id}",
                "target_locale": f"eq.{locale}",
            },
            timeout=10,
        )
        if not resp.ok or not resp.text:
            return
        rows = resp.json()
        if not isinstance(rows, list) or len(rows) == 0:
            return
        trans_id = rows[0]["id"]
    except Exception:
        return

    # Patch it
    patch_data: Dict = {"push_error": push_error}
    if pushed_at:
        patch_data["pushed_at"] = pushed_at
    try:
        patch_headers = _headers("return=minimal")
        resp = requests.patch(
            f"{REST_BASE}/{TRANSLATIONS_TABLE}?id=eq.{trans_id}",
            json=patch_data,
            headers=patch_headers,
            timeout=10,
        )
        if resp.status_code == 400:
            # Columns might not exist yet; skip silently
            print(f"[push_service] Could not update push status: columns may not exist. Run migration SQL.")
    except Exception:
        pass


def bulk_push(
    intercom_ids: List[str],
    locale: str,
    intercom_client,
    concurrency: int = 3,
) -> Dict:
    """
    Push multiple articles for a locale.
    Returns: { total_jobs, completed, failed, results }
    """
    import concurrent.futures

    results = []

    def _push_one(iid):
        return push_single(iid, locale, intercom_client)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_push_one, iid): iid for iid in intercom_ids}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                iid = futures[future]
                results.append({
                    "success": False,
                    "intercom_id": iid,
                    "locale": locale,
                    "message": str(e),
                })

    completed = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))

    return {
        "total_jobs": len(results),
        "completed": completed,
        "failed": failed,
        "results": results,
    }
