"""
Sweep service: find and demote leaked translations.

An article "leaks" when its English source state is not 'published'
(draft, deleted, etc.) but one or more translated_content[locale].state
is still 'published' — meaning those translations remain visible on the
public Help Center.

scan_and_demote() is the main entry point, called by:
  - /api/cron/sweep  (nightly Vercel cron at 03:00 UTC)
  - /api/sweep/run   (manual UI trigger in the Automation section)
"""
import time
from typing import Dict, List

from intercom_client import IntercomClient


def _collect_all_articles(client: IntercomClient) -> List[Dict]:
    articles = []
    page = 1
    per_page = 50
    while True:
        resp = client._make_request("GET", "/articles", params={"page": page, "per_page": per_page})
        data = resp.json()
        batch = data.get("data", []) or []
        articles.extend(batch)
        pages = data.get("pages") or {}
        total_pages = pages.get("total_pages") or 1
        print(f"[sweep] page {page}/{total_pages} ({len(articles)} fetched)", flush=True)
        if not batch or not pages.get("next") or page >= total_pages:
            break
        page += 1
    return articles


def _find_leaks(articles: List[Dict]) -> Dict[str, List[str]]:
    """Return {article_id: [leaked_locale, ...]} for every article with leaked translations."""
    leaks: Dict[str, List[str]] = {}
    for a in articles:
        state = (a.get("state") or "").lower()
        if state == "published":
            continue
        tc = a.get("translated_content") or {}
        if not isinstance(tc, dict):
            continue
        for loc, entry in tc.items():
            if not isinstance(entry, dict):
                continue
            if (entry.get("state") or "").lower() == "published":
                leaks.setdefault(str(a.get("id") or ""), []).append(loc)
    return leaks


def scan_and_demote(client: IntercomClient, dry_run: bool = False, sleep_ms: int = 200) -> Dict:
    """
    Scan all Intercom articles for leaked translations and demote them to draft.

    Returns a summary: articles_checked, leaks_found, articles_demoted,
    locales_demoted, errors[].
    """
    print(f"[sweep] Starting {'DRY RUN' if dry_run else 'LIVE'} sweep...", flush=True)

    articles = _collect_all_articles(client)
    leaks = _find_leaks(articles)

    articles_checked = len(articles)
    leaks_found = sum(len(v) for v in leaks.values())

    print(
        f"[sweep] Checked {articles_checked} articles — "
        f"{len(leaks)} article(s) with {leaks_found} leaked locale(s).",
        flush=True,
    )

    if dry_run or not leaks:
        return {
            "articles_checked": articles_checked,
            "leaks_found": leaks_found,
            "articles_demoted": 0,
            "locales_demoted": 0,
            "errors": [],
            "dry_run": dry_run,
        }

    articles_demoted = 0
    locales_demoted = 0
    errors = []

    for article_id, locs in leaks.items():
        try:
            result = client.demote_locales_to_draft(article_id, locs)
            if result:
                articles_demoted += 1
                locales_demoted += len(locs)
                print(f"[sweep] Demoted article {article_id}: {locs}", flush=True)
            else:
                print(f"[sweep] NOOP article {article_id} (already draft or missing)", flush=True)
        except Exception as e:
            err = f"article {article_id}: {str(e)[:200]}"
            errors.append(err)
            print(f"[sweep] ERROR {err}", flush=True)
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    print(
        f"[sweep] Done. demoted={articles_demoted} articles / {locales_demoted} locales, errors={len(errors)}",
        flush=True,
    )

    return {
        "articles_checked": articles_checked,
        "leaks_found": leaks_found,
        "articles_demoted": articles_demoted,
        "locales_demoted": locales_demoted,
        "errors": errors,
        "dry_run": False,
    }
