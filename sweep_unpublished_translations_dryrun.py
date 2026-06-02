"""
DRY RUN — sweep Intercom for translations that should be hidden but aren't.

Finds every article where:
  - article-level state == "draft"  (English source is unpublished), AND
  - any translated_content[locale].state == "published"  (translated version
    is still visible on the public Help Center)

Reports affected articles + locales to stdout and a CSV. Does NOT make any
PUT calls.  Pair with sweep_unpublished_translations_apply.py to actually
demote.

Usage:
    py sweep_unpublished_translations_dryrun.py
    py sweep_unpublished_translations_dryrun.py --csv out.csv
"""
import argparse
import csv
import sys
from typing import Dict, List

from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient


def collect_articles(client: IntercomClient) -> List[Dict]:
    """List every article in the workspace via paginated /articles."""
    articles: List[Dict] = []
    page = 1
    per_page = 50
    while True:
        resp = client._make_request(
            "GET", "/articles", params={"page": page, "per_page": per_page}
        )
        data = resp.json()
        batch = data.get("data", []) or []
        articles.extend(batch)
        pages = data.get("pages") or {}
        total_pages = pages.get("total_pages") or 1
        print(f"  ...page {page}/{total_pages} ({len(articles)} so far)", flush=True)
        if not batch or not pages.get("next") or page >= total_pages:
            break
        page += 1
    return articles


def find_leaks(articles: List[Dict]) -> List[Dict]:
    """Return one row per (article, locale) where the leak applies."""
    leaks: List[Dict] = []
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
            loc_state = (entry.get("state") or "").lower()
            if loc_state != "published":
                continue
            leaks.append({
                "article_id": str(a.get("id") or ""),
                "source_state": state,
                "locale": loc,
                "locale_state": loc_state,
                "title": (a.get("title") or "")[:120],
                "locale_title": (entry.get("title") or "")[:120],
                "url": a.get("url") or "",
            })
    return leaks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="unpublished_translation_leaks.csv",
                    help="Path to write the report CSV (default: ./unpublished_translation_leaks.csv)")
    args = ap.parse_args()

    print("Listing all articles from Intercom...", flush=True)
    client = IntercomClient()
    articles = collect_articles(client)
    print(f"Fetched {len(articles)} articles total.\n", flush=True)

    leaks = find_leaks(articles)

    by_article: Dict[str, List[str]] = {}
    for row in leaks:
        by_article.setdefault(row["article_id"], []).append(row["locale"])

    print(f"== DRY RUN RESULTS ==")
    print(f"Articles with leaked translations : {len(by_article)}")
    print(f"Total (article x locale) demotions: {len(leaks)}\n")

    for aid, locs in sorted(by_article.items()):
        title = next((r["title"] for r in leaks if r["article_id"] == aid), "")
        src_state = next((r["source_state"] for r in leaks if r["article_id"] == aid), "")
        print(f"  {aid}  [{src_state}]  {title}")
        print(f"           locales -> draft: {', '.join(sorted(locs))}")

    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "article_id", "source_state", "locale", "locale_state",
            "title", "locale_title", "url",
        ])
        w.writeheader()
        w.writerows(leaks)
    print(f"\nWrote detailed CSV: {args.csv}")
    print("No PUTs were made. Review the CSV, then run the apply script to demote.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
