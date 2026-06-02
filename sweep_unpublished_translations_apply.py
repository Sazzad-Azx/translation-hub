"""
APPLY — demote leaked translations to draft on Intercom.

Reads unpublished_translation_leaks.csv (produced by the dry-run script),
groups rows by article_id, and calls IntercomClient.demote_locales_to_draft
for each article. Edit the CSV first to remove any (article, locale) pairs
you don't want demoted.

By default this script REQUIRES --confirm. Without it, the script prints
what it would do and exits without making any PUT calls.

Usage:
    # Safety preview (no PUTs):
    py sweep_unpublished_translations_apply.py

    # Actually apply:
    py sweep_unpublished_translations_apply.py --confirm

    # Use a different CSV:
    py sweep_unpublished_translations_apply.py --csv leaks.csv --confirm
"""
import argparse
import csv
import sys
import time
from typing import Dict, List

from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient


def load_targets(csv_path: str) -> Dict[str, List[str]]:
    targets: Dict[str, List[str]] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            aid = (row.get("article_id") or "").strip()
            loc = (row.get("locale") or "").strip()
            if not aid or not loc:
                continue
            locs = targets.setdefault(aid, [])
            if loc not in locs:
                locs.append(loc)
    return targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="unpublished_translation_leaks.csv",
                    help="Input CSV from the dry-run script")
    ap.add_argument("--audit", default="unpublished_translation_leaks_applied.csv",
                    help="Output audit CSV with per-article result")
    ap.add_argument("--confirm", action="store_true",
                    help="Required to actually PUT to Intercom. Without it, prints preview only.")
    ap.add_argument("--sleep-ms", type=int, default=200,
                    help="Sleep between PUTs to stay under rate limit (default 200ms)")
    args = ap.parse_args()

    targets = load_targets(args.csv)
    total_articles = len(targets)
    total_locales = sum(len(v) for v in targets.values())
    print(f"Loaded {total_articles} articles / {total_locales} locale demotions from {args.csv}")

    if not args.confirm:
        print("\n[PREVIEW] --confirm not set; no PUTs will be made.")
        for aid, locs in sorted(targets.items()):
            print(f"  {aid}  -> {', '.join(sorted(locs))}")
        print(f"\nRun with --confirm to actually apply.")
        return

    print(f"\nApplying. Sleep between calls: {args.sleep_ms}ms.\n")
    client = IntercomClient()

    audit_rows: List[Dict] = []
    ok = 0
    fail = 0
    skipped = 0

    for i, (aid, locs) in enumerate(sorted(targets.items()), start=1):
        try:
            result = client.demote_locales_to_draft(aid, locs)
            if result:
                ok += 1
                status = "OK"
                detail = ""
            else:
                skipped += 1
                status = "NOOP"
                detail = "no eligible locales (already draft or missing)"
        except Exception as e:
            fail += 1
            status = "FAIL"
            detail = str(e)[:200]
        audit_rows.append({
            "article_id": aid,
            "locales": ",".join(sorted(locs)),
            "status": status,
            "detail": detail,
        })
        print(f"  [{i}/{total_articles}] {aid:>10s}  {status:5s}  {','.join(sorted(locs))}  {detail}",
              flush=True)
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000.0)

    with open(args.audit, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["article_id", "locales", "status", "detail"])
        w.writeheader()
        w.writerows(audit_rows)

    print(f"\nDone. OK={ok}  NOOP={skipped}  FAIL={fail}")
    print(f"Audit log: {args.audit}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
