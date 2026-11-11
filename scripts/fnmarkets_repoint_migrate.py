"""
Re-point the FNmarkets product at its new help centers and carry over translations.

Background (2026-11-11): FNmarkets help centers were re-created inside the
FundedNext Intercom workspace with NEW article ids (HC 5874689 + 5884692). The
`fnmarket` Supabase schema still holds 4,367 finished translations keyed to the
OLD article ids (old workspace qr1kxx9n, now switched off). This script:

  1. Backs up fnmarket.pull_registry + fnmarket.article_translations to backups/.
  2. Matches each new article to an old one (same title + identical visible text;
     ties broken by same site — fnmarkets vs fnmarketsglobal).
  3. --apply: syncs + pulls the new articles into the fnmarket schema (this also
     removes the old rows — they are in the backup), then copies the matched old
     translations onto the new ids with source_checksum = the new content hash,
     pushed_at empty → they show as READY to push in the hub.

Articles whose text changed are reported, not copied — translate those fresh.

Usage (from repo root, .env loaded):
    python scripts/fnmarkets_repoint_migrate.py            # backup + dry-run report
    python scripts/fnmarkets_repoint_migrate.py --apply    # do it
Uses INTERCOM_ACCESS_TOKEN (FundedNext workspace) for the FNmarkets product.
"""
import collections
import html
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["SUPABASE_URL"] = os.environ.get("SUPABASE_URL") or "https://reiacekmluvuguqfswac.supabase.co"
# FNmarkets now lives in the FundedNext workspace → use that token for this run.
os.environ["FNMARKET_INTERCOM_TOKEN"] = os.environ["INTERCOM_ACCESS_TOKEN"]

import requests  # noqa: E402

import config  # noqa: E402,F401  (must load before product_context — circular import)

import product_context  # noqa: E402

product_context.bind_thread_product("fnmarket")

from intercom_client import IntercomClient  # noqa: E402
import pull_service  # noqa: E402
from translation_supabase import upsert_article_translation  # noqa: E402

APPLY = "--apply" in sys.argv
PROD = product_context.current_product()
assert PROD["id"] == "fnmarket" and PROD["schema"] == "fnmarket", PROD["id"]
OWN_HCS = set(PROD["help_center_ids"])
SITE_OF_HC = {"5874689": "help.fnmarkets.com", "5884692": "help.fnmarketsglobal.com"}


def rest(path):
    base = product_context.supabase_rest_base()
    out, off = [], 0
    while True:
        h = product_context.supabase_headers({"Range": f"{off}-{off + 999}"})
        r = requests.get(f"{base}/{path}", headers=h, timeout=120)
        r.raise_for_status()
        batch = r.json()
        out += batch
        if len(batch) < 1000:
            return out
        off += 1000


