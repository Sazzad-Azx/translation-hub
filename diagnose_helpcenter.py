"""
Diagnostic script: Investigate why English and French help center views differ.
Checks help center structure, collection visibility, and article translated_content.
"""
import sys
import json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient

client = IntercomClient()

print("=" * 70)
print("INTERCOM HELP CENTER DIAGNOSTIC")
print("=" * 70)

# 1. Check Help Centers
print("\n[1] HELP CENTERS")
print("-" * 40)
help_centers = client.get_help_centers()
for hc in help_centers:
    print(f"  ID: {hc.get('id')}")
    print(f"  Name: {hc.get('display_name') or hc.get('name')}")
    print(f"  Identifier: {hc.get('identifier')}")
    print(f"  Workspace ID: {hc.get('workspace_id')}")
    tc = hc.get('translated_content')
    if tc and isinstance(tc, dict):
        print(f"  Translated locales: {[k for k in tc.keys() if k != 'type']}")
    print()

# 2. Check Collections
print("\n[2] COLLECTIONS")
print("-" * 40)
collections = client.get_collections()
print(f"  Total collections: {len(collections)}\n")

for c in collections:
    cid = c.get('id')
    name = c.get('name', 'Unknown')
    description = (c.get('description') or '')[:60]
    parent_id = c.get('parent_id') or 'None'
    order = c.get('order')
    tc = c.get('translated_content')

    locale_names = {}
    if tc and isinstance(tc, dict):
        for loc, content in tc.items():
            if loc == 'type':
                continue
            if isinstance(content, dict):
                loc_name = content.get('name', '')
                loc_state = content.get('state') or content.get('published') or ''
                if loc_name:
                    locale_names[loc] = loc_name

    print(f"  [{cid}] {name}")
    print(f"    parent_id={parent_id}, order={order}")
    if locale_names:
        print(f"    Translations: {json.dumps(locale_names, ensure_ascii=False)[:200]}")
    else:
        print(f"    Translations: NONE")
    print()

# 3. Check articles in "Ongoing Offers and Updates" collection
print("\n[3] ARTICLES IN 'Ongoing Offers and Updates'")
print("-" * 40)
target_collection = None
for c in collections:
    name = (c.get('name') or '').lower()
    if 'ongoing' in name and 'offer' in name:
        target_collection = c
        break

if target_collection:
    cid = str(target_collection.get('id'))
    print(f"  Collection ID: {cid}")
    print(f"  Collection Name: {target_collection.get('name')}")

    articles = client.get_articles(collection_id=cid)
    print(f"  Total articles in this collection: {len(articles)}\n")

    # Check translated_content on each article
    fr_count = 0
    en_count = 0
    for a in articles[:5]:  # Sample first 5
        aid = a.get('id')
        title = (a.get('title') or '')[:60]
        state = a.get('state')
        parent_id = a.get('parent_id')
        tc = a.get('translated_content')

        print(f"    [{aid}] {title}")
        print(f"      state={state}, parent_id={parent_id}")

        if tc and isinstance(tc, dict):
            locales_with_content = []
            for loc, content in tc.items():
                if loc == 'type':
                    continue
                if isinstance(content, dict):
                    loc_title = (content.get('title') or '')[:40]
                    loc_state = content.get('state', '')
                    locales_with_content.append(f"{loc}(state={loc_state})")
            print(f"      translated_content: {', '.join(locales_with_content)}")
        else:
            print(f"      translated_content: NONE")
        print()

    # Count articles with French translation
    for a in articles:
        tc = a.get('translated_content')
        en_count += 1
        if tc and isinstance(tc, dict) and 'fr' in tc:
            fr_content = tc['fr']
            if isinstance(fr_content, dict) and fr_content.get('title'):
                fr_count += 1

    print(f"  Summary: {en_count} total articles, {fr_count} have French translated_content")
else:
    print("  Collection not found!")

# 4. Count ALL articles and check for anomalies
print("\n\n[4] GLOBAL ARTICLE STATS")
print("-" * 40)
all_articles = client.get_articles()
print(f"  Total articles: {len(all_articles)}")

# Group by parent_id
from collections import Counter
parent_counts = Counter()
state_counts = Counter()
has_fr = 0
has_any_tc = 0

for a in all_articles:
    pid = str(a.get('parent_id') or 'NONE')
    parent_counts[pid] += 1
    state_counts[a.get('state', 'unknown')] += 1
    tc = a.get('translated_content')
    if tc and isinstance(tc, dict):
        non_type_keys = [k for k in tc.keys() if k != 'type']
        if non_type_keys:
            has_any_tc += 1
        if 'fr' in tc:
            has_fr += 1

print(f"  States: {dict(state_counts)}")
print(f"  Articles with ANY translated_content: {has_any_tc}")
print(f"  Articles with French translated_content: {has_fr}")
print(f"\n  Articles by parent_id (top 20):")

# Map parent_id to collection name
coll_name_map = {str(c.get('id')): c.get('name', '?') for c in collections}
for pid, count in parent_counts.most_common(20):
    cname = coll_name_map.get(pid, '(section or unknown)')
    print(f"    parent_id={pid}: {count} articles  [{cname}]")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
