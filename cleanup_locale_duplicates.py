"""
Cleanup script: Find and delete [LOCALE]-prefixed duplicate articles from Intercom.

These orphan articles were created by the push fallback (Approach 3) and inflate
collection article counts on the live Intercom Help Center.

Usage:
    py cleanup_locale_duplicates.py          # Dry-run (list only, no deletion)
    py cleanup_locale_duplicates.py --delete  # Actually delete the duplicates
"""
import re
import sys
import os

# Fix Windows console encoding for non-ASCII characters
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient

_LOCALE_PREFIX_RE = re.compile(r'^\[[A-Z]{2}(?:-[A-Z]{1,4})?\]\s+', re.IGNORECASE)

def main():
    delete_mode = "--delete" in sys.argv

    print("=" * 70)
    print("Intercom [LOCALE] Duplicate Article Cleanup")
    print("=" * 70)
    if delete_mode:
        print("MODE: DELETE (will remove articles from Intercom)")
    else:
        print("MODE: DRY-RUN (listing only — use --delete to actually remove)")
    print()

    client = IntercomClient()

    # Step 1: Fetch ALL articles from Intercom
    print("[1/3] Fetching all articles from Intercom...")
    all_articles = client.get_articles()
    print(f"      Total articles in Intercom: {len(all_articles)}")

    # Step 2: Find [LOCALE] prefixed duplicates
    print("[2/3] Scanning for [LOCALE]-prefixed duplicates...")
    duplicates = []
    for a in all_articles:
        title = (a.get("title") or "").strip()
        aid = str(a.get("id") or "")
        parent_id = a.get("parent_id") or ""
        state = a.get("state") or ""
        if aid and _LOCALE_PREFIX_RE.match(title):
            duplicates.append({
                "id": aid,
                "title": title,
                "parent_id": str(parent_id),
                "state": state,
            })

    if not duplicates:
        print("\n  No [LOCALE] duplicate articles found. The Help Center is clean.")
        return

    print(f"\n  Found {len(duplicates)} duplicate articles:\n")
    for i, d in enumerate(duplicates, 1):
        print(f"    {i:3d}. [{d['id']}] {d['title'][:70]}")
        print(f"         parent_id={d['parent_id']}, state={d['state']}")

    # Step 3: Delete if in delete mode
    if not delete_mode:
        print(f"\n  Run with --delete to remove these {len(duplicates)} articles from Intercom.")
        return

    print(f"\n[3/3] Deleting {len(duplicates)} duplicate articles from Intercom...")
    deleted = 0
    failed = 0
    for d in duplicates:
        ok = client.delete_article(d["id"])
        if ok:
            deleted += 1
            print(f"    DELETED: [{d['id']}] {d['title'][:60]}")
        else:
            failed += 1
            print(f"    FAILED:  [{d['id']}] {d['title'][:60]}")

    print()
    print("=" * 70)
    print(f"  Done! Deleted: {deleted}, Failed: {failed}, Total found: {len(duplicates)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
