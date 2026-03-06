"""
Content Hub Service – Operational Control Center.

Reads metadata from pull_registry + article_translations to compute
derived operational health for every article.  NO article body is stored
or returned here – metadata only.

Health priority (highest → lowest):
  NEEDS_PULL  → article never pulled or pull failed
  OUTDATED    → source updated after last pull
  NEEDS_TRANSLATION → pulled but no translation for ≥1 target language
  NEEDS_PUSH  → translation exists but not pushed
  COMPLETE    → all languages pushed
  FAILED      → reserved for future error tracking
"""

import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, TARGET_LANGUAGES

REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
PULL_TABLE = "pull_registry"
TRANSLATIONS_TABLE = "article_translations"

# Health priority order (lower = more urgent)
HEALTH_PRIORITY = {
    "NEEDS_PULL": 0,
    "OUTDATED": 1,
    "NEEDS_TRANSLATION": 2,
    "NEEDS_PUSH": 3,
    "COMPLETE": 4,
    "FAILED": 5,
}


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


def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp string to a timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _relative_time(dt: Optional[datetime]) -> str:
    """Return a human-readable relative time string."""
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    diff = now - dt
    secs = int(diff.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = secs // 60
        return f"{m}m ago"
    if secs < 86400:
        h = secs // 3600
        return f"{h}h ago"
    days = secs // 86400
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    return f"{months}mo ago"


def _estimate_word_count(title: str, description: str) -> int:
    """Rough word count from title + description (body is NOT read here)."""
    text = f"{title or ''} {description or ''}"
    return len(text.split())


# ---------------------------------------------------------------------------
# Core: Compute health for one article
# ---------------------------------------------------------------------------

def _compute_health(
    article: Dict,
    translations_by_article: Dict[str, List[Dict]],
) -> Tuple[str, Dict[str, str]]:
    """
    Compute the overall health badge and per-language status.

    Returns:
      (health: str, lang_statuses: { locale: status_string })

    Statuses per language:
      NOT_STARTED, TRANSLATED, APPROVED, PUSHED, OUTDATED
    """
    iid = article.get("intercom_id", "")
    pulled_at = _parse_ts(article.get("pulled_at"))
    source_updated = _parse_ts(article.get("source_updated_at"))
    pull_status = article.get("pull_status") or ""

    # --- Pull state ---
    if pull_status == "failed":
        return "NEEDS_PULL", {loc: "NOT_STARTED" for loc in TARGET_LANGUAGES}
    if not pulled_at:
        return "NEEDS_PULL", {loc: "NOT_STARTED" for loc in TARGET_LANGUAGES}

    # --- Outdated check ---
    if source_updated and pulled_at and source_updated > pulled_at:
        lang_statuses = {}
        for loc in TARGET_LANGUAGES:
            lang_statuses[loc] = "OUTDATED"
        return "OUTDATED", lang_statuses

    # --- Translation state per language ---
    article_translations = translations_by_article.get(iid, [])
    trans_map: Dict[str, Dict] = {}
    for t in article_translations:
        locale = t.get("target_locale", "")
        if locale:
            trans_map[locale] = t

    lang_statuses: Dict[str, str] = {}
    has_untranslated = False
    has_unpushed = False
    all_pushed = True

    for loc in TARGET_LANGUAGES:
        t = trans_map.get(loc)
        if not t:
            lang_statuses[loc] = "NOT_STARTED"
            has_untranslated = True
            all_pushed = False
        else:
            status = (t.get("status") or "draft").lower()
            pushed_at_val = t.get("pushed_at")
            if pushed_at_val:
                # Check if translation is outdated relative to pull
                trans_updated = _parse_ts(t.get("updated_at"))
                if trans_updated and pulled_at and pulled_at > trans_updated:
                    lang_statuses[loc] = "OUTDATED"
                    all_pushed = False
                else:
                    lang_statuses[loc] = "PUSHED"
            elif status == "ready" or status == "approved":
                lang_statuses[loc] = "APPROVED"
                has_unpushed = True
                all_pushed = False
            elif t.get("translated_title") or t.get("translated_body_html"):
                lang_statuses[loc] = "TRANSLATED"
                has_unpushed = True
                all_pushed = False
            else:
                lang_statuses[loc] = "NOT_STARTED"
                has_untranslated = True
                all_pushed = False

    # --- Overall health ---
    if all_pushed and len(TARGET_LANGUAGES) > 0:
        return "COMPLETE", lang_statuses
    if has_untranslated:
        return "NEEDS_TRANSLATION", lang_statuses
    if has_unpushed:
        return "NEEDS_PUSH", lang_statuses

    return "NEEDS_TRANSLATION", lang_statuses


# ---------------------------------------------------------------------------
# Fetch all translations (batch)
# ---------------------------------------------------------------------------

def _fetch_all_translations() -> Dict[str, List[Dict]]:
    """
    Fetch all rows from article_translations (metadata only, not body).
    Returns dict keyed by parent_intercom_article_id.
    """
    if not REST_BASE:
        return {}
    try:
        resp = requests.get(
            f"{REST_BASE}/{TRANSLATIONS_TABLE}",
            headers=_headers(),
            params={
                "select": "parent_intercom_article_id,target_locale,status,updated_at,source_checksum,translated_title",
                "limit": "5000",
            },
            timeout=20,
        )
        if not resp.ok:
            return {}
        rows = resp.json() if resp.text else []
        if not isinstance(rows, list):
            return {}
        result: Dict[str, List[Dict]] = {}
        for r in rows:
            pid = r.get("parent_intercom_article_id", "")
            if pid:
                result.setdefault(pid, []).append(r)
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# List articles with health (paginated, searchable, filterable, sortable)
# ---------------------------------------------------------------------------

def list_content_hub_articles(
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    health_filter: str = "",
    sort_by: str = "attention",
    tab: str = "articles",
) -> Dict:
    """
    Main query for Content Hub Articles tab.

    Returns: {
        articles: [ { id, intercom_id, title, collection_name, word_count,
                       source_updated_at, source_updated_relative,
                       pulled, health, lang_statuses, ... } ],
        total: int,
        page: int,
        page_size: int,
        counts: { NEEDS_PULL: n, OUTDATED: n, ... }
    }
    """
    if not REST_BASE:
        return {"articles": [], "total": 0, "page": page, "page_size": page_size, "counts": {}}

    headers = _headers()
    headers.pop("Prefer", None)

    # Fetch all pull_registry rows (metadata only – no body_html)
    params: Dict = {
        "select": "id,intercom_id,title,description,state,url,source_updated_at,pulled_at,pull_status,pull_error,collection_id,collection_name,created_at,updated_at",
        "order": "title.asc",
        "limit": "5000",
    }
    if search:
        params["title"] = f"ilike.*{search}*"

    resp = requests.get(f"{REST_BASE}/{PULL_TABLE}", headers=headers, params=params, timeout=20)
    if not resp.ok:
        return {"articles": [], "total": 0, "page": page, "page_size": page_size, "counts": {}}

    all_articles = resp.json() if resp.text else []
    if not isinstance(all_articles, list):
        all_articles = []

    # Fetch all translations for health computation
    translations_map = _fetch_all_translations()

    # Compute health for each article
    enriched = []
    counts: Dict[str, int] = {
        "NEEDS_PULL": 0,
        "OUTDATED": 0,
        "NEEDS_TRANSLATION": 0,
        "NEEDS_PUSH": 0,
        "COMPLETE": 0,
        "FAILED": 0,
        "ALL": len(all_articles),
    }

    for a in all_articles:
        health, lang_statuses = _compute_health(a, translations_map)
        counts[health] = counts.get(health, 0) + 1

        word_count = _estimate_word_count(a.get("title", ""), a.get("description", ""))
        source_updated_dt = _parse_ts(a.get("source_updated_at"))

        enriched.append({
            "id": a.get("id", ""),
            "intercom_id": a.get("intercom_id", ""),
            "title": a.get("title", "Untitled"),
            "description": a.get("description", ""),
            "state": a.get("state", ""),
            "url": a.get("url", ""),
            "collection_id": a.get("collection_id", ""),
            "collection_name": a.get("collection_name", ""),
            "word_count": word_count,
            "source_updated_at": a.get("source_updated_at"),
            "source_updated_relative": _relative_time(source_updated_dt),
            "pulled": bool(a.get("pulled_at")),
            "pulled_at": a.get("pulled_at"),
            "health": health,
            "health_priority": HEALTH_PRIORITY.get(health, 99),
            "lang_statuses": lang_statuses,
        })

    # Apply health filter
    if health_filter and health_filter != "ALL":
        enriched = [a for a in enriched if a["health"] == health_filter]

    # Sort
    if sort_by == "attention":
        enriched.sort(key=lambda a: (a["health_priority"], (a.get("title") or "").lower()))
    elif sort_by == "updated_desc":
        enriched.sort(key=lambda a: a.get("source_updated_at") or "", reverse=True)
    elif sort_by == "word_count_desc":
        enriched.sort(key=lambda a: a.get("word_count", 0), reverse=True)
    elif sort_by == "title_asc":
        enriched.sort(key=lambda a: (a.get("title") or "").lower())

    total_filtered = len(enriched)
    total_words = sum(a.get("word_count", 0) for a in enriched)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_articles = enriched[start:end]

    return {
        "articles": page_articles,
        "total": total_filtered,
        "total_words": total_words,
        "page": page,
        "page_size": page_size,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Collections tab
# ---------------------------------------------------------------------------

def list_collections() -> List[Dict]:
    """
    Aggregate articles by collection_id/collection_name from pull_registry.
    Returns list of { collection_id, collection_name, article_count, health_summary }.
    """
    if not REST_BASE:
        return []
    headers = _headers()
    headers.pop("Prefer", None)
    try:
        resp = requests.get(
            f"{REST_BASE}/{PULL_TABLE}",
            headers=headers,
            params={
                "select": "intercom_id,title,description,collection_id,collection_name,pulled_at,pull_status,source_updated_at",
                "limit": "5000",
            },
            timeout=20,
        )
        if not resp.ok:
            return []
        rows = resp.json() if resp.text else []
        if not isinstance(rows, list):
            return []

        translations_map = _fetch_all_translations()

        collections: Dict[str, Dict] = {}
        for a in rows:
            cid = a.get("collection_id") or "uncategorized"
            cname = a.get("collection_name") or "Uncategorized"
            if cid not in collections:
                collections[cid] = {
                    "collection_id": cid,
                    "collection_name": cname,
                    "article_count": 0,
                    "word_count": 0,
                    "health_counts": {},
                }
            c = collections[cid]
            c["article_count"] += 1
            c["word_count"] += _estimate_word_count(a.get("title", ""), a.get("description", ""))
            health, _ = _compute_health(a, translations_map)
            c["health_counts"][health] = c["health_counts"].get(health, 0) + 1

        result = list(collections.values())
        result.sort(key=lambda c: c["collection_name"].lower())
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Article detail (for drawer)
# ---------------------------------------------------------------------------

def get_article_detail(intercom_id: str) -> Optional[Dict]:
    """
    Get detailed metadata for one article, including per-language operational status
    and activity log (last pulled, last translated, etc.).
    """
    if not REST_BASE or not intercom_id:
        return None
    headers = _headers()
    headers.pop("Prefer", None)

    # Get article from pull_registry
    resp = requests.get(
        f"{REST_BASE}/{PULL_TABLE}",
        headers=headers,
        params={
            "select": "id,intercom_id,title,description,state,url,source_updated_at,pulled_at,pull_status,pull_error,collection_id,collection_name,created_at,updated_at",
            "intercom_id": f"eq.{intercom_id}",
        },
        timeout=15,
    )
    if not resp.ok or not resp.text:
        return None
    rows = resp.json()
    if not isinstance(rows, list) or len(rows) == 0:
        return None
    article = rows[0]

    # Get translations for this article
    trans_resp = requests.get(
        f"{REST_BASE}/{TRANSLATIONS_TABLE}",
        headers=headers,
        params={
            "select": "target_locale,translated_title,status,updated_at,source_checksum",
            "parent_intercom_article_id": f"eq.{intercom_id}",
        },
        timeout=15,
    )
    article_translations = []
    if trans_resp.ok and trans_resp.text:
        article_translations = trans_resp.json()
        if not isinstance(article_translations, list):
            article_translations = []

    translations_map = {intercom_id: article_translations}
    health, lang_statuses = _compute_health(article, translations_map)
    word_count = _estimate_word_count(article.get("title", ""), article.get("description", ""))
    source_updated_dt = _parse_ts(article.get("source_updated_at"))
    pulled_dt = _parse_ts(article.get("pulled_at"))

    # Build per-language detail
    trans_by_locale: Dict[str, Dict] = {}
    for t in article_translations:
        loc = t.get("target_locale", "")
        if loc:
            trans_by_locale[loc] = t

    languages_detail = []
    for loc, lang_name in TARGET_LANGUAGES.items():
        t = trans_by_locale.get(loc)
        languages_detail.append({
            "locale": loc,
            "language": lang_name,
            "status": lang_statuses.get(loc, "NOT_STARTED"),
            "translated_title": (t.get("translated_title") or "") if t else "",
            "last_translated": t.get("updated_at") if t else None,
            "last_translated_relative": _relative_time(_parse_ts(t.get("updated_at"))) if t else "",
        })

    # Activity log
    activity = []
    if pulled_dt:
        activity.append({
            "action": "Pulled from Intercom",
            "time": article.get("pulled_at"),
            "relative": _relative_time(pulled_dt),
            "icon": "fa-cloud-download-alt",
            "color": "#2563eb",
        })
    for t in article_translations:
        t_dt = _parse_ts(t.get("updated_at"))
        locale = t.get("target_locale", "")
        lang_name = TARGET_LANGUAGES.get(locale, locale)
        activity.append({
            "action": f"Translated to {lang_name}",
            "time": t.get("updated_at"),
            "relative": _relative_time(t_dt),
            "icon": "fa-exchange-alt",
            "color": "#059669",
        })
    activity.sort(key=lambda a: a.get("time") or "", reverse=True)

    return {
        "id": article.get("id", ""),
        "intercom_id": intercom_id,
        "title": article.get("title", "Untitled"),
        "description": article.get("description", ""),
        "state": article.get("state", ""),
        "url": article.get("url", ""),
        "collection_id": article.get("collection_id", ""),
        "collection_name": article.get("collection_name", "") or "Uncategorized",
        "word_count": word_count,
        "source_updated_at": article.get("source_updated_at"),
        "source_updated_relative": _relative_time(source_updated_dt),
        "pulled_at": article.get("pulled_at"),
        "pulled_relative": _relative_time(pulled_dt),
        "pull_status": article.get("pull_status", ""),
        "health": health,
        "languages": languages_detail,
        "activity": activity[:20],
    }
