"""
Translate Service – operational status engine and bulk translation orchestrator.

Reads pull_registry (pulled articles) + article_translations to compute
per-article × per-language translation status.  Orchestrates bulk translation
jobs with a concurrency limit.

Statuses per Article × Language:
  NOT_STARTED  – no translation row exists
  IN_PROGRESS  – currently being translated (job running)
  TRANSLATED   – translation exists
  APPROVED     – translation marked approved
  OUTDATED     – source updated after pull (sourceUpdatedAt > pulledAt)
  FAILED       – last translation attempt failed

Priority (for sorting):
  OUTDATED > FAILED > NOT_STARTED > IN_PROGRESS > TRANSLATED > APPROVED
"""

import hashlib
import time
import requests
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, TARGET_LANGUAGES, BASE_LANGUAGE

REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
PULL_TABLE = "pull_registry"
TRANSLATIONS_TABLE = "article_translations"

STATUS_PRIORITY = {
    "OUTDATED": 0,
    "FAILED": 1,
    "NOT_STARTED": 2,
    "IN_PROGRESS": 3,
    "TRANSLATED": 4,
    "APPROVED": 5,
}

# In-memory tracking of currently running translation jobs
_active_jobs: Dict[str, str] = {}  # key = "intercom_id:locale" → "IN_PROGRESS"
_active_jobs_lock = threading.Lock()


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
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _relative_time(dt: Optional[datetime]) -> str:
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
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    days = secs // 86400
    if days < 30:
        return f"{days}d ago"
    return f"{days // 30}mo ago"


# ---------------------------------------------------------------------------
# Fetch data
# ---------------------------------------------------------------------------

def _fetch_pulled_articles(search: str = "") -> List[Dict]:
    """Fetch articles from pull_registry that have been pulled (have body)."""
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


