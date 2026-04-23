"""
Compare English vs French help center visibility.
Shows exactly which collections/articles differ and why.
"""
import sys
import json
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient

client = IntercomClient()

print("=" * 70)
print("ENGLISH vs FRENCH HELP CENTER COMPARISON")
print("=" * 70)

# 1. Get help centers to know which collections belong where
print("\n[1] Loading help centers...")
help_centers = client.get_help_centers()
for hc in help_centers:
    print(f"  [{hc.get('id')}] {hc.get('display_name') or hc.get('name')} (identifier: {hc.get('identifier')})")

# 2. Get all collections
print("\n[2] Loading collections...")
collections = client.get_collections()
coll_map = {}
for c in collections:
    cid = str(c.get('id'))
    name_en = c.get('name', '?')
    tc = c.get('translated_content') or {}
    name_fr = tc.get('fr', {}).get('name', '') if isinstance(tc, dict) else ''
    parent_id = c.get('parent_id')
    help_center_id = c.get('help_center_id')
    coll_map[cid] = {
        'name_en': name_en,
        'name_fr': name_fr or name_en,
        'parent_id': str(parent_id) if parent_id else None,
        'help_center_id': help_center_id,
    }

# 3. Get all articles
print("[3] Loading all articles...")
all_articles = client.get_articles()
print(f"    Total: {len(all_articles)}")

# 4. For each article, determine:
#    - Is it visible in English? (state == published)
#    - Is it visible in French? (translated_content.fr.state == published, OR state == published and Intercom shows fallback)
#    - Which collection does it belong to? (parent_id → section → collection)

# Build section → collection map
section_to_collection = {}
for cid, info in coll_map.items():
    if info['parent_id'] and info['parent_id'] in coll_map:
        # This is a section, parent is a collection (or another section)
        section_to_collection[cid] = info['parent_id']

def get_top_collection(parent_id):
    """Walk up the collection hierarchy to find the top-level collection."""
    visited = set()
    current = str(parent_id) if parent_id else None
    while current and current in coll_map:
        if current in visited:
            break
        visited.add(current)
        parent = coll_map[current].get('parent_id')
        if parent and parent in coll_map:
            current = parent
        else:
            return current
    return current

# Aggregate per top-level collection
en_counts = defaultdict(int)
fr_counts = defaultdict(int)
en_articles_by_coll = defaultdict(list)
fr_articles_by_coll = defaultdict(list)
missing_fr = defaultdict(list)

for a in all_articles:
    aid = str(a.get('id', ''))
    title = (a.get('title') or '')[:60]
    state = (a.get('state') or '').lower()
    parent_id = str(a.get('parent_id') or '') or None
    tc = a.get('translated_content') or {}

    # Find top-level collection
    top_coll = get_top_collection(parent_id) if parent_id else 'UNCATEGORIZED'
    if not top_coll:
        top_coll = 'UNCATEGORIZED'

    # English visibility: base state == published
    en_visible = (state == 'published')

    # French visibility: translated_content.fr.state == published
    fr_tc = tc.get('fr', {}) if isinstance(tc, dict) else {}
    fr_state = (fr_tc.get('state') or '').lower() if isinstance(fr_tc, dict) else ''
    fr_visible = (fr_state == 'published')

    if en_visible:
        en_counts[top_coll] += 1
        en_articles_by_coll[top_coll].append(title)

    if fr_visible:
        fr_counts[top_coll] += 1
        fr_articles_by_coll[top_coll].append(title)

    # Track published English articles missing French translation
    if en_visible and not fr_visible:
        missing_fr[top_coll].append(f"[{aid}] {title}")

# 5. Print comparison
print("\n" + "=" * 70)
print(f"  {'Collection':<45} {'EN':>5} {'FR':>5} {'Diff':>6}")
print("-" * 70)

all_colls = sorted(set(list(en_counts.keys()) + list(fr_counts.keys())),
                   key=lambda c: coll_map.get(c, {}).get('name_en', c))

for cid in all_colls:
    info = coll_map.get(cid, {})
    name = info.get('name_en', cid)[:43]
    en = en_counts.get(cid, 0)
    fr = fr_counts.get(cid, 0)
    diff = fr - en
    diff_str = f"+{diff}" if diff > 0 else str(diff) if diff != 0 else "="
    marker = "  <<<" if diff != 0 else ""
    print(f"  {name:<45} {en:>5} {fr:>5} {diff_str:>6}{marker}")

print("-" * 70)
total_en = sum(en_counts.values())
total_fr = sum(fr_counts.values())
print(f"  {'TOTAL':<45} {total_en:>5} {total_fr:>5} {total_fr - total_en:>+6}")

# 6. Show collections with French articles but no English articles
print("\n\n[COLLECTIONS VISIBLE IN FRENCH BUT EMPTY IN ENGLISH]")
print("-" * 70)
fr_only = [(cid, fr_counts[cid]) for cid in fr_counts if en_counts.get(cid, 0) == 0]
if fr_only:
    for cid, count in fr_only:
        name = coll_map.get(cid, {}).get('name_en', cid)
        name_fr = coll_map.get(cid, {}).get('name_fr', '')
        print(f"  [{cid}] {name} → FR: \"{name_fr}\" ({count} articles)")
        # Show sample articles
        for title in fr_articles_by_coll[cid][:3]:
            print(f"      - {title}")
        if count > 3:
            print(f"      ... and {count - 3} more")
else:
    print("  None — good!")

# 7. Show published English articles missing French translations
print("\n\n[PUBLISHED ENGLISH ARTICLES MISSING FRENCH TRANSLATION]")
print("-" * 70)
total_missing = sum(len(v) for v in missing_fr.values())
print(f"  Total: {total_missing} articles across {len(missing_fr)} collections\n")
for cid in sorted(missing_fr.keys(), key=lambda c: -len(missing_fr[c])):
    name = coll_map.get(cid, {}).get('name_en', cid)
    articles = missing_fr[cid]
    print(f"  {name} ({len(articles)} missing):")
    for art in articles[:3]:
        print(f"      {art}")
    if len(articles) > 3:
        print(f"      ... and {len(articles) - 3} more")
    print()

print("=" * 70)
print("COMPARISON COMPLETE")
print("=" * 70)
