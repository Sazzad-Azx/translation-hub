"""
Collection-name localization for Intercom help centers.

The Translation Hub translates article *bodies* but never collection *names*.
Intercom builds each localized help-center site collection-first: a collection
with no translated name for a locale hides itself — and every article inside it —
on that locale's site, even when the article bodies are translated and published.
This module closes that gap for ANY help center.

Design notes
------------
- Reads/writes go through the project's ``IntercomClient`` (same auth/session).
- ``PUT /help_center/collections/{id}`` MERGES ``translated_content`` per locale,
  so we only send the locales we add; existing ones are preserved. We never
  overwrite a locale that already has a name.
- The single-collection ``GET`` does NOT return ``translated_content``; the LIST
  endpoint does, so we source existing translations from ``get_collections``.
- Locale entry shape is ``{"type": "group_content", "name", "description"}``.
- By default we only localize collections that contain published articles, to
  avoid creating empty collection shells for a locale with no article coverage.
"""
import threading
import time
from typing import Dict, List, Optional, Set

from intercom_client import IntercomClient
from translator import GPTTranslator
from config import TARGET_LANGUAGES
import product_context

_CTX = (
    "Intercom help-center collection title. Keep product/brand names in English "
    "(FundedNext, FundedNext Futures, FN Market, Rapid, Rapid Pro, Rapid Daily, "
    "FundedNext Labs, Bolt, Flex, Legacy, Stellar, NinjaTrader, TradingView, Tradovate, FAQ). "
    "Do not add words."
)


def resolve_help_center_id(client: IntercomClient, match: str) -> Optional[int]:
    """Resolve a help center by numeric id, or by substring of display_name/identifier."""
    m = str(match).strip()
    if m.isdigit():
        return int(m)
    ml = m.lower()
    for hc in client.get_help_centers():
        name = (hc.get("display_name") or hc.get("name") or "").lower()
        ident = (hc.get("identifier") or "").lower()
        if ml in name or ml in ident:
            try:
                return int(hc.get("id"))
            except (TypeError, ValueError):
                return None
    return None


def _collections_for(client: IntercomClient, hc_id: int) -> List[Dict]:
    return [c for c in client.get_collections() if str(c.get("help_center_id")) == str(hc_id)]


def collections_with_published_articles(client: IntercomClient, hc_id: int) -> Set[str]:
    """Collection ids in this help center that hold at least one published article,
    directly or through a sub-collection (a parent with no name hides its children)."""
    used: Set[str] = set()
    for a in client.search_articles(help_center_id=hc_id, state="published", limit=10000):
        for p in [a.get("parent_id")] + (a.get("parent_ids") or []):
            if p:
                used.add(str(p))
    parent_of = {str(c.get("id")): str(c.get("parent_id") or "") for c in client.get_collections()}
    for cid in list(used):
        cid = parent_of.get(cid, "")
        while cid and cid not in used:
            used.add(cid)
            cid = parent_of.get(cid, "")
    return used


def localize_collection_names(
    match: str,
    locales: List[str],
    apply: bool = False,
    only_with_articles: bool = True,
    with_descriptions: bool = False,
    client: Optional[IntercomClient] = None,
    translator: Optional[GPTTranslator] = None,
) -> Dict:
    """Translate + (optionally) publish collection names for a help center.

    Returns a report: {help_center_id, collections: [{id, name, added:{loc:name}, skipped:[loc]}], applied}
    Only locales missing a name are translated; existing locales are never touched.
    """
    client = client or IntercomClient()
    translator = translator or GPTTranslator()
    hc_id = resolve_help_center_id(client, match)
    if hc_id is None:
        raise ValueError(f"No help center matched {match!r}")

    cols = _collections_for(client, hc_id)
    if only_with_articles:
        used = collections_with_published_articles(client, hc_id)
        cols = [c for c in cols if str(c.get("id")) in used]

    report = {"help_center_id": hc_id, "applied": apply, "collections": []}
    for c in cols:
        cid = str(c.get("id"))
        en_name = (c.get("name") or "").strip()
        en_desc = (c.get("description") or "").strip()
        existing = c.get("translated_content") or {}
        tc: Dict[str, Dict] = {}
        added: Dict[str, str] = {}
        skipped: List[str] = []
        for loc in locales:
            if loc not in TARGET_LANGUAGES:
                continue
            ic_loc = product_context.intercom_locale(loc)
            cur = existing.get(ic_loc)
            if isinstance(cur, dict) and cur.get("name"):
                skipped.append(loc)
                continue
            name = translator.translate_text(en_name, loc, "en", context=_CTX, is_html=False) if en_name else en_name
            entry = {"type": "group_content", "name": name}
            if with_descriptions and en_desc:
                entry["description"] = translator.translate_text(en_desc, loc, "en", context=_CTX, is_html=False)
            tc[ic_loc] = entry
            added[loc] = name
        if tc and apply:
            client._make_request("PUT", f"/help_center/collections/{cid}", json={"translated_content": tc})
        report["collections"].append({"id": cid, "name": en_name, "added": added, "skipped": skipped})
    return report