def norm_title(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def norm_body(b):
    t = re.sub(r"<[^>]+>", " ", b or "")
    t = html.unescape(t)
    t = re.sub(r"https?://\S+", "", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def host(url):
    m = re.match(r"https?://([^/]+)/", url or "")
    return m.group(1) if m else ""


def main():
    client = IntercomClient(access_token=PROD["intercom_token"])
    visible = {str(h["id"]) for h in client.get_help_centers()}
    missing = OWN_HCS - visible
    if missing:
        sys.exit(f"Token cannot see FNmarkets help centers {sorted(missing)} — aborting")

    # ── 1. Backup ────────────────────────────────────────────────────────
    old_rows = rest("pull_registry?select=*")
    old_tr = rest("article_translations?select=*")
    os.makedirs(os.path.join(ROOT, "backups"), exist_ok=True)
    bpath = os.path.join(ROOT, "backups", f"fnmarket_before_repoint_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(bpath, "w") as f:
        json.dump({"pull_registry": old_rows, "article_translations": old_tr}, f)
    print(f"Backup: {len(old_rows)} registry rows, {len(old_tr)} translations → {bpath}")
    old_ids = {r["intercom_id"] for r in old_rows}
    if old_ids and not any(r["intercom_id"] for r in old_rows if host(r.get("url")) in SITE_OF_HC.values()):
        print("WARN: no old rows carry a known FNmarkets URL")

    # ── 2. New articles (published, in the two new HCs) ──────────────────
    # /articles/search pagination is unstable (dup ids, silently missing ones),
    # so use the hub's multi-pass listing, scoped by collection → help center.
    coll_hc = {str(c["id"]): str(c.get("help_center_id") or "") for c in client.get_collections()}
    own_colls = {cid for cid, hc in coll_hc.items() if hc in OWN_HCS}
    listing, unstable, passes = pull_service._fetch_article_listing(client)
    new_articles, seen = [], set()
    for a in listing:
        aid = str(a.get("id") or "")
        if not aid or aid in seen or (a.get("state") or "published").lower() != "published":
            continue
        cid = pull_service._resolve_collection_id(a, own_colls)
        if cid not in own_colls:
            continue
        seen.add(aid)
        a["_hc"] = coll_hc[cid]
        new_articles.append(a)
    if unstable:
        print(f"WARN: article listing unstable after {passes} passes — counts may be short")
    bodies = {str(a["id"]): a.get("body") or "" for a in new_articles}
    print(f"New published articles: {len(new_articles)} "
          f"({collections.Counter(a['_hc'] for a in new_articles)})")

    by_title = collections.defaultdict(list)
    for r in old_rows:
        by_title[norm_title(r["title"])].append(r)

    matches, changed, unmatched = {}, [], []
    for a in new_articles:
        nid = str(a["id"])
        cands = by_title.get(norm_title(a.get("title")), [])
        if not cands:
            unmatched.append((nid, a.get("title")))
            continue
        nb = norm_body(bodies[nid])
        same = [c for c in cands if norm_body(c.get("body_html")) == nb]
        if not same:
            changed.append((nid, a.get("title")))
            continue
        same.sort(key=lambda c: host(c.get("url")) != SITE_OF_HC[a["_hc"]])
        matches[nid] = same[0]["intercom_id"]

    tr_by_old = collections.defaultdict(list)
    for t in old_tr:
        tr_by_old[t["parent_intercom_article_id"]].append(t)
    to_copy = sum(len(tr_by_old[o]) for o in matches.values())
    no_tr = [n for n, o in matches.items() if not tr_by_old[o]]

    print("\n── Match report ──")
    print(f"  identical (reuse translations): {len(matches)}  → {to_copy} translation rows to copy")
    print(f"  matched but old had no translations: {len(no_tr)}")
    print(f"  title match, text changed (translate fresh): {len(changed)}")
    for nid, t in changed:
        print(f"     {nid}  {t}")
    print(f"  no title match (translate fresh): {len(unmatched)}")
    for nid, t in unmatched:
        print(f"     {nid}  {t}")
    print(f"  locales: {dict(collections.Counter(t['target_locale'] for o in matches.values() for t in tr_by_old[o]))}")

    if not APPLY:
        print("\nDry run — nothing written. Re-run with --apply.")
        return

    # ── 3. Sync + pull new articles into the fnmarket schema ─────────────
    print("\nSyncing source list (scoped to FNmarkets HCs)…")
    res = pull_service.sync_source_list(client)
    print("  sync:", {k: v for k, v in res.items() if not isinstance(v, (list, dict))})
    ids = [str(a["id"]) for a in new_articles]
    print(f"Pulling {len(ids)} articles…")
    pulled = []
    for i in range(0, len(ids), 100):
        pulled += pull_service.pull_articles(ids[i:i + 100], client)
    print("  pull:", collections.Counter(p.get("status") for p in pulled))

    hashes = {r["intercom_id"]: r.get("content_hash") or "" for r in rest("pull_registry?select=intercom_id,content_hash")}

    # ── 4. Copy translations onto new ids ───────────────────────────────
    done = failed = 0
    for nid, oid in matches.items():
        for t in tr_by_old[oid]:
            try:
                upsert_article_translation(
                    parent_intercom_article_id=nid,
                    target_locale=t["target_locale"],
                    translated_title=t.get("translated_title") or "",
                    translated_body_html=t.get("translated_body_html") or "",
                    status=t.get("status") or "draft",
                    source_locale=t.get("source_locale") or "en",
                    engine=t.get("engine") or "",
                    model=t.get("model") or "",
                    source_checksum=hashes.get(nid, ""),
                )
                done += 1
            except Exception as e:
                failed += 1
                print(f"  FAIL {nid}/{t['target_locale']}: {str(e)[:200]}")
    print(f"\nCopied {done} translations ({failed} failed). "
          f"Translate fresh: {len(changed) + len(unmatched)} articles.")


if __name__ == "__main__":
    main()
