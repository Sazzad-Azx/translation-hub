"""
FNmarkets collection localization (HC 4802013).

Translates collection names for help.fnmarkets.com into 10 target locales
and PUTs them to Intercom. Reuses the futures_collections_i18n.py pattern.

Usage:
    python fnmarkets_collections_i18n.py            # DRY RUN
    python fnmarkets_collections_i18n.py --apply     # write to Intercom
"""
import os, sys, json, argparse, urllib.request

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
FNMARKETS_HC = 4802013

TARGET_LOCALES = ["ar", "zh-CN", "fr", "de", "hi", "it", "ja", "pt-BR", "es", "th"]

for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TOKEN = os.environ["FNMARKET_INTERCOM_TOKEN"]

from translator import GPTTranslator  # noqa: E402


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://api.intercom.io" + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
                 "Content-Type": "application/json", "Intercom-Version": "2.14"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fetch_collections():
    cols, page = [], 1
    while True:
        r = api("GET", f"/help_center/collections?per_page=50&page={page}")
        batch = r.get("data") or []
        cols.extend(batch)
        pages = r.get("pages") or {}
        if not batch or page >= (pages.get("total_pages") or 1):
            break
        page += 1
    return [c for c in cols if str(c.get("help_center_id")) == str(FNMARKETS_HC)]


def locale_entry(tc, loc):
    v = (tc or {}).get(loc)
    return v if isinstance(v, dict) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    tr = GPTTranslator()
    cols = fetch_collections()
    print(f"FNmarkets collections: {len(cols)}   locales: {TARGET_LOCALES}   mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    ctx = ("Intercom help-center collection title. Keep product/brand names in English "
           "(FNmarkets, FNmarkets Futures, CFDs, MT5, KYC). Do not add words. "
           "Keep translations concise and natural.")

    proposal = []
    for c in cols:
        cid = str(c.get("id"))
        en_name = (c.get("name") or "").strip()
        en_desc = (c.get("description") or "").strip()
        tc = c.get("translated_content") or {}
        row = {"id": cid, "en_name": en_name, "en_desc": en_desc, "translations": {}}

        for loc in TARGET_LOCALES:
            existing = locale_entry(tc, loc)
            has = bool(existing.get("name"))
            loc_name = tr.translate_text(en_name, loc, "en", context=ctx, is_html=False) if en_name and not has else ""
            loc_desc = tr.translate_text(en_desc, loc, "en", context=ctx, is_html=False) if en_desc and not has else ""
            row["translations"][loc] = {
                "name": loc_name if not has else existing.get("name", ""),
                "description": loc_desc,
                "already_present": has,
            }
        proposal.append(row)

    for row in proposal:
        print(f"\n{'='*60}")
        print(f"EN: {row['en_name']}")
        for loc in TARGET_LOCALES:
            t = row["translations"][loc]
            flag = " [SKIP — already set]" if t["already_present"] else ""
            print(f"  {loc:6s}: {t['name']}{flag}")

    out = os.path.join(PROJECT_DIR, "fnmarkets_collections_proposal.json")
    json.dump(proposal, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nProposal written to {out}")

    if not args.apply:
        print("\nDRY RUN — re-run with --apply to publish.")
        return 0

    wrote = skipped = 0
    for row in proposal:
        cid = row["id"]
        current = api("GET", f"/help_center/collections/{cid}")
        tc = current.get("translated_content") or {}
        changed = False
        for loc in TARGET_LOCALES:
            t = row["translations"][loc]
            if t["already_present"]:
                skipped += 1
                continue
            entry = dict(tc.get(loc) or {})
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
    print(f"\nDone. Updated: {wrote}   Skipped (already set): {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
