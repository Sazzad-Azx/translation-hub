"""
Demo: Fetch 10 different articles from the FundedNext Help Center (Intercom)
by discovering all articles across all collections, then dump them into
Supabase tables intercom_content_items and intercom_content_versions.

Requires: .env with INTERCOM_ACCESS_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_KEY
"""
import sys
from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient
from content_supabase import dump_articles_to_supabase


def main() -> int:
    limit = 10
    print("Fetching articles from FundedNext Help Center (Intercom API 2.14)...")
    client = IntercomClient()
    all_articles = []

    # 1) Doc-compliant: find FundedNext Help Center and search articles by help_center_id
    try:
        all_articles = client.get_fundednext_help_center_articles(limit=limit * 2, fetch_full=True)
        if all_articles:
            print(f"  FundedNext Help Center: {len(all_articles)} article(s) via /help_center/help_centers + /articles/search")
    except Exception as e:
        print(f"  FundedNext-specific fetch failed: {e}")

    # 2) Fallback: collections + list /articles + search per help center
    if not all_articles:
        seen_ids = set()
        for a in client.get_all_help_center_articles():
            aid = a.get("id")
            if aid is not None and str(aid) not in seen_ids:
                seen_ids.add(str(aid))
                all_articles.append(a)
        for a in client.get_articles():
            aid = a.get("id")
            if aid is not None and str(aid) not in seen_ids:
                seen_ids.add(str(aid))
                all_articles.append(a)
        try:
            for hc in client.get_help_centers():
                hc_id = hc.get("id")
                if hc_id is None:
                    continue
                try:
                    hc_id_int = int(hc_id)
                except (TypeError, ValueError):
                    continue
                for a in client.search_articles(help_center_id=hc_id_int, state="published", limit=50):
                    aid = a.get("id")
                    if aid is not None and str(aid) not in seen_ids:
                        seen_ids.add(str(aid))
                        all_articles.append(a)
        except Exception as e:
            print(f"  Fallback search skipped: {e}")
        if all_articles:
            print(f"  Fallback: {len(all_articles)} total article(s) from collections + list + search")

    if not all_articles:
        print("No articles found. Check INTERCOM_ACCESS_TOKEN and Help Center permissions.")
        return 1
    print(f"Found {len(all_articles)} total article(s). Taking up to {limit}.")
    articles = (all_articles or [])[:limit]
    # Fetch full article details if body is missing (e.g. from search/list)
    for i, a in enumerate(articles):
        if not (a.get("body") or a.get("title")):
            try:
                full = client.get_article(str(a.get("id", "")))
                if full:
                    articles[i] = full
            except Exception:
                pass
    print(f"Selected {len(articles)} article(s). Dumping to Supabase...")
    try:
        count = dump_articles_to_supabase(articles)
        already = len(articles) - count
        print(f"Done. Dumped {count} new article(s) to Supabase." + (f" ({already} already existed.)" if already else ""))
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
