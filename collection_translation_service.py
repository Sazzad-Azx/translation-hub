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
from typing import Dict, List, Optional, Set

from intercom_client import IntercomClient
from translator import GPTTranslator
from config import TARGET_LANGUAGES
import product_context

_CTX = (
    "Intercom help-center collection title. Keep product/brand names in English "
    "(FundedNext, FundedNext Futures, FN Market, Rapid, Rapid Pro, Rapid Daily, "
    "Bolt, Flex, Legacy, Stellar, NinjaTrader, TradingView, Tradovate, FAQ). "
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
    """Collection ids in this help center that hold at least one published article."""
    used: Set[str] = set()
    for a in client.search_articles(help_center_id=hc_id, state="published", limit=10000):
        for p in [a.get("parent_id")] + (a.get("parent_ids") or []):
            if p:
                used.add(str(p))
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
