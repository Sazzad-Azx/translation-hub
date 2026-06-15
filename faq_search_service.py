"""
Read-only FAQ search over pull_registry (published articles only).
~405 published rows, searched by keyword across title + body, then ranked
by relevance so the most on-topic article surfaces in the top results.
No writes, no changes to existing tables or schema.
"""
import re
import html as html_lib
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_REST = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
_SNIPPET_LEN = 400
_CANDIDATE_CAP = 200  # over-fetch lightweight candidates, then rank
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


def _snippet(body_html, keywords=None):
    """Return a snippet, centered on the first keyword hit when possible."""
    text = _strip_html(body_html)
    if len(text) <= _SNIPPET_LEN:
        return text

    lowered = text.lower()
    hit = -1
    for kw in (keywords or []):
        idx = lowered.find(kw)
        if idx != -1 and (hit == -1 or idx < hit):
            hit = idx

    if hit <= _SNIPPET_LEN // 2:
        cut = text.rfind(' ', 0, _SNIPPET_LEN)
        return text[:cut if cut > 0 else _SNIPPET_LEN] + '\u2026'

    start = max(0, hit - _SNIPPET_LEN // 3)
    start = text.rfind(' ', 0, start) + 1 if start > 0 else 0
    end = start + _SNIPPET_LEN
    cut = text.rfind(' ', start, end)
    end = cut if cut > start else end
    prefix = '\u2026' if start > 0 else ''
    suffix = '\u2026' if end < len(text) else ''
    return prefix + text[start:end].strip() + suffix


def _keywords(query, max_kw=6):
    # Split on whitespace/underscore/slash but KEEP hyphenated compounds
    # intact ("2-step" stays one token) — the digit is the discriminator
    # between "Stellar 1-Step" and "Stellar 2-Step".
    words = re.split(r'[\s_/]+', query.strip().lower())
    filtered = [w for w in words if len(w) > 2 and w not in _STOP_WORDS]
    return filtered[:max_kw] if filtered else [query.strip().lower()]


def _score(title, description, keywords, phrase):
    """Higher is better. Title hits weigh far more than description hits."""
    t = (title or '').lower()
    d = (description or '').lower()
    score = 0.0
    title_hits = 0
    for kw in keywords:
        if kw in t:
            score += 10.0
            title_hits += 1
        if kw in d:
            score += 2.0
    # Bonus when the title carries every keyword from the query.
    if keywords and title_hits == len(keywords):
        score += 20.0
    # Bonus for the full phrase appearing intact in the title.
    if phrase and phrase in t:
        score += 30.0
    # Shorter, more focused titles win ties.
    score -= len(t) * 0.01
    return score


def _fetch(params):
    resp = requests.get(
        f"{_REST}/pull_registry",
        headers=_headers(),
        params=params,
        timeout=8,
    )
    if not resp.ok:
        print(f"[faq_search] Supabase error {resp.status_code}: {resp.text[:200]}", flush=True)
        return None
    return resp.json() or []


def search_articles(query, limit=20):
    """
    Search published FAQ articles by keyword, ranked by relevance.
    Phase 1: over-fetch lightweight candidates (id/title/description/url)
             matching any keyword in the title or the phrase in the body.
    Phase 2: score candidates, then fetch body_html only for the top `limit`.
    Returns list of {title, snippet, url}. Empty list on any error.
    """
    if not query or not query.strip():
        return []

    kws = _keywords(query)
    phrase = ' '.join(kws)

    # Title matches any keyword OR body contains the joined phrase.
    or_parts = [f"title.ilike.*{kw}*" for kw in kws]
    or_parts.append(f"body_html.ilike.*{phrase}*")

    try:
        candidates = _fetch({
            "select": "id,title,description,url",
            "state": "eq.published",
            "or": f"({','.join(or_parts)})",
            "limit": str(_CANDIDATE_CAP),
        })
        if candidates is None:
            return []
    except Exception as e:
        print(f"[faq_search] candidate fetch error: {e}", flush=True)
        return []

    if not candidates:
        return []

    ranked = sorted(
        candidates,
        key=lambda r: _score(r.get("title"), r.get("description"), kws, phrase),
        reverse=True,
    )
    top = ranked[:limit]
    ids = [r.get("id") for r in top if r.get("id") is not None]
    if not ids:
        return []

    try:
        id_list = ",".join(str(i) for i in ids)
        bodies = _fetch({
            "select": "id,body_html",
            "id": f"in.({id_list})",
        })
        if bodies is None:
            bodies = []
    except Exception as e:
        print(f"[faq_search] body fetch error: {e}", flush=True)
        bodies = []

    body_by_id = {b.get("id"): b.get("body_html", "") for b in bodies}

    return [
        {
            "title": r.get("title", ""),
            "snippet": _snippet(body_by_id.get(r.get("id"), ""), kws),
            "url": r.get("url") or None,
        }
        for r in top
    ]
