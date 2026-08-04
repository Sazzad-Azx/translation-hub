"""
Fast parallel publisher for Futures collection NAMES across locales.
One PUT per collection (all locales merged) so concurrent writes never race on
Intercom's server-side translated_content merge. Names only — descriptions are
handled separately (Intercom rejects some description shapes with 400).

    python futures_collections_names.py --locales es,de,fr,it,ja,hi,th,pt-BR,ar --apply
    python futures_collections_names.py --locales es,de --dry     # print, no writes
"""
import os, sys, json, argparse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
FUTURES_HC = 4171779
for line in open(os.path.join(PROJECT_DIR, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
TOKEN = os.environ["INTERCOM_ACCESS_TOKEN"]
from translator import GPTTranslator  # noqa: E402

CTX = ("Intercom help-center collection title. Keep product/brand names in English "
       "(FundedNext, FundedNext Futures, Rapid, Rapid Pro, Rapid Daily, Bolt, Flex, "
       "Legacy, NinjaTrader, TradingView, Tradovate, FAQ). Do not add words.")


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("https://api.intercom.io" + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
                 "Content-Type": "application/json", "Intercom-Version": "2.14"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fetch_cols():
    cols, page = [], 1
    while True:
        r = api("GET", f"/help_center/collections?per_page=50&page={page}")
        cols += r.get("data") or []
        pages = r.get("pages") or {}
        if page >= (pages.get("total_pages") or 1):
            break
        page += 1
    return [c for c in cols if str(c.get("help_center_id")) == str(FUTURES_HC)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locales", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    locales = [l.strip() for l in args.locales.split(",") if l.strip()]
    tr = GPTTranslator()
    cols = fetch_cols()
    print(f"Futures collections: {len(cols)}  locales: {locales}  "
          f"mode: {'APPLY' if args.apply else 'DRY'}", flush=True)

    def do_col(c):
        cid = str(c.get("id"))
        en = (c.get("name") or "").strip()
        existing = c.get("translated_content") or {}
        tc = {}
        added = []
        for loc in locales:
            cur = existing.get(loc)
            if isinstance(cur, dict) and cur.get("name"):
                continue  # never overwrite an existing name
            name = tr.translate_text(en, loc, "en", context=CTX, is_html=False) if en else en
            tc[loc] = {"type": "group_content", "name": name}
            added.append((loc, name))
        if added and args.apply:
            api("PUT", f"/help_center/collections/{cid}", {"translated_content": tc})
        return cid, en, added

    ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(do_col, c): c for c in cols}
        for fut in as_completed(futs):
            try:
                cid, en, added = fut.result()
                ok += 1
                tag = "wrote" if args.apply else "would write"
                print(f"  {cid} {en[:34]:34} {tag} {[l for l,_ in added]}", flush=True)
            except Exception as e:
                c = futs[fut]
                print(f"  FAIL {c.get('id')} {c.get('name')}: {str(e)[:160]}", flush=True)
    print(f"\nDone. collections processed: {ok}/{len(cols)}"
          f"{'' if args.apply else '  (DRY — no writes)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
