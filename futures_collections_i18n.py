"""
Futures collection localization (one-off, reusable).

The FN Futures help center hides every localized site because its COLLECTIONS
have no translated names — Intercom renders a locale page collection-first, so a
collection with no name in <locale> (and all its articles) is hidden, even when
the article bodies are translated and published.

This translates the Futures collection name + description into the target
locale(s) and (in --apply mode) PUTs them back as published translated_content,
merging with any locales already present (never overwriting existing ones).

Usage:
    python futures_collections_i18n.py            # DRY RUN, zh-CN, no writes
    python futures_collections_i18n.py --apply     # write zh-CN to Intercom
    python futures_collections_i18n.py --locales zh-CN,es,de --apply

Dry-run writes the full proposal to futures_collections_proposal.json.
"""
import os, sys, json, argparse, urllib.request, urllib.parse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
FUTURES_HC = 4171779

# --- load .env into os.environ (dotenv isn't installed in this env) ---
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TOKEN = os.environ["INTERCOM_ACCESS_TOKEN"]

from config import DEFAULT_TARGET_LANGUAGES  # noqa: E402
from translator import GPTTranslator  # noqa: E402


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://api.intercom.io" + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
                 "Content-Type": "application/json", "Intercom-Version": "2.14"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fetch_futures_collections():
    cols, page = [], 1
    while True:
        r = api("GET", f"/help_center/collections?per_page=50&page={page}")
        batch = r.get("data") or []
        cols.extend(batch)
        pages = r.get("pages") or {}
        if not batch or page >= (pages.get("total_pages") or 1):
            break
        page += 1
    return [c for c in cols if str(c.get("help_center_id")) == str(FUTURES_HC)]


def locale_entry(tc, loc):
    v = (tc or {}).get(loc)
    return v if isinstance(v, dict) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to Intercom (default: dry run)")
    ap.add_argument("--locales", default="zh-CN", help="comma-separated locale codes")
    args = ap.parse_args()
    locales = [l.strip() for l in args.locales.split(",") if l.strip()]

    tr = GPTTranslator()
    cols = fetch_futures_collections()
    print(f"FN Futures collections: {len(cols)}   locales: {locales}   mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    # Show the exact translated_content shape Intercom already stores (PUT contract)
    sample = next((c for c in cols if c.get("translated_content")), None)
    if sample:
        any_loc = next(iter([k for k in sample["translated_content"] if isinstance(sample['translated_content'][k], dict)]), None)
        print(f"Existing translated_content entry shape (collection {sample['id']}, locale '{any_loc}'):")
        print("  " + json.dumps(sample["translated_content"].get(any_loc), ensure_ascii=False)[:300] + "\n")

    proposal = []
    ctx = ("Intercom help-center collection title. Keep product/brand names in English "
           "(FundedNext, FundedNext Futures, Rapid, Bolt, Flex, Legacy, NinjaTrader, "
           "TradingView, Tradovate, FAQ). Do not add words.")

    for c in cols:
        cid = str(c.get("id"))
        en_name = (c.get("name") or "").strip()
        en_desc = (c.get("description") or "").strip()
        tc = c.get("translated_content") or {}
        row = {"id": cid, "en_name": en_name, "en_desc": en_desc, "translations": {}}
        for loc in locales:
            existing = locale_entry(tc, loc)
            has = bool(existing.get("name"))
            zh_name = tr.translate_text(en_name, loc, "en", context=ctx, is_html=False) if en_name else ""
            zh_desc = tr.translate_text(en_desc, loc, "en", context=ctx, is_html=False) if en_desc else ""
            row["translations"][loc] = {
                "name": zh_name, "description": zh_desc,
                "already_present": has, "existing_name": existing.get("name", ""),
            }
        proposal.append(row)

    # ---- Dry-run render (Chinese-focused) ----
    for loc in locales:
        print("=" * 78)
        print(f"PROPOSED  {loc}  ({DEFAULT_TARGET_LANGUAGES.get(loc, loc)})")
        print("=" * 78)
        for row in proposal:
            t = row["translations"][loc]
            flag = "  [already set → will SKIP]" if t["already_present"] else ""
            print(f"\n• EN : {row['en_name']}")
            print(f"  {loc}: {t['name']}{flag}")
            if row["en_desc"]:
                print(f"    desc EN: {row['en_desc'][:80]}")
                print(f"    desc {loc}: {t['description'][:80]}")

    out = os.path.join(PROJECT_DIR, "futures_collections_proposal.json")
    json.dump(proposal, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nFull proposal written to {out}")

    if not args.apply:
        print("\nDRY RUN — nothing was written to Intercom. Re-run with --apply to publish.")
        return 0

    # ---- APPLY: merge missing locales into translated_content, publish ----
    wrote = skipped = 0
    for row in proposal:
        cid = row["id"]
        current = api("GET", f"/help_center/collections/{cid}")
        tc = current.get("translated_content") or {}
        changed = False
        for loc in locales:
            t = row["translations"][loc]
            if t["already_present"]:
                skipped += 1
                continue
            entry = dict(tc.get(loc) or {})
            # Intercom's real shape (verified from an existing entry) is
            # {"type": "group_content", "name": ..., "description": ...}
            entry["type"] = "group_content"
            entry["name"] = t["name"]
            if row["en_desc"]:
                entry["description"] = t["description"]
            tc[loc] = entry
            changed = True
        if changed:
            api("PUT", f"/help_center/collections/{cid}", {"translated_content": tc})
            wrote += 1
            print(f"  ✓ updated collection {cid}  ({row['en_name']})")
    print(f"\nAPPLY done. collections updated: {wrote}   locale-entries skipped (already set): {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