# ---------------------------------------------------------------------------
# Push-time hook: keep collection names in step with article pushes
# ---------------------------------------------------------------------------
# Every time the Hub publishes an article translation, the article's parent
# collection chain must also carry a name in that locale, or the article stays
# invisible on the localized site. New collections created in Intercom never
# went through the one-off CLI above, so we close the gap at push time.

_COLL_CACHE_TTL = 300  # seconds; a bulk push reuses one collection listing
_coll_cache: Dict[str, Dict] = {}  # product id → {"at": ts, "by_id": {cid: collection}}
_coll_lock = threading.Lock()


def _collections_by_id(client: IntercomClient) -> Dict[str, Dict]:
    pid = product_context.current_product().get("id", "")
    with _coll_lock:
        hit = _coll_cache.get(pid)
        if hit and time.time() - hit["at"] < _COLL_CACHE_TTL:
            return hit["by_id"]
    by_id = {str(c.get("id")): c for c in client.get_collections()}
    with _coll_lock:
        _coll_cache[pid] = {"at": time.time(), "by_id": by_id}
    return by_id


def ensure_collection_names_for_article(
    client: IntercomClient,
    article_id: str,
    locale: str,
    translator: Optional[GPTTranslator] = None,
) -> List[str]:
    """Give the article's parent collections (and their ancestors) a name in
    ``locale`` where missing. Returns the collection ids that were localized.
    Existing names are never overwritten."""
    article = client.get_article(article_id)
    parents = [str(p) for p in [article.get("parent_id")] + (article.get("parent_ids") or []) if p]
    if not parents:
        return []

    by_id = _collections_by_id(client)
    ic_loc = product_context.intercom_locale(locale)

    chain: List[str] = []
    for cid in parents:
        seen = 0
        while cid and cid in by_id and cid not in chain and seen < 10:
            chain.append(cid)
            parent = by_id[cid].get("parent_id")
            cid = str(parent) if parent else ""
            seen += 1

    localized: List[str] = []
    for cid in chain:
        coll = by_id[cid]
        cur = (coll.get("translated_content") or {}).get(ic_loc)
        if isinstance(cur, dict) and cur.get("name"):
            continue
        en_name = (coll.get("name") or "").strip()
        if not en_name:
            continue
        translator = translator or GPTTranslator()
        name = translator.translate_text(en_name, locale, "en", context=_CTX, is_html=False)
        client._make_request("PUT", f"/help_center/collections/{cid}",
                             json={"translated_content": {ic_loc: {"type": "group_content", "name": name}}})
        # Reflect the write in the cached listing so concurrent pushes in the
        # same bulk job don't translate this collection again.
        with _coll_lock:
            tc = coll.setdefault("translated_content", {}) or {}
            tc[ic_loc] = {"type": "group_content", "name": name}
            coll["translated_content"] = tc
        localized.append(cid)
    return localized


# ---------------------------------------------------------------------------
# Nightly sweep: catch what the push hook can't see
# ---------------------------------------------------------------------------
# The push hook only fires for translations pushed from the Hub. Three gaps stay
# open without this sweep: translations published directly in Intercom, an
# already-translated article moved into a collection with no localized name,
# and an English collection rename (the hook never overwrites a name).
#
# Rename detection needs the English name we last saw, kept per product schema:
STATE_TABLE = "collection_name_state"

# Left alone by the sweep: legacy locales the Hub doesn't manage (it uses de /
# pt-BR), and collections kept English-only on purpose.
SKIP_LOCALES = {"de-form", "pt"}
SKIP_COLLECTIONS = {
    "19767325",  # FundedNext HC "Test article" — pending owner review
}
STATE_SQL = """
CREATE TABLE IF NOT EXISTS collection_name_state (
    collection_id text PRIMARY KEY,
    en_name       text NOT NULL,
    updated_at    timestamptz DEFAULT now()
);
""".strip()


def _load_name_state() -> Optional[Dict[str, str]]:
    """{collection_id: last seen English name}, or None if the table is missing."""
    import requests
    base = product_context.supabase_rest_base()
    if not base:
        return None
    r = requests.get(f"{base}/{STATE_TABLE}?select=collection_id,en_name",
                     headers=product_context.supabase_headers(), timeout=20)
    if r.status_code != 200:
        print(f"[collections] {STATE_TABLE} unavailable ({r.status_code}): {r.text[:200]}", flush=True)
        return None
    return {row["collection_id"]: row["en_name"] for row in r.json()}


