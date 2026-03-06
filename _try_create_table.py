"""Attempt to create pull_registry via Supabase pg-meta API."""
import requests
import json

SUPABASE_URL = "https://reiacekmluvuguqfswac.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJlaWFjZWttbHV2dWd1cWZzd2FjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDAxMTE3NywiZXhwIjoyMDg1NTg3MTc3fQ.dAHUSTH5XhAS6WAGFA1YyqBcIFzjGCWWwsRj1jH8ruo"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Try pg-meta endpoints
for path in ["/pg/tables", "/pg-meta/tables", "/table"]:
    try:
        r = requests.get(f"{SUPABASE_URL}{path}", headers=headers, timeout=10)
        print(f"GET {path}: {r.status_code}")
        if r.ok:
            data = r.json()
            print(f"  Found {len(data) if isinstance(data, list) else '?'} tables")
    except Exception as e:
        print(f"GET {path}: ERROR {e}")

# Try creating table via pg-meta POST endpoint
table_data = {
    "name": "pull_registry",
    "schema": "public",
    "columns": [
        {"name": "id", "type": "uuid", "default_value": "gen_random_uuid()", "is_primary_key": True, "is_nullable": False},
        {"name": "intercom_id", "type": "text", "is_nullable": False, "is_unique": True},
        {"name": "title", "type": "text", "is_nullable": False, "default_value": "''"},
        {"name": "description", "type": "text", "default_value": "''"},
        {"name": "state", "type": "text", "default_value": "'published'"},
        {"name": "url", "type": "text", "default_value": "''"},
        {"name": "source_updated_at", "type": "timestamptz", "is_nullable": True},
        {"name": "pulled_at", "type": "timestamptz", "is_nullable": True},
        {"name": "pull_status", "type": "text", "is_nullable": True},
        {"name": "pull_error", "type": "text", "default_value": "''"},
        {"name": "content_hash", "type": "text", "default_value": "''"},
        {"name": "body_html", "type": "text", "default_value": "''"},
        {"name": "author_id", "type": "text", "default_value": "''"},
        {"name": "collection_id", "type": "text", "default_value": "''"},
        {"name": "collection_name", "type": "text", "default_value": "''"},
        {"name": "created_at", "type": "timestamptz", "default_value": "now()"},
        {"name": "updated_at", "type": "timestamptz", "default_value": "now()"},
    ],
}

for path in ["/pg/tables", "/pg-meta/tables"]:
    try:
        r = requests.post(f"{SUPABASE_URL}{path}", headers=headers, json=table_data, timeout=15)
        print(f"POST {path}: {r.status_code}")
        if r.status_code != 404:
            print(f"  Response: {r.text[:300]}")
    except Exception as e:
        print(f"POST {path}: ERROR {e}")

# Verify
r2 = requests.get(f"{SUPABASE_URL}/rest/v1/pull_registry?select=id&limit=1", headers=headers, timeout=10)
print(f"\nVerify pull_registry: {r2.status_code}")
if r2.status_code == 200:
    print("TABLE EXISTS!")
else:
    print(f"Not found: {r2.text[:200]}")