def _fetch_all_translations() -> Dict[str, List[Dict]]:
    """Fetch all translation rows, keyed by parent_intercom_article_id."""
    if not REST_BASE:
        return {}
    headers = _headers()
    headers.pop("Prefer", None)
    try:
        resp = requests.get(
            f"{REST_BASE}/{TRANSLATIONS_TABLE}",
            headers=headers,
            params={
                "select": "id,parent_intercom_article_id,target_locale,translated_title,status,updated_at,source_checksum,engine,model",
                "limit": "10000",
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
# Status computation
# ---------------------------------------------------------------------------

def _compute_article_lang_status(
    article: Dict,
    locale: str,
    translation: Optional[Dict],
) -> str:
    """Compute status for one article × one language."""
    iid = article.get("intercom_id", "")
    job_key = f"{iid}:{locale}"

    # Check in-progress jobs
    with _active_jobs_lock:
        if job_key in _active_jobs:
            return "IN_PROGRESS"

    pulled_at = _parse_ts(article.get("pulled_at"))
    source_updated = _parse_ts(article.get("source_updated_at"))

    # Check if translation exists and when it was last updated
    if translation:
        translation_updated = _parse_ts(translation.get("updated_at"))
        status = (translation.get("status") or "").lower()
        has_content = bool(translation.get("translated_title"))

        # Check if failed
        if status == "failed":
            return "FAILED"
        
        # Check if approved/ready
        if status == "approved" or status == "ready":
            return "APPROVED"
        
        # If translation exists with content, check if it's outdated
        if has_content:
            # Translation is outdated only if source was updated AFTER the translation was created/updated
            if source_updated and translation_updated and source_updated > translation_updated:
                return "OUTDATED"
            # Otherwise, translation is current
            return "TRANSLATED"
    
    # No translation exists
    if not translation:
        # Check if source was updated after pull (needs translation)
        if source_updated and pulled_at and source_updated > pulled_at:
            return "OUTDATED"
        return "NOT_STARTED"

    return "NOT_STARTED"


def _compute_row_priority(lang_statuses: Dict[str, str]) -> int:
    """Compute row sort priority (lower = needs more attention)."""
    if not lang_statuses:
        return STATUS_PRIORITY.get("NOT_STARTED", 2)
    min_priority = 99
    for status in lang_statuses.values():
        p = STATUS_PRIORITY.get(status, 99)
        if p < min_priority:
            min_priority = p
    return min_priority


# ---------------------------------------------------------------------------
# Main listing API
# ---------------------------------------------------------------------------

def list_translate_articles(
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    status_filter: str = "",
    language_filter: str = "",
    sort_by: str = "attention",
) -> Dict:
    """
    List pulled articles with per-language translation status matrix.

    Returns: {
        articles: [ { intercom_id, title, collection_name, pulled_at,
                       source_updated_at, lang_statuses: {locale: status},
                       row_status, row_priority } ],
        total, page, page_size,
        counts: { NOT_STARTED, OUTDATED, IN_PROGRESS, TRANSLATED, APPROVED, FAILED, ALL },
        languages: { locale: name }
    }
    """
    articles = _fetch_pulled_articles(search)
    translations_map = _fetch_all_translations()

    enriched = []
    counts: Dict[str, int] = {
        "NOT_STARTED": 0,
        "OUTDATED": 0,
        "IN_PROGRESS": 0,
        "TRANSLATED": 0,
        "APPROVED": 0,
        "FAILED": 0,
        "ALL": 0,
    }

    for a in articles:
        iid = a.get("intercom_id", "")
        article_translations = translations_map.get(iid, [])
        trans_by_locale: Dict[str, Dict] = {}
        for t in article_translations:
            loc = t.get("target_locale", "")
            if loc:
                trans_by_locale[loc] = t

        lang_statuses: Dict[str, str] = {}
        for loc in TARGET_LANGUAGES:
            t = trans_by_locale.get(loc)
            lang_statuses[loc] = _compute_article_lang_status(a, loc, t)

        row_priority = _compute_row_priority(lang_statuses)
        # Row status = worst status across all languages
        row_status = "APPROVED"
        for s in lang_statuses.values():
            if STATUS_PRIORITY.get(s, 99) < STATUS_PRIORITY.get(row_status, 99):
                row_status = s

        pulled_dt = _parse_ts(a.get("pulled_at"))
        source_dt = _parse_ts(a.get("source_updated_at"))

        enriched.append({
            "intercom_id": iid,
            "title": a.get("title", "Untitled"),
            "collection_name": a.get("collection_name", ""),
            "state": a.get("state", ""),
            "url": a.get("url", ""),
            "pulled_at": a.get("pulled_at"),
            "pulled_relative": _relative_time(pulled_dt),
            "source_updated_at": a.get("source_updated_at"),
            "source_updated_relative": _relative_time(source_dt),
            "lang_statuses": lang_statuses,
            "row_status": row_status,
            "row_priority": row_priority,
        })

    # Count by row_status
    for a in enriched:
        counts["ALL"] += 1
        rs = a["row_status"]
        if rs in counts:
            counts[rs] += 1

    # Apply status filter
    if status_filter and status_filter != "ALL":
        if status_filter == "NEEDS_TRANSLATION":
            enriched = [a for a in enriched if a["row_status"] in ("NOT_STARTED", "OUTDATED")]
        else:
            enriched = [a for a in enriched if a["row_status"] == status_filter]

    # Apply language filter
    if language_filter:
        enriched = [a for a in enriched if a["lang_statuses"].get(language_filter) in
                    ("NOT_STARTED", "OUTDATED", "FAILED")]

    # Sort
    if sort_by == "attention":
        enriched.sort(key=lambda a: (a["row_priority"], (a.get("title") or "").lower()))
    elif sort_by == "title_asc":
        enriched.sort(key=lambda a: (a.get("title") or "").lower())
    elif sort_by == "updated_desc":
        enriched.sort(key=lambda a: a.get("source_updated_at") or "", reverse=True)

    total_filtered = len(enriched)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_articles = enriched[start:end]

    return {
        "articles": page_articles,
        "total": total_filtered,
        "page": page,
        "page_size": page_size,
        "counts": counts,
        "languages": TARGET_LANGUAGES,
    }


# ---------------------------------------------------------------------------
# Article detail for drawer
# ---------------------------------------------------------------------------

def get_translate_article_detail(intercom_id: str) -> Optional[Dict]:
    """Get article detail with source content preview and translation previews."""
    if not REST_BASE or not intercom_id:
        return None
    headers = _headers()
    headers.pop("Prefer", None)

    # Get article from pull_registry (includes body_html)
    resp = requests.get(
        f"{REST_BASE}/{PULL_TABLE}",
        headers=headers,
        params={
            "select": "id,intercom_id,title,state,url,source_updated_at,pulled_at,pull_status,content_hash,collection_name,body_html",
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

    # Get translations
    trans_resp = requests.get(
        f"{REST_BASE}/{TRANSLATIONS_TABLE}",
        headers=headers,
        params={
            "select": "id,target_locale,translated_title,translated_body_html,status,updated_at,engine,model",
            "parent_intercom_article_id": f"eq.{intercom_id}",
        },
        timeout=15,
    )
    translations = []
    if trans_resp.ok and trans_resp.text:
        translations = trans_resp.json()
        if not isinstance(translations, list):
            translations = []

    trans_by_locale: Dict[str, Dict] = {}
    for t in translations:
        loc = t.get("target_locale", "")
        if loc:
            trans_by_locale[loc] = t

    # Build per-language detail
    languages_detail = []
    for loc, lang_name in TARGET_LANGUAGES.items():
        t = trans_by_locale.get(loc)
        status = _compute_article_lang_status(article, loc, t)
        t_dt = _parse_ts(t.get("updated_at")) if t else None
        languages_detail.append({
            "locale": loc,
            "language": lang_name,
            "status": status,
            "translated_title": (t.get("translated_title") or "") if t else "",
            "translated_body_preview": ((t.get("translated_body_html") or "")[:2000]) if t else "",
            "last_translated": t.get("updated_at") if t else None,
            "last_translated_relative": _relative_time(t_dt) if t_dt else "",
            "engine": (t.get("engine") or "") if t else "",
            "model": (t.get("model") or "") if t else "",
        })

    pulled_dt = _parse_ts(article.get("pulled_at"))
    source_dt = _parse_ts(article.get("source_updated_at"))

    return {
        "intercom_id": intercom_id,
        "title": article.get("title", "Untitled"),
        "collection_name": article.get("collection_name", "") or "Uncategorized",
        "state": article.get("state", ""),
        "url": article.get("url", ""),
        "pulled_at": article.get("pulled_at"),
        "pulled_relative": _relative_time(pulled_dt),
        "source_updated_at": article.get("source_updated_at"),
        "source_updated_relative": _relative_time(source_dt),
        "source_body_preview": (article.get("body_html") or "")[:3000],
        "languages": languages_detail,
    }


# ---------------------------------------------------------------------------
# Bulk translate
# ---------------------------------------------------------------------------

def bulk_translate(
    intercom_ids: List[str],
    locales: List[str],
    translator_instance,
    concurrency: int = 3,
    glossary_id: Optional[str] = None,
) -> Dict:
    """
    Translate multiple articles x multiple languages.
    Uses ThreadPoolExecutor with concurrency limit.
    If glossary_id is provided (or a default exists), glossary terms are
    matched and enforced during translation.

    Returns: { total_jobs, completed, failed, results: [...] }
    """
    from translation_supabase import upsert_article_translation

    # --- Load glossary terms once (shared across threads) ---
    glossary_terms: List[Dict] = []
    try:
        from glossary_service import get_active_glossary_terms, match_glossary_terms, build_glossary_prompt, log_glossary_usage
        glossary_terms = get_active_glossary_terms(glossary_id)
    except Exception:
        glossary_terms = []

    jobs = []
    for iid in intercom_ids:
        for loc in locales:
            if loc not in TARGET_LANGUAGES:
                continue
            jobs.append((iid, loc))

    if not jobs:
        return {"total_jobs": 0, "completed": 0, "failed": 0, "results": []}

    results = []
    completed = 0
    failed = 0

    def do_translate(iid: str, locale: str) -> Dict:
        job_key = f"{iid}:{locale}"
        with _active_jobs_lock:
            _active_jobs[job_key] = "IN_PROGRESS"
        try:
            # Get source content from pull_registry
            headers = _headers()
            headers.pop("Prefer", None)
            resp = requests.get(
                f"{REST_BASE}/{PULL_TABLE}",
                headers=headers,
                params={
                    "select": "title,body_html,content_hash",
                    "intercom_id": f"eq.{iid}",
                },
                timeout=15,
            )
            if not resp.ok or not resp.text:
                raise Exception(f"Article {iid} not found in pull_registry")
            rows = resp.json()
            if not isinstance(rows, list) or len(rows) == 0:
                raise Exception(f"Article {iid} not found in pull_registry")

            article_data = rows[0]
            title = article_data.get("title") or "Untitled"
            body = article_data.get("body_html") or ""
            content_hash = article_data.get("content_hash") or ""

            if not body and not title:
                raise Exception(f"Article {iid} has no content to translate")

            # --- Glossary matching ---
            glossary_prompt = ""
            matched = []
            if glossary_terms:
                try:
                    full_text = title + " " + body
                    matched = match_glossary_terms(full_text, glossary_terms)
                    if matched:
                        glossary_prompt = build_glossary_prompt(matched, locale)
                except Exception:
                    pass

            # Translate using GPT
            article_dict = {"title": title, "body": body}
            lang_name = TARGET_LANGUAGES.get(locale, locale)
            safe_title = title.encode("ascii", "replace").decode("ascii")
            glossary_info = f" (glossary: {len(matched)} terms)" if matched else ""
            print(f"  [TRANSLATE] {safe_title} -> {lang_name}{glossary_info}...", flush=True)

            translated = translator_instance.translate_article(
                article_dict,
                target_language=locale,
                source_language=BASE_LANGUAGE,
                glossary_prompt=glossary_prompt,
            )

            # Save to Supabase
            upsert_article_translation(
                parent_intercom_article_id=str(iid),
                target_locale=locale,
                translated_title=translated.get("title", ""),
                translated_body_html=translated.get("body", ""),
                status="draft",
                source_locale=BASE_LANGUAGE,
                engine="openai",
                model=translator_instance.model or "gpt-4o-mini",
                source_checksum=content_hash,
            )

            # --- Log glossary usage ---
            if matched:
                try:
                    for m in matched:
                        log_glossary_usage(
                            term_id=m["term_id"],
                            glossary_id=m["glossary_id"],
                            article_intercom_id=str(iid),
                            locale=locale,
                            matched_count=m.get("match_count", 1),
                        )
                except Exception:
                    pass

            print(f"  [TRANSLATE OK] {safe_title} -> {lang_name}", flush=True)
            return {"intercom_id": iid, "locale": locale, "status": "success"}

        except Exception as e:
            err = str(e)
            safe_err = err.encode("ascii", "replace").decode("ascii")
            print(f"  [TRANSLATE FAIL] {iid} -> {locale}: {safe_err}", flush=True)
            return {"intercom_id": iid, "locale": locale, "status": "failed", "error": err}
        finally:
            with _active_jobs_lock:
                _active_jobs.pop(job_key, None)

    # Execute with thread pool
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(do_translate, iid, loc): (iid, loc)
                   for iid, loc in jobs}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if result["status"] == "success":
                completed += 1
            else:
                failed += 1

    return {
        "total_jobs": len(jobs),
        "completed": completed,
        "failed": failed,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Auto-select missing translations
# ---------------------------------------------------------------------------

def get_missing_translations(locales: List[str]) -> List[Dict]:
    """
    Find all articles × languages where status is NOT_STARTED or OUTDATED.
    Returns list of { intercom_id, locale, title, status }.
    """
    articles = _fetch_pulled_articles()
    translations_map = _fetch_all_translations()
    missing = []

    for a in articles:
        iid = a.get("intercom_id", "")
        article_translations = translations_map.get(iid, [])
        trans_by_locale = {t.get("target_locale", ""): t for t in article_translations if t.get("target_locale")}

        for loc in locales:
            if loc not in TARGET_LANGUAGES:
                continue
            t = trans_by_locale.get(loc)
            status = _compute_article_lang_status(a, loc, t)
            if status in ("NOT_STARTED", "OUTDATED"):
                missing.append({
                    "intercom_id": iid,
                    "locale": loc,
                    "title": a.get("title", "Untitled"),
                    "status": status,
                })

    return missing
