"""
CLI: localize Intercom collection names for a help center (closes the gap where
localized help-center sites render empty because collections lack translated
names). See collection_translation_service for the why/how.

Examples
--------
    # Dry run (default) — show what would be published for FN Futures
    python translate_collections.py --help-center fn-futures --locales zh-CN,es,de

    # Publish names for all default target languages, collections with articles only
    python translate_collections.py --help-center 4171779 --locales all --apply

    # Include descriptions and localize every collection (even empty ones)
    python translate_collections.py --help-center fundednext --locales all \
        --with-descriptions --all-collections --apply

--help-center accepts a numeric id or a substring of the help center's
display_name / identifier (e.g. 'fn-futures', 'affiliate', 'fundednext').
--locales accepts a comma list of codes, or 'all' for every target language.
"""
import argparse
import sys

from config import TARGET_LANGUAGES
from collection_translation_service import localize_collection_names


def main() -> int:
    ap = argparse.ArgumentParser(description="Localize Intercom collection names for a help center.")
    ap.add_argument("--help-center", required=True, help="numeric id or name/identifier substring")
    ap.add_argument("--locales", required=True, help="comma list of locale codes, or 'all'")
    ap.add_argument("--apply", action="store_true", help="publish to Intercom (default: dry run)")
    ap.add_argument("--with-descriptions", action="store_true", help="also translate collection descriptions")
    ap.add_argument("--all-collections", action="store_true",
                    help="localize every collection (default: only those with published articles)")
    args = ap.parse_args()

    if args.locales.strip().lower() == "all":
        locales = list(TARGET_LANGUAGES.keys())
    else:
        locales = [x.strip() for x in args.locales.split(",") if x.strip()]

    report = localize_collection_names(
        match=args.help_center,
        locales=locales,
        apply=args.apply,
        only_with_articles=not args.all_collections,
        with_descriptions=args.with_descriptions,
    )

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Help center {report['help_center_id']}   locales {locales}   mode {mode}")
    total_added = 0
    for c in report["collections"]:
        if c["added"]:
            total_added += len(c["added"])
            tag = "published" if args.apply else "would add"
            print(f"  {c['id']}  {c['name'][:40]:40}  {tag}: {list(c['added'].keys())}")
            for loc, name in c["added"].items():
                print(f"        {loc}: {name}")
        else:
            print(f"  {c['id']}  {c['name'][:40]:40}  (all target locales already set)")
    print(f"\n{'Published' if args.apply else 'Would publish'} {total_added} locale-name(s) "
          f"across {len(report['collections'])} collection(s)."
          + ("" if args.apply else "  Re-run with --apply to write."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