def _save_name_state(rows: List[Dict]) -> None:
    import requests
    if not rows:
        return
    r = requests.post(
        f"{product_context.supabase_rest_base()}/{STATE_TABLE}?on_conflict=collection_id",
        headers=product_context.supabase_headers({"Prefer": "resolution=merge-duplicates"}),
        json=rows, timeout=30)
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"saving {STATE_TABLE} failed ({r.status_code}): {r.text[:200]}")


def sync_collection_names(
    client: IntercomClient,
    translator: Optional[GPTTranslator] = None,
    apply: bool = True,
) -> Dict:
    """Bring every collection name in line with what's actually published.

    1. Missing: a collection (or ancestor) holding an article published in a
       locale gets a name in that locale if it has none.
    2. Renamed: if the English name changed since the last run, every existing
       localized name is re-translated. The first run only records a baseline.
    """
    by_id = {str(c.get("id")): c for c in client.get_collections()}

    # Intercom locale codes → internal codes for the translator prompt.
    inverse = {v: k for k, v in product_context.current_product().get("locale_map", {}).items()}

    # (collection, locale) pairs that must carry a name.
    need: Set[tuple] = set()
    seen_articles: Set[str] = set()
    for a in client.get_articles():
        aid = str(a.get("id"))
        if aid in seen_articles or (a.get("state") or "") != "published":
            continue
        seen_articles.add(aid)
        locs = [loc for loc, v in (a.get("translated_content") or {}).items()
                if loc != "en" and loc not in SKIP_LOCALES and isinstance(v, dict) and v.get("state") == "published"]
        if not locs:
            continue
        for cid in [str(p) for p in [a.get("parent_id")] + (a.get("parent_ids") or []) if p]:
            depth = 0
            while cid and cid in by_id and depth < 10:
                for loc in locs:
                    need.add((cid, loc))
                parent = by_id[cid].get("parent_id")
                cid = str(parent) if parent else ""
                depth += 1

    state = _load_name_state()
    updates: Dict[str, Dict[str, Dict]] = {}  # cid → {locale: entry}
    missing = renamed = 0
    translator_ = translator

    def _translate(text: str, loc: str) -> str:
        nonlocal translator_
        translator_ = translator_ or GPTTranslator()
        return translator_.translate_text(text, inverse.get(loc, loc), "en", context=_CTX, is_html=False)

    if state is not None:
        for cid, coll in by_id.items():
            en_name = (coll.get("name") or "").strip()
            old = state.get(cid)
            if not en_name or old is None or old == en_name or cid in SKIP_COLLECTIONS:
                continue
            tc = coll.get("translated_content") or {}
            for loc, v in tc.items():
                if loc != "en" and loc not in SKIP_LOCALES and isinstance(v, dict) and v.get("name"):
                    updates.setdefault(cid, {})[loc] = {"type": "group_content", "name": _translate(en_name, loc)}
            renamed += 1

    for cid, loc in sorted(need):
        if cid in SKIP_COLLECTIONS:
            continue
        coll = by_id[cid]
        cur = (coll.get("translated_content") or {}).get(loc)
        if (isinstance(cur, dict) and cur.get("name")) or loc in updates.get(cid, {}):
            continue
        en_name = (coll.get("name") or "").strip()
        if not en_name:
            continue
        updates.setdefault(cid, {})[loc] = {"type": "group_content", "name": _translate(en_name, loc)}
        missing += 1

    failed: List[str] = []
    if apply:
        for cid, tc in updates.items():
            try:
                client._make_request("PUT", f"/help_center/collections/{cid}", json={"translated_content": tc})
            except Exception as e:
                print(f"[collections] PUT {cid} failed: {e}", flush=True)
                failed.append(cid)
        if state is not None:
            _save_name_state([
                {"collection_id": cid, "en_name": (c.get("name") or "").strip(),
                 "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                for cid, c in by_id.items()
                if cid not in failed and (c.get("name") or "").strip()
                and state.get(cid) != (c.get("name") or "").strip()
            ])
        with _coll_lock:
            _coll_cache.pop(product_context.current_product().get("id", ""), None)

    return {
        "collections": len(by_id),
        "articles": len(seen_articles),
        "missing_names_added": missing,
        "renamed_collections": renamed,
        "collections_updated": len(updates) - len(failed),
        "failed": failed,
        "rename_tracking": state is not None,
        "updates": {cid: {loc: e["name"] for loc, e in tc.items()} for cid, tc in updates.items()},
        "applied": apply,
    }
