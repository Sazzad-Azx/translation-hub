"""
Fill missing Futures article translations (one-off, reusable).

Some FN Futures published articles (the newest ones) have English only, so they
stay hidden on every localized site even after the collections are localized.
This finds articles missing a target locale, translates title/body/description
with the project's GPTTranslator, and PUTs them back as PUBLISHED
translated_content — one PUT per article carrying all its missing locales (so
concurrent per-locale PUTs can't race on Intercom's server-side merge).

Usage:
    python futures_articles_fill.py                       # DRY RUN (list gaps)
    python futures_articles_fill.py --apply               # translate+publish
    python futures_articles_fill.py --locales zh-CN --apply
"""
import os, sys, json, argparse, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
FUTURES_HC = 4171779
DEFAULT_LOCALES = ["ar", "zh-CN", "fr", "de", "hi", "it", "ja", "es", "th", "pt-BR"]

for line in open(os.path.join(PROJECT_DIR, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TOKEN = os.environ["INTERCOM_ACCESS_TOKEN"]
from translator import GPTTranslator  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


def sanitize_html(html):
    """Make list HTML pass Intercom's PUT validator. Intercom rejects a list that
    contains an EMPTY <li> (e.g. a trailing '<li><p></p></li>') with the misleading
    'unsupported_html: ... needs to contain at least one list item'. Such empty
    items exist in some source articles and the translator preserves them. Strip
    empty list items, then drop any <ul>/<ol> left with no <li>."""
    if not html or BeautifulSoup is None:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for li in soup.find_all("li"):
        if not li.get_text(strip=True) and not li.find(["img", "iframe", "video"]):
            li.decompose()
    changed = True
    while changed:
        changed = False
        for lst in soup.find_all(["ul", "ol"]):
            if lst.find("li") is None:
                lst.decompose(); changed = True
    return str(soup)


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://api.intercom.io" + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
                 "Content-Type": "application/json", "Intercom-Version": "2.14"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def fetch_futures_articles():
    arts, page = [], 1
    while True:
        qs = urllib.parse.urlencode({"help_center_id": FUTURES_HC, "state": "published",
                                     "per_page": 50, "page": page})
        r = api("GET", "/articles/search?" + qs)
        batch = (r.get("data") or {}).get("articles") or []
        arts.extend(batch)
        pages = r.get("pages") or {}
        if not batch or page >= (pages.get("total_pages") or 1):
            break
        page += 1
    return arts


def missing_locales(article, locales):
    tc = article.get("translated_content") or {}
    out = []
    for loc in locales:
        v = tc.get(loc)
        if not (isinstance(v, dict) and (v.get("title") or v.get("body"))):
            out.append(loc)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--locales", default=",".join(DEFAULT_LOCALES))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    locales = [l.strip() for l in args.locales.split(",") if l.strip()]

    arts = fetch_futures_articles()
    gaps = [(a, missing_locales(a, locales)) for a in arts]
    gaps = [(a, m) for a, m in gaps if m]
    total_jobs = sum(len(m) for _, m in gaps)

    print(f"Futures published articles: {len(arts)}   locales: {locales}")
    print(f"Articles with missing locales: {len(gaps)}   translate+push jobs: {total_jobs}   "
          f"mode: {'APPLY' if args.apply else 'DRY RUN'}\n")
    for a, m in gaps:
        print(f"  • {str(a.get('id')):>9}  {(a.get('title') or '')[:60]:60}  missing: {m}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to translate & publish.")
        return 0

    tr = GPTTranslator()
    ctx = ("FAQ article for the FundedNext Futures help center. Keep product/brand names in "
           "English (FundedNext, FundedNext Futures, Rapid, Rapid Pro, Rapid Daily, Bolt, Flex, "
           "Legacy, NinjaTrader, TradingView, Tradovate).")

    def do_article(a, miss):
        aid = str(a.get("id"))
        full = api("GET", f"/articles/{aid}")
        src = {"title": full.get("title") or "", "body": full.get("body") or "",
               "description": full.get("description") or ""}
        tc_update = {}
        for loc in miss:
            t = tr.translate_article(src, target_language=loc, source_language="en")
            entry = {"title": t.get("title", ""), "body": sanitize_html(t.get("body", "")), "state": "published"}
            if t.get("description"):
                entry["description"] = t["description"]
            tc_update[loc] = entry
        api("PUT", f"/articles/{aid}", {"translated_content": tc_update})
        return aid, list(tc_update.keys())

    done = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(do_article, a, m): a for a, m in gaps}
        for fut in as_completed(futs):
            a = futs[fut]
            try:
                aid, locs = fut.result()
                done += 1
                print(f"  ✓ {aid}  published {locs}")
            except Exception as e:
                failed += 1
                print(f"  ✗ {a.get('id')}  {str(e)[:160]}")
    print(f"\nAPPLY done. articles updated: {done}   failed: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
