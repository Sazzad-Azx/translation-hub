"""
Read-only FAQ search over pull_registry (published articles only).
405 published rows, searched by keyword across title + body.
No writes, no changes to existing tables or schema.
"""
import re
import html as html_lib
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_REST = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
_SNIPPET_LEN = 400
_STOP_WORDS = {
    "is", "are", "the", "a", "an", "in", "on", "at", "to", "for", "of",
    "and", "or", "not", "with", "this", "that", "my", "do", "did", "does",
    "was", "were", "can", "how", "what", "why", "when", "who", "will",
    "i", "it", "be", "has", "have", "had", "me", "we", "us", "you",
}


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }


def _strip_html(raw):
    clean = re.sub(r'<[^>]+>', ' ', raw or '')
    clean = html_lib.unescape(clean)
    return re.sub(r'\s+', ' ', clean).strip()


def _snippet(body_html):
    text = _strip_html(body_html)
    if len(text) <= _SNIPPET_LEN:
        return text
    cut = text.rfind(' ', 0, _SNIPPET_LEN)
    return text[:cut if cut > 0 else _SNIPPET_LEN] + '\u2026'


def _keywords(query, max_kw=4):
    words = re.split(r'[\s\-_/]+', query.strip().lower())
    filtered = [w for w in words if len(w) > 2 and w not in _STOP_WORDS]
    return filtered[:max_kw] if filtered else [query.strip()]


def search_articles(query, limit=20):
    """
    Search published FAQ articles by keyword.
    Queries pull_registry (state=published, 405 rows).
    Returns list of {title, snippet, url}. Empty list on any error.
    """
    if not query or not query.strip():
        return []

    kws = _keywords(query)
    body_phrase = ' '.join(kws)

    # Title matches any keyword OR body contains the joined phrase
    or_parts = [f"title.ilike.*{kw}*" for kw in kws]
    or_parts.append(f"body_html.ilike.*{body_phrase}*")

    try:
        resp = requests.get(
            f"{_REST}/pull_registry",
            headers=_headers(),
            params={
                "select": "title,body_html,url",
                "state": "eq.published",
                "or": f"({','.join(or_parts)})",
                "limit": str(limit),
            },
            timeout=8,
        )
        if not resp.ok:
            print(f"[faq_search] Supabase error {resp.status_code}: {resp.text[:200]}", flush=True)
            return []
        rows = resp.json() or []
    except Exception as e:
        print(f"[faq_search] fetch error: {e}", flush=True)
        return []

    return [
        {
            "title": row.get("title", ""),
            "snippet": _snippet(row.get("body_html", "")),
            "url": row.get("url") or None,
        }
        for row in rows
    ]
