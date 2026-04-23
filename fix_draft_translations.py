"""
Fix script: Set translated_content state to 'draft' for all draft articles.

The push code was setting translated_content.{locale}.state = "published" for
ALL articles, even draft ones. This made draft articles visible in non-English
help center views, causing different article counts per language.

This script finds all draft articles that have published translations and
sets their translated_content state to 'draft' so they're hidden in all locales.

Usage:
    py fix_draft_translations.py          # Dry-run (count only)
    py fix_draft_translations.py --fix    # Actually fix the articles
"""
import sys
import json

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient

def main():
    fix_mode = "--fix" in sys.argv
    client = IntercomClient()

    print("=" * 70)
    print("FIX DRAFT ARTICLES WITH PUBLISHED TRANSLATIONS")
    print("=" * 70)
    if fix_mode:
        print("MODE: FIX (will update articles in Intercom)")
    else:
        print("MODE: DRY-RUN (counting only — use --fix to apply)")
    print()

    # Step 1: Fetch all articles
    print("[1/3] Fetching all articles from Intercom...")
    all_articles = client.get_articles()
    print(f"      Total articles: {len(all_articles)}")

    # Step 2: Find draft articles with published translations
    print("[2/3] Finding draft articles with published translations...")
    to_fix = []
    for a in all_articles:
        state = (a.get("state") or "").lower()
        if state != "draft":
            continue

        tc = a.get("translated_content")
        if not tc or not isinstance(tc, dict):
            continue

        # Check if any locale has state=published
        published_locales = []
        for loc, content in tc.items():
            if loc == "type":
                continue
            if isinstance(content, dict) and (content.get("state") or "").lower() == "published":
                published_locales.append(loc)

        if published_locales:
            to_fix.append({
                "id": str(a.get("id")),
                "title": (a.get("title") or "")[:60],
                "published_locales": published_locales,
            })

    if not to_fix:
        print("\n  No draft articles with published translations found. All clean!")
        return

    total_locale_fixes = sum(len(a["published_locales"]) for a in to_fix)
    print(f"\n  Found {len(to_fix)} draft articles with published translations")
    print(f"  Total locale entries to fix: {total_locale_fixes}")
    print()

    # Show sample
    for a in to_fix[:5]:
        print(f"    [{a['id']}] {a['title']}")
        print(f"      Locales with state=published: {', '.join(a['published_locales'])}")
    if len(to_fix) > 5:
        print(f"    ... and {len(to_fix) - 5} more")

    if not fix_mode:
        print(f"\n  Run with --fix to set translated_content state to 'draft' for these {len(to_fix)} articles.")
        return

    # Step 3: Fix each article
    print(f"\n[3/3] Fixing {len(to_fix)} articles...")
    fixed = 0
    failed = 0

    for i, a in enumerate(to_fix):
        aid = a["id"]
        locales = a["published_locales"]

        # Build translated_content update: set all published locales to draft
        tc_update = {}
        for loc in locales:
            tc_update[loc] = {"state": "draft"}

        try:
            response = client._make_request(
                "PUT",
                f"/articles/{aid}",
                json={"translated_content": tc_update},
            )
            if response.ok:
                fixed += 1
                if (i + 1) % 25 == 0 or (i + 1) == len(to_fix):
                    print(f"    Progress: {i + 1}/{len(to_fix)} fixed...")
            else:
                failed += 1
                print(f"    FAILED [{aid}]: HTTP {response.status_code}")
        except Exception as e:
            failed += 1
            print(f"    FAILED [{aid}]: {str(e)[:80]}")

    print()
    print("=" * 70)
    print(f"  Done! Fixed: {fixed}, Failed: {failed}, Total: {len(to_fix)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
