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

import json
import re
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, TARGET_LANGUAGES

# Skip translated articles created by Push Approach 3 (e.g. "[FA] Title")
_LOCALE_PREFIX_RE = re.compile(r'^\[[A-Z]{2}(?:-[A-Z]{1,4})?\]\s+', re.IGNORECASE)

REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
PULL_TABLE = "pull_registry"
TRANSLATIONS_TABLE = "article_translations"
SETTINGS_TABLE = "automation_settings"
ARCHIVE_KEY = "archived_articles"

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

    current_hash = article.get("content_hash", "")
    # Pull-level outdated: source updated after last pull (needs re-pull)
    pull_is_stale = bool(source_updated and pulled_at and source_updated > pulled_at)
    lang_statuses: Dict[str, str] = {}
    has_untranslated = False
    has_unpushed = False
    has_outdated = False
    all_pushed = True

    def _content_changed(t: Dict) -> bool:
        """Check if source content genuinely changed since this translation was created."""
        trans_checksum = t.get("source_checksum", "")
        if current_hash and trans_checksum:
            return current_hash != trans_checksum
        return False

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
                if pull_is_stale or _content_changed(t):
                    if pull_is_stale:
                        lang_statuses[loc] = "OUTDATED"
                        has_outdated = True
                    else:
                        lang_statuses[loc] = "NOT_STARTED"
                        has_untranslated = True
                    all_pushed = False
                else:
                    lang_statuses[loc] = "PUSHED"
            elif status == "ready" or status == "approved":
                if pull_is_stale:
                    lang_statuses[loc] = "OUTDATED"
                    has_outdated = True
                elif _content_changed(t):
                    lang_statuses[loc] = "NOT_STARTED"
                    has_untranslated = True
                else:
                    lang_statuses[loc] = "APPROVED"
                    has_unpushed = True
                all_pushed = False
            elif t.get("translated_title") or t.get("translated_body_html"):
                if pull_is_stale:
                    lang_statuses[loc] = "OUTDATED"
                    has_outdated = True
                elif _content_changed(t):
                    lang_statuses[loc] = "NOT_STARTED"
                    has_untranslated = True
                else:
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
    if has_outdated:
        return "OUTDATED", lang_statuses
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
        all_rows: list = []
        offset = 0
        batch_size = 1000
        while True:
            resp = requests.get(
                f"{REST_BASE}/{TRANSLATIONS_TABLE}",
                headers=_headers(),
                params={
                    "select": "parent_intercom_article_id,target_locale,status,updated_at,pushed_at,source_checksum,translated_title,translated_body_html",
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
        result: Dict[str, List[Dict]] = {}
        for r in all_rows:
            pid = r.get("parent_intercom_article_id", "")
            if pid:
                result.setdefault(pid, []).append(r)
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Archive helpers (uses automation_settings table)
# ---------------------------------------------------------------------------

def _read_archived_ids() -> Set[str]:
    """Read set of archived intercom_ids from automation_settings."""
    if not REST_BASE:
        return set()
    try:
        h = _headers()
        h.pop("Prefer", None)
        r = requests.get(
            f"{REST_BASE}/{SETTINGS_TABLE}",
            headers=h,
            params={"select": "last_run_message", "key": f"eq.{ARCHIVE_KEY}"},
            timeout=15,
        )
        if not r.ok or not r.text:
            return set()
        rows = r.json()
        if not rows:
            return set()
        raw = rows[0].get("last_run_message", "")
        if not raw:
            return set()
        data = json.loads(raw)
        if isinstance(data, list):
            return set(str(x) for x in data)
    except Exception:
        pass
    return set()


def _write_archived_ids(ids: Set[str]) -> bool:
    """Write archived IDs to automation_settings."""
    if not REST_BASE:
        return False
    msg = json.dumps(sorted(ids))
    try:
        h = _headers("return=minimal")
        r = requests.patch(
            f"{REST_BASE}/{SETTINGS_TABLE}?key=eq.{ARCHIVE_KEY}",
            json={"last_run_message": msg},
            headers=h,
            timeout=15,
        )
        if r.status_code in (200, 204):
            # Verify write
            check = _read_archived_ids()
            if check:
                return True
        # Row doesn't exist — INSERT
        payload = {"key": ARCHIVE_KEY, "enabled": True, "last_run_message": msg}
        h2 = _headers("return=minimal")
        r2 = requests.post(f"{REST_BASE}/{SETTINGS_TABLE}", json=payload, headers=h2, timeout=15)
        return r2.status_code in (200, 201)
    except Exception:
        return False


def archive_articles(intercom_ids: List[str]) -> Dict:
    """Archive articles by adding their IDs to the archived set."""
    ids = _read_archived_ids()
    added = []
    for iid in intercom_ids:
        s = str(iid)
        if s not in ids:
            ids.add(s)
            added.append(s)
    if added:
        _write_archived_ids(ids)
    return {"archived": len(added), "total_archived": len(ids)}


def unarchive_articles(intercom_ids: List[str]) -> Dict:
    """Unarchive articles by removing their IDs from the archived set."""
    ids = _read_archived_ids()
    removed = []
    for iid in intercom_ids:
        s = str(iid)
        if s in ids:
            ids.discard(s)
            removed.append(s)
    if removed:
        _write_archived_ids(ids)
    return {"unarchived": len(removed), "total_archived": len(ids)}


def list_archived_articles() -> List[str]:
    """Return list of archived intercom_ids."""
    return sorted(_read_archived_ids())


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
    base_params: Dict = {
        "select": "id,intercom_id,title,description,state,url,source_updated_at,pulled_at,pull_status,pull_error,content_hash,collection_id,collection_name,created_at,updated_at",
        "order": "title.asc",
    }
    if search:
        base_params["title"] = f"ilike.*{search}*"

    all_articles: list = []
    offset = 0
    batch_size = 1000
    while True:
        params = {**base_params, "limit": str(batch_size), "offset": str(offset)}
        resp = requests.get(f"{REST_BASE}/{PULL_TABLE}", headers=headers, params=params, timeout=20)
        if not resp.ok:
            break
        batch = resp.json() if resp.text else []
        if not isinstance(batch, list) or len(batch) == 0:
            break
        all_articles.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size

    if not all_articles:
        return {"articles": [], "total": 0, "page": page, "page_size": page_size, "counts": {}}

    # Filter out [LOCALE] translated articles created by Push Approach 3
    all_articles = [a for a in all_articles
                    if not _LOCALE_PREFIX_RE.match((a.get("title") or ""))]

    # Separate archived vs active articles
    archived_ids = _read_archived_ids()
    archived_articles = []
    active_articles = []
    for a in all_articles:
        if str(a.get("intercom_id", "")) in archived_ids:
            archived_articles.append(a)
        else:
            active_articles.append(a)

    # If viewing archived tab, show only archived articles
    showing_archived = (health_filter == "ARCHIVED")
    working_articles = archived_articles if showing_archived else active_articles

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
        "ALL": len(active_articles),
        "ARCHIVED": len(archived_articles),
    }

    # Always compute counts from active (non-archived) articles
    if showing_archived:
        for a in active_articles:
            h, _ = _compute_health(a, translations_map)
            counts[h] = counts.get(h, 0) + 1

    for a in working_articles:
        health, lang_statuses = _compute_health(a, translations_map)
        if not showing_archived:
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
            "health": "ARCHIVED" if showing_archived else health,
            "health_priority": HEALTH_PRIORITY.get(health, 99),
            "lang_statuses": lang_statuses,
        })

    # Apply health filter (skip for ARCHIVED since we already filtered above)
    if health_filter and health_filter not in ("ALL", "ARCHIVED"):
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
        rows: list = []
        offset = 0
        batch_size = 1000
        while True:
            resp = requests.get(
                f"{REST_BASE}/{PULL_TABLE}",
                headers=headers,
                params={
                    "select": "intercom_id,title,description,collection_id,collection_name,pulled_at,pull_status,source_updated_at",
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
            rows.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size
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
            "select": "id,intercom_id,title,description,state,url,source_updated_at,pulled_at,pull_status,pull_error,content_hash,collection_id,collection_name,created_at,updated_at",
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
